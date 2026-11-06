import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { build } from 'esbuild'
import { parse, compileScript } from '@vue/compiler-sfc'
import { JSDOM } from 'jsdom'

const root = process.cwd()
const output = resolve(root, 'node_modules/.cache/synthetic-wicks-test.mjs')
await build({
  stdin: { contents: "export { default as Chart } from '@/components/stockdb/StockDbChart.vue'; export { createApp, ref, nextTick } from 'vue'; export * from '@/utils/syntheticWicks'", resolveDir: root, loader: 'ts' },
  outfile: output, bundle: true, format: 'esm', platform: 'browser', alias: { '@': resolve(root, 'src') },
  define: { 'process.env.NODE_ENV': '"test"', __VUE_OPTIONS_API__: 'true', __VUE_PROD_DEVTOOLS__: 'false', __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false' },
  plugins: [{ name: 'chart-fixtures', setup(builder) {
    builder.onResolve({ filter: /^@\/(composables\/useSyntheticWicks|api\/stockdb)$/ }, ({ path }) => ({ path, namespace: 'fixture' }))
    builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({ contents: path.includes('composables')
      ? 'export const useSyntheticWicks = () => globalThis.factor'
      : 'export const percent = n => n.toFixed(2) + "%"' }))
    builder.onLoad({ filter: /\.vue$/ }, async ({ path }) => {
      const { descriptor } = parse(await readFile(path, 'utf8'), { filename: path })
      return { contents: compileScript(descriptor, { id: 'wick-test', inlineTemplate: true }).content, loader: 'ts' }
    })
  } }], logLevel: 'error',
})
const dom = new JSDOM('<body><div id="synthetic"></div><div id="stock"></div></body>')
for (const key of ['window', 'document', 'HTMLElement', 'SVGElement', 'Element', 'Node']) globalThis[key] = dom.window[key]
const { Chart, createApp, ref, nextTick, displaySyntheticCandle } = await import(pathToFileURL(output).href)
for (const [open, close] of [[100, 110], [110, 100], [100, 100]]) {
  const raw = Object.freeze({ open, close, high: 120, low: 90, volume: 42 })
  for (const factor of [0, 0.25, 0.5, 1]) {
    const shown = displaySyntheticCandle(raw, factor)
    assert.equal(shown.high, Math.max(open, close) + (120 - Math.max(open, close)) * factor)
    assert.equal(shown.low, Math.min(open, close) - (Math.min(open, close) - 90) * factor)
    assert.equal(shown.open, open); assert.equal(shown.close, close); assert.equal(shown.volume, 42)
    assert.equal(raw.high, 120); assert.equal(raw.low, 90)
  }
}
globalThis.factor = ref(1)
const bars = Object.freeze([Object.freeze([20261104, 100, 120, 90, 110, 42, 200, 99]), Object.freeze([20261105, 130, 142, 125, 135, 30, 100, 110])])
const synthetic = createApp(Chart, { bars, label: 'index', synthetic: true })
const stock = createApp(Chart, { bars, label: 'stock' })
synthetic.mount('#synthetic'); stock.mount('#stock'); await nextTick()
const geometry = id => document.querySelector(`#${id} svg`).innerHTML
const stockBefore = geometry('stock'), original = geometry('synthetic')
globalThis.factor.value = 0.5; await nextTick()
assert.notEqual(geometry('synthetic'), original, 'synthetic SVG must react to the shared coefficient')
assert.equal(geometry('stock'), stockBefore, 'individual stock SVG must stay unchanged')
assert.equal(bars[0][2], 120); assert.equal(bars[0][3], 90)
globalThis.factor.value = 0; await nextTick()
const line = document.querySelector('#synthetic g line'), body = document.querySelector('#synthetic g rect')
assert.equal(Number(line.getAttribute('y1')), Number(body.getAttribute('y')))
assert.ok(Math.abs(Number(line.getAttribute('y2')) - Number(body.getAttribute('y')) - Number(body.getAttribute('height'))) < 1e-8)
globalThis.factor.value = 1; await nextTick()
assert.equal(geometry('synthetic'), original, 'restoring factor must not compound previous scaling')
synthetic.unmount(); stock.unmount(); dom.window.close()
console.log('Synthetic wick formula, reactive SVG, scope isolation and immutable source checks passed')
