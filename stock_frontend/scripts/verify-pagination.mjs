/**
 * G27（P1-6b）前端回归验证：列表分页续拉 + 消息增量加载 + 渲染耗时埋点。
 *
 * 做法：用 esbuild 把真实的 `src/stores/ai.ts` 与 `src/utils/monitor.ts` 打包（`@/api/ai`、
 * `@/api/monitor` 换成内存桩），在 jsdom 下驱动 store，断言游标累积、去重、终止条件与
 * 埋点阈值。**不覆盖 DOM 层的虚拟滚动布局**（jsdom 不做布局计算，clientHeight 恒为 0），
 * 该部分由 vue-tsc + vite build 与人工浏览器验证覆盖。
 *
 * 运行：npm run verify:pagination
 */
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const OUT = resolve(ROOT, 'node_modules/.cache/_pagination_bundle.mjs')

/** 把两个网络模块换成内存桩，其余（@/stores/ai 等）走真实源码 */
const stubPlugin = {
  name: 'stub-network',
  setup(b) {
    b.onResolve({ filter: /^@\/api\/ai$/ }, () => ({ path: resolve(ROOT, 'scripts/stubs/ai-api.ts') }))
    b.onResolve({ filter: /^@\/api\/monitor$/ }, () => ({
      path: resolve(ROOT, 'scripts/stubs/monitor-api.ts'),
    }))
  },
}

await build({
  stdin: {
    contents: `
      export { createPinia, setActivePinia } from 'pinia'
      export { useAiStore, MESSAGE_PAGE_SIZE, LIST_PAGE_SIZE } from '@/stores/ai'
      export { trackRender, trackTiming, flush, SLOW_RENDER_MS } from '@/utils/monitor'
      export { state } from '@/api/ai'
      export { reported } from '@/api/monitor'
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
  // monitor.ts 用 import.meta.env.DEV 做调试输出；脚本环境无 Vite，显式注入为 false
  define: { 'import.meta.env.DEV': 'false' },
  logLevel: 'error',
})

// jsdom 提供 window/document/localStorage（monitor.ts 依赖）
const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'http://localhost/' })
globalThis.window = dom.window
globalThis.document = dom.window.document
globalThis.localStorage = dom.window.localStorage

const {
  createPinia,
  setActivePinia,
  useAiStore,
  MESSAGE_PAGE_SIZE,
  trackRender,
  flush,
  SLOW_RENDER_MS,
  state,
  reported,
} = await import(pathToFileURL(OUT).href)

let failed = 0
function check(name, cond, detail) {
  if (cond) {
    console.log(`  ✓ ${name}`)
  } else {
    failed++
    console.error(`  ✗ ${name}${detail ? ` — ${detail}` : ''}`)
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

/** 造 n 条升序消息（id 从 base+1 开始） */
function seedMessages(convId, n, base = 0) {
  const rows = []
  for (let i = 0; i < n; i++) {
    rows.push({
      id: base + i + 1,
      conversation_id: convId,
      role: i % 2 === 0 ? 'user' : 'assistant',
      content: `消息${i}`,
      created_at: new Date(2026, 0, 1, 0, 0, i).toISOString(),
    })
  }
  state.messages.set(convId, rows)
  return rows
}

function resetState() {
  state.conversations = []
  state.messages = new Map()
  state.messageCalls = []
  state.conversationCalls = []
  state.delayMs = 0
  reported.length = 0
  setActivePinia(createPinia())
  return useAiStore()
}

/* ------------------------------------------------------------------ */
console.log('\n[1] 消息游标分页：首屏 + 增量加载')
{
  const ai = resetState()
  const all = seedMessages(1, 120)
  await ai.openConversation(1)

  check('首屏加载最新 50 条', ai.messages.length === MESSAGE_PAGE_SIZE, `实际 ${ai.messages.length}`)
  check('首屏内容为最新的 50 条', ai.messages[49].id === all[119].id && ai.messages[0].id === all[70].id)
  check('has_more 为真', ai.messagesHasMore === true)
  check('游标为本页最旧一条 id', ai.messagesCursor === all[70].id)

  const added = await ai.loadOlderMessages()
  check('增量加载返回新增条数 50', added === 50, `实际 ${added}`)
  check('更早消息 prepend 到前面', ai.messages.length === 100 && ai.messages[0].id === all[20].id)
  check('游标推进到更早一条', ai.messagesCursor === all[20].id)
  check('has_more 仍为真', ai.messagesHasMore === true)

  const added2 = await ai.loadOlderMessages()
  check('末页返回新增 20 条', added2 === 20, `实际 ${added2}`)
  check('已到最早：has_more 为假、游标为 null', ai.messagesHasMore === false && ai.messagesCursor === null)
  check('拼接后无重无漏、顺序升序', ai.messages.length === 120 && ai.messages[0].id === all[0].id && ai.messages[119].id === all[119].id)

  const callsBefore = state.messageCalls.length
  const added3 = await ai.loadOlderMessages()
  check('已到最早时不再发请求', added3 === 0 && state.messageCalls.length === callsBefore)
}

/* ------------------------------------------------------------------ */
console.log('\n[2] 消息增量加载：加载期间切换会话则丢弃结果')
{
  const ai = resetState()
  seedMessages(1, 120)
  seedMessages(2, 10, 1000)
  await ai.openConversation(1)
  const before = ai.messages.length

  state.delayMs = 30
  const pending = ai.loadOlderMessages()
  await sleep(5)
  await ai.openConversation(2) // 加载中途切走
  const added = await pending
  state.delayMs = 0

  check('切走后丢弃结果（返回 0）', added === 0, `实际 ${added}`)
  check('当前会话仍是切过去的会话', ai.activeConversationId === 2)
  check('未把旧会话消息插入新会话', ai.messages.length === 10 && ai.messages.every((m) => m.conversation_id === 2), `实际 ${ai.messages.length} 条`)
  check('切走前的会话消息未被污染', before === MESSAGE_PAGE_SIZE)
}

/* ------------------------------------------------------------------ */
console.log('\n[3] 列表续拉：追加、去重、到 total 终止')
{
  const ai = resetState()
  state.conversations = Array.from({ length: 250 }, (_, i) => ({
    id: 250 - i,
    title: `会话${i}`,
    created_at: '',
    updated_at: '',
  }))
  await ai.loadConversations()
  check('首屏取一页（100 条）', ai.conversations.length === 100, `实际 ${ai.conversations.length}`)
  check('记录 total', ai.conversationsTotal === 250)

  const added = await ai.loadMoreConversations()
  check('续拉第二页新增 100 条', added === 100, `实际 ${added}`)
  check('累计 200 条且无重复', ai.conversations.length === 200 && new Set(ai.conversations.map((c) => c.id)).size === 200)

  const added2 = await ai.loadMoreConversations()
  check('第三页新增 50 条', added2 === 50, `实际 ${added2}`)
  check('累计等于 total', ai.conversations.length === 250)

  const callsBefore = state.conversationCalls.length
  const added3 = await ai.loadMoreConversations()
  check('已达 total 时不再发请求', added3 === 0 && state.conversationCalls.length === callsBefore)
}

/* ------------------------------------------------------------------ */
console.log('\n[4] 渲染耗时埋点：阈值告警')
{
  const warn = console.warn
  const warns = []
  console.warn = (...args) => warns.push(args.join(' '))

  trackRender('unit_test_fast', SLOW_RENDER_MS - 100, { count: 1 })
  check('未超阈值不告警', warns.length === 0, warns.join('|'))

  trackRender('unit_test_slow', SLOW_RENDER_MS + 100, { count: 1 })
  check('超阈值触发 console.warn', warns.length === 1 && warns[0].includes('unit_test_slow'), warns.join('|'))

  console.warn = warn
  // track() 只是入队 + 5s 定时上报，断言前显式 flush
  await flush()
  const names = reported.map((e) => e.name)
  check(
    '两次均走 monitor 通道上报',
    reported.length === 2 &&
      names.includes('render:unit_test_fast') &&
      names.includes('render:unit_test_slow'),
    `reported=${JSON.stringify(names)}`
  )
  check(
    '上报含 duration_ms 与 count',
    reported.length > 0 &&
      reported.every((e) => typeof e.meta?.duration_ms === 'number' && 'count' in e.meta)
  )
}

/* ------------------------------------------------------------------ */
if (failed) {
  console.error(`\n✗ G27 验证失败：${failed} 项断言未通过`)
  process.exit(1)
}
console.log('\n✓ G27 验证全部通过（消息增量加载 / 列表续拉 / 渲染埋点）')
