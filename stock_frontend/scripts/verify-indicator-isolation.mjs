import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'

const dir = resolve('node_modules/.cache/indicator-isolation')
await mkdir(dir, { recursive: true })
const output = resolve(dir, 'test.mjs')
await build({
  stdin: { contents: "export {useChartIndicators} from './src/composables/useChartIndicators';export {useOverlayIndicators} from './src/composables/useOverlayIndicators';export {createApp,h,nextTick} from 'vue'", resolveDir: process.cwd() },
  bundle: true, format: 'esm', outfile: output, platform: 'browser',
  define: { 'process.env.NODE_ENV': '"test"', __VUE_OPTIONS_API__: 'true', __VUE_PROD_DEVTOOLS__: 'false', __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false' },
})
const dom = new JSDOM('<div id="app"></div>')
for (const name of ['window', 'document', 'Element', 'HTMLElement', 'SVGElement', 'Node']) globalThis[name] = dom.window[name]
const { useChartIndicators, useOverlayIndicators, createApp, h, nextTick } = await import(pathToFileURL(output).href)
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
const queue = []
let state
const app = createApp({
  setup() {
    state = useChartIndicators(params => {
      const task = deferred()
      queue.push({ ...task, params })
      return task.promise
    })
    return () => h('main', [
      h('p', { id: 'ma-error' }, state.priceMaError.value),
      h('p', { id: 'panel-error' }, state.indicatorError.value),
      h('div', { id: 'ma' }, JSON.stringify(state.priceMaRows.value)),
      h('div', { id: 'panels' }, JSON.stringify(state.indicatorRows.value)),
    ])
  },
})
app.mount('#app')
const params = { symbol: 1, period: '1d' }
const panelRows = [{ ts: '2026-11-05', macd_hist: 1.23, kdj_k: 56, volume: 100, amount: 1000, volume_ma5: 90 }]
const maRows = [{ ts: '2026-11-05', ma5: 10, ma30: 9 }]
const text = id => document.querySelector(id).textContent

// A delayed/failing MA must not delay or erase successful panels.
let job = state.load(params, true, () => true)
assert.equal(queue[0].params.names, 'ma')
assert.equal(queue[1].params.names, 'macd,kdj,volume,amount')
queue[1].resolve(panelRows)
await new Promise(resolve => setTimeout(resolve, 0))
await nextTick()
assert.match(text('#panels'), /1.23/)
queue[0].reject(Error('SDK unavailable'))
await job; await nextTick()
assert.match(text('#ma-error'), /主图价格均线获取失败/)
assert.equal(text('#panel-error'), '')
assert.match(text('#panels'), /volume_ma5/)

// Successful MA also survives a panel failure; recovery clears only its own error.
job = state.load(params, true, () => true)
queue[2].resolve(maRows); queue[3].reject(Error('panels unavailable'))
await job; await nextTick()
assert.match(text('#ma'), /ma30/)
assert.equal(text('#ma-error'), '')
assert.match(text('#panel-error'), /附图指标获取失败/)
job = state.load(params, true, () => true)
queue[4].resolve(maRows); queue[5].resolve(panelRows)
await job; await nextTick()
assert.equal(text('#panel-error'), '')

// Ignore responses from an earlier symbol/period or from a removed chart.
const old = state.load(params, true, () => true)
job = state.load({ symbol: 2, period: '1w' }, true, () => true)
queue[8].resolve(maRows); queue[9].resolve(panelRows)
await job
queue[6].reject(Error('late failure')); queue[7].resolve([{ ts: 'old' }])
await old
assert.deepEqual(JSON.parse(JSON.stringify(state.indicatorRows.value)), panelRows)
assert.equal(state.priceMaError.value, '')
job = state.load(params, true, () => true)
state.reset()
queue[10].resolve(maRows); queue[11].resolve(panelRows)
await job
assert.equal(state.indicatorRows.value.length, 0)
assert.equal(state.priceMaRows.value.length, 0)

job = state.load(params, false, () => true)
assert.equal(queue.length, 13, 'a chart without panels requests only MA')
queue[12].resolve(maRows)
await job
// Detail-only selection sends custom parameters and only enabled panels.
job = state.load(params, true, () => true, { periods: [7,20,60], panels: ['kdj'] })
assert.deepEqual(JSON.parse(queue[13].params.params), { ma: { periods: [7,20,60] } })
assert.equal(queue[14].params.names, 'kdj')
queue[13].resolve([{ ts: 'new', ma7: 7 }]); queue[14].resolve([{ ts: 'new', kdj_k: 50 }])
await job
job = state.load(params, false, () => true, { periods: [1], panels: [] })
assert.equal(queue.length, 16)
queue[15].resolve([{ ts: 'new', ma1: 10 }])
await job
assert.equal(state.indicatorRows.value.length, 0)
const start = queue.length
job = state.load(params, true, () => true, {periods:[7],panels:['volume','macd','kdj'],parameters:{kdj:{params:{n:14}}}})
assert.equal(queue[start+1].params.names,'volume')
assert.equal(queue[start+2].params.names,'macd')
assert.deepEqual(JSON.parse(queue[start+3].params.params),{kdj:{n:14}})
queue[start].resolve(maRows)
queue[start+1].resolve([{ts:'2026-11-05',volume:100}])
queue[start+2].reject(Error('only MACD failed'))
queue[start+3].resolve([{ts:'2026-11-05',kdj_k:55}])
await job
assert.equal(state.indicatorRows.value[0].volume,100)
assert.equal(state.indicatorRows.value[0].kdj_k,55)
assert.ok(state.panelErrors.value.macd)
assert.equal(state.panelErrors.value.kdj,undefined)
// Retrying one failed panel neither re-fetches MA/healthy panels nor clears their data.
let retryIndex = queue.length
const healthy = JSON.stringify(state.indicatorRows.value)
const maBefore = state.priceMaRows.value
job = state.retryPanel('macd')
assert.equal(queue.length, retryIndex+1)
assert.equal(queue[retryIndex].params.names,'macd')
assert.equal(JSON.stringify(state.indicatorRows.value),healthy)
assert.equal(state.priceMaRows.value,maBefore)
assert.equal(state.panelRetrying.value.macd,true)
await state.retryPanel('macd')
assert.equal(queue.length,retryIndex+1,'duplicate retries are suppressed')
queue[retryIndex].reject(Error('MACD is still unavailable'))
await job
assert.equal(JSON.stringify(state.indicatorRows.value),healthy)
assert.ok(state.panelErrors.value.macd)
assert.equal(state.panelRetrying.value.macd,false)
retryIndex=queue.length
job=state.retryPanel('macd')
queue[retryIndex].resolve([{ts:'2026-11-05',macd_hist:1.5}])
await job
assert.equal(state.indicatorRows.value[0].volume,100)
assert.equal(state.indicatorRows.value[0].kdj_k,55)
assert.equal(state.indicatorRows.value[0].macd_hist,1.5)
assert.equal(state.panelErrors.value.macd,undefined)
assert.equal(state.priceMaRows.value,maBefore)
// A retry cannot overwrite data following a symbol/period/parameter change.
retryIndex=queue.length
const oldRetry=state.retryPanel('macd')
job=state.load({symbol:2,period:'1w'},true,()=>true,{periods:[20],panels:['kdj'],parameters:{kdj:{params:{n:21}}}})
queue[retryIndex+1].resolve([{ts:'new',ma20:20}])
queue[retryIndex+2].resolve([{ts:'new',kdj_k:70}])
await job
queue[retryIndex].resolve([{ts:'old',macd_hist:999}])
await oldRetry
assert.deepEqual(JSON.parse(JSON.stringify(state.indicatorRows.value)),[{ts:'new',kdj_k:70}])
retryIndex=queue.length
await state.retryPanel('macd')
assert.equal(queue.length,retryIndex,'closed panels cannot be retried')
job=state.retryPanel('kdj')
state.reset()
queue[retryIndex].resolve([{ts:'removed',kdj_k:999}])
await job
assert.equal(state.indicatorRows.value.length,0)
assert.deepEqual(state.panelRetrying.value,{})
await state.retryPanel('kdj')
assert.equal(queue.length,retryIndex+1)
const commonStart=queue.length
job=state.load(params,true,()=>true,{periods:[5],panels:['rsi','wr','cci'],parameters:{rsi:{params:{n:7}},wr:{params:{n:14,n1:5}},cci:{params:{n:9}}}})
assert.deepEqual(queue.slice(commonStart).map(q=>q.params.names),['ma','rsi','wr','cci'])
queue[commonStart].resolve(maRows)
queue[commonStart+1].reject(Error('RSI unavailable'))
queue[commonStart+2].resolve([{ts:'2026-11-05',wr1:33,wr2:55}])
queue[commonStart+3].resolve([{ts:'2026-11-05',cci:125}])
await job
assert.equal(state.indicatorRows.value[0].wr1,33)
assert.equal(state.indicatorRows.value[0].cci,125)
const unaffected=JSON.stringify(state.indicatorRows.value)
const commonRetry=queue.length
job=state.retryPanel('rsi')
assert.equal(queue.length,commonRetry+1)
assert.equal(JSON.stringify(state.indicatorRows.value),unaffected)
assert.deepEqual(JSON.parse(queue[commonRetry].params.params),{rsi:{n:7}})
queue[commonRetry].resolve([{ts:'2026-11-05',rsi:61}])
await job
assert.equal(state.indicatorRows.value[0].rsi,61)
assert.equal(state.indicatorRows.value[0].wr2,55)
assert.equal(state.panelErrors.value.rsi,undefined)
app.unmount()
console.log('Independent chart rendering, failure recovery, delayed MA and stale-response protection passed.')

const overlayQueue=[]
const main=useOverlayIndicators(p=>{const task=deferred();overlayQueue.push({...task,params:p});return task.promise})
let overlayJob=main.load(params,['boll','ema','dma'],{boll:{params:{n:10,p:2.5}},dma:{params:{a:.25}}},()=>true)
assert.equal(overlayQueue.length,1,'overlays are queued instead of flooding native worker')
assert.equal(overlayQueue[0].params.names,'boll')
assert.deepEqual(JSON.parse(overlayQueue[0].params.params),{boll:{n:10,p:2.5}})
overlayQueue[0].resolve([{ts:'2026-11-05',boll_upper:12,boll_mid:10,boll_lower:8}])
await new Promise(r=>setTimeout(r,0))
assert.equal(overlayQueue.length,2)
overlayQueue[1].reject(Error('EMA unavailable'))
await new Promise(r=>setTimeout(r,0))
assert.equal(overlayQueue.length,3)
overlayQueue[2].resolve([{ts:'2026-11-05',dma:10}]);await overlayJob
assert.equal(main.rows.value.boll[0].boll_mid,10)
assert.equal(main.rows.value.dma[0].dma,10)
assert.ok(main.errors.value.ema)
const bollBefore=main.rows.value.boll,dmaBefore=main.rows.value.dma
let retryMain=main.retry('ema')
assert.equal(overlayQueue.length,4)
assert.equal(main.rows.value.boll,bollBefore);assert.equal(main.rows.value.dma,dmaBefore)
await main.retry('ema');assert.equal(overlayQueue.length,4)
overlayQueue[3].resolve([{ts:'2026-11-05',ema:11}]);await retryMain
assert.equal(main.errors.value.ema,undefined)
retryMain=main.retry('ema')
overlayJob=main.load({symbol:2,period:'1w'},['bbi'],{},()=>true)
overlayQueue[5].resolve([{ts:'new',bbi:30}]);await overlayJob
overlayQueue[4].resolve([{ts:'old',ema:999}]);await retryMain
assert.deepEqual(main.rows.value,{bbi:[{ts:'new',bbi:30}]})
await main.retry('ema');assert.equal(overlayQueue.length,6)
overlayJob=main.load(params,['sma','wma'],{},()=>true)
main.reset();overlayQueue[6].resolve([{ts:'removed',sma:999}]);await overlayJob
assert.equal(overlayQueue.length,7,'reset prevents queued overlays from starting')
assert.deepEqual(main.rows.value,{})
console.log('Independent main overlays: native queue, failures, targeted retries and stale-response protection passed.')

const momentumQueue=[]
const momentum=useChartIndicators(p=>{const task=deferred();momentumQueue.push({...task,params:p});return task.promise})
let momentumJob=momentum.load(params,true,()=>true,{periods:[5],panels:['bias','psy','dpo'],parameters:{bias:{params:{l1:3,l2:9,l3:18}}}})
assert.deepEqual(momentumQueue.map(q=>q.params.names),['ma','bias','psy','dpo'])
momentumQueue[0].resolve(maRows)
momentumQueue[1].reject(Error('BIAS unavailable'))
momentumQueue[2].resolve([{ts:'2026-11-05',psy:60,psy_ma:55}])
momentumQueue[3].resolve([{ts:'2026-11-05',dpo:-2,dpo_ma:-1}])
await momentumJob
const retained=momentum.indicatorRows.value
momentumJob=momentum.retryPanel('bias')
assert.equal(momentumQueue.length,5)
assert.equal(momentum.indicatorRows.value,retained)
assert.deepEqual(JSON.parse(momentumQueue[4].params.params),{bias:{l1:3,l2:9,l3:18}})
momentumQueue[4].resolve([{ts:'2026-11-05',bias1:-3,bias2:2,bias3:1}]);await momentumJob
assert.equal(momentum.indicatorRows.value[0].psy,60)
assert.equal(momentum.indicatorRows.value[0].bias1,-3)
const oldMomentum=momentum.retryPanel('bias')
momentumJob=momentum.load({symbol:2,period:'15m'},true,()=>true,{periods:[20],panels:['mtm','roc'],parameters:{roc:{params:{n:7,m:3}}}})
momentumQueue[6].resolve(maRows)
momentumQueue[7].resolve([{ts:'new',mtm:-5,mtm_ma:1}])
momentumQueue[8].resolve([{ts:'new',roc:-2,roc_ma:3}])
await momentumJob
momentumQueue[5].resolve([{ts:'old',bias1:999}]);await oldMomentum
assert.equal(momentum.indicatorRows.value[0].mtm,-5)
assert.equal(momentum.indicatorRows.value[0].bias1,undefined)
momentum.reset()
console.log('Momentum panel failures, targeted retries, preserved successful results and stale responses passed.')

const channelQueue=[]
const channels=useOverlayIndicators(p=>{const task=deferred();channelQueue.push({...task,params:p});return task.promise})
let channelJob=channels.load(params,['taq','ktn','xsii'],{taq:{params:{n:9}},xsii:{params:{n:104,m:5}}},()=>true)
assert.equal(channelQueue[0].params.names,'taq')
channelQueue[0].reject(Error('TAQ unavailable'));await new Promise(r=>setTimeout(r,0))
assert.equal(channelQueue[1].params.names,'ktn')
channelQueue[1].resolve([{ts:'2026-11-05',ktn_up:30,ktn_mid:20,ktn_down:10}]);await new Promise(r=>setTimeout(r,0))
assert.equal(channelQueue[2].params.names,'xsii')
assert.deepEqual(JSON.parse(channelQueue[2].params.params),{xsii:{n:104,m:5}})
channelQueue[2].resolve([{ts:'2026-11-05',xsii_td1:21,xsii_td2:19,xsii_td3:25,xsii_td4:15}]);await channelJob
const goodKTN=channels.rows.value.ktn
channelJob=channels.retry('taq')
assert.equal(channelQueue.length,4)
assert.equal(channels.rows.value.ktn,goodKTN)
assert.deepEqual(JSON.parse(channelQueue[3].params.params),{taq:{n:9}})
channelQueue[3].resolve([{ts:'2026-11-05',taq_up:30,taq_mid:20,taq_down:10}]);await channelJob
const oldChannel=channels.retry('xsii')
channelJob=channels.load({symbol:2,period:'15m'},['xsii'],{xsii:{params:{n:106,m:9}}},()=>true)
channelQueue[5].resolve([{ts:'new',xsii_td1:32}]);await channelJob
channelQueue[4].resolve([{ts:'old',xsii_td1:999}]);await oldChannel
assert.equal(channels.rows.value.xsii[0].xsii_td1,32)
assert.deepEqual(JSON.parse(channelQueue[5].params.params),{xsii:{n:106,m:9}})
channels.reset()

for(const group of [['dmi','trix','dfma'],['mass','vr','cr'],['emv','brar','obv'],['mfi','asi']]){
  const queue=[]
  const state=useChartIndicators(p=>{const task=deferred();queue.push({...task,params:p});return task.promise})
  let job=state.load(params,true,()=>true,{periods:[5],panels:group})
  assert.deepEqual(queue.map(q=>q.params.names),['ma',...group])
  queue[0].resolve(maRows)
  queue[1].reject(Error(`${group[0]} unavailable`))
  group.slice(1).forEach((key,i)=>queue[i+2].resolve([{ts:'2026-11-05',[key]:12+i}]))
  await job
  const good=state.indicatorRows.value
  job=state.retryPanel(group[0])
  assert.equal(state.indicatorRows.value,good)
  assert.equal(queue.length,group.length+2)
  queue.at(-1).resolve([{ts:'2026-11-05',[group[0]]:-3}]);await job
  for(const key of group.slice(1)) assert.equal(state.indicatorRows.value[0][key],good[0][key])
  assert.equal(state.indicatorRows.value[0][group[0]],-3)
  state.reset()
}
console.log('Batches 5–7: each panel group isolates failures, price channels queue independently, targeted retries retain healthy data and parameter/symbol/period changes discard stale channel results.')
