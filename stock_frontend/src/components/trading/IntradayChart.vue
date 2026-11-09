<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { createChart, LineSeries, HistogramSeries, ColorType, LineStyle, type IChartApi, type UTCTimestamp, type Time } from 'lightweight-charts'
import { useThemeStore } from '@/stores/theme'
import { averageSegments } from '@/utils/intradaySegments'
import { fetchStockDb } from '@/api/stockdbCache'
const props=defineProps<{code:string}>()
interface Row {date:number;price:number;volume:number|null;average:number|null}
interface History {rows:Row[];latest:number|null;start:string|null;end:string|null;previous:number|null;baseline_date:number|null}
const theme=useThemeStore(), host=ref<HTMLElement>(), data=ref<History|null>(null)
const busy=ref(false),error=ref(''),hover=ref('')
let chart:IChartApi|undefined, observer:ResizeObserver|undefined,sequence=0
function time(row:Row):UTCTimestamp {
  const s=String(row.date)
  return (Date.UTC(+s.slice(0,4),+s.slice(4,6)-1,+s.slice(6,8),+s.slice(8,10),+s.slice(10,12),+s.slice(12,14))/1000) as UTCTimestamp
}
function label(t:Time){return typeof t==='number'?new Date(t*1000).toISOString().slice(5,16).replace('T',' '):''}
function dispose(){observer?.disconnect();observer=undefined;chart?.remove();chart=undefined}
async function render(){
  await nextTick(); dispose()
  if(!host.value || !data.value?.rows.length)return
  const rows=data.value.rows,light=theme.mode==='light',text=light?'#1f2937':'#e5e7eb',grid=light?'#e4e7ec':'#2d3748'
  const baseline=data.value.previous
  const sessionCounts = new Map<number, number>()
  for (const row of rows) {
    const day = Math.floor(row.date / 1_000_000)
    sessionCounts.set(day, (sessionCounts.get(day) ?? 0) + 1)
  }
  const sessionBars = Math.max(...sessionCounts.values())
  const maxBarSpacing = (width: number) => Math.max(0.05, width / sessionBars)

  let lastFrom = -1
  let lastTo = -1
  let priceRange = { minValue: 0, maxValue: 0 }
  // Both price axes must use the same visible price and average range.
  function autoscaleInfoProvider() {
    const visible = chart?.timeScale().getVisibleLogicalRange()
    if (!visible) return null
    const from = Math.max(0, Math.floor(visible.from))
    const to = Math.min(rows.length - 1, Math.ceil(visible.to))
    if (from > to) return null
    if (from !== lastFrom || to !== lastTo) {
      let min = Infinity
      let max = -Infinity
      for (let index = from; index <= to; index++) {
        const row = rows[index]!
        min = Math.min(min, row.price, row.average ?? row.price)
        max = Math.max(max, row.price, row.average ?? row.price)
      }
      const padding = Math.max((max - min) * 0.06, 0.01)
      priceRange = { minValue: min - padding, maxValue: max + padding }
      lastFrom = from
      lastTo = to
    }
    return { priceRange }
  }
  chart = createChart(host.value, {
    width: host.value.clientWidth,
    height: host.value.clientHeight,
    layout: {
      background: { type: ColorType.Solid, color: light ? '#ffffff' : '#111827' },
      textColor: text,
      fontFamily: getComputedStyle(host.value).fontFamily,
      fontSize: 11,
      attributionLogo: false,
      panes: { enableResize: false, separatorColor: grid, separatorHoverColor: grid },
    },
    grid: { vertLines: { color: grid }, horzLines: { color: grid } },
    leftPriceScale: { visible: true, borderColor: grid },
    rightPriceScale: { visible: !!baseline, borderColor: grid },
    timeScale: {
      fixLeftEdge: true,
      fixRightEdge: true,
      minBarSpacing: 0.05,
      maxBarSpacing: maxBarSpacing(host.value.clientWidth),
      timeVisible: true,
      secondsVisible: false,
      borderColor: grid,
      tickMarkFormatter: label,
    },
    handleScale: {
      axisPressedMouseMove: { time: true, price: false },
      axisDoubleClickReset: { time: true, price: false },
    },
    localization: { timeFormatter: label },
    crosshair: { mode: 0 },
  })
  const price=chart.addSeries(LineSeries,{color:light?'#394150':'#e5e7eb',lineWidth:1,priceScaleId:'left',priceLineVisible:false,autoscaleInfoProvider})
  price.setData(rows.map(r=>({time:time(r),value:r.price})))
  for (const segment of averageSegments(rows)) {
    const average=chart.addSeries(LineSeries,{color:light?'#a88300':'#e5e65b',lineWidth:1,priceScaleId:'left',priceLineVisible:false,lastValueVisible:false,autoscaleInfoProvider,pointMarkersVisible:segment.length===1})
    average.setData(segment.map(r=>({time:time(r),value:r.average!})))
  }
  if(baseline){
    price.createPriceLine({price:baseline,color:light?'#6b7280':'#9ca3af',lineWidth:1,lineStyle:LineStyle.Dashed,axisLabelVisible:true,title:'基准'})
    const percent=chart.addSeries(LineSeries,{color:'transparent',priceScaleId:'right',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false,autoscaleInfoProvider,priceFormat:{type:'custom',formatter:(v:number)=>`${((v/baseline-1)*100).toFixed(2)}%`}})
    percent.setData(rows.map(r=>({time:time(r),value:r.price})))
  }
  const volume=chart.addSeries(HistogramSeries,{priceFormat:{type:'volume'},priceScaleId:'left',lastValueVisible:false,priceLineVisible:false},1)
  volume.setData(rows.map((r,i)=>r.volume==null?{time:time(r)}:{time:time(r),value:r.volume,color:r.price>=(rows[i-1]?.price??r.price)?(light?'#cf202f':'#ff3535'):(light?'#008740':'#00cf4a')}))
  chart.panes()[0]?.setStretchFactor(3);chart.panes()[1]?.setStretchFactor(1)
  const timeScale = chart.timeScale()
  timeScale.subscribeSizeChange(width => {
    if (width > 0) timeScale.applyOptions({ maxBarSpacing: maxBarSpacing(width) })
  })
  timeScale.fitContent()
  const lookup=new Map(rows.map(r=>[time(r),r]))
  chart.subscribeCrosshairMove(p=>{const r=lookup.get(p.time as UTCTimestamp);hover.value=r?`${label(time(r))}  价格 ${r.price.toFixed(2)}  均价 ${r.average?.toFixed(2)??'暂无数据'}  成交量 ${r.volume?.toLocaleString()??'暂无数据'} 股`:''})
  observer=new ResizeObserver(()=>{if(host.value)chart?.resize(host.value.clientWidth,host.value.clientHeight)});observer.observe(host.value)
}
async function load(){
  const id=++sequence;busy.value=true;error.value='';hover.value=''
  dispose();data.value=null
  try{
    const result=await fetchStockDb<History>(`/stocks/${props.code}/minutes/history`)
    if(id!==sequence)return
    data.value=result
    busy.value=false;await render()
  }catch(e){if(id===sequence)error.value=e instanceof Error?e.message:'读取分时数据失败'}
  finally{if(id===sequence)busy.value=false}
}
watch(()=>props.code,load,{immediate:true})
watch(()=>theme.mode,render)
onBeforeUnmount(()=>{sequence++;dispose()})
</script>
<template>
<section class="intraday-main">
  <header class="chart-toolbar">
    <strong>分时图</strong>
    <button type="button" :disabled="!data?.rows.length" @click="chart?.timeScale().fitContent()">适应全图</button>
    <span v-if="hover" class="chart-info">{{ hover }}</span>
    <span v-else class="chart-info">
      价格线 · 黄色为每日成交均价 · 下方成交量（股）<template v-if="data?.previous"> · 涨跌幅基准 {{ data.previous.toFixed(2) }}（{{ data.baseline_date }} 昨收）</template>
    </span>
  </header>
  <p v-if="busy">正在读取分时数据…</p><p v-else-if="error" role="alert">{{ error }}</p><p v-else-if="!data?.rows.length">近一个月暂无分时数据</p>
  <div v-show="!busy&&!error&&data?.rows.length" ref="host" class="chart-host" aria-label="多日分时价格、每日均价及成交量" />
</section>
</template>
<style scoped>
.intraday-main { flex: 1; min-height: 0; min-width: 0; display: flex; flex-direction: column; background: var(--bg-panel); border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.chart-toolbar { display: flex; align-items: center; gap: 8px; padding: 6px 8px; font-size: 12px; min-width: 0; }
.chart-toolbar strong, .chart-toolbar button { flex: none; }
.chart-toolbar button { font: inherit; color: var(--text); background: var(--bg-panel); border: 1px solid var(--border-strong); border-radius: 3px; padding: 4px; cursor: pointer; }
.chart-toolbar button:disabled { opacity: .5; }
.chart-info { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-secondary); font-size: 11px; }
.chart-host { flex: 1; min-height: 180px; min-width: 0; }
p { margin: auto; color: var(--text-secondary); font-size: 13px; }
</style>
