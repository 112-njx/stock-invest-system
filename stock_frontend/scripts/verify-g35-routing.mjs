/**
 * G35（方案 B）路由与守卫回归验证。
 *
 * 做法：用 esbuild 打包**真实的** `src/router/index.ts`（把所有 `.vue` 视图替换为空组件桩，
 * 把 `@/api/monitor` 换成内存桩以免拉入 axios/网络），在 jsdom 下断言：
 * - 登录首页、行情及账户相关路由的 name / meta.bare
 * - 旧登录链接保留回跳参数，旧法律链接转到行情
 * - 未登录可浏览行情页与 AI 页（不再被强制跳登录页）
 * - 已登录访问根目录会进入行情
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
    ['/', 'login', true],
    ['/market', 'market-home', false],
    ['/market/detail', 'market-detail', false],
    ['/ai', 'ai', false],
    ['/forgot-password', 'forgot-password', true],
    ['/reset-password', 'reset-password', true],
    ['/verify-email', 'verify-email', true],
  ]
  for (const [path, name, bare] of expect) {
    const r = router.resolve(path)
    check(
      `${path} → name=${name}${bare ? ' / bare' : ''}`,
      r.name === name && !!r.meta.bare === bare,
      `实际 name=${String(r.name)} bare=${String(r.meta.bare)}`
    )
  }
  for (const path of ['/terms', '/privacy', '/disclaimer']) {
    await router.push(path)
    check(`${path} 重定向到 /market`, router.currentRoute.value.path === '/market')
  }
}

/* ------------------------------------------------------------------ */
console.log('\n[2] 未登录可浏览（免登录不跳登录页）')
{
  user.clearAuth()
  for (const path of ['/market', '/ai', '/market/detail']) {
    await router.push(path)
    check(`未登录访问 ${path} 停留在本页`, router.currentRoute.value.fullPath === path, router.currentRoute.value.fullPath)
  }
  await router.push('/login?redirect=%2Fai#sign-in')
  const legacy = router.currentRoute.value
  check('旧登录链接跳转到根目录并保留回跳参数和锚点',
    legacy.path === '/' && legacy.name === 'login' && legacy.query.redirect === '/ai' && legacy.hash === '#sign-in')
}

/* ------------------------------------------------------------------ */
console.log('\n[3] 已登录访问登录首页后进入行情')
{
  user.setAuth('fake-token-for-guard-test', { id: 1, username: 'tester' })
  for (const path of ['/', '/login']) {
    await router.push('/ai')
    await router.push(path)
    check(`已登录访问 ${path} → /market`, router.currentRoute.value.path === '/market')
  }
  // 已登录仍可正常访问业务页
  await router.push('/ai')
  check('已登录访问 /ai 正常', router.currentRoute.value.name === 'ai')

  user.clearAuth()
  await router.push('/')
  check('退出登录后访问根目录展示登录页', router.currentRoute.value.name === 'login')
}

/* ------------------------------------------------------------------ */
if (failed) {
  console.error(`\n✗ G35 路由验证失败：${failed} 项断言未通过`)
  process.exit(1)
}
console.log('\n✓ G35 路由验证全部通过（路由表 / 免登录浏览 / 登录页守卫）')
