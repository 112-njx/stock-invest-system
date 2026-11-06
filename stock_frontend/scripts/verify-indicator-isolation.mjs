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
app.unmount()
console.log('Independent chart rendering, failure recovery, delayed MA and stale-response protection passed.')
