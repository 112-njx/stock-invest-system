import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { parse, compileScript } from '@vue/compiler-sfc'
import { readFile } from 'node:fs/promises'
import { JSDOM } from 'jsdom'

const result = await build({
  stdin: { contents: "export {default as Details} from './src/components/admin/AdminUpdateDetails.vue';export{createApp,h,reactive,nextTick}from'vue'", resolveDir: process.cwd() },
  bundle: true, write: false, format: 'esm', platform: 'browser',
  define: { 'process.env.NODE_ENV': '"test"', __VUE_OPTIONS_API__: 'true', __VUE_PROD_DEVTOOLS__: 'false', __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false' },
  plugins: [{ name: 'fixture', setup(builder) {
    builder.onResolve({filter:/^@\/api\/http$/}, () => ({path:'http',namespace:'fixture'}))
    builder.onLoad({filter:/.*/,namespace:'fixture'}, () => ({contents:'export const request=config=>globalThis.updateReviewFetch(config)'}))
    builder.onLoad({filter:/\.vue$/}, async ({path}) => ({contents:compileScript(parse(await readFile(path,'utf8'),{filename:path}).descriptor,{id:'test',inlineTemplate:true}).content,loader:'ts'}))
  } }],
})
const dom = new JSDOM('<div id="app"></div>', {pretendToBeVisual:true})
for (const key of ['window','document','Element','HTMLElement','SVGElement','Node']) globalThis[key] = dom.window[key]
const {Details,createApp,h,reactive,nextTick} = await import('data:text/javascript;base64,'+Buffer.from(result.outputFiles[0].text).toString('base64'))
const timeout = globalThis.setTimeout, clear = globalThis.clearTimeout
const timers = new Map()
let id = 0
globalThis.setTimeout = (fn,ms,...args) => ms>=1000 ? (timers.set(++id,fn),id) : timeout(fn,ms,...args)
globalThis.clearTimeout = key => { if(!timers.delete(key)) clear(key) }
const page = (seq,message,more=false) => ({events:[{seq,time:0,phase:'downloading',level:'info',message}],files:[],has_more:more})

try {
  for (const terminal of ['全部完成','更新失败']) {
    let calls=0, release
    const seen=[]
    globalThis.updateReviewFetch = config => {
      seen.push(config.params)
      calls++
      if(calls===1) return Promise.resolve(page(1,'下载中'))
      if(calls===2) return new Promise(resolve => {release=resolve})
      if(calls===3) return Promise.resolve(page(2,'正在校验',true))
      return Promise.resolve(page(3,terminal))
    }
    const state=reactive({running:true,taskId:'00000000-0000-4000-8000-000000000001'})
    const app=createApp({render:()=>h(Details,state)})
    app.mount('#app'); await new Promise(setImmediate); await nextTick()
    const [key,callback]=[...timers][0]; timers.delete(key)
    const pending=callback(); await nextTick()
    state.running=false; await nextTick()
    assert.equal(calls,2,'terminal refresh should wait for the active request')
    release({events:[],files:[],has_more:false})
    await pending; await nextTick()
    assert.equal(calls,4,'the final refresh must drain every remaining page')
    assert.equal(seen[2].after_seq,1)
    assert.equal(seen[3].after_seq,2)
    assert.match(document.querySelector('.update-log').textContent,new RegExp(terminal))
    assert.equal(timers.size,0,'completed tasks should stop polling after fetching final events')
    app.unmount()
  }

  // A response for a previous task must not swallow the new task's queued load.
  let release, calls=0
  globalThis.updateReviewFetch = config => {
    calls++
    if(calls===1) return new Promise(resolve=>{release=resolve})
    assert.equal(config.params.task_id,'00000000-0000-4000-8000-000000000002')
    return Promise.resolve(page(5,'新任务日志'))
  }
  const state=reactive({running:false,taskId:'00000000-0000-4000-8000-000000000001'})
  const app=createApp({render:()=>h(Details,state)})
  app.mount('#app'); await nextTick()
  state.taskId='00000000-0000-4000-8000-000000000002'; await nextTick()
  release(page(1,'旧任务日志'))
  await new Promise(setImmediate); await nextTick()
  assert.equal(calls,2)
  assert.match(document.querySelector('.update-log').textContent,/新任务日志/)
  assert.doesNotMatch(document.querySelector('.update-log').textContent,/旧任务日志/)
  app.unmount()
  console.log('Final success/failure logs, multi-page drain and task-switch races passed.')
} finally {
  globalThis.setTimeout=timeout
  globalThis.clearTimeout=clear
}
