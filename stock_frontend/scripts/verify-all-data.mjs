import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { build } from 'esbuild'
import { parse, compileScript } from '@vue/compiler-sfc'
import { JSDOM } from 'jsdom'

const root = process.cwd()
const output = resolve(root, 'node_modules/.cache/all-data-test.mjs')
await build({
  stdin: { contents: "export {default as View} from '@/views/AllDataView.vue'; export {createApp,nextTick} from 'vue'", resolveDir: root, loader: 'ts' },
  outfile: output, bundle: true, format: 'esm', platform: 'browser', alias: {'@': resolve(root, 'src')},
  define: {'process.env.NODE_ENV': '"test"', __VUE_OPTIONS_API__: 'true', __VUE_PROD_DEVTOOLS__: 'false', __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false'},
  plugins: [{ name: 'fixtures', setup(b) {
    b.onResolve({filter: /^@\/api\/http$/}, () => ({path: 'http', namespace: 'fixture'}))
    b.onLoad({filter: /.*/, namespace: 'fixture'}, () => ({contents: 'export const request = config => globalThis.onlineFixture(config)'}))
    b.onLoad({filter: /AllDataView\.vue$/}, async ({path}) => ({contents: compileScript(parse(await readFile(path, 'utf8'), {filename: path}).descriptor, {id: 'test', inlineTemplate: true}).content, loader: 'ts'}))
  }}], logLevel: 'error',
})
const dom = new JSDOM('<div id="app"></div>', {url: 'http://localhost/all-data'})
for (const key of ['window', 'document', 'HTMLElement', 'SVGElement', 'Element']) globalThis[key] = dom.window[key]
const calls = []
globalThis.onlineFixture = async config => {
  calls.push(config)
  return config.url.endsWith('/status') ? {retry_after: 0, interval_seconds: 30} : {data: [], fetched_at: '2026-11-07', saved_path: 'mydb/龙虎榜/全市场.json', retry_after: 30, interval_seconds: 30}
}
const {View, createApp, nextTick} = await import(pathToFileURL(output).href)
const app = createApp(View); app.mount('#app')
await nextTick(); await nextTick()
assert.equal(calls.length, 1)
assert.equal(calls[0].url, '/all-data/status')
document.querySelectorAll('aside button')[3].click(); await nextTick()
assert.equal(calls.length, 1, 'Changing category must not call upstream')
const range = document.querySelector('select'); range.selectedIndex = 1; range.dispatchEvent(new window.Event('change')); await nextTick()
assert.equal(document.querySelector('input[placeholder="六位股票代码"]'), null)
document.querySelector('form').dispatchEvent(new window.Event('submit', {cancelable: true})); await nextTick(); await nextTick()
assert.equal(calls.filter(c => c.url.endsWith('/query')).length, 1)
assert.equal(calls.at(-1).data.code, '')
assert.match(document.body.textContent, /当前条件下无数据/)
assert.equal(document.querySelector('.submit').disabled, true)
app.unmount()
console.log('全数据页面：手动触发、动态参数、全市场查询、空结果及冷却验证通过')
