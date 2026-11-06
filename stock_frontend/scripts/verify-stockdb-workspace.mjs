/** Run the real workspace component against controlled asynchronous responses. */
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { build } from 'esbuild'
import { parse, compileScript } from '@vue/compiler-sfc'
import { JSDOM } from 'jsdom'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const output = resolve(root, 'node_modules/.cache/_stockdb_workspace_test.mjs')
await build({
  stdin: {
    contents: "export { default as Workspace } from '@/views/StockDbView.vue'; export { createApp, nextTick } from 'vue'",
    resolveDir: root, loader: 'ts',
  },
  outfile: output, bundle: true, format: 'esm', platform: 'browser',
  alias: { '@': resolve(root, 'src') },
  define: {
    'process.env.NODE_ENV': '"test"',
    __VUE_OPTIONS_API__: 'true',
    __VUE_PROD_DEVTOOLS__: 'false',
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false',
  },
  logLevel: 'error',
  plugins: [{
    name: 'workspace-fixtures',
    setup(builder) {
      builder.onResolve({ filter: /^@\/api\/stockdbCache$/ }, () => ({ path: 'cache', namespace: 'fixture' }))
      builder.onLoad({ filter: /^cache$/, namespace: 'fixture' }, () => ({
        contents: `
          const runtime = () => globalThis.stockDbFixture;
          const key = path => 'api:' + path;
          export const peekCache = key => runtime().memory.get(key);
          export const readCache = async key => peekCache(key);
          export const putCache = (key, value) => runtime().memory.set(key, value);
          export async function fetchStockDb(path) {
            const result = await runtime().request(path);
            putCache(key(path), result);
            return result;
          }
          export const cachedStockDb = async path =>
            peekCache(key(path)) ?? fetchStockDb(path);
          export class StockDbHttpError extends Error {}
        `,
      }))
      builder.onResolve({ filter: /TrendView[.]vue$/ }, () => ({ path: 'trend', namespace: 'fixture' }))
      builder.onLoad({ filter: /^trend$/, namespace: 'fixture' }, () => ({
        contents: 'export default { props: ["industry", "embedded"], template: "<div />" }',
      }))
      builder.onResolve({ filter: /StockDbChart[.]vue$/ }, () => ({ path: 'chart', namespace: 'fixture' }))
      builder.onLoad({ filter: /^chart$/, namespace: 'fixture' }, () => ({
        resolveDir: root,
        contents: `
          import { h } from 'vue';
          export default {
            props: ['bars', 'label'],
            setup: props => () => h('div', {
              class: 'test-chart', 'data-label': props.label,
              'data-close': props.bars.at(-1)?.[4]
            })
          };
        `,
      }))
      builder.onLoad({ filter: /StockDbView[.]vue$/ }, async ({ path }) => {
        const { descriptor } = parse(await readFile(path, 'utf8'), { filename: path })
        return { contents: compileScript(descriptor, { id: 'workspace-test', inlineTemplate: true }).content, loader: 'ts' }
      })
    },
  }],
})

const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'http://localhost/stockdb' })
for (const name of ['window', 'document', 'localStorage', 'HTMLElement', 'SVGElement', 'Element']) {
  globalThis[name] = dom.window[name]
}
dom.window.HTMLElement.prototype.scrollTo = function (x, y) {
  this.scrollTop = typeof x === 'object' ? (x.top ?? 0) : (y ?? 0)
}
globalThis.fetch = async () => ({ ok: true })
const { Workspace, createApp, nextTick } = await import(pathToFileURL(output).href)
const query = selector => document.querySelector(selector)
const all = selector => [...document.querySelectorAll(selector)]
const boardName = () => query('.card-name')?.textContent.trim()
const selectedBoard = () => query('.constituents .panel-head strong')?.textContent.trim()
const selectedStock = () => query('.stock-chart strong')?.textContent.trim()
const chartCount = () => all('.card .test-chart').length

async function until(predicate, description) {
  for (let i = 0; i < 200; i++) {
    await new Promise(resolve => setImmediate(resolve))
    await nextTick()
    if (predicate()) return
  }
  throw new Error('Timed out: ' + description)
}
function deferred() {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}
function row(code) { return all('.stock-row').find(item => item.querySelector('strong').textContent === code) }
function clickBoard(id) { all('.board-row').find(item => item.title === id).click() }

async function fixture(run, legacy = false) {
  localStorage.clear()
  document.body.innerHTML = '<div id="test-app"></div>'
  const state = {
    version: 'v1', memory: new Map(), calls: [], hold: null,
    bars: () => [[20261104, 100, 210, 90, state.version === 'v1' ? 100 : 200, 1, 1, 99]],
    boards: () => Array.from({ length: 24 }, (_, i) => ({
      id: 'board-' + i, name: 'Board ' + i, count: 2, price: 1000 - i,
      changes: Object.fromEntries([1, 3, 5, 10, 15, 30].map(days => [days, i])),
    })),
    bundle: (selected = '600001') => ({
      members: ['600001', '600002'].map(code => ({ code, name: code, bar: state.bars()[0] })),
      count: 2, stockCode: selected, stockBars: state.bars(),
    }),
    async request(path) {
      state.calls.push(path)
      if (state.hold) await state.hold(path)
      const url = new URL(path, 'http://localhost')
      if (url.pathname === '/home') return {
        version: state.version, date: 20261104, boards: state.boards(),
        charts: Object.fromEntries(state.boards().slice(0, 10).map(board => [board.id, state.bars()])),
        boardId: 'board-0', detail: state.bundle(),
      }
      if (url.pathname === '/ranking') return { version: state.version, date: 20261104, boards: state.boards() }
      if (url.pathname === '/charts') return {
        charts: Object.fromEntries(url.searchParams.get('ids').split(',').map(id => [id, state.bars()])),
      }
      if (url.pathname.startsWith('/members/')) return state.bundle(url.searchParams.get('selected') || '600001')
      if (url.pathname.startsWith('/stocks/')) return { bars: state.bars() }
      if (url.pathname === '/status') return { refreshing: false, error: '' }
      throw new Error('Unexpected request ' + path)
    },
  }
  globalThis.stockDbFixture = state
  if (legacy) state.memory.set('last-workspace', {
    version: 'legacy', date: 20261104, category: 'custom', weight: 'equal',
    boards: [], charts: {}, boardId: '', detail: state.bundle(),
  })
  const app = createApp(Workspace)
  app.mount('#test-app')
  try {
    await until(() => chartCount() === 10 && selectedStock()?.includes('600001'), 'initial workspace')
    await run(state)
  } finally {
    app.unmount()
  }
}

await fixture(async state => {
  const pending = deferred()
  state.hold = path => path.startsWith('/charts?') ? pending.promise : undefined
  query('.ranking select').dispatchEvent(new dom.window.Event('click', { bubbles: true }))
  await until(() => state.calls.some(path => path.startsWith('/charts?')), 'pending sorted curves')
  assert.equal(boardName(), 'Board 0')
  assert.equal(chartCount(), 10, 'keep all previous curves while sorting')
  assert.equal(selectedBoard(), 'Board 0')
  pending.resolve()
  await until(() => boardName() === 'Board 23', 'sorted workspace')
  assert.equal(selectedBoard(), 'Board 23', 'unfixed selection follows the new leader')
  assert.equal(chartCount(), 10)
})
console.log('Passed atomic ranking/curves and default selection follow')

await fixture(async () => {
  clickBoard('Board 1')
  await until(() => selectedBoard() === 'Board 1', 'manually selected board')
  query('.ranking select').dispatchEvent(new dom.window.Event('click', { bubbles: true }))
  await until(() => boardName() === 'Board 23', 'new ranking with fixed board')
  assert.equal(selectedBoard(), 'Board 1', 'preserve manual board selection')
})
console.log('Passed manually fixed selection preservation')

await fixture(async state => {
  const pending = deferred()
  state.hold = path => path.startsWith('/members/board-1?') ? pending.promise : undefined
  clickBoard('Board 1')
  await until(() => state.calls.some(path => path.startsWith('/members/board-1?')), 'pending board')
  clickBoard('Board 0')
  pending.resolve()
  await new Promise(resolve => setTimeout(resolve, 10))
  await nextTick()
  assert.equal(selectedBoard(), 'Board 0')
})
console.log('Passed rapid board re-selection')

await fixture(async state => {
  const pending = deferred()
  state.hold = path => path.startsWith('/stocks/600002?') ? pending.promise : undefined
  row('600002').click()
  await until(() => state.calls.some(path => path.startsWith('/stocks/600002?')), 'pending stock')
  row('600001').click()
  pending.resolve()
  await new Promise(resolve => setTimeout(resolve, 10))
  await nextTick()
  assert.match(selectedStock(), /600001/)
})
console.log('Passed rapid stock re-selection')

await fixture(async state => {
  const cards = query('.cards')
  cards.scrollTop = 4000
  cards.dispatchEvent(new dom.window.Event('scroll'))
  await until(() => chartCount() === 10 && query('.rank').textContent.trim() === 'TOP 11', 'scrolled curves')
  state.version = 'v2'
  const pending = deferred()
  state.hold = path => path.startsWith('/charts?') ? pending.promise : undefined
  query('.source button').click()
  await until(() => state.calls.some(path => path.startsWith('/charts?') && path.includes('version=v2')), 'next generation viewport')
  assert(all('.card .test-chart').every(chart => chart.dataset.close === '100'), 'keep old generation until ready')
  pending.resolve()
  await until(() => all('.card .test-chart').every(chart => chart.dataset.close === '200'), 'new generation viewport')
  assert.equal(chartCount(), 10)
  assert.equal(cards.scrollTop, 4000)
  assert.equal(query('.rank').textContent.trim(), 'TOP 11')
})
console.log('Passed version replacement at the current viewport')
await fixture(async state => {
  assert(!document.body.textContent.includes('我的指数'))
  assert(!query('.edit-dialog'))
  assert(state.calls.includes('/home'), 'discard the retired category from persisted workspaces')
  assert(!state.calls.some(path => path.includes('/custom') || path.includes('category=custom')))
}, true)
console.log('Passed retired category cache recovery and removed editor')

dom.window.close()
