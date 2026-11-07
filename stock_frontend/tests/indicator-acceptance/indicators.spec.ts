import { test, expect, type Browser, type BrowserContext, type Page } from '@playwright/test'
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import type { IndicatorDefinition } from '../../src/composables/useIndicatorCatalog'

const baseURL=process.env.INDICATOR_TEST_URL || 'http://127.0.0.1:8081'
const artifacts=resolve('../.artifacts/indicators')
const catalog:IndicatorDefinition[]=JSON.parse(readFileSync(resolve('../stock_backend/app/services/indicator_catalog.json'),'utf8'))
const panelDefs=catalog.filter(d=>d.placement==='panel')
const overlayDefs=catalog.filter(d=>d.placement==='main'&&d.key!=='ma')
const indexParams={members:[{code:'600519',weight:3},{code:'300502',weight:1}],weighting:'custom',base:1000,start:'2025-01-01'}
const defaults=()=>({version:2,ma:{lines:[5,10,20,30].map(period=>({period,visible:true}))},panels:['volume','macd'],panel_options:{},overlays:[],overlay_options:{}} as any)
const periods=[['1d','日K'],['1w','周K'],['1mon','月K'],['15m','15min']]
const timing:any[]=[]
let actor:{context:BrowserContext;headers:Record<string,string>},stockId:string

async function newActor(browser:Browser,index=0){
  const credentials=JSON.parse(readFileSync(resolve(process.env.INDICATOR_TEST_ACCOUNTS || '../.artifacts/indicators/accounts.credentials.json'),'utf8')).accounts[index]
  const context=await browser.newContext({baseURL,viewport:{width:1600,height:1000}})
  const response=await context.request.post('/api/v1/auth/login',{data:{username:credentials.username,password:credentials.password}})
  expect(response.status(),'disposable account login').toBe(200)
  return {context,headers:{Authorization:`Bearer ${(await response.json()).data.token}`}}
}
async function save(config:any,target=actor){
  const r=await target.context.request.put('/api/v1/users/me/chart-settings',{headers:target.headers,data:config})
  expect(r.status(),'save isolated chart settings').toBe(200)
  return (await r.json()).data
}
async function read(target=actor){
  const r=await target.context.request.get('/api/v1/users/me/chart-settings?version=2',{headers:target.headers})
  expect(r.status()).toBe(200);return (await r.json()).data
}
async function openPicker(page:Page){await page.locator('[title="选择技术指标"]').click();await expect(page.locator('.modal--indicator-detail')).toBeVisible()}
function panel(page:Page,key:string){return page.locator('.picker-item').filter({has:page.locator('.picker-item__label',{hasText:catalog.find(d=>d.key===key)!.label})})}
function observe(page:Page){
  const responses:any[]=[],errors:string[]=[]
  page.on('pageerror',e=>errors.push(e.message))
  page.on('response',async response=>{
    const url=new URL(response.url())
    if(url.pathname==='/api/v1/indicators'){
      try{responses.push({symbol:url.searchParams.get('symbol'),period:url.searchParams.get('period'),key:url.searchParams.get('names'),status:response.status(),rows:(await response.json()).data})}catch{/* canceled stale load */}
    }
  })
  return {responses,errors}
}
async function ready(page:Page,state:ReturnType<typeof observe>,keys:string[],period:string,mark=0){
  await expect.poll(()=>keys.every(key=>state.responses.slice(mark).some(r=>r.symbol===stockId&&r.period===period&&r.key===key&&r.status===200&&r.rows?.length)),{timeout:60_000,message:`native results: ${period} ${keys}`}).toBe(true)
  await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))))
  expect(state.errors,'browser runtime errors').toEqual([])
}
async function boot(page:Page,config:any,period='1d'){
  const state=observe(page),keys=['ma',...(config.overlays||[]),...config.panels],start=Date.now()
  await page.goto('/market/detail?symbol=300308')
  await expect(page.locator('.kline-chart__symbol')).toContainText('300308')
  await ready(page,state,keys,'1d')
  if(period!=='1d'){
    const mark=state.responses.length
    await page.locator('.period-tab').getByText(periods.find(p=>p[0]===period)![1],{exact:true}).click()
    await ready(page,state,keys,period,mark)
  }
  timing.push({kind:'chart-ready',period,panels:config.panels,overlays:config.overlays,ms:Date.now()-start})
  return state
}
async function withPage(run:(page:Page)=>Promise<void>){
  const page=await actor.context.newPage()
  try{await run(page)}catch(error){
    await test.info().attach('chart-failure',{body:await page.screenshot(),contentType:'image/png'}).catch(()=>{})
    throw error
  }finally{await page.close()}
}
async function panePixels(page:Page){
  return page.locator('.kline-chart__canvas canvas').evaluateAll(nodes=>{
    const unique=new Map<number,HTMLCanvasElement>()
    for(const node of nodes){const c=node as HTMLCanvasElement,r=c.getBoundingClientRect();if(r.width>300&&r.height>50&&!unique.has(Math.round(r.y)))unique.set(Math.round(r.y),c)}
    return [...unique.entries()].sort((a,b)=>a[0]-b[0]).map(([y,c])=>{
      const ctx=c.getContext('2d')!,data=ctx.getImageData(0,0,c.width,c.height).data,colors:Record<string,number>={}
      for(let i=0;i<data.length;i+=4){if(data[i+3]>200){const key=[data[i],data[i+1],data[i+2]].join(',');colors[key]=(colors[key]||0)+1}}
      return {y,width:c.width,height:c.height,colors}
    })
  })
}
function rgb(hex:string){return hex.slice(1).match(/../g)!.map(x=>parseInt(x,16)).join(',')}

test.beforeAll(async({browser})=>{
  mkdirSync(artifacts,{recursive:true});actor=await newActor(browser)
  const r=await actor.context.request.get('/api/v1/symbols/search?q=300308')
  stockId=String((await r.json()).data.find((s:any)=>s.code==='300308').id)
})
test.afterAll(async()=>{if(actor)await actor.context.close();writeFileSync(resolve(artifacts,`browser-timing-${test.info().workerIndex}.json`),JSON.stringify(timing,null,2))})

test('guest: direct detail browsing and local settings survive reload',async({browser})=>{
  const context=await browser.newContext({baseURL}),page=await context.newPage()
  try{
    await page.goto('/market/detail?symbol=300308')
    await expect(page.locator('.kline-chart__symbol')).toContainText('300308')
    await expect(page).toHaveURL(/\/market\/detail/)
    await openPicker(page)
    await panel(page,'kdj').click()
    await expect.poll(()=>page.evaluate(()=>JSON.parse(localStorage.getItem('detail_chart_settings_v1')||'{}').panels)).toEqual(['volume','macd','kdj'])
    await page.reload();await openPicker(page)
    await expect(panel(page,'kdj')).toHaveClass(/active/)
  }finally{await context.close()}
})

for(const [period] of periods)for(let group=0;group<10;group++){
  const panels=panelDefs.slice(group*3,group*3+3),overlay=overlayDefs[group]
  test(`matrix ${period} ${panels.map(d=>d.key).join('+')} + ${overlay?.key||'MA'}`,async()=>{
    const config=defaults();config.panels=panels.map(d=>d.key);config.overlays=overlay?[overlay.key]:[]
    for(const d of panels){if(d.cross)config.panel_options[d.key]={params:{cross:true}};if(d.key==='zhishu')config.panel_options.zhishu={params:indexParams}}
    await save(config)
    await withPage(async page=>{
      const state=await boot(page,config,period)
      await expect(page.locator('.kline-chart__indicator-legend')).toHaveCount(panels.length)
      await expect(page.locator('.overlay-legend')).toHaveCount(config.overlays.length)
      const pixels=await panePixels(page)
      expect(pixels.length,'one main pane plus selected panels').toBe(panels.length+1)
      for(const [i,d] of panels.entries()){
        const legend=page.locator('.kline-chart__indicator-legend').nth(i)
        await expect(legend).toContainText(d.label)
        const response=state.responses.filter(r=>r.symbol===stockId&&r.period===period&&r.key===d.key&&r.status===200).at(-1)
        const last=response.rows.at(-1)
        for(const line of d.series){
          const slot=legend.locator('span').filter({hasText:new RegExp(`^${line.label}:`)})
          if(last[line.field]==null)await expect(slot).toContainText('—')
          else await expect(slot).not.toContainText('—')
          if(line.kind==='line'&&response.rows.slice(-15).some((r:any)=>r[line.field]!=null)){
            expect(pixels[i+1]!.colors[rgb(line.color)]||0,`${period} ${d.key}.${line.field} visible native curve`).toBeGreaterThan(2)
          }
        }
        if(d.cross)await expect(legend).toContainText('金叉:')
      }
      if(group===0||group===9)await page.screenshot({path:resolve(artifacts,`chart-${period}-${group}.png`)})
      const box=await page.locator('.kline-chart__canvas').boundingBox()
      await page.mouse.move(box!.x+box!.width*.7,box!.y+box!.height*.15)
      await expect(page.locator('.kline-chart__hover-data')).not.toHaveCount(0)
      await expect(page.locator('.kline-chart__body [role=alert]')).toHaveCount(0)
    })
  })
}

test('account: six MA, three-panel cap, sorting, independent defaults, zero panels and cross-device settings',async({browser})=>{
  const config=defaults();config.panels=['rsi','std','macd'];config.overlays=['boll'];config.panel_options={std:{params:{n:7,field:'volume'}},macd:{params:{cross:true}}}
  config.ma.lines=[5,10,20,30,60,120].map(period=>({period,visible:true}))
  await save(config)
  await withPage(async page=>{
    await boot(page,config);await openPicker(page)
    await expect(panel(page,'kdj')).toBeDisabled()
    await panel(page,'rsi').click();await expect(panel(page,'kdj')).toBeEnabled();await panel(page,'kdj').click()
    await expect.poll(async()=>(await read()).panels).toEqual(['std','macd','kdj'])
    await page.getByRole('button',{name:'上移 KDJ',exact:true}).click()
    await expect.poll(async()=>(await read()).panels).toEqual(['std','kdj','macd'])
    await page.getByRole('button',{name:'恢复 STD 标准差 默认',exact:true}).click()
    await expect.poll(async()=>(await read()).panel_options.std).toBeUndefined()
    expect((await read()).panel_options.macd.params.cross).toBe(true)
    expect((await read()).overlays).toEqual(['boll'])
    expect((await read()).ma.lines.length).toBe(6)
    for(const key of ['std','kdj','macd'])await panel(page,key).click()
    await expect.poll(async()=>(await read()).panels).toEqual([])
    await page.locator('.modal__close').click()
    await expect(page.locator('.kline-chart__indicator-legend')).toHaveCount(0)
  })
  const device=await newActor(browser),other=await newActor(browser,1)
  try{
    expect((await read(device)).panels).toEqual([])
    expect((await read(device)).ma.lines.length).toBe(6)
    expect((await read(other)).panels).toEqual(['volume','macd'])
    await device.context.addInitScript(()=>localStorage.setItem('detail_chart_settings_v1',JSON.stringify({ma:{lines:[{period:999,visible:true}]},panels:['rsi']})))
    const devicePage=await device.context.newPage()
    await devicePage.goto('/market/detail?symbol=300308')
    await expect(devicePage.locator('.kline-chart__ma-legend')).toContainText('MA120:')
    await expect(devicePage.locator('.kline-chart__ma-legend')).not.toContainText('MA999:')
    await expect(devicePage.locator('.kline-chart__indicator-legend')).toHaveCount(0)
    const otherPage=await other.context.newPage()
    await otherPage.goto('/market/detail?symbol=300308')
    await expect(otherPage.locator('.kline-chart__indicator-legend')).toHaveCount(2)
    await expect(otherPage.locator('.kline-chart__ma-legend')).not.toContainText('MA120:')
  }finally{await device.context.close();await other.context.close()}
})

test('isolation: one SDK failure, targeted retry and failed settings save',async()=>{
  const config=defaults();config.panels=['rsi','kdj','std'];await save(config)
  await withPage(async page=>{
    let failing=true
    await page.route('**/api/v1/indicators?**',async route=>{
      const u=new URL(route.request().url())
      if(u.searchParams.get('names')==='rsi'&&failing)await route.fulfill({status:503,json:{code:50331,msg:'isolated test SDK failure',data:null}})
      else await route.continue()
    })
    const state=observe(page);await page.goto('/market/detail?symbol=300308')
    await expect(page.locator('.kline-chart__symbol')).toContainText('300308')
    await ready(page,state,['ma','kdj','std'],'1d')
    const rsi=page.locator('.kline-chart__indicator-legend').filter({hasText:'RSI'})
    await expect(rsi).toContainText('获取失败')
    const kdj=await page.locator('.kline-chart__indicator-legend').filter({hasText:'KDJ'}).innerText()
    failing=false;const mark=state.responses.length
    await rsi.getByRole('button',{name:'重试',exact:true}).click()
    await ready(page,state,['rsi'],'1d',mark)
    expect(state.responses.slice(mark).map(r=>r.key)).toEqual(['rsi'])
    // Clicking a pane's retry button moves the shared crosshair. Compare the
    // healthy pane again at the same (latest) time, outside the chart.
    await page.mouse.move(5,5)
    await expect.poll(()=>page.locator('.kline-chart__indicator-legend').filter({hasText:'KDJ'}).innerText()).toBe(kdj)
    await openPicker(page)
    await page.route('**/api/v1/users/me/chart-settings',async route=>{
      if(route.request().method()==='PUT')await route.fulfill({status:503,json:{code:503,msg:'isolated test save failure',data:null}})
      else await route.continue()
    })
    await panel(page,'rsi').click()
    await expect(page.locator('.modal__body')).toContainText('保存失败')
    await expect(panel(page,'rsi')).toHaveClass(/active/)
    expect((await read()).panels).toEqual(config.panels)
  })
})

test('MA editor: validation, six lines, null history, visibility and explicit save',async()=>{
  const config=defaults();config.panels=['rsi','kdj','macd'];await save(config)
  await withPage(async page=>{
    const state=await boot(page,config)
    await page.getByRole('button',{name:'MA 设置',exact:true}).click()
    const form=page.getByRole('dialog',{name:'MA设置',exact:true})
    await form.getByRole('button',{name:/添加 MA/}).click();await form.getByRole('button',{name:/添加 MA/}).click()
    await expect(form.getByRole('button',{name:/添加 MA/})).toBeDisabled()
    await form.getByRole('spinbutton',{name:'第6条MA周期',exact:true}).fill('5')
    await expect(form.getByRole('button',{name:'保存',exact:true})).toBeDisabled()
    await form.getByRole('spinbutton',{name:'第6条MA周期',exact:true}).fill('10000')
    expect((await read()).ma.lines.length,'draft does not autosave').toBe(4)
    const mark=state.responses.length
    await form.getByRole('button',{name:'保存',exact:true}).click()
    await ready(page,state,['ma'],'1d',mark)
    await expect(page.locator('.kline-chart__ma-legend')).toContainText('MA10000:—')
    expect((await read()).ma.lines.length).toBe(6)
    expect((await read()).panels).toEqual(config.panels)
    await page.getByRole('button',{name:'MA 设置',exact:true}).click()
    await form.getByRole('checkbox').nth(0).uncheck()
    await form.getByRole('button',{name:'保存',exact:true}).click()
    await expect(page.locator('.kline-chart__ma-legend').getByText(/^MA5:/)).toHaveCount(0)
    await page.reload();await expect(page.locator('.kline-chart__ma-legend')).toContainText('MA10000:—')
    await page.getByRole('button',{name:'MA 设置',exact:true}).click()
    await form.getByRole('button',{name:'恢复默认',exact:true}).click()
    await form.getByRole('button',{name:'保存',exact:true}).click()
    await expect.poll(async()=>(await read()).ma.lines).toEqual(defaults().ma.lines)
  })
})

test('viewport: pane changes preserve zoom and candles, dragging loads older native history',async()=>{
  const config=defaults();config.panels=['macd','kdj'];await save(config)
  await withPage(async page=>{
    const state=await boot(page,config,'1w')
    const box=await page.locator('.kline-chart__canvas').boundingBox()
    await page.mouse.move(box!.x+box!.width*.6,box!.y+40)
    await page.mouse.wheel(0,-300);await page.waitForTimeout(300)
    const at=async(f:number)=>{
      // Pane value scales can have different widths. Compare the same fraction
      // of the price plot, rather than including its changing right scale.
      const plot=await page.locator('.kline-chart__canvas canvas').evaluateAll(nodes=>{
        const r=nodes.map(c=>c.getBoundingClientRect()).find(r=>r.width>300&&r.height>50)!
        return {x:r.x,y:r.y,width:r.width}
      })
      await page.mouse.move(plot.x+plot.width*f,plot.y+40)
      await expect(page.locator('.kline-chart__hover-data')).toBeVisible()
      return page.locator('.kline-chart__hover-data').innerText()
    }
    const before=[await at(.3),await at(.7)]
    expect(before[0]).not.toBe(before[1])
    const changed=state.responses.length
    await openPicker(page);await panel(page,'kdj').click();await page.locator('.modal__close').click()
    await ready(page,state,['ma','macd'],'1w',changed)
    expect([await at(.3),await at(.7)]).toEqual(before)
    const added=state.responses.length
    await openPicker(page);await panel(page,'rsi').click();await page.locator('.modal__close').click()
    await ready(page,state,['ma','macd','rsi'],'1w',added)
    expect([await at(.3),await at(.7)]).toEqual(before)
    let older=0
    page.on('response',async r=>{const u=new URL(r.url());if(u.pathname==='/api/v1/kline'&&u.searchParams.get('end')&&r.status()===200){const body=await r.json();older+=body.data?.length||0}})
    const mark=state.responses.length
    for(let i=0;i<8&&!older;i++){
      await page.mouse.move(box!.x+50,box!.y+40);await page.mouse.down()
      await page.mouse.move(box!.x+box!.width*.9,box!.y+40,{steps:15});await page.mouse.up()
      await page.waitForTimeout(250)
    }
    await expect.poll(()=>older,{timeout:30_000}).toBeGreaterThan(0)
    await ready(page,state,['ma','macd','rsi'],'1w',mark)
    await expect(page.locator('.kline-chart__body [role=alert]')).toHaveCount(0)
  })
})

test('legacy guest: crop four old panels in catalog order without writing the source preferences',async({browser})=>{
  const context=await browser.newContext({baseURL}),page=await context.newPage()
  const legacy={ma:defaults().ma,panels:['kdj','macd','amount','volume']}
  await context.addInitScript(value=>localStorage.setItem('detail_chart_settings_v1',JSON.stringify(value)),legacy)
  try{
    await page.goto('/market/detail?symbol=300308');await openPicker(page)
    await expect(page.locator('.picker-item.active')).toHaveCount(3)
    for(const key of ['volume','amount','macd'])await expect(panel(page,key)).toHaveClass(/active/)
    await expect(panel(page,'kdj')).toBeDisabled()
    expect(await page.evaluate(()=>JSON.parse(localStorage.getItem('detail_chart_settings_v1')!))).toEqual(legacy)
  }finally{await context.close()}
})

test('stale responses: a delayed old parameter result cannot replace the new period and parameters',async()=>{
  const config=defaults();config.panels=['rsi','std'];await save(config)
  await withPage(async page=>{
    const state=await boot(page,config)
    let held=false,release!:()=>void
    const barrier=new Promise<void>(resolve=>release=resolve)
    await page.route('**/api/v1/indicators?**',async route=>{
      const u=new URL(route.request().url()),params=JSON.parse(u.searchParams.get('params')||'{}')
      if(u.searchParams.get('names')==='rsi'&&u.searchParams.get('period')==='1d'&&params.rsi?.n===7){
        const response=await route.fetch();held=true;await barrier;await route.fulfill({response}).catch(()=>{})
      }else await route.continue()
    })
    try{
      await openPicker(page)
      await page.getByRole('button',{name:'RSI 相对强弱 参数',exact:true}).click()
      await page.getByRole('spinbutton',{name:'RSI 相对强弱 周期',exact:true}).fill('7')
      await page.getByRole('button',{name:'保存参数',exact:true}).click()
      await expect.poll(()=>held).toBe(true)
      await page.locator('.modal__close').click()
      const mark=state.responses.length
      await page.locator('.period-tab').getByText('15min',{exact:true}).click()
      await ready(page,state,['ma','rsi','std'],'15m',mark)
      await openPicker(page)
      await page.getByRole('button',{name:'RSI 相对强弱 参数',exact:true}).click()
      await page.getByRole('spinbutton',{name:'RSI 相对强弱 周期',exact:true}).fill('9')
      const newer=state.responses.length
      await page.getByRole('button',{name:'保存参数',exact:true}).click()
      await page.locator('.modal__close').click()
      await ready(page,state,['ma','rsi','std'],'15m',newer)
      const legend=page.locator('.kline-chart__indicator-legend').filter({hasText:'RSI'})
      await expect(legend).toContainText('(9)')
      const before=await legend.innerText()
      release();await page.waitForTimeout(300)
      expect(await legend.innerText()).toBe(before)
      await expect(page.locator('.period-tab.active')).toHaveText('15min')
    }finally{release()}
  })
})

test('basket UI: choose stocks, validate weights, save and restore only the composite defaults',async()=>{
  const config=defaults();config.panels=['std','macd'];await save(config)
  await withPage(async page=>{
    await boot(page,config);await openPicker(page)
    await panel(page,'zhishu').click()
    const form=page.locator('[aria-label="合成指数设置"]')
    await expect(form).toBeVisible()
    await expect(form.getByRole('button',{name:'保存合成指数',exact:true})).toBeDisabled()
    for(const code of ['600519','300502']){
      await form.getByRole('textbox',{name:'搜索合成指数股票',exact:true}).fill(code)
      await form.getByRole('button',{name:new RegExp(`${code} 添加$`)}).click()
    }
    await form.getByLabel('合成指数权重方式',{exact:true}).selectOption('custom')
    await form.getByLabel('600519 权重',{exact:true}).fill('0')
    await form.getByLabel('300502 权重',{exact:true}).fill('0')
    await expect(form.getByRole('button',{name:'保存合成指数',exact:true})).toBeDisabled()
    await form.getByLabel('600519 权重',{exact:true}).fill('3')
    await form.getByLabel('300502 权重',{exact:true}).fill('1')
    await form.getByLabel('指数基点',{exact:true}).fill('2000')
    await form.getByLabel('指数起算日期',{exact:true}).fill('2025-01-01')
    await form.getByRole('button',{name:'保存合成指数',exact:true}).click()
    await expect.poll(async()=>(await read()).panels).toEqual(['std','macd','zhishu'])
    expect((await read()).panel_options.zhishu.params).toEqual({...indexParams,base:2000})
    await expect(panel(page,'kdj')).toBeDisabled()
    await page.getByRole('button',{name:'恢复 ZHISHU 合成指数 默认',exact:true}).click()
    await expect.poll(async()=>(await read()).panel_options.zhishu.params.weighting).toBe('equal')
    expect((await read()).panels).toEqual(['std','macd','zhishu'])
    expect((await read()).panel_options.zhishu.params.members).toEqual(indexParams.members.map(m=>({...m,weight:1})))
  })
})

test('configuration: all parameter options round-trip without replacing another account or homepage settings',async({browser})=>{
  const config=defaults();config.panels=['std','macd','zhishu'];config.overlays=overlayDefs.map(d=>d.key)
  for(const d of catalog.filter(d=>d.key!=='ma'&&d.key!=='zhishu')){
    const params:any=Object.fromEntries(d.parameters.map(p=>[p.key,p.default]))
    if(d.cross)params.cross=true
    if(d.input_fields)params.field=d.placement==='panel'?'amount':'open'
    config[d.placement==='main'?'overlay_options':'panel_options'][d.key]={params}
  }
  config.panel_options.zhishu={params:indexParams}
  expect(await save(config)).toEqual(config)
  expect(await read()).toEqual(config)
  const other=await newActor(browser,1)
  try{expect((await read(other)).panels).toEqual(['volume','macd'])}finally{await other.context.close()}
  await withPage(async page=>{
    await page.goto('/')
    await expect(page.getByRole('button',{name:'MA 设置',exact:true})).toHaveCount(0)
    await expect(page.locator('.kline-chart__ma-legend').filter({hasText:'MA120:'})).toHaveCount(0)
  })
})

test('performance: warm chart ready time, maximum overlay/three-panel load and repeated toggles',async()=>{
  test.setTimeout(180_000)
  const config=defaults();config.panels=['rsi','kdj','macd'];config.overlays=overlayDefs.map(d=>d.key)
  await save(config)
  const metrics:any[]=[]
  for(let run=0;run<3;run++)await withPage(async page=>{
    await page.addInitScript(()=>{
      ;(window as any).__indicatorLongTasks=[]
      new PerformanceObserver(list=>{for(const e of list.getEntries())(window as any).__indicatorLongTasks.push(e.duration)}).observe({type:'longtask',buffered:true})
    })
    const start=Date.now();await boot(page,config)
    const readyMs=Date.now()-start
    const cdp=await page.context().newCDPSession(page)
    await cdp.send('Performance.enable')
    await cdp.send('HeapProfiler.collectGarbage')
    const before=(await cdp.send('Performance.getMetrics')).metrics
    await openPicker(page)
    const startToggle=Date.now()
    for(let i=0;i<5;i++){
      await panel(page,'rsi').click();await expect.poll(async()=>(await read()).panels.includes('rsi')).toBe(false)
      await panel(page,'rsi').click();await expect.poll(async()=>(await read()).panels.includes('rsi')).toBe(true)
    }
    await page.locator('.modal__close').click()
    await expect.poll(async()=>{
      const text=await page.locator('.overlay-legend, .kline-chart__indicator-legend').allTextContents()
      return text.length===13&&text.every(t=>!t.includes('—')&&!t.includes('获取失败'))
    },{timeout:60_000,message:'all current curves must finish before measuring retained heap'}).toBe(true)
    await expect(page.locator('.kline-chart__body [role=alert]')).toHaveCount(0)
    await cdp.send('HeapProfiler.collectGarbage')
    const after=(await cdp.send('Performance.getMetrics')).metrics
    const heap=(m:any[])=>m.find(x=>x.name==='JSHeapUsedSize')?.value || 0
    metrics.push({run,readyMs,toggleMs:Date.now()-startToggle,heapBefore:heap(before),heapAfter:heap(after),longTasks:await page.evaluate(()=>(window as any).__indicatorLongTasks)})
    expect(readyMs,'maximum overlay chart must settle before API timeout').toBeLessThan(20_000)
    if(heap(before))expect(heap(after),'toggle lifecycle should release obsolete charts').toBeLessThan(heap(before)*2+10_000_000)
  })
  const label=process.env.INDICATOR_PERF_LABEL || 'current'
  writeFileSync(resolve(artifacts,`performance-${label}.json`),JSON.stringify(metrics,null,2))
})
