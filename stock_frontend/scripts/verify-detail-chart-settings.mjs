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
await build({ stdin: { contents: "export {default as Chart} from '@/components/trading/KLineChart.vue'; export {useUserStore} from '@/stores/user'; export {createApp,h,nextTick} from 'vue';export {createPinia} from 'pinia';export {createIndicatorSeries,fillIndicatorSeries} from '@/components/trading/indicatorRenderer'", resolveDir: root, loader: 'ts' }, outfile: out, bundle: true, format: 'esm', platform: 'browser', loader: { '.png':'dataurl' }, alias: { '@': resolve('src') },
  define: { 'process.env.NODE_ENV': '"test"', __VUE_OPTIONS_API__: 'true', __VUE_PROD_DEVTOOLS__: 'false', __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false' },
  plugins: [{ name: 'fixture', setup(b) {
    b.onResolve({ filter: /(?:^|\/)http$/ }, ({path}) => ({path, namespace:'fixture'}))
    b.onLoad({filter:/.*/, namespace:'fixture'}, () => ({contents:'export const request=config=>globalThis.chartFixture.request(config); export default {}'}))
    b.onLoad({filter:/\.vue$/}, async ({path}) => { const {descriptor}=parse(await readFile(path,'utf8'),{filename:path}); return {contents:compileScript(descriptor,{id:path,inlineTemplate:true}).content,loader:'ts',resolveDir:resolve(path,'..')} })
  } }] })
const dom = new JSDOM('<div id="app"></div>', { url: 'http://localhost' })
for (const name of ['window','document','Document','ShadowRoot','Element','HTMLElement','SVGElement','Node','localStorage','getComputedStyle','Event']) globalThis[name]=dom.window[name]
globalThis.requestAnimationFrame = fn => setTimeout(fn,0)
globalThis.cancelAnimationFrame = clearTimeout
globalThis.BroadcastChannel = undefined
const m = await import(pathToFileURL(out).href)
const defaults = () => ({ma:{lines:[5,10,20,30].map(period=>({period,visible:true}))},panels:['volume','macd']})
const definitions = JSON.parse(await readFile(resolve('../stock_backend/app/services/indicator_catalog.json'),'utf8'))
const saved = new Map()
let fail = false, catalogFails = false, pending
const pinia = m.createPinia(), user = m.useUserStore(pinia)
globalThis.chartFixture = { async request(c) {
  if (c.url === '/indicators/catalog') { if (catalogFails) throw Error('catalog offline'); return {version:1,indicators:definitions} }
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
await click(button('MACD 参数'))
await input(document.querySelector('[aria-label="MACD FAST"]'),'7')
await input(document.querySelector('[aria-label="MACD SLOW"]'),'20')
await input(document.querySelector('[aria-label="MACD SIGNAL"]'),'5')
await click(button('保存参数'))
assert.deepEqual(saved.get(1).panel_options.macd.params,{fast:7,slow:20,signal:5})
await click(panel('MACD'));await click(panel('MACD'))
assert.deepEqual(saved.get(1).panel_options.macd.params,{fast:7,slow:20,signal:5})
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

// Generic renderer: arbitrary multi-line channels, reference lines and finite-value filtering.
const fakeSeries=[]
const pane={addSeries(type,options){const series={type,options,data:[],references:[],setData(data){this.data=data},createPriceLine(line){this.references.push(line);return line}};fakeSeries.push(series);return series}}
const channel={key:'probe',parameters:[],series:[{field:'upper',kind:'line',color:'#123',label:'upper'},{field:'lower',kind:'line',color:'#456',label:'lower'}],reference_lines:[20,80]}
const built=m.createIndicatorSeries(pane,channel,'#aaa')
assert.equal(built.series.length,2);assert.equal(built.referenceLines.length,2)
m.fillIndicatorSeries(built.series,channel,[{ts:'1',upper:12,lower:null},{ts:'2',upper:Infinity,lower:9}],Number,{up:'red',down:'green'})
assert.deepEqual(fakeSeries[0].data,[{time:1,value:12},{time:2}])
assert.deepEqual(fakeSeries[1].data,[{time:1},{time:2,value:9}])
const histogram=definitions.find(d=>d.key==='macd')
const bars=m.createIndicatorSeries(pane,histogram,'#aaa')
m.fillIndicatorSeries(bars.series,histogram,[{ts:'3',macd_hist:-1,macd_dif:2,macd_dea:3}],Number,{up:'red',down:'green'})
assert.equal(bars.series[0].data[0].color,'green')
assert.equal(bars.series[0].options.priceFormat.precision,3)
console.log('Catalog-driven parameter forms, saved parameters, generic channels/histograms and reference lines passed.')

// A catalog outage must not block an independent MA edit or mutate saved panels/options.
catalogFails=true
const guest={version:2,ma:defaults().ma,panels:['macd','volume'],panel_options:{macd:{params:{fast:7,slow:20,signal:5}}}}
localStorage.setItem('detail_chart_settings_v1',JSON.stringify(guest))
app=mount(true);await settle()
assert.match(document.body.textContent,/指标目录加载失败/)
await click(button('MA 设置'))
await input(periods()[0],'0');assert.equal(button('保存').disabled,true)
await input(periods()[0],'7');await click(button('保存'))
const guestAfter=JSON.parse(localStorage.getItem('detail_chart_settings_v1'))
assert.equal(guestAfter.ma.lines[0].period,7)
assert.deepEqual(guestAfter.panels,guest.panels)
assert.deepEqual(guestAfter.panel_options,guest.panel_options)
assert.doesNotMatch(document.body.textContent,/MA须为/)
// Authenticated preferences use the same independent MA-save path.
saved.set(3,{version:2,ma:defaults().ma,panels:['kdj'],panel_options:{kdj:{params:{n:14}}}})
user.setAuth('fixture',{id:3,username:'three'});await settle()
await click(button('MA 设置'));await input(periods()[0],'9');await click(button('保存'))
assert.equal(saved.get(3).ma.lines[0].period,9)
assert.deepEqual(saved.get(3).panels,['kdj'])
assert.deepEqual(saved.get(3).panel_options,{kdj:{params:{n:14}}})
catalogFails=false
await click(button('重试目录'))
assert.doesNotMatch(document.body.textContent,/指标目录加载失败/)
await click(document.querySelector('[title="选择技术指标"]'))
assert.match(document.body.textContent,/已开启 1\/3/)
assert.equal(panel('KDJ').classList.contains('active'),true)
app.unmount()
console.log('Catalog outage: guest/account MA saves preserve panels and parameters; catalog recovery passed.')

// Batch 2 panels are catalog-driven, consume one slot each and persist custom parameters.
const commonKeys=['rsi','wr','cci','atr']
const commonParams={rsi:{n:7},wr:{n:14,n1:5},cci:{n:9},atr:{n:6}}
saved.set(4,{version:2,ma:defaults().ma,panels:[],panel_options:{}})
user.setAuth('fixture',{id:4,username:'four'})
app=mount(true);await settle();await click(document.querySelector('[title="选择技术指标"]'))
assert.equal(document.querySelectorAll('.picker-item').length,8)
for(const key of ['rsi','wr','cci']) await click(panel(key.toUpperCase()))
assert.match(document.body.textContent,/已开启 3\/3/)
assert.equal(panel('ATR').disabled,true)
for(const key of commonKeys){
  if(key==='atr'){await click(panel('CCI'));await click(panel('ATR'))}
  const definition=definitions.find(d=>d.key===key)
  await click(button(`${definition.label} 参数`))
  for(const param of definition.parameters){
    const el=document.querySelector(`[aria-label="${definition.label} ${param.label}"]`)
    assert.equal(Number(el.value),param.default)
    await input(el,String(commonParams[key][param.key]))
  }
  await click(button('保存参数'))
  assert.deepEqual(saved.get(4).panel_options[key].params,commonParams[key])
  await click(button(`${definition.label} 参数`))
  for(const param of definition.parameters) assert.equal(Number(document.querySelector(`[aria-label="${definition.label} ${param.label}"]`).value),commonParams[key][param.key])
  await click(button('恢复默认参数'))
  for(const param of definition.parameters) assert.equal(Number(document.querySelector(`[aria-label="${definition.label} ${param.label}"]`).value),param.default)
  await click(button('取消'))
  const fake=m.createIndicatorSeries(pane,definition,'#aaa')
  assert.equal(fake.series.length,key==='wr'?2:1)
  assert.deepEqual(fake.referenceLines.map(l=>l.price),definition.reference_lines)
  for(const ts of ['2026-11-05T00:00:00Z','2026-11-06T00:00:00Z','2026-11-30T00:00:00Z','2026-11-05T01:45:00Z']){
    const row={ts,...Object.fromEntries(definition.native_outputs.map((f,i)=>[f,42+i]))}
    m.fillIndicatorSeries(fake.series,definition,[row],stamp=>Date.parse(stamp)/1000,{up:'red',down:'green'})
    fake.series.forEach((line,i)=>assert.deepEqual(line.data,[{time:Date.parse(ts)/1000,value:42+i}]))
    m.fillIndicatorSeries(fake.series,definition,[{ts,...Object.fromEntries(definition.native_outputs.map(f=>[f,null]))}],stamp=>Date.parse(stamp)/1000,{up:'red',down:'green'})
    fake.series.forEach(line=>assert.deepEqual(line.data,[{time:Date.parse(ts)/1000}]))
  }
}
assert.deepEqual(saved.get(4).panels,['rsi','wr','atr'])
app.unmount();app=mount(true);await settle()
await click(document.querySelector('[title="选择技术指标"]'))
assert.match(document.body.textContent,/已开启 3\/3/)
assert.equal(panel('WR').classList.contains('active'),true)
await click(button('WR 威廉指标 参数'))
assert.equal(document.querySelector('[aria-label="WR 威廉指标 周期1"]').value,'14')
await click(button('取消'))
user.setAuth('fixture',{id:5,username:'five'});await settle()
assert.match(document.body.textContent,/已开启 2\/3/)
assert.equal(panel('WR').classList.contains('active'),false)
user.setAuth('fixture',{id:4,username:'four'});await settle()
assert.match(document.body.textContent,/已开启 3\/3/)
assert.equal(panel('WR').classList.contains('active'),true)
app.unmount()
console.log('RSI/WR/CCI/ATR: parameter defaults/custom/reload/reset, 3-panel limit, account isolation, all-period timestamps and null rendering passed.')
