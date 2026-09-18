/**
 * G35（方案 B）路由与守卫回归验证。
 *
 * 做法：用 esbuild 打包**真实的** `src/router/index.ts`（把所有 `.vue` 视图替换为空组件桩，
 * 把 `@/api/monitor` 换成内存桩以免拉入 axios/网络），在 jsdom 下断言：
 * - `/` `/market` `/market/detail` `/ai` `/login` `/terms` `/privacy` `/disclaimer`
 *   与 G33 三条找回密码路由的 name / meta.bare 符合方案 B 定义
 * - 未登录可浏览行情页与 AI 页（不再被强制跳登录页）
 * - 已登录访问 `/login` 会被守卫送回首页（deep link 登录页对已登录用户不展示）
 *
 * 运行：npm run verify:routing
 */
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const OUT = resolve(ROOT, 'node_modules/.cache/_routing_bundle.mjs')

const stubPlugin = {
  name: 'stub-vue-and-network',
  setup(b) {
    // 所有 .vue 视图/组件 → 空组件桩（本脚本只验证路由表与守卫，不渲染页面）
    b.onResolve({ filter: /\.vue$/ }, (args) => ({ path: args.path, namespace: 'vue-stub' }))
    b.onLoad({ filter: /.*/, namespace: 'vue-stub' }, () => ({
      contents: 'export default { name: "Stub", render() { return null } }',
      loader: 'js',
    }))
    b.onResolve({ filter: /^@\/api\/monitor$/ }, () => ({ path: 'monitor-stub', namespace: 'stub' }))
    b.onLoad({ filter: /^monitor-stub$/, namespace: 'stub' }, () => ({
      contents: 'export function reportEvents() { return Promise.resolve() }',
      loader: 'js',
    }))
  },
}

await build({
  stdin: {
    contents: `
      export { default as router } from '@/router'
      export { useUserStore } from '@/stores/user'
      export { createPinia, setActivePinia } from 'pinia'
    `,
    resolveDir: resolve(ROOT, 'src'),
    loader: 'ts',
  },
  bundle: true,
  format: 'esm',
  outfile: OUT,
  platform: 'browser',
  alias: { '@': resolve(ROOT, 'src') },
  plugins: [stubPlugin],
  define: { 'import.meta.env.DEV': 'false' },
  logLevel: 'error',
})

const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'http://localhost/' })
globalThis.window = dom.window
globalThis.document = dom.window.document
globalThis.localStorage = dom.window.localStorage
globalThis.history = dom.window.history
globalThis.location = dom.window.location

const { router, useUserStore, createPinia, setActivePinia } = await import(pathToFileURL(OUT).href)

let failed = 0
function check(name, cond, detail) {
  if (cond) console.log(`  ✓ ${name}`)
  else {
    failed++
    console.error(`  ✗ ${name}${detail ? ` — ${detail}` : ''}`)
  }
}

setActivePinia(createPinia())
const user = useUserStore()
user.clearAuth()
// 不调用 router.isReady()：未挂载到 app 时首次导航不会被自动触发，await 会永久挂起。
// 直接 push 一次即完成首次导航。
await router.push('/')

/* ------------------------------------------------------------------ */
console.log('\n[1] 路由表（方案 B）')
{
  const expect = [
    ['/', 'market-home', false],
    ['/market/detail', 'market-detail', false],
    ['/ai', 'ai', false],
    ['/login', 'login', true],
    ['/forgot-password', 'forgot-password', true],
    ['/reset-password', 'reset-password', true],
    ['/verify-email', 'verify-email', true],
    ['/terms', 'terms', true],
    ['/privacy', 'privacy', true],
    ['/disclaimer', 'disclaimer', true],
  ]
  for (const [path, name, bare] of expect) {
    const r = router.resolve(path)
    check(
      `${path} → name=${name}${bare ? ' / bare' : ''}`,
      r.name === name && !!r.meta.bare === bare,
      `实际 name=${String(r.name)} bare=${String(r.meta.bare)}`
    )
  }
  // /market 兼容旧链接 → 重定向到 /
  const legacy = router.resolve('/market')
  check(
    '/market 重定向到 /',
    legacy.matched.some((m) => m.redirect === '/'),
    JSON.stringify(legacy.matched.map((m) => m.redirect))
  )
}

/* ------------------------------------------------------------------ */
console.log('\n[2] 未登录可浏览（免登录不跳登录页）')
{
  user.clearAuth()
  for (const path of ['/', '/ai', '/market/detail']) {
    await router.push(path)
    check(`未登录访问 ${path} 停留在本页`, router.currentRoute.value.fullPath === path, router.currentRoute.value.fullPath)
  }
  await router.push('/login')
  check('未登录访问 /login 正常展示登录页', router.currentRoute.value.name === 'login')
}

/* ------------------------------------------------------------------ */
console.log('\n[3] 已登录访问 /login 被送回首页')
{
  user.setAuth('fake-token-for-guard-test', { id: 1, username: 'tester' })
  // 注意：当前就在 /login，直接再 push('/login') 会被 vue-router 判为重复导航而短路，
  // 守卫根本不会执行。必须先离开该路由再进入。
  await router.push('/terms')
  await router.push('/login')
  check(
    '已登录访问 /login → market-home',
    router.currentRoute.value.name === 'market-home',
    String(router.currentRoute.value.name)
  )
  // 已登录仍可正常访问业务页
  await router.push('/ai')
  check('已登录访问 /ai 正常', router.currentRoute.value.name === 'ai')

  // 法律页对已登录用户同样可达（免登录页不设反向跳转）
  await router.push('/terms')
  check('已登录访问 /terms 正常', router.currentRoute.value.name === 'terms')

  user.clearAuth()
  await router.push('/')
  check('登出后回到首页正常', router.currentRoute.value.name === 'market-home')
}

/* ------------------------------------------------------------------ */
if (failed) {
  console.error(`\n✗ G35 路由验证失败：${failed} 项断言未通过`)
  process.exit(1)
}
console.log('\n✓ G35 路由验证全部通过（路由表 / 免登录浏览 / 登录页守卫）')
