import assert from 'node:assert/strict'
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { build } from 'esbuild'
import { parse, compileScript } from '@vue/compiler-sfc'
import { JSDOM } from 'jsdom'

const root = process.cwd()
const dir = resolve(root, 'node_modules/.cache/admin-preview')
await mkdir(dir, { recursive: true })
await build({
  stdin: {
    contents:
      "export {default as Admin} from '@/views/AdminView.vue';export {createApp,nextTick,reactive} from 'vue'",
    resolveDir: root,
    loader: 'ts',
  },
  outfile: resolve(dir, 'admin.mjs'),
  bundle: true,
  format: 'esm',
  platform: 'browser',
  alias: { '@': resolve(root, 'src') },
  define: {
    'process.env.NODE_ENV': '"test"',
    __VUE_OPTIONS_API__: 'true',
    __VUE_PROD_DEVTOOLS__: 'false',
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false',
  },
  plugins: [
    {
      name: 'admin-fixture',
      setup(builder) {
        builder.onResolve(
          { filter: /^(vue-router|@\/api\/admin|@\/composables\/useSyntheticWicks)$/ },
          ({ path }) => ({ path, namespace: 'fixture' })
        )
        builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({
          resolveDir: root,
          contents:
            path === 'vue-router'
              ? 'export const useRoute=()=>globalThis.adminFixture.route;export const useRouter=()=>({replace:async ({query})=>{globalThis.adminFixture.route.query=query}})'
              : path.endsWith('useSyntheticWicks')
                ? "import {ref} from 'vue';export const syntheticWickFactor=ref(.5)"
                : 'export const adminApi=new Proxy({},{get:(_,key)=>(...args)=>globalThis.adminFixture.call(key,...args)})',
        }))
        builder.onLoad({ filter: /\.vue$/ }, async ({ path }) => {
          const { descriptor } = parse(await readFile(path, 'utf8'), { filename: path })
          return {
            contents: compileScript(descriptor, { id: path, inlineTemplate: true }).content,
            loader: 'ts',
          }
        })
        builder.onLoad({ filter: /\.css$/ }, () => ({ contents: '', loader: 'js' }))
      },
    },
  ],
  logLevel: 'error',
})
const fixtureCode = `
const replies={
 services:{stockdb:{state:'online',latest_date:'20261105'},sdk:{state:'online'},date_scope:'600519'},
 policy:{akshare_enabled:false,history_storage_enabled:false,auto_sync_enabled:false},
 traffic:{day:'20261106',interval_seconds:2,retry_interval_seconds:10,daily_budget:2000,providers:[{name:'eastmoney',used:0,health:{state:'disabled',failures:0,last_success_at:null}}]},
 queues:{queues:Object.fromEntries(['watchlist','fixed_indices','backfill','control','sync','backtest','ai','backup'].map(n=>[n,{ready:0,active:n==='fixed_indices'?1:0,delayed:0,reserved:0,abnormal:0}])),workers:{watchlist:true,fixed_indices:true,control:true,backfill:true,ai:false,backup:false,sync:true}},
 sync:{status:'idle',task_id:null,error:null,progress:0,message:'尚未同步本地行情'},display:{synthetic_wick_factor:.5},
 requests:{requests:[{id:'1',task_id:'test-task',queue:'fixed_indices',provider:'stockdb',interface:'日k',symbol:'600519',symbol_name:'贵州茅台',symbols:[],period:'1d',phase:'requesting',attempt:1,attempts:1,started_at:'2026-11-06T00:00:00Z',updated_at:'2026-11-06T00:00:00Z'}]},
};
const fixture={calls:[],failSave:false,reply:replies,route:null,async call(key,data){this.calls.push(key);if(key.startsWith('save')){if(this.failSave)throw Error('save failed');if(key==='savePolicy')return this.reply.policy={...data};if(key==='saveLimits')return this.reply.traffic={...this.reply.traffic,...data};return this.reply.display={...data}}if(key==='startSync'){this.reply.sync={status:'queued',task_id:'new-task',error:null,progress:0,message:'等待同步'};return this.reply.sync}return structuredClone(this.reply[key])}};
globalThis.adminFixture=fixture;
`
if (process.argv.includes('--preview')) {
  await writeFile(
    resolve(dir, 'fixture.mjs'),
    fixtureCode +
      "\nimport {Admin,createApp,reactive} from './admin.mjs';fixture.route=reactive({query:{}});createApp(Admin).mount('#app');"
  )
  const css = await readFile('src/components/admin/admin.css', 'utf8')
  await writeFile(
    resolve(dir, 'index.html'),
    `<!doctype html><html><meta charset="utf-8"><style>:root{--bg:#f5f7fb;--bg-panel:#fff;--bg-panel-2:#f5f7fa;--bg-hover:#f3f6fa;--border:#e5e9ef;--border-strong:#cfd7e2;--text:#1e293b;--text-secondary:#64748b;--text-muted:#8391a6;--accent:#3478ed;--accent-soft:#edf3ff}*{box-sizing:border-box}body{margin:0;font-family:Arial,'Microsoft YaHei',sans-serif}button,input{font:inherit}button{border:0;background:transparent;cursor:pointer}#app{height:100vh;display:flex}${css}</style><body><div id="app"></div><script type="module" src="./fixture.mjs"></script></body></html>`
  )
  console.log(dir)
  process.exit(0)
}
const dom = new JSDOM('<!doctype html><body><div id="app"></div></body>', {
  url: 'http://localhost/admin',
  pretendToBeVisual: true,
})
for (const name of [
  'window',
  'document',
  'localStorage',
  'HTMLElement',
  'SVGElement',
  'Element',
  'Node',
  'Document',
  'ShadowRoot',
])
  globalThis[name] = dom.window[name]
await import('data:text/javascript;base64,' + Buffer.from(fixtureCode).toString('base64'))
const fixture = globalThis.adminFixture
const { Admin, createApp, nextTick, reactive } = await import(
  pathToFileURL(resolve(dir, 'admin.mjs')).href
)
const realSetTimeout = globalThis.setTimeout
const realClearTimeout = globalThis.clearTimeout
const pollTimers = new Map()
let timerId = 0
globalThis.setTimeout = (callback, delay, ...args) => {
  if (delay >= 3000) {
    const id = `poll-${++timerId}`
    pollTimers.set(id, callback)
    return id
  }
  return realSetTimeout(callback, delay, ...args)
}
globalThis.clearTimeout = (id) => {
  if (!pollTimers.delete(id)) realClearTimeout(id)
}
fixture.route = reactive({ query: {} })
const app = createApp(Admin)
app.mount('#app')
const settle = async () => {
  await new Promise((r) => setTimeout(r, 10))
  await nextTick()
}
const navigate = async (section) => {
  fixture.route.query = { section }
  await settle()
}
await settle()
assert.match(document.body.textContent, /本地数据服务/)
await navigate('sources')
const inputs = [...document.querySelectorAll('input[type=checkbox]')]
assert.equal(inputs.length, 3)
inputs[0].click()
await nextTick()
assert.equal(fixture.calls.filter((c) => c === 'savePolicy').length, 0)
assert.match(document.body.textContent, /有未保存修改/)
const form = inputs[0].closest('form')
const submit = async (element) => {
  element.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true }))
  await settle()
}
fixture.failSave = true
await submit(form)
assert.match(document.body.textContent, /修改尚未生效/)
assert.equal(inputs[0].checked, true)
fixture.failSave = false
await submit(form)
assert.equal(fixture.reply.policy.akshare_enabled, true)
assert.equal(document.querySelectorAll('input[type=checkbox]').length, 3, 'enabling AkShare must not duplicate policy switches')
const limitsForm = document.querySelector('input[type=number]').closest('form')
assert.equal(limitsForm.querySelectorAll('input[type=checkbox]').length, 0, 'request protection must not contain policy controls')
inputs[2].click()
await nextTick()
await submit(form)
assert.equal(fixture.reply.policy.auto_sync_enabled, true, 'automatic sync must be saved through the policy form')
inputs[1].click()
await nextTick()
inputs[0].click()
await nextTick()
assert.equal(inputs[1].checked, true, 'AkShare storage preference is independent of the fallback switch')
const interval = document.querySelector('input[type=number]')
interval.value = '7'
interval.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
await nextTick()
const refresh = [...document.querySelectorAll('button')].find((b) =>
  b.textContent.includes('刷新当前页')
)
refresh.click()
await settle()
assert.equal(interval.value, '7', 'refresh must preserve unsaved limits')
await navigate('requests')
assert.match(document.querySelector('table').textContent, /Free-StockDB/)
assert.ok(!document.body.textContent.includes('上游接口（Akshare）'))
await navigate('tasks')
assert.match(document.body.textContent, /本地行情与固定指数/)
assert.match(document.body.textContent, /未发现在线消费者/)
await navigate('display')
const factor = document.querySelector('input[type=number]')
factor.value = '0.75'
factor.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
await nextTick()
await submit(factor.closest('form'))
assert.equal(fixture.reply.display.synthetic_wick_factor, 0.75)
const originalCall = fixture.call
let releaseDisplay
fixture.call = function (key, data) {
  if (key === 'display') return new Promise(resolve => { releaseDisplay = resolve })
  return originalCall.call(this, key, data)
}
const displayRefresh = [...document.querySelectorAll('button')].find(b => b.textContent.includes('刷新当前页'))
displayRefresh.click(); await nextTick()
factor.value = '0.8'; factor.dispatchEvent(new dom.window.Event('input', { bubbles: true })); await nextTick()
await submit(factor.closest('form'))
releaseDisplay({ synthetic_wick_factor: 0.5 }); await settle()
assert.equal(factor.value, '0.8', 'late pre-save reads must not restore old settings')
fixture.call = originalCall
Object.defineProperty(document, 'hidden', { configurable: true, value: true })
document.dispatchEvent(new dom.window.Event('visibilitychange'))
await nextTick()
assert.equal(pollTimers.size, 0, 'hidden document must have no polling timers')
Object.defineProperty(document, 'hidden', { configurable: true, value: false })
document.dispatchEvent(new dom.window.Event('visibilitychange'))
await settle()
assert.equal(pollTimers.size, 1, 'resume must schedule a single polling timer')
await navigate('requests')
let release
const previousCall = fixture.call
fixture.call = function (key, data) {
  if (key === 'requests') {
    this.calls.push(key)
    return new Promise((resolve) => {
      release = () => resolve(structuredClone(this.reply.requests))
    })
  }
  return previousCall.call(this, key, data)
}
const baseline = fixture.calls.filter((key) => key === 'requests').length
const [id, callback] = [...pollTimers][0]
pollTimers.delete(id)
const polling = callback()
await nextTick()
const activeRefresh = [...document.querySelectorAll('button')].find((b) =>
  b.textContent.includes('更新中')
)
assert.ok(activeRefresh.disabled, 'refresh must be disabled during an in-flight request')
fixture.route.query = { section: 'overview' }
await settle()
fixture.route.query = { section: 'requests' }
await nextTick()
assert.equal(
  fixture.calls.filter((key) => key === 'requests').length,
  baseline + 1,
  'tab switching must not duplicate a pending request'
)
release()
await polling
await settle()
app.unmount()
assert.equal(pollTimers.size, 0, 'unmount must clear polling')
globalThis.setTimeout = realSetTimeout
globalThis.clearTimeout = realClearTimeout
console.log(
  'Admin console sections, explicit saves, failure drafts, refresh preservation, dependent switches, request labels, queue states and display save passed.'
)
