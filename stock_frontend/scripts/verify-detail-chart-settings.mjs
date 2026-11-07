import assert from 'node:assert/strict'
import { readFile, mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { build } from 'esbuild'
import { parse, compileScript } from '@vue/compiler-sfc'
import { JSDOM } from 'jsdom'
const root = process.cwd(), dir = resolve('node_modules/.cache/detail-chart')
await mkdir(dir, { recursive: true })
const out = resolve(dir, 'test.mjs')
await build({ stdin: { contents: "export {default as Chart} from '@/components/trading/KLineChart.vue'; export {useUserStore} from '@/stores/user'; export {createApp,h,nextTick} from 'vue';export {createPinia} from 'pinia'", resolveDir: root, loader: 'ts' }, outfile: out, bundle: true, format: 'esm', platform: 'browser', loader: { '.png':'dataurl' }, alias: { '@': resolve('src') },
  define: { 'process.env.NODE_ENV': '"test"', __VUE_OPTIONS_API__: 'true', __VUE_PROD_DEVTOOLS__: 'false', __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false' },
  plugins: [{ name: 'fixture', setup(b) {
    b.onResolve({ filter: /(?:^|\/)http$/ }, ({path}) => ({path, namespace:'fixture'}))
    b.onLoad({filter:/.*/, namespace:'fixture'}, () => ({contents:'export const request=config=>globalThis.chartFixture.request(config); export default {}'}))
    b.onLoad({filter:/\.vue$/}, async ({path}) => { const {descriptor}=parse(await readFile(path,'utf8'),{filename:path}); return {contents:compileScript(descriptor,{id:path,inlineTemplate:true}).content,loader:'ts',resolveDir:resolve(path,'..')} })
  } }] })
const dom = new JSDOM('<div id="app"></div>', { url: 'http://localhost' })
for (const name of ['window','document','Element','HTMLElement','SVGElement','Node','localStorage','getComputedStyle','Event']) globalThis[name]=dom.window[name]
globalThis.requestAnimationFrame = fn => setTimeout(fn,0)
globalThis.cancelAnimationFrame = clearTimeout
globalThis.BroadcastChannel = undefined
const m = await import(pathToFileURL(out).href)
const defaults = () => ({ma:{lines:[5,10,20,30].map(period=>({period,visible:true}))},panels:['volume','macd']})
const saved = new Map()
let fail = false, pending
const pinia = m.createPinia(), user = m.useUserStore(pinia)
globalThis.chartFixture = { async request(c) {
  if (c.url !== '/users/me/chart-settings') return []
  const id = user.user?.id
  if (c.method === 'put') {
    if (pending) return new Promise(resolve=>{ pending.resolve = () => resolve(structuredClone(c.data)) })
    if (fail) throw Error('offline')
    saved.set(id, structuredClone(c.data)); return structuredClone(c.data)
  }
  return structuredClone(saved.get(id) || defaults())
} }
const settle = async () => { await new Promise(r=>setTimeout(r,0)); await m.nextTick() }
const mount = custom => {const app=m.createApp({render:()=>m.h(m.Chart,{symbol:null,showIndicators:true,customizeIndicators:custom})});app.use(pinia);app.mount('#app');return app}
const click = async button => { assert.ok(button); button.click(); await settle() }
const button = text => [...document.querySelectorAll('button')].find(b=>b.textContent.trim()===text)
const panel = text => [...document.querySelectorAll('.picker-item')].find(b=>b.textContent.includes(text))
localStorage.setItem('indicator_visibility',JSON.stringify(['kdj','macd','amount','volume']))
let app=mount(true);await settle()
await click(document.querySelector('[title="选择技术指标"]'))
assert.match(document.body.textContent,/已开启 3\/3/)
assert.equal(panel('KDJ').disabled,true)
await click(panel('成交额'));assert.equal(panel('KDJ').disabled,false)
await click(panel('KDJ'));assert.equal(panel('成交额').disabled,true)
assert.equal(JSON.parse(localStorage.getItem('indicator_visibility')).length,4,'home preferences stay intact')
await click(document.querySelector('.modal__close'))
await click(button('MA 设置'))
const periods=()=>[...document.querySelectorAll('input[type=number]')]
const input = async (el,value) => {el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));await settle()}
await input(periods()[0],'7')
await click([...document.querySelectorAll('button')].find(b=>b.textContent.includes('添加 MA')))
await click([...document.querySelectorAll('button')].find(b=>b.textContent.includes('添加 MA')))
assert.equal(periods().length,6)
assert.equal([...document.querySelectorAll('button')].find(b=>b.textContent.includes('添加 MA')).disabled,true)
await input(periods()[1],'7'); assert.equal(button('保存').disabled,true)
await input(periods()[1],'20'); await input(periods()[2],'60')
await input(periods()[3],'120'); await input(periods()[4],'250'); await input(periods()[5],'10000')
await click(button('保存'));assert.equal(document.querySelector('[aria-label="MA设置"]'),null)
assert.deepEqual(JSON.parse(localStorage.getItem('detail_chart_settings_v1')).ma.lines.map(l=>l.period),[7,20,60,120,250,10000])
await click(button('MA 设置'))
for (const checkbox of document.querySelectorAll('[aria-label="MA设置"] input[type=checkbox]')) await click(checkbox)
await click(button('保存'))
assert.equal(JSON.parse(localStorage.getItem('detail_chart_settings_v1')).ma.lines.every(l=>!l.visible),true)
user.setAuth('fixture',{id:1,username:'one'});await settle()
await click(button('MA 设置'));assert.equal(periods().length,4,'account defaults do not import guest preferences');await click(button('取消'))
await click(document.querySelector('[title="选择技术指标"]'))
fail=true;await click(panel('KDJ'));assert.match(document.body.textContent,/已开启 2\/3/);assert.match(document.body.textContent,/保存失败/)
fail=false;await click(panel('KDJ'));assert.equal(saved.get(1).panels.length,3)
for(const name of ['成交量','MACD','KDJ']) await click(panel(name))
assert.deepEqual(saved.get(1).panels,[])
user.setAuth('fixture',{id:2,username:'two'});await settle();assert.match(document.body.textContent,/已开启 2\/3/)
user.setAuth('fixture',{id:1,username:'one'});await settle();assert.match(document.body.textContent,/已开启 0\/3/)
pending={};await click(panel('KDJ'))
user.setAuth('fixture',{id:2,username:'two'});await settle()
pending.resolve();pending=null;await settle();assert.match(document.body.textContent,/已开启 2\/3/,'late save cannot overwrite another account')
user.clearAuth();await settle();await click(button('MA 设置'));assert.equal(periods().length,6);await click(button('取消'))
app.unmount();await settle()
app=mount(false);await settle();assert.equal(button('MA 设置'),undefined);assert.equal(localStorage.getItem('indicator_visibility'),JSON.stringify(['kdj','macd','amount','volume']))
app.unmount()
console.log('Detail MA editor, six-line validation, three-panel cap, rollback, guest/account isolation, stale saves and homepage isolation passed.')
