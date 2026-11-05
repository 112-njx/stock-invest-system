import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { build } from 'esbuild'
import { parse, compileScript } from '@vue/compiler-sfc'
import { JSDOM } from 'jsdom'

const root = process.cwd()
const output = resolve(root, 'node_modules/.cache/stock-search-test.mjs')
await build({
  stdin: { contents: "export { default as Search } from '@/components/layout/StockSearch.vue'; export { createApp, nextTick } from 'vue'; export * from '@/utils/stockSearch'", resolveDir: root, loader: 'ts' },
  outfile: output, bundle: true, format: 'esm', platform: 'browser',
  alias: { '@': resolve(root, 'src') },
  define: { 'process.env.NODE_ENV': '"test"', __VUE_OPTIONS_API__: 'true', __VUE_PROD_DEVTOOLS__: 'false', __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false' },
  plugins: [{ name: 'search-fixtures', setup(builder) {
    builder.onResolve({ filter: /^@\/(api\/(market|stockSearch)|stores\/|utils\/toast)/ }, ({ path }) => ({ path, namespace: 'fixture' }))
    builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({ contents:
      path === '@/api/market' ? 'export const addWatchlist = async code => { globalThis.fixture.picked.push(code); return { code: code.slice(6), type: "stock", id: 2 } }' :
      path === '@/api/stockSearch' ? 'export const fetchStockDirectory = () => globalThis.fixture.fetch()' :
      path.endsWith('/toast') ? 'export const toast = { success() {} }' :
      `export const ${path.includes('authModal') ? 'useAuthModalStore' : path.includes('wsStore') ? 'useWsStore' : path.includes('user') ? 'useUserStore' : 'useMarketStore'} = () => globalThis.fixture.store`
    }))
    builder.onLoad({ filter: /StockSearch\.vue$/ }, async ({ path }) => {
      // Control module arrival without replacing the real matcher or component logic.
      const source = (await readFile(path, 'utf8')).replace(
        "await import('@/utils/stockSearch')",
        "await globalThis.fixture.loadMatcher(() => import('@/utils/stockSearch'))",
      )
      const { descriptor } = parse(source, { filename: path })
      return { contents: compileScript(descriptor, { id: 'search-test', inlineTemplate: true }).content, loader: 'ts' }
    })
  } }], logLevel: 'error',
})
const dom = new JSDOM('<!DOCTYPE html><body><div id="app"></div><button id="outside">outside</button></body>', { url: 'http://localhost/' })
for (const key of ['window', 'document', 'localStorage', 'HTMLElement', 'SVGElement', 'Element', 'Node', 'Document', 'ShadowRoot']) globalThis[key] = dom.window[key]
const item = (code, name) => ({ code, name, type: 'stock', market: 'SSE', latest_date: '20261105', ordinal: 0 })
const items = [item('000001', '平安银行'), item('601398', '工商银行'), item('600519', '贵州茅台'), item('000625', '长安汽车'), item('601127', '赛力斯')]
for (let i = 0; i < 5000; i++) items.push(item(String(300000 + i), `测试股票${i}`))
const directory = { version: 'v1', source: 'stockdb', items, latest_session: '20261105', stale: false }
const fixture = {
  picked: [], fetch: async () => directory,
  loadMatcher: load => load(),
  store: { token: 'test', watchlist: [{ code: '000001', type: 'stock' }], addWatchlistItem() {}, syncSubscriptions() {}, show() {} },
}
globalThis.fixture = fixture
const { Search, createApp, nextTick, indexStocks, filterStocks } = await import(pathToFileURL(output).href)
const indexed = indexStocks(items.slice(0, 5))
for (const query of ['工商', 'gongshang', 'gsyh', 'ＧＳＹＨ', '6013', '601398']) assert.equal(filterStocks(indexed, query)[0].code, '601398', query)
assert.equal(filterStocks(indexed, 'chang an')[0].code, '000625')
assert.equal(filterStocks(indexed, '上证指数').length, 0)
const settle = async () => { for (let i = 0; i < 8; i++) { await new Promise(r => setTimeout(r, 5)); await nextTick() } }
const app = createApp(Search); app.mount('#app'); await settle()
const input = document.querySelector('input')
input.focus(); await settle()
assert.equal(input.getAttribute('aria-expanded'), 'true')
assert.equal(document.querySelector('[role=listbox]').firstElementChild.style.height, `${items.length * 36}px`)
assert.ok(document.querySelectorAll('[role=option]').length <= 18, 'full directory must be virtualized')
const type = async value => { input.value = value; input.dispatchEvent(new dom.window.Event('input', { bubbles: true })); await nextTick() }
await type('gsyh')
assert.equal(document.querySelectorAll('[role=option]').length, 1)
assert.match(document.querySelector('[role=option]').textContent, /工商银行/)
input.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true, isComposing: true })); await nextTick()
assert.equal(fixture.picked.length, 0, 'IME confirmation must not add a watchlist entry')
input.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true })); await nextTick()
assert.equal(input.getAttribute('aria-activedescendant'), 'stock-option-601398')
input.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); await settle()
assert.deepEqual(fixture.picked, ['stock:601398'])
input.click(); await nextTick(); await type('不存在的股票')
assert.match(document.querySelector('.stock-search__dropdown').textContent, /未找到匹配股票/)
await type(''); assert.equal(document.querySelectorAll('[role=option]').length, 18)
document.querySelector('#outside').dispatchEvent(new dom.window.Event('pointerdown', { bubbles: true })); await nextTick()
assert.equal(input.getAttribute('aria-expanded'), 'false')
input.click(); await nextTick()
const scrolledList = document.querySelector('[role=listbox]')
scrolledList.scrollTop = 3600
scrolledList.dispatchEvent(new dom.window.Event('scroll'))
await nextTick()
assert.ok(Number.parseInt(document.querySelector('[role=option]').style.top) > 0)
for (const close of ['outside', 'Escape']) {
  if (close === 'outside') document.querySelector('#outside').dispatchEvent(new dom.window.Event('pointerdown', { bubbles: true }))
  else input.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  await nextTick()
  input.click(); await nextTick()
  assert.equal(document.querySelector('[role=listbox]').scrollTop, 0)
  assert.equal(document.querySelector('[role=option]').style.top, '0px', 'reopened viewport must contain its rendered rows')
  // Calling show() during keyboard navigation must not reset the active selection.
  for (let i = 0; i < 100; i++) {
    input.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }))
    await nextTick()
  }
  assert.ok(document.querySelector('[role=listbox]').scrollTop > 0)
}
app.unmount()
fixture.fetch = async () => { throw new Error('offline') }
const offlineApp = createApp(Search); offlineApp.mount('#app'); await settle()
document.querySelector('input').focus(); await settle()
assert.match(document.querySelector('.stock-search__dropdown').textContent, /正在使用缓存目录/)
offlineApp.unmount()
localStorage.clear()
const emptyApp = createApp(Search); emptyApp.mount('#app'); await settle()
document.querySelector('input').focus(); await settle()
assert.match(document.querySelector('.stock-search__dropdown').textContent, /无法加载股票目录/)
emptyApp.unmount()
fixture.fetch = async () => directory
let releaseMatcher
fixture.loadMatcher = load => new Promise(resolve => { releaseMatcher = () => resolve(load()) })
const earlyApp = createApp(Search); earlyApp.mount('#app'); await nextTick()
const earlyInput = document.querySelector('input')
earlyInput.focus(); await nextTick()
assert.equal(document.querySelectorAll('[role=option]').length, 0)
releaseMatcher(); await settle()
assert.equal(document.querySelector('[role=listbox]').firstElementChild.style.height, `${items.length * 36}px`)
earlyInput.value = 'gsyh'; earlyInput.dispatchEvent(new dom.window.Event('input', { bubbles: true })); await nextTick()
assert.match(document.querySelector('[role=option]').textContent, /工商银行/)
earlyApp.unmount()
console.log('Stock search: matching, IME, keyboard, watchlist, virtualization, offline states, early focus and scroll reopening passed.')
