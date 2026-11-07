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
const realNow = Date.now
const realSetInterval = globalThis.setInterval
const realClearInterval = globalThis.clearInterval
let now = 1000000
let tick
Date.now = () => now
globalThis.setInterval = callback => { tick = callback; return 1 }
globalThis.clearInterval = () => {}
globalThis.onlineFixture = async config => {
  calls.push(config)
  return config.url.endsWith('/status') ? {retry_after: 0, interval_seconds: 30} : {data: [], fetched_at: '2026-11-07', saved_path: 'mydb/龙虎榜/全市场.json', retry_after: 30, interval_seconds: 30}
}
const {View, createApp, nextTick} = await import(pathToFileURL(output).href)
const app = createApp(View); app.mount('#app')
await nextTick(); await nextTick()
assert.equal(calls.length, 1)
assert.equal(calls[0].url, '/all-data/status')
const count = document.querySelector('input[type="number"]')
count.value = '0'; count.dispatchEvent(new window.Event('input')); await nextTick()
document.querySelectorAll('aside button')[3].click(); await nextTick()
assert.equal(calls.length, 1, 'Changing category must not call upstream')
const range = document.querySelector('select'); range.selectedIndex = 1; range.dispatchEvent(new window.Event('change')); await nextTick()
assert.equal(document.querySelector('input[placeholder="六位股票代码"]'), null)
document.querySelector('form').dispatchEvent(new window.Event('submit', {cancelable: true})); await nextTick(); await nextTick()
assert.equal(calls.filter(c => c.url.endsWith('/query')).length, 1)
assert.equal(calls.at(-1).data.code, '')
assert.equal('count' in calls.at(-1).data, false, 'Hidden Tick count must not be sent')
assert.equal('quarter' in calls.at(-1).data, false, 'Hidden report fields must not be sent')
assert.match(document.body.textContent, /当前条件下无数据/)
assert.equal(document.querySelector('.submit').disabled, true)
now += 31000
tick(); await nextTick()
assert.equal(document.querySelector('.submit').disabled, false, 'One callback after sleep must expire the full cooldown')
document.querySelector('form').dispatchEvent(new window.Event('submit', {cancelable: true})); await nextTick(); await nextTick()
assert.equal(document.querySelector('.submit').disabled, true)
now += 31000
Object.defineProperty(document, 'visibilityState', {configurable: true, value: 'visible'})
document.dispatchEvent(new window.Event('visibilitychange')); await nextTick(); await nextTick()
assert.equal(document.querySelector('.submit').disabled, false, 'Returning to tab must refresh cooldown')
assert.equal(calls.filter(c => c.url.endsWith('/query')).length, 2, 'Visibility changes must not query upstream')
assert.equal(calls.filter(c => c.url.endsWith('/status')).length, 2)
const view = await readFile(resolve(root, 'src/views/AllDataView.vue'), 'utf8')
const backend = await readFile(resolve(root, '../stock_backend/app/api/v1/all_data.py'), 'utf8')
const backendTimeout = Number(backend.match(/timeout=(\d+)/)[1])
const browserTimeout = Number(view.match(/timeout:\s*(\d+)/)[1]) / 1000
for (const path of ['nginx.conf', '../deploy/nginx/nginx.conf']) {
  const config = await readFile(resolve(root, path), 'utf8')
  const location = config.match(/location = \/api\/v1\/all-data\/query\s*\{([\s\S]*?)\n\s*\}/)[1]
  const proxyTimeout = Number(location.match(/proxy_read_timeout\s+(\d+)s/)[1])
  assert.ok(backendTimeout < proxyTimeout && proxyTimeout < browserTimeout, `${path}: timeouts must allow backend completion`)
}
app.unmount()
const before = calls.length
document.dispatchEvent(new window.Event('visibilitychange'))
assert.equal(calls.length, before, 'Unmount must remove visibility listener')
Date.now = realNow
globalThis.setInterval = realSetInterval
globalThis.clearInterval = realClearInterval
console.log('全数据页面：手动查询、隐藏参数、休眠与可见性恢复、超时链路验证通过')
