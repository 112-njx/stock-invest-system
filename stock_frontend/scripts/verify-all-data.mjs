import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
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
    b.onResolve({filter: /^(?:@\/api\/http|\.\/http)$/}, () => ({path: 'http', namespace: 'fixture'}))
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
const python = resolve(root, '../stock_backend/.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
const catalog = JSON.parse(execFileSync(python, ['-c', "import sys,json;sys.path.insert(0,'../scripts');from stockdb_online_catalog import catalog;print(json.dumps(catalog()))"], {cwd: root, encoding: 'utf8'}))
let rejectNext = false
let held = null
let resolveHeld
let statusRemaining = 0
const reply = config => ({method: config.data.method, parameters: config.data, data: [], fetched_at: '2026-11-07', saved_path: 'mydb/查询/全市场.json', retry_after: 40, interval_seconds: 40})
globalThis.onlineFixture = async config => {
  calls.push(config)
  if (config.url.endsWith('/catalog')) return catalog
  if (config.url.endsWith('/status')) return {retry_after: statusRemaining, interval_seconds: 40}
  if (rejectNext) { rejectNext = false; throw {response: {data: {msg: '接口返回参数错误'}}} }
  if (held) { await held; held = null }
  return reply(config)
}
const {View, createApp, nextTick} = await import(pathToFileURL(output).href)
const app = createApp(View); app.mount('#app')
async function settle() { await nextTick(); await nextTick(); await nextTick() }
async function group(name) { document.querySelector(`[data-group="${name}"]`).click(); await settle() }
async function dataset(id) { const select = document.querySelector('.dataset-picker select'); select.value = id; select.dispatchEvent(new window.Event('change')); await settle() }
async function submit() { document.querySelector('form').dispatchEvent(new window.Event('submit', {cancelable: true})); await settle() }
async function fill(name, value) { const input = document.querySelector(`[data-param="${name}"]`); assert.ok(input, name); input.value = value; input.dispatchEvent(new window.Event('input')); await settle() }
async function expire() { now += 41000; tick(); await settle() }
const queryCount = () => calls.filter(c => c.url.endsWith('/query')).length
await settle()
assert.equal(calls.length, 2)
assert.equal(queryCount(), 0)
assert.equal(document.querySelectorAll('aside button').length, 21)
await fill('count', '0')
await group('龙虎榜')
assert.equal(calls.length, 2, 'Changing category must not call upstream')
await fill('start_date', '2026-11-01'); await fill('end_date', '2026-11-06')
await submit()
assert.equal(queryCount(), 1)
assert.equal('code' in calls.at(-1).data, false, 'Blank optional code means whole market')
assert.equal('count' in calls.at(-1).data, false, 'Hidden Tick count must not be sent')
assert.equal('quarter' in calls.at(-1).data, false)
assert.match(document.body.textContent, /当前条件下无数据/)
assert.equal(document.querySelector('.submit').disabled, true)
await submit(); assert.equal(queryCount(), 1, 'Guard duplicate submits while cooling down')
await expire()
assert.equal(document.querySelector('.submit').disabled, false, 'One callback after sleep must expire the full cooldown')
await group('融资融券')
const marginIds = [...document.querySelectorAll('.dataset-picker option')].map(option => option.value)
assert.deepEqual(marginIds, ['get_mtss', 'get_margincash_stocks', 'get_marginsec_stocks'])
await dataset('get_margincash_stocks')
assert.equal(document.querySelector('[data-param="code"]'), null)
await submit(); assert.deepEqual(calls.at(-1).data, {method:'get_margincash_stocks'})
now += 41000
Object.defineProperty(document, 'visibilityState', {configurable: true, value: 'visible'})
document.dispatchEvent(new window.Event('visibilitychange')); await settle()
assert.equal(document.querySelector('.submit').disabled, false)
assert.equal(queryCount(), 2, 'Visibility changes must not query upstream')
await group('基金与 ETF')
assert.equal(document.querySelector('select [value="is_st"]'), null)
for (const entry of catalog.entries) {
  if (entry.group !== document.querySelector('aside .active')?.dataset.group) await group(entry.group)
  await dataset(entry.id)
  assert.match(document.querySelector('form h2').textContent, new RegExp(entry.id.replaceAll('.', '\\.')))
  if (entry.kind === 'table') assert.ok(document.querySelector('button[type="button"]'))
  else for (const param of entry.params) assert.ok([...document.querySelectorAll('form label')].some(label => label.textContent.includes(param.label)), `${entry.id}: ${param.name}`)
}
assert.equal(queryCount(), 2, 'Browsing all 83 entries must not query upstream')
await group('业绩事件')
document.querySelector('button[type="button"]').click(); await settle()
const filter = document.querySelector('.filter-row input'); filter.value = 'code'; filter.dispatchEvent(new window.Event('input')); await settle()
const filterValue = document.querySelectorAll('.filter-row input')[1]; filterValue.value = '000001'; filterValue.dispatchEvent(new window.Event('input')); await settle()
held = new Promise(resolve => { resolveHeld = resolve })
await submit()
assert.equal(document.querySelector('fieldset').disabled, true)
await submit(); assert.equal(queryCount(), 3, 'Guard duplicate submits during request')
resolveHeld(); await settle()
assert.equal(calls.at(-1).data.filters[0].value, '000001', 'Preserve leading zeros')
assert.equal(calls.at(-1).data.limit, 100)
await expire()
rejectNext = true; statusRemaining = 40
await submit()
assert.match(document.body.textContent, /接口返回参数错误/)
assert.equal(document.querySelector('.submit').disabled, true, 'Failed requests must retain server cooldown')
const api = await readFile(resolve(root, 'src/api/allData.ts'), 'utf8')
const backend = await readFile(resolve(root, '../stock_backend/app/api/v1/all_data.py'), 'utf8')
const backendTimeout = Number(backend.match(/timeout=(\d+)/)[1])
const browserTimeout = Number(api.match(/timeout:\s*(\d+)/)[1]) / 1000
for (const path of ['nginx.conf', '../deploy/nginx/nginx.conf']) {
  const config = await readFile(resolve(root, path), 'utf8')
  const location = config.match(/location = \/api\/v1\/all-data\/query\s*\{([\s\S]*?)\n\s*\}/)[1]
  const proxyTimeout = Number(location.match(/proxy_read_timeout\s+(\d+)s/)[1])
  assert.ok(backendTimeout < proxyTimeout && proxyTimeout < browserTimeout)
}
app.unmount()
const before = calls.length
document.dispatchEvent(new window.Event('visibilitychange'))
assert.equal(calls.length, before, 'Unmount must remove visibility listener')
Date.now = realNow
globalThis.setInterval = realSetInterval
globalThis.clearInterval = realClearInterval
console.log('全数据页面：83项目录、分组与动态表单、结构化筛选、40秒冷却及失败处理验证通过')
