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
          { filter: /^(vue-router|@\/api\/admin|@\/api\/http|@\/composables\/useSyntheticWicks)$/ },
          ({ path }) => ({ path, namespace: 'fixture' })
        )
        builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({
          resolveDir: root,
          contents:
            path === '@/api/http'
              ? 'export const request=async config=>globalThis.adminFixture.http(config)'
              : path === 'vue-router'
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
 update:{status:'idle',phase:'idle',helper_online:true,maintenance:false,can_retry:false,data_version:'test-v1',progress:0,message:'尚未更新',error:null,task_id:null},
 indicatorSettings:{pandas_enabled:false,revision:1},
 services:{stockdb:{state:'online',latest_date:'20261105'},sdk:{state:'online'},date_scope:'600519'},
 policy:{akshare_enabled:false,history_storage_enabled:false,auto_sync_enabled:false},
 traffic:{day:'20261106',interval_seconds:2,retry_interval_seconds:10,daily_budget:2000,providers:[{name:'eastmoney',used:0,health:{state:'disabled',failures:0,last_success_at:null}}]},
 queues:{queues:Object.fromEntries(['watchlist','fixed_indices','backfill','control','sync','backtest','ai','backup'].map(n=>[n,{ready:0,active:n==='fixed_indices'?1:0,delayed:0,reserved:0,abnormal:0}])),workers:{watchlist:true,fixed_indices:true,control:true,backfill:true,ai:false,backup:false,sync:true}},
 sync:{status:'idle',task_id:null,error:null,progress:0,message:'尚未同步本地行情'},display:{synthetic_wick_factor:.5},
 requests:{requests:[{id:'1',task_id:'test-task',queue:'fixed_indices',provider:'stockdb',interface:'日k',symbol:'600519',symbol_name:'贵州茅台',symbols:[],period:'1d',phase:'requesting',attempt:1,attempts:1,started_at:'2026-11-06T00:00:00Z',updated_at:'2026-11-06T00:00:00Z'}]},
};
const fixture={calls:[],failSave:false,reply:replies,route:null,async http(config){if(config.url.includes('/events')){const before=config.params.before_seq;const after=config.params.after_seq||0;const all=Array.from({length:10},(_,i)=>({seq:i+1,time:1794020400,phase:i<8?'downloading':'verifying',level:'info',file:'007593.ldb',message:i<8?'续传 2 007593.ldb':'正在校验原始文件'}));const rows=before?all.filter(e=>e.seq<before).slice(-3):all.filter(e=>e.seq>after);return {events:rows,files:[{file:'007593.ldb',status:'retrying',retries:2}],has_more:!!before&&rows[0]?.seq>1}}return {interval_seconds:30}},async call(key,data){this.calls.push(key);if(key.startsWith('save')){if(this.failSave)throw Error('save failed');if(key==='saveIndicatorSettings')return this.reply.indicatorSettings={...data,revision:2};if(key==='savePolicy')return this.reply.policy={...data};if(key==='saveLimits')return this.reply.traffic={...this.reply.traffic,...data};return this.reply.display={...data}}if(key==='startUpdate'){this.reply.update={...this.reply.update,status:'queued',maintenance:true,task_id:'update-task'};return this.reply.update}if(key==='startSync'){this.reply.sync={status:'queued',task_id:'new-task',error:null,progress:0,message:'等待同步'};return this.reply.sync}return structuredClone(this.reply[key])}};
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
const style = document.createElement('style')
style.textContent = await readFile('src/components/admin/admin.css', 'utf8')
document.head.appendChild(style)
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
assert.match(document.body.textContent, /不会创建备份，也不会自动导入项目数据库/)
assert.match(document.body.textContent, /不会运行“数据更新.exe”、下载原始文件或重启 StockDB/)
const updateButton = [...document.querySelectorAll('button')].find(b => b.textContent.includes('一键更新原始数据'))
const syncButton = [...document.querySelectorAll('button')].find(b => b.textContent.includes('同步本地行情'))
assert.ok(updateButton && !updateButton.disabled)
updateButton.click(); await settle()
assert.equal(fixture.calls.filter(c => c === 'startUpdate').length, 1)
assert.ok(syncButton.disabled, 'manual sync must be blocked during raw-file maintenance')
assert.match(document.querySelector('.update-log').textContent, /正在校验原始文件/)
assert.match(document.querySelector('.update-files').textContent, /007593.ldb/)
assert.match(document.querySelector('.update-files').textContent, /重试中/)
const logViewport = document.querySelector('.update-log')
assert.equal(dom.window.getComputedStyle(logViewport).height, '288px')
Object.defineProperty(logViewport, 'scrollHeight', {configurable:true,value:1000})
Object.defineProperty(logViewport, 'clientHeight', {configurable:true,value:288})
logViewport.scrollTop = 0
logViewport.dispatchEvent(new dom.window.Event('scroll'))
await nextTick()
assert.match(document.body.textContent, /正在查看历史，已暂停跟随/)
const earlier = [...document.querySelectorAll('button')].find(b=>b.textContent.includes('加载更早记录'))
earlier.click(); await settle()
assert.equal(document.querySelectorAll('.update-log time').length, 6)

fixture.reply.update = {...fixture.reply.update, status:'success', maintenance:false, progress:100}
await navigate('overview'); await navigate('sources')
assert.equal(syncButton.isConnected, false)
assert.ok(![...document.querySelectorAll('button')].find(b => b.textContent.includes('同步本地行情')).disabled)
fixture.reply.update.helper_online = false
await navigate('overview'); await navigate('sources')
assert.ok([...document.querySelectorAll('button')].find(b => b.textContent.includes('一键更新原始数据')).disabled)
fixture.reply.update.helper_online = true
await navigate('overview'); await navigate('sources')
const inputs = [...document.querySelectorAll('input[type=checkbox]')]
assert.equal(inputs.length, 4)
assert.equal(inputs[3].checked, false, 'SDK must be the default')
inputs[3].click()
await nextTick()
assert.equal(fixture.calls.filter(c => c === 'saveIndicatorSettings').length, 0)
const indicatorForm = inputs[3].closest('form')
indicatorForm.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }))
await settle()
assert.equal(fixture.reply.indicatorSettings.pandas_enabled, true)
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
assert.equal(document.querySelectorAll('input[type=checkbox]').length, 4, 'enabling AkShare must not duplicate policy switches')
const limitsForm = document.querySelector('input[type=number][min="1"]').closest('form')
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
const interval = document.querySelector('input[type=number][min="1"]')
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
fixture.reply.sync.error = Array.from({length:24}, (_,i) => `行业${i}: 行业${i} 的所有数据源均未返回日 K`).join('；')
fixture.reply.sync.status = 'failed'
await navigate('overview')
assert.equal(document.querySelectorAll('.admin-errors li').length, 24)
assert.equal(document.querySelector('.admin-errors li strong').textContent, '行业0')
assert.equal(document.querySelector('.admin-errors li span').textContent, '所有数据源均未返回日 K')
assert.equal(dom.window.getComputedStyle(document.querySelector('.admin-errors ul')).maxHeight, '288px')
await navigate('sources')
assert.equal(document.querySelectorAll('.admin-errors li').length, 24, 'both sync cards use the same readable list')
fixture.reply.sync.error = '<img src=x onerror=alert(1)>;单条错误'
await navigate('overview')
assert.equal(document.querySelector('.admin-errors img'), null, 'errors must remain escaped text')
fixture.reply.sync.error = null
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
const statusRow = document.querySelector('.resource-status')
const timestamp = statusRow.firstElementChild.textContent
const workspace = document.querySelector('.admin-workspace')
workspace.scrollTop = 250
const polling = callback()
await nextTick()
const activeRefresh = [...document.querySelectorAll('button')].find((b) =>
  b.textContent.includes('更新中')
)
assert.equal(document.querySelector('.resource-status'), statusRow, 'polling must keep the same status row')
assert.equal(statusRow.firstElementChild.textContent, timestamp, 'polling must preserve the last update text')
assert.equal(dom.window.getComputedStyle(statusRow).minHeight, '24px')
assert.equal(workspace.scrollTop, 250)
assert.equal(document.querySelector('.resource-refresh.visible').textContent, '正在刷新…')
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
