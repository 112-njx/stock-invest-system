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
  stdin: { contents: "export {useChartIndicators} from './src/composables/useChartIndicators';export {createApp,h,nextTick} from 'vue'", resolveDir: process.cwd() },
  bundle: true, format: 'esm', outfile: output, platform: 'browser',
  define: { 'process.env.NODE_ENV': '"test"', __VUE_OPTIONS_API__: 'true', __VUE_PROD_DEVTOOLS__: 'false', __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false' },
})
const dom = new JSDOM('<div id="app"></div>')
for (const name of ['window', 'document', 'Element', 'HTMLElement', 'SVGElement', 'Node']) globalThis[name] = dom.window[name]
const { useChartIndicators, createApp, h, nextTick } = await import(pathToFileURL(output).href)
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
