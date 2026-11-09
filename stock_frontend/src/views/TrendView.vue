<script setup lang="ts">
import { useMobileLayout } from '@/composables/useMobileLayout'
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { cachedStockDb, fetchStockDb, peekCache, putCache, readCache, StockDbHttpError } from '@/api/stockdbCache'
import type { Bar } from '@/api/stockdb'
import type { TrendCell, TrendColumn, TrendHover, TrendOverview, TrendScreen } from '@/api/trend'
import StockDbChart from '@/components/stockdb/StockDbChart.vue'

const props = defineProps<{ embedded?: boolean; industry?: string }>()
const pageSize = 12
const screen = shallowRef(peekCache<TrendScreen>(props.embedded ? 'trend:screen:' + props.industry : 'trend:last-screen'))
const requested = ref(props.industry ?? screen.value?.overview.industry ?? 'all')
const busy = ref(false)
const message = ref('')
const stage = ref('正在连接本地数据服务')
const hover = shallowRef<TrendHover | null>(null)
const mini = ref<HTMLElement | null>(null)
let disposed = false
let requestId = 0
let hoverId = 0
let hoverTimer: ReturnType<typeof setTimeout> | undefined
let timer: ReturnType<typeof setTimeout> | undefined
let dragging = false

const overview = computed(() => screen.value?.overview)
const start = computed(() => screen.value?.start ?? 0)
const stocks = computed(() => overview.value?.stocks ?? [])
const visible = computed(() => stocks.value.slice(start.value, start.value + pageSize))
const dates = computed(() => overview.value?.dates ?? [])
const selectedIndustry = computed(() => overview.value?.industries.find(item => item.id === overview.value?.industry)?.name ?? '全部')
const maxStart = computed(() => Math.max(0, stocks.value.length - pageSize))
const maxBreadth = computed(() => Math.max(1, ...(overview.value?.breadth ?? []).map(Math.abs)))
const maxWave = computed(() => Math.max(1, ...stocks.value.map(stock => Math.abs(stock.wave))))
const selectionStyle = computed(() => ({
  left: (stocks.value.length ? start.value / stocks.value.length * 100 : 0) + '%',
  width: Math.min(100, Math.max(1, pageSize / Math.max(1, stocks.value.length) * 100)) + '%',
}))
const miniPaths = computed(() => {
  let up = ''
  let down = ''
  stocks.value.forEach((stock, index) => {
    const magnitude = Math.min(25, Math.abs(stock.wave) / maxWave.value * 25)
    const segment = `M${index + .5} 28v${stock.wave >= 0 ? -magnitude : magnitude}`
    if (stock.wave >= 0) up += segment
    else down += segment
  })
  return { up, down }
})

function save(value: TrendScreen) {
  screen.value = value
  putCache('trend:last-screen', value)
  putCache('trend:screen:' + value.overview.industry, value)
}
async function columns(data: TrendOverview, position: number) {
  const codes = data.stocks.slice(position, position + pageSize).map(stock => stock.code)
  if (!codes.length) return {}
  const query = new URLSearchParams({ codes: codes.join(','), version: data.version })
  return (await cachedStockDb<{ columns: Record<string, TrendColumn> }>('/trend/columns?' + query)).columns
}
async function load(industry: string, position = 0, retry = true) {
  const ticket = ++requestId
  requested.value = industry
  busy.value = true
  message.value = ''
  clearHover()
  try {
    const saved = await readCache<TrendScreen>('trend:screen:' + industry)
    if (disposed || ticket !== requestId) return
    if (saved && saved.overview.industry !== overview.value?.industry) screen.value = saved
    const data = await fetchStockDb<TrendOverview>('/trend/overview?' + new URLSearchParams({ industry }))
    const offset = Math.min(position, Math.max(0, data.stocks.length - pageSize))
    const cells = await columns(data, offset)
    if (disposed || ticket !== requestId) return
    save({ overview: data, start: offset, columns: cells })
  } catch (cause) {
    if (disposed || ticket !== requestId) return
    if (cause instanceof StockDbHttpError && cause.status === 409 && retry) {
      void load(industry, position, false)
      return
    }
    message.value = screen.value ? '暂未更新，当前显示上次完整数据。' : (cause as Error).message
    if (!screen.value) {
      try {
        const status = await fetchStockDb<{ stage: string; error: string }>('/trend/status')
        if (!disposed && ticket === requestId) stage.value = status.error || status.stage || message.value
      } catch { stage.value = message.value }
    }
  } finally {
    if (!disposed && ticket === requestId) busy.value = false
  }
}
async function move(position: number) {
  const current = screen.value
  if (!current || (props.embedded && current.overview.industry !== props.industry)) return
  const offset = Math.max(0, Math.min(maxStart.value, Math.round(position)))
  const ticket = ++requestId
  if (offset === current.start) { busy.value = false; return }
  clearHover()
  busy.value = true
  try {
    const cells = await columns(current.overview, offset)
    if (!disposed && ticket === requestId && screen.value?.overview.version === current.overview.version) {
      save({ overview: current.overview, start: offset, columns: cells })
      message.value = ''
    }
  } catch (cause) {
    if (!disposed && ticket === requestId) {
      if (cause instanceof StockDbHttpError && cause.status === 409) void load(requested.value, offset)
      else message.value = '暂时无法切换，保留当前股票。'
    }
  } finally {
    if (!disposed && ticket === requestId) busy.value = false
  }
}
function seek(event: PointerEvent) {
  if (!mini.value || !stocks.value.length) return
  const box = mini.value.getBoundingClientRect()
  void move((event.clientX - box.left) / box.width * stocks.value.length - pageSize / 2)
}
function beginDrag(event: PointerEvent) {
  dragging = true
  mini.value?.setPointerCapture(event.pointerId)
  seek(event)
}
function endDrag(event: PointerEvent) {
  dragging = false
  if (mini.value?.hasPointerCapture(event.pointerId)) mini.value.releasePointerCapture(event.pointerId)
}
function clearHover() {
  clearTimeout(hoverTimer)
  hoverId++
  hover.value = null
}
const mobile = useMobileLayout()

function preview(stock: TrendColumn, cell: TrendCell | null, date: number, event: MouseEvent, tapped = false) {
  clearHover()
  if (!cell || (!tapped && 'pointerType' in event && event.pointerType !== 'mouse')) return
  const ticket = hoverId
  const x = Math.max(8, Math.min(innerWidth - 428, event.clientX - 210))
  const y = Math.max(8, Math.min(innerHeight - 278, event.clientY + 14))
  hoverTimer = setTimeout(async () => {
    try {
      const query = new URLSearchParams({ date: String(date), version: overview.value?.version ?? '' })
      const bars = await cachedStockDb<Bar[]>('/stocks/' + stock.code + '/minutes?' + query, 60000)
      if (!disposed && ticket === hoverId) hover.value = {
        code: stock.code, name: stock.name, date, baseline: cell.preClose, bars, x, y,
      }
    } catch {
      if (!disposed && ticket === hoverId) message.value = '该日期的分时数据暂不可用。'
    }
  }, 220)
}
function tileStyle(cell: TrendCell) {
  if (!cell.wave) return {}
  const intensity = Math.min(1, Math.abs(cell.wave) / 10)
  return {
    background: cell.wave > 0 ? `hsl(356 90% ${94 - intensity * 63}%)` : `hsl(198 92% ${94 - intensity * 63}%)`,
    color: intensity >= .45 ? '#fff' : '#142432',
    '--day-up': intensity >= .45 ? '#ffff65' : '#9c6500',
    '--day-down': intensity >= .45 ? '#60ffd1' : '#0b8667',
  }
}
function breadthStyle(value: number) {
  if (!value) return {}
  const intensity = Math.abs(value) / maxBreadth.value
  return { background: `hsl(${value > 0 ? 356 : 198} 90% ${94 - intensity * 63}%)`, color: intensity > .6 ? '#fff' : '#142432' }
}
function formatDate(date: number) {
  const text = String(date)
  return text.slice(0, 4) + '-' + text.slice(4, 6) + '-' + text.slice(6, 8)
}
function number(value: number | null | undefined, digits = 2) {
  return value === null || value === undefined ? '—' : value.toFixed(digits)
}
function column(code: string) { return screen.value!.columns[code]! }
function industryName(id: string) { return overview.value?.industries.find(item => item.id === id)?.name ?? '未分类' }
function schedule() {
  timer = setTimeout(async () => {
    if (!disposed && !busy.value && document.visibilityState === 'visible') await load(requested.value, start.value)
    if (!disposed) schedule()
  }, screen.value ? 60000 : 3000)
}
async function refresh() {
  if (busy.value) return
  try {
    const result = await fetch('/api/v1/stockdb/trend/refresh', { method: 'POST' })
    if (!result.ok) throw new Error()
    stage.value = '后台更新中'
    message.value = '后台正在核对本地行情，可继续浏览。'
    clearTimeout(timer)
    timer = setTimeout(async () => { await load(requested.value, start.value); schedule() }, 5000)
  } catch { message.value = '暂时无法刷新本地数据。' }
}

onMounted(async () => {
  const ticket = requestId
  const saved = screen.value ?? await readCache<TrendScreen>(props.embedded ? 'trend:screen:' + props.industry : 'trend:last-screen')
  if (disposed) return
  if (ticket === requestId) {
    if (saved) { screen.value = saved; requested.value = saved.overview.industry }
    await load(requested.value, start.value)
  }
  if (!disposed) schedule()
})
watch(() => props.industry, industry => { if (industry) void load(industry) })
onBeforeUnmount(() => {
  disposed = true
  clearTimeout(timer)
  clearHover()
})
</script>

<template>
  <div class="trend-page">
    <aside v-if="!embedded" class="industry-nav">
      <RouterLink to="/stockdb" class="back-link">‹ 指数蓝图</RouterLink>
      <strong class="nav-title">申万一级行业</strong>
      <div class="industry-list">
        <button v-for="item in overview?.industries ?? []" :key="item.id"
          :class="{ active: overview?.industry === item.id }" :aria-pressed="overview?.industry === item.id"
          @click="load(item.id)">
          <span>{{ item.name }}</span><small>{{ item.count }}</small>
        </button>
      </div>
    </aside>
    <section class="trend-main">
      <header class="trend-head">
        <h1>股票大蓝图 · {{ selectedIndustry }}</h1>
        <span>实时两日确认 · 最近 15 个交易日</span>
        <button :disabled="busy" @click="refresh">刷新</button>
      </header>
      <div v-if="!screen" class="initial-state" role="status">
        <strong>正在建立波段追踪数据</strong><p>{{ stage }}</p>
        <small>首次建立完整历史状态，后续优先恢复缓存。</small>
      </div>
      <template v-else>
        <div class="matrix-scroll" @scroll.passive="clearHover">
          <table class="matrix">
            <thead><tr><th class="date-col">日期</th><th class="breadth-col" title="全市场已确认上涨趋势家数减下跌趋势家数，切换行业时保持全市场口径">涨跌指数</th>
              <th v-for="(stock, i) in visible" :key="stock.code" :title="stock.code">
                {{ start + i + 1 }}·{{ stock.name }}
              </th>
            </tr></thead>
            <tbody>
              <tr v-for="(date, i) in dates" :key="date">
                <th class="date-col">{{ formatDate(date) }}</th>
                <td class="breadth-col breadth" :style="breadthStyle(overview!.breadth[i]!)">{{ overview!.breadth[i] }}</td>
                <td v-for="stock in visible" :key="stock.code" class="day-cell"
                  :style="column(stock.code).cells[i] ? tileStyle(column(stock.code).cells[i]!) : {}"
                  @pointerenter="preview(column(stock.code), column(stock.code).cells[i] ?? null, date, $event)"
                  @pointerleave="$event.pointerType === 'mouse' && clearHover()"
                  @click="mobile && preview(column(stock.code), column(stock.code).cells[i] ?? null, date, $event, true)">
                  <template v-if="column(stock.code).cells[i]">
                    <span class="wave" :class="column(stock.code).cells[i]!.change >= 0 ? 'day-up' : 'day-down'">{{ column(stock.code).cells[i]!.wave }}</span>
                    <span class="daily-change">{{ number(column(stock.code).cells[i]!.change) }}</span>
                    <span class="signals"><b v-for="signal in column(stock.code).cells[i]!.signals" :key="signal">{{ signal }}</b></span>
                  </template>
                  <span v-else class="missing">—</span>
                </td>
              </tr>
              <tr class="returns"><th class="date-col">波段涨跌幅%</th>
                <td class="breadth-col" title="当前选中股票池的有效波段涨幅简单平均">avg:{{ number(overview!.average) }}%</td>
                <td v-for="stock in visible" :key="stock.code"
                  :title="`基准日 ${column(stock.code).baseDate ? formatDate(column(stock.code).baseDate!) : '尚未确认'} · 最新行情 ${formatDate(column(stock.code).quoteDate)}`">{{ number(stock.return) }}</td>
              </tr>
              <tr v-for="metric in (['dif', 'dea', 'macd'] as const)" :key="metric" class="metric-row">
                <th class="date-col">{{ metric.toUpperCase() }}</th><td class="breadth-col">—</td>
                <td v-for="stock in visible" :key="stock.code">{{ number(column(stock.code)[metric], 3) }}</td>
              </tr>
              <tr class="metric-row"><th class="date-col">CROSS</th><td class="breadth-col">num:{{ overview!.crossCount }}</td>
                <td v-for="stock in visible" :key="stock.code" :class="{ cross: column(stock.code).cross }">{{ column(stock.code).cross ? '✦' : '×' }}</td>
              </tr>
              <tr class="metric-row"><th class="date-col">板块</th><td class="breadth-col">—</td>
                <td v-for="stock in visible" :key="stock.code">{{ industryName(column(stock.code).industry) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="legend">
          <span><b>B</b> 上涨波段第2日</span><span><b>S</b> 确认转跌首日</span><span><b>V</b> 上涨放量突破前20日</span>
          <span>日涨跌幅% · 波段天数颜色跟随当日涨跌</span>
          <small v-if="busy">后台准备中</small><small v-else role="status">{{ message || '本地数据 · ' + formatDate(dates.at(-1)!) }}</small>
        </div>
        <footer class="navigation">
          <div class="range-label">
            <button aria-label="上一组股票" :disabled="start === 0" @click="move(start - pageSize)">‹</button>
            <span>{{ stocks.length ? start + 1 : 0 }}–{{ Math.min(stocks.length, start + pageSize) }}/{{ stocks.length }}</span>
            <button aria-label="下一组股票" :disabled="start >= maxStart" @click="move(start + pageSize)">›</button>
          </div>
          <div ref="mini" class="mini-map" @pointerdown="beginDrag" @pointermove="dragging && seek($event)"
            @pointerup="endDrag" @pointercancel="endDrag">
            <svg :viewBox="`0 0 ${Math.max(1, stocks.length)} 58`" preserveAspectRatio="none" aria-hidden="true">
              <path :d="miniPaths.up" stroke="#e86b7b" stroke-width=".85" />
              <path :d="miniPaths.down" stroke="#53accd" stroke-width=".85" />
              <line x1="0" :x2="stocks.length" y1="28" y2="28" stroke="var(--border-strong)" />
            </svg>
            <div class="selection" :style="selectionStyle"><span>{{ start + 1 }}</span></div>
          </div>
          <input class="range-input" type="range" min="0" :max="maxStart" :value="start" step="1"
            aria-label="股票范围" @input="move(Number(($event.target as HTMLInputElement).value))" />
          <div class="stock-strip"><span v-for="(stock, i) in visible" :key="stock.code">{{ start + i + 1 }}·{{ stock.name }}</span></div>
        </footer>
      </template>
    </section>
    <div v-if="hover" class="trend-popup" :style="{ left: hover.x + 'px', top: hover.y + 'px' }">
      <header>
        <strong>{{ formatDate(hover.date) }} · {{ hover.name }} · {{ hover.code }}</strong>
        <button class="mobile-only" type="button" @click="clearHover">关闭</button>
      </header>
      <StockDbChart :bars="hover.bars" :label="hover.name + '分时'" minute :baseline="hover.baseline" />
    </div>
  </div>
</template>

<style scoped>
.trend-page { flex: 1; min-height: 0; display: flex; background: var(--bg-panel); color: var(--text); --blueprint-link: var(--accent); --blueprint-up: var(--up); --blueprint-down: var(--down); --blueprint-candle-up: var(--up); --blueprint-candle-down: var(--down); }
.industry-nav { width: 154px; flex: none; display: flex; flex-direction: column; border-right: 1px solid var(--border); min-height: 0; padding: 5px; }
.back-link { padding: 7px; text-decoration: none; color: var(--accent); }
.nav-title { padding: 8px; font-size: 12px; }
.industry-list { overflow: auto; flex: 1; }
.industry-list button { width: 100%; display: flex; align-items: center; justify-content: space-between; padding: 9px; gap: 6px; background: transparent; color: var(--text); border-radius: 4px; font-size: 12px; cursor: pointer; }
.industry-list button:hover, .industry-list button.active { background: var(--accent-soft); color: var(--accent); }
.industry-list small { font-variant-numeric: tabular-nums; color: var(--text-secondary); }
.trend-main { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow: auto; padding: 10px; gap: 12px; }
.trend-head { display: flex; gap: 14px; align-items: center; flex: none; }
h1 { font-size: 18px; margin: 0; }
.trend-head > span { font-size: 12px; color: var(--text-secondary); }
.trend-head button { margin-left: auto; }
button { border: 0; font: inherit; cursor: pointer; color: var(--accent); background: var(--accent-soft); border-radius: 4px; padding: 4px 9px; }
button:disabled { opacity: .5; cursor: default; }
button:focus-visible, a:focus-visible { outline: 2px solid var(--accent); }
.matrix-scroll { overflow: auto; min-height: 0; flex-shrink: 0; }
.matrix { width: 100%; min-width: 1210px; table-layout: fixed; border-spacing: 3px 1px; font-variant-numeric: tabular-nums; }
th, td { text-align: center; height: 30px; padding: 3px 4px; font-size: 12px; font-weight: 400; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
thead th { font-weight: 700; background: var(--bg-panel-2); height: 35px; position: sticky; top: 0; z-index: 2; }
.date-col { width: 88px; color: var(--text-secondary); background: var(--bg-panel); position: sticky; left: 0; z-index: 2; font-size: 11px; }
.breadth-col { width: 94px; position: sticky; left: 91px; z-index: 1; background: var(--bg-panel); }
thead .date-col, thead .breadth-col { z-index: 3; }
.breadth { font-weight: 700; }
.day-cell { position: relative; background: var(--bg-panel-2); cursor: crosshair; }
.wave { position: absolute; left: 4px; top: 50%; transform: translateY(-50%); font-size: 11px; font-weight: 700; }
.day-up { color: var(--day-up, #b38b00); }.day-down { color: var(--day-down, #119e74); }
.daily-change { display: inline-block; padding: 0 9px; }
.signals { position: absolute; right: 2px; top: 50%; transform: translateY(-50%); display: flex; gap: 1px; }
.signals b, .legend b { background: #080d14; color: white; padding: 0 3px; font-size: 10px; line-height: 17px; border-radius: 2px; }
.missing { color: var(--text-muted); }
.returns th { background: var(--bg-panel); }.returns td { background: #111827; color: #fff; font-weight: 700; height: 34px; }
.metric-row td, .metric-row th { color: var(--text-secondary); font-size: 11px; height: 27px; }
.metric-row td.cross { color: var(--up); font-weight: 700; }
.legend { display: flex; flex-wrap: wrap; gap: 8px 16px; color: var(--text-secondary); font-size: 11px; }
.legend small { margin-left: auto; }
.navigation { margin-top: auto; flex: none; }
.range-label { display: flex; gap: 10px; align-items: center; justify-content: flex-end; margin-bottom: 10px; color: var(--text-secondary); font-size: 11px; }
.mini-map { height: 60px; position: relative; border: 1px solid var(--border); background: var(--bg-panel-2); border-radius: 5px; touch-action: none; cursor: ew-resize; }
.mini-map svg { width: 100%; height: 100%; position: absolute; inset: 0; }
.selection { position: absolute; inset-block: 0; border: 2px solid var(--accent); border-radius: 3px; background: var(--accent-soft); pointer-events: none; }
.selection span { position: absolute; left: 50%; transform: translate(-50%, -75%); background: var(--accent); color: white; min-width: 26px; height: 26px; border-radius: 20px; font-size: 11px; display: grid; place-items: center; }
.range-input { width: 100%; height: 10px; accent-color: var(--accent); margin: 4px 0; }
.stock-strip { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 3px; }
.stock-strip span { padding: 4px; text-align: center; color: var(--accent); background: var(--accent-soft); font-size: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.initial-state { margin: auto; text-align: center; color: var(--text-secondary); padding: 30px; }
.initial-state p { margin: 12px; }
.trend-popup { position: fixed; z-index: 50; width: 420px; max-width: calc(100vw - 16px); height: 260px; padding: 9px; display: flex; flex-direction: column; gap: 6px; background: var(--bg-panel); color: var(--text); border: 1px solid var(--border-strong); box-shadow: var(--shadow); border-radius: 6px; pointer-events: none; font-size: 12px; }
@media (max-width: 800px) {
  .industry-nav { width: 115px; }.trend-head { flex-wrap: wrap; }.trend-head > span { display: none; }
}
@media (max-width: 767px), (max-width: 1023px) and (max-height: 500px) and (pointer: coarse) {
  .trend-page { flex-direction: column; }
  .industry-nav { width: auto; }
  .industry-list { display: flex; overflow-x: auto; }
  .industry-list button { width: auto; white-space: nowrap; min-height: var(--touch-target); }
  .trend-main { overflow: visible; }
  .matrix-scroll { max-width: 100%; }
  .trend-popup {
    inset: auto var(--safe-right) var(--safe-bottom) var(--safe-left) !important;
    width: auto; max-width: none; pointer-events: auto;
  }
  .trend-popup header { display: flex; justify-content: space-between; align-items: center; }
  .trend-popup button { min-height: var(--touch-target); }
}
</style>
