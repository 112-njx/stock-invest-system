<script setup lang="ts">
/**
 * K 线图组件（第一层 A+B 区 / 第二层 F 区共用）。
 * - lightweight-charts v5 多 pane：蜡烛图主图 + 可切换的技术指标 pane（成交量/成交额/MACD/KDJ）
 * - 所有 pane 共享同一 timeScale，K 线缩放时指标自动同步对齐
 * - 周期 Tab：日K/周K/月K/15min
 * - 支撑/压力横线 + 弹窗设置（showSrButton）
 * - 指标选择弹窗（showIndicators），默认开启成交量+MACD，持久化 localStorage
 * - 双击 emit，由父级决定是否进入详情页
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  CandlestickSeries,
  ColorType,
  createChart,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type IPaneApi,
  type IPriceLine,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts'
import {
  addSupportResistance,
  fetchIndicators,
  fetchKLine,
  fetchSupportResistance,
  removeSupportResistance,
  type IndicatorRow,
  type KLineBar,
  type SupportResistanceItem,
} from '@/api/market'
import type { SymbolInfo } from '@/api/market'
import { useMarketStore, type Period } from '@/stores/market'
import { useThemeStore } from '@/stores/theme'
import { trackTiming } from '@/utils/monitor'
import { toast } from '@/utils/toast'
import BaseButton from '@/components/base/BaseButton.vue'

type IndicatorKey = 'volume' | 'amount' | 'macd' | 'kdj'

interface IndicatorMeta {
  key: IndicatorKey
  label: string
  icon: string
}

const INDICATORS: IndicatorMeta[] = [
  { key: 'volume', label: '成交量', icon: '<rect x="1" y="8" width="3" height="7" rx="0.5"/><rect x="6.5" y="4" width="3" height="11" rx="0.5"/><rect x="12" y="1" width="3" height="14" rx="0.5"/>' },
  { key: 'amount', label: '成交额', icon: '<circle cx="8" cy="8" r="6.5"/><text x="8" y="11" text-anchor="middle" font-size="8" font-weight="bold" fill="currentColor" stroke="none">¥</text>' },
  { key: 'macd', label: 'MACD', icon: '<path d="M1 11 L5 5 L9 9 L15 3" fill="none"/><path d="M1 13 L5 9 L9 11 L15 7" fill="none" opacity="0.5"/>' },
  { key: 'kdj', label: 'KDJ', icon: '<path d="M1 10 Q4 4 8 8 T15 6" fill="none"/><path d="M1 12 Q5 7 9 10 T15 9" fill="none" opacity="0.6"/><path d="M1 14 Q6 10 10 12 T15 11" fill="none" opacity="0.35"/>' },
]

const props = withDefaults(
  defineProps<{
    symbol: SymbolInfo | null
    showSrButton?: boolean
    showIndicators?: boolean
  }>(),
  { showSrButton: false, showIndicators: false }
)
const emit = defineEmits<{
  (e: 'dblclick'): void
  (e: 'sr-changed'): void
}>()

const market = useMarketStore()
const theme = useThemeStore()

const container = ref<HTMLDivElement | null>(null)
const loading = ref(false)
const error = ref('')

let chart: IChartApi | null = null
let candleSeries: ISeriesApi<'Candlestick'> | null = null
let srLines: IPriceLine[] = []
let lastBar: KLineBar | null = null

/** 优化4/优化7：最大缩放限制——放大最多显示15条K线，可无限缩小 */
const MAX_VISIBLE_BARS = 15
let lastZoomToast = 0

/**
 * 拦截滚轮事件：在 window capture 阶段（事件传播第一站）监听，
 * 已达最大放大（可见≤15条）时阻止继续放大（deltaY<0=向上滚=放大），
 * 缩小不受限制。window capture 确保先于 chart 内部 wheel 处理器执行。
 */
function onWheel(e: WheelEvent) {
  if (!chart || !container.value?.contains(e.target as Node)) return
  if (e.deltaY >= 0) return // 只拦截放大方向（向上滚 deltaY<0）
  const range = chart.timeScale().getVisibleLogicalRange()
  if (!range) return
  const visibleCount = range.to - range.from + 1
  if (visibleCount <= MAX_VISIBLE_BARS) {
    e.preventDefault()
    e.stopPropagation() // 阻止事件到达 chart 内部元素
    const now = Date.now()
    if (now - lastZoomToast > 60000) { // 1分钟防抖
      lastZoomToast = now
      toast.info('不能再放大了喵!')
    }
  }
}

/** 指标 pane 和 series 引用 */
interface IndicatorPaneRef {
  pane: IPaneApi<any>
  series: ISeriesApi<any>[]
}
const indicatorPanes = new Map<IndicatorKey, IndicatorPaneRef>()

const PERIODS: { label: string; value: Period }[] = [
  { label: '日K', value: '1d' },
  { label: '周K', value: '1w' },
  { label: '月K', value: '1mon' },
  { label: '15min', value: '15m' },
]

const symbolTitle = computed(() =>
  props.symbol ? `${props.symbol.name} ${props.symbol.code}` : '未选择标的'
)

/* ---------- 指标显隐（持久化） ---------- */
const STORAGE_KEY = 'indicator_visibility'
const enabledIndicators = ref<Set<IndicatorKey>>(new Set(['volume', 'macd']))

function loadVisibility() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const arr = JSON.parse(raw) as IndicatorKey[]
      if (Array.isArray(arr) && arr.length) {
        const filtered = arr.filter((k) => INDICATORS.some((i) => i.key === k))
        if (filtered.length) {
          enabledIndicators.value = new Set(filtered)
          return
        }
      }
    }
  } catch { /* ignore */ }
  enabledIndicators.value = new Set(['volume', 'macd'])
}

function saveVisibility() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify([...enabledIndicators.value])) } catch { /* ignore */ }
}

function toggleIndicator(key: IndicatorKey) {
  const next = new Set(enabledIndicators.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  enabledIndicators.value = next
  saveVisibility()
  // 保存当前缩放范围，重建 pane 后恢复，避免切换指标时缩放重置
  const visibleRange = chart?.timeScale().getVisibleLogicalRange()
  rebuildIndicatorPanes()
  setIndicatorData()
  if (visibleRange && chart) {
    // 延迟一帧恢复，确保 series 数据已设置
    requestAnimationFrame(() => {
      chart?.timeScale().setVisibleLogicalRange(visibleRange)
    })
  }
}

const enabledList = computed(() => INDICATORS.filter((i) => enabledIndicators.value.has(i.key)))

/* ---------- 配色 ---------- */
function cssColors() {
  const g = getComputedStyle(document.documentElement)
  const get = (name: string) => g.getPropertyValue(name).trim()
  return {
    bg: get('--bg-panel') || '#111827',
    text: get('--text-secondary') || '#9ca3af',
    grid: get('--border') || '#1f2937',
    up: get('--up') || '#ef4444',
    down: get('--down') || '#22c55e',
    accent: get('--accent') || '#3b82f6',
    indK: get('--ind-k') || '#eab308',
    indD: get('--ind-d') || '#3b82f6',
    indJ: get('--ind-j') || '#a855f7',
    indDif: get('--ind-dif') || '#3b82f6',
    indDea: get('--ind-dea') || '#f59e0b',
  }
}

function toUtcSeconds(ts: string): UTCTimestamp {
  const iso = /(Z|[+-]\d{2}:?\d{2})$/.test(ts) ? ts : `${ts}Z`
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp
}

/* ---------- 图表初始化 ---------- */
function initChart() {
  if (!container.value || chart) return
  const c = cssColors()
  chart = createChart(container.value, {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: c.bg },
      textColor: c.text,
      fontFamily: 'inherit',
      fontSize: 11,
      attributionLogo: false,
    },
    grid: {
      vertLines: { color: c.grid },
      horzLines: { color: c.grid },
    },
    rightPriceScale: { borderColor: c.grid, scaleMargins: { top: 0.06, bottom: 0.06 } },
    timeScale: {
      borderColor: c.grid,
      timeVisible: true,
      secondsVisible: false,
      rightOffset: 4,
      barSpacing: 8,
    },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { color: c.accent, labelBackgroundColor: c.accent },
      horzLine: { color: c.accent, labelBackgroundColor: c.accent },
    },
  })

  candleSeries = chart.addSeries(CandlestickSeries, {
    upColor: c.up,
    downColor: c.down,
    borderUpColor: c.up,
    borderDownColor: c.down,
    wickUpColor: c.up,
    wickDownColor: c.down,
    priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
  })

  // 优化7：window capture 阶段拦截 wheel，达到最大放大（≤15条）时阻止继续放大，可无限缩小
  window.addEventListener('wheel', onWheel, { capture: true, passive: false })

  // 主图 stretch factor 较大
  chart.panes()[0].setStretchFactor(2)

  container.value.addEventListener('dblclick', onDblClick)
}

function applyTheme() {
  if (!chart || !candleSeries) return
  const c = cssColors()
  chart.applyOptions({
    layout: { background: { type: ColorType.Solid, color: c.bg }, textColor: c.text },
    grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
    rightPriceScale: { borderColor: c.grid },
    timeScale: { borderColor: c.grid },
  })
  candleSeries.applyOptions({
    upColor: c.up, downColor: c.down,
    borderUpColor: c.up, borderDownColor: c.down,
    wickUpColor: c.up, wickDownColor: c.down,
  })
  // 重新应用指标 series 配色
  for (const [key, ref] of indicatorPanes) {
    const c2 = cssColors()
    if (key === 'volume' || key === 'amount') {
      // 柱状图颜色在数据中设置，series 本身不需要改
    } else if (key === 'macd') {
      // ref.series: [hist, dif, dea]
      if (ref.series[1]) ref.series[1].applyOptions({ color: c2.indDif })
      if (ref.series[2]) ref.series[2].applyOptions({ color: c2.indDea })
    } else if (key === 'kdj') {
      if (ref.series[0]) ref.series[0].applyOptions({ color: c2.indK })
      if (ref.series[1]) ref.series[1].applyOptions({ color: c2.indD })
      if (ref.series[2]) ref.series[2].applyOptions({ color: c2.indJ })
    }
  }
  redrawSRLines()
}

function onDblClick() {
  emit('dblclick')
}

/* ---------- 指标 pane 管理 ---------- */
function removeAllIndicatorPanes() {
  if (!chart) return
  // 移除所有指标 pane（从后往前，因为移除后索引会变）
  const panes = chart.panes()
  for (let i = panes.length - 1; i >= 1; i--) {
    chart.removePane(i)
  }
  indicatorPanes.clear()
}

function rebuildIndicatorPanes() {
  if (!chart || !props.showIndicators) return
  removeAllIndicatorPanes()
  const c = cssColors()

  for (const meta of enabledList.value) {
    const pane = chart.addPane()
    pane.setStretchFactor(1)
    const series: ISeriesApi<any>[] = []

    if (meta.key === 'volume') {
      const s = pane.addSeries(HistogramSeries, {
        priceFormat: { type: 'volume' },
      })
      series.push(s)
    } else if (meta.key === 'amount') {
      const s = pane.addSeries(HistogramSeries, {
        priceFormat: { type: 'volume' },
      })
      series.push(s)
    } else if (meta.key === 'macd') {
      const hist = pane.addSeries(HistogramSeries, {
        priceFormat: { type: 'price', precision: 3, minMove: 0.001 },
      })
      const dif = pane.addSeries(LineSeries, {
        color: c.indDif, lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
      })
      const dea = pane.addSeries(LineSeries, {
        color: c.indDea, lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
      })
      series.push(hist, dif, dea)
    } else if (meta.key === 'kdj') {
      const k = pane.addSeries(LineSeries, {
        color: c.indK, lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
      })
      const d = pane.addSeries(LineSeries, {
        color: c.indD, lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
      })
      const j = pane.addSeries(LineSeries, {
        color: c.indJ, lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
      })
      series.push(k, d, j)
    }

    indicatorPanes.set(meta.key, { pane, series })
  }

  // 重新设置主图 stretch factor
  chart.panes()[0]?.setStretchFactor(2)
}

/* ---------- 数据 ---------- */
const indicatorRows = ref<IndicatorRow[]>([])

function toCandleData(bars: KLineBar[]) {
  return bars.map((b) => ({
    time: toUtcSeconds(b.ts),
    open: b.open, high: b.high, low: b.low, close: b.close,
  }))
}

function setIndicatorData() {
  if (!indicatorRows.value.length) return
  const c = cssColors()
  const rows = indicatorRows.value

  for (const [key, ref] of indicatorPanes) {
    if (key === 'volume') {
      ref.series[0].setData(rows.map((r) => ({
        time: toUtcSeconds(r.ts),
        value: r.volume,
        color: r.close >= r.open ? c.up : c.down,
      })))
    } else if (key === 'amount') {
      ref.series[0].setData(rows.map((r) => ({
        time: toUtcSeconds(r.ts),
        value: r.amount,
        color: r.close >= r.open ? c.up : c.down,
      })))
    } else if (key === 'macd') {
      ref.series[0].setData(rows.map((r) => ({
        time: toUtcSeconds(r.ts),
        value: r.macd_hist ?? 0,
        color: (r.macd_hist ?? 0) >= 0 ? c.up : c.down,
      })))
      ref.series[1].setData(rows.map((r) => ({ time: toUtcSeconds(r.ts), value: r.macd_dif ?? 0 })))
      ref.series[2].setData(rows.map((r) => ({ time: toUtcSeconds(r.ts), value: r.macd_dea ?? 0 })))
    } else if (key === 'kdj') {
      ref.series[0].setData(rows.map((r) => ({ time: toUtcSeconds(r.ts), value: r.kdj_k ?? 0 })))
      ref.series[1].setData(rows.map((r) => ({ time: toUtcSeconds(r.ts), value: r.kdj_d ?? 0 })))
      ref.series[2].setData(rows.map((r) => ({ time: toUtcSeconds(r.ts), value: r.kdj_j ?? 0 })))
    }
  }
}

async function loadKline() {
  if (!props.symbol) return
  loading.value = true
  error.value = ''
  const t0 = performance.now()
  try {
    const bars = await fetchKLine({ symbol: props.symbol.id, period: market.period })
    if (!chart) initChart()
    candleSeries?.setData(toCandleData(bars))
    lastBar = bars.length ? bars[bars.length - 1] : null

    // K线数据设置后再创建指标 pane，确保 chart 尺寸稳定、pane 可见（修复 bug5）
    if (props.showIndicators) {
      rebuildIndicatorPanes()
    }

    // 加载指标数据
    if (props.showIndicators && enabledList.value.length) {
      try {
        indicatorRows.value = await fetchIndicators({
          symbol: props.symbol.id,
          period: market.period,
          names: 'macd,kdj,volume,amount',
          limit: 500,
        })
        setIndicatorData()
      } catch { /* 指标失败不阻塞K线 */ }
    }

    chart?.timeScale().fitContent()
    trackTiming('kline_load', performance.now() - t0, {
      symbol: props.symbol.code, period: market.period, bars: bars.length,
    })
  } catch {
    error.value = 'K 线加载失败'
  } finally {
    loading.value = false
  }
}

/* ---------- 支撑/压力横线 ---------- */
function clearSRLines() {
  for (const line of srLines) candleSeries?.removePriceLine(line)
  srLines = []
}
function redrawSRLines() {
  if (!candleSeries) return
  const lines = srLines
  srLines = []
  for (const line of lines) {
    const opts = line.options()
    candleSeries.removePriceLine(line)
    srLines.push(candleSeries.createPriceLine(opts))
  }
}
function drawSRLines(list: SupportResistanceItem[]) {
  clearSRLines()
  if (!candleSeries) return
  const c = cssColors()
  for (const sr of list) {
    const line = candleSeries.createPriceLine({
      price: sr.price,
      color: sr.type === 'support' ? c.down : c.up,
      lineWidth: 1, lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: sr.type === 'support' ? '支撑' : '压力',
    })
    srLines.push(line)
  }
}
async function loadSRLines() {
  if (!props.symbol) return
  try {
    const list = await fetchSupportResistance(props.symbol.id)
    drawSRLines(list)
  } catch { /* 静默 */ }
}

defineExpose({
  setSRLines: (list: SupportResistanceItem[]) => drawSRLines(list),
  refreshSRLines: () => loadSRLines(),
})

/* ---------- 实时行情 ---------- */
watch(
  () => (props.symbol ? market.snapshots[props.symbol.id]?.price : undefined),
  (price) => {
    if (price == null || !lastBar || !candleSeries) return
    const next: KLineBar = {
      ...lastBar, close: price,
      high: Math.max(lastBar.high, price),
      low: Math.min(lastBar.low, price),
    }
    candleSeries.update({
      time: toUtcSeconds(next.ts),
      open: next.open, high: next.high, low: next.low, close: next.close,
    })
  }
)

watch(() => props.symbol, () => {
  if (!props.symbol) {
    lastBar = null
    candleSeries?.setData([])
    clearSRLines()
    indicatorRows.value = []
    if (props.showIndicators) removeAllIndicatorPanes()
    return
  }
  loadKline()
  loadSRLines()
})

watch(() => market.period, () => { loadKline() })
watch(() => theme.mode, () => applyTheme())

onMounted(() => {
  loadVisibility()
  if (props.symbol) {
    initChart()
    loadKline()
    loadSRLines()
  }
})

onBeforeUnmount(() => {
  container.value?.removeEventListener('dblclick', onDblClick)
  window.removeEventListener('wheel', onWheel, true)
  closeSrDialog()
  closeIndicatorPicker()
  chart?.remove()
  chart = null
  candleSeries = null
  srLines = []
  indicatorPanes.clear()
})

/* ---------- 支撑/压力位弹窗 ---------- */
const srDialogOpen = ref(false)
const srType = ref<'support' | 'pressure'>('support')
const srPrice = ref('')
const srNote = ref('')
const srList = ref<SupportResistanceItem[]>([])
const srSubmitting = ref(false)

async function openSrDialog() {
  if (!props.symbol) return
  srList.value = []
  srDialogOpen.value = true
  try { srList.value = await fetchSupportResistance(props.symbol.id) } catch { /* 静默 */ }
}
function closeSrDialog() {
  srDialogOpen.value = false
  srPrice.value = ''
  srNote.value = ''
  srSubmitting.value = false
}
async function onAddSr() {
  if (!props.symbol) return
  const price = Number(srPrice.value)
  if (!Number.isFinite(price) || price <= 0) { toast.error('请输入有效价位'); return }
  srSubmitting.value = true
  try {
    const item = await addSupportResistance({
      symbol: props.symbol.id, type: srType.value, price,
      note: srNote.value.trim() || undefined,
    })
    srList.value.push(item)
    srPrice.value = ''
    srNote.value = ''
    drawSRLines(srList.value)
    emit('sr-changed')
    toast.success('已添加' + (srType.value === 'support' ? '支撑位' : '压力位'))
  } catch { /* 错误已 toast */ }
  finally { srSubmitting.value = false }
}
async function onDeleteSr(item: SupportResistanceItem) {
  try {
    await removeSupportResistance(item.id)
    srList.value = srList.value.filter((s) => s.id !== item.id)
    drawSRLines(srList.value)
    emit('sr-changed')
  } catch { /* 错误已 toast */ }
}

/* ---------- 指标选择弹窗 ---------- */
const indicatorPickerOpen = ref(false)
function openIndicatorPicker() { indicatorPickerOpen.value = true }
function closeIndicatorPicker() { indicatorPickerOpen.value = false }
</script>

<template>
  <div class="kline-chart">
    <header class="kline-chart__header">
      <div class="kline-chart__header-left">
        <span class="kline-chart__symbol">{{ symbolTitle }}</span>
        <button v-if="showSrButton" class="sr-btn" title="支撑/压力位设置" @click="openSrDialog">
          <svg class="sr-btn__icon" viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M6 2 L2 8 L6 14" />
            <path d="M10 2 L14 8 L10 14" />
          </svg>
          <span>支撑或压力位</span>
        </button>
      </div>
      <div class="kline-chart__header-right">
        <button v-if="showIndicators" class="gear-btn" title="选择技术指标" @click="openIndicatorPicker">
          <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor">
            <path d="M8 0 9.4 2.1l2.5-.5 1 2.3 2.3 1-.5 2.5L16.7 8l-2 1.6.5 2.5-2.3 1-1 2.3-2.5-.5L8 16l-1.4-2.1-2.5.5-1-2.3-2.3-1 .5-2.5L-.7 8l2-1.6-.5-2.5 2.3-1 1-2.3 2.5.5L8 0zm0 5.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z" />
          </svg>
        </button>
        <div class="kline-chart__tabs" role="tablist">
          <button
            v-for="p in PERIODS"
            :key="p.value"
            class="period-tab"
            :class="{ active: market.period === p.value }"
            @click="market.setPeriod(p.value)"
          >
            {{ p.label }}
          </button>
        </div>
      </div>
    </header>

    <div ref="container" class="kline-chart__body" @dblclick.stop="emit('dblclick')" />

    <div v-if="loading" class="kline-chart__state">加载中…</div>
    <div v-else-if="error" class="kline-chart__state kline-chart__state--error">{{ error }}</div>
    <div v-else-if="!symbol" class="kline-chart__state">请选择标的</div>

    <!-- 支撑/压力位弹窗 -->
    <Teleport to="body">
      <div v-if="srDialogOpen" class="modal-mask" @click.self="closeSrDialog">
        <div class="modal">
          <header class="modal__header">
            <span>支撑/压力位设置</span>
            <button class="modal__close" @click="closeSrDialog">×</button>
          </header>
          <div class="modal__body">
            <div class="modal__symbol">{{ symbol?.name }} <span class="t-muted">{{ symbol?.code }}</span></div>
            <div class="sr-type">
              <button class="sr-type__btn" :class="{ active: srType === 'support' }" @click="srType = 'support'">支撑位</button>
              <button class="sr-type__btn" :class="{ active: srType === 'pressure' }" @click="srType = 'pressure'">压力位</button>
            </div>
            <label class="sr-field">
              <span class="sr-field__label">价位</span>
              <input v-model="srPrice" class="sr-input" type="number" step="0.01" placeholder="请输入股价支撑/压力位" />
            </label>
            <label class="sr-field">
              <span class="sr-field__label">备注</span>
              <input v-model="srNote" class="sr-input" type="text" maxlength="50" placeholder="可选，如：强支撑 / 前高" />
            </label>
            <BaseButton size="sm" block :loading="srSubmitting" @click="onAddSr">添加</BaseButton>
            <div v-if="srList.length" class="sr-list">
              <div class="sr-list__title">已设置</div>
              <div v-for="sr in srList" :key="sr.id" class="sr-item">
                <span class="sr-item__tag" :class="sr.type">{{ sr.type === 'support' ? '支撑' : '压力' }}</span>
                <span class="sr-item__price">{{ sr.price }}</span>
                <span v-if="sr.note" class="sr-item__note">{{ sr.note }}</span>
                <button class="sr-item__del" @click="onDeleteSr(sr)">删除</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 指标选择弹窗 -->
    <Teleport to="body">
      <div v-if="indicatorPickerOpen" class="modal-mask" @click.self="closeIndicatorPicker">
        <div class="modal">
          <header class="modal__header">
            <span>选择技术指标</span>
            <button class="modal__close" @click="closeIndicatorPicker">×</button>
          </header>
          <div class="modal__body">
            <div class="picker-grid">
              <button
                v-for="ind in INDICATORS"
                :key="ind.key"
                class="picker-item"
                :class="{ active: enabledIndicators.has(ind.key) }"
                @click="toggleIndicator(ind.key)"
              >
                <span class="picker-item__icon" v-html="ind.icon" />
                <span class="picker-item__label">{{ ind.label }}</span>
                <span class="picker-item__check">{{ enabledIndicators.has(ind.key) ? '✓' : '' }}</span>
              </button>
            </div>
            <div class="picker-hint">点击切换指标显示，选择自动保存</div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.kline-chart {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  min-height: 0;
  min-width: 0;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
  position: relative;
}
.kline-chart__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex: none;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  z-index: 2;
  background: var(--bg-panel);
}
.kline-chart__header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.kline-chart__header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}
.kline-chart__symbol {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}
.sr-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--bg-panel-2);
  border: 1px solid var(--border-strong);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.sr-btn:hover {
  color: var(--text);
  border-color: var(--accent);
  background: var(--bg-hover);
}
.gear-btn {
  display: inline-flex;
  align-items: center;
  padding: 3px;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 3px;
  transition: all 0.15s;
}
.gear-btn:hover {
  color: var(--text);
  background: var(--bg-hover);
}
.kline-chart__tabs {
  display: flex;
  gap: 2px;
  background: var(--bg-panel-2);
  border-radius: 4px;
  padding: 2px;
}
.period-tab {
  padding: 3px 10px;
  font-size: 12px;
  color: var(--text-secondary);
  border-radius: 3px;
  transition: all 0.15s;
}
.period-tab:hover { color: var(--text); }
.period-tab.active {
  background: var(--bg-active);
  color: var(--text);
  font-weight: 600;
}
.kline-chart__body {
  flex: 1;
  min-height: 0;
  position: relative;
}
.kline-chart__state {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--text-muted);
  background: var(--bg-panel);
  pointer-events: none;
}
.kline-chart__state--error { color: var(--up); }

/* 弹窗 */
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal {
  width: 380px;
  max-width: 90vw;
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  overflow: hidden;
}
.modal__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  font-weight: 600;
}
.modal__close {
  font-size: 18px;
  color: var(--text-muted);
  cursor: pointer;
  line-height: 1;
}
.modal__close:hover { color: var(--text); }
.modal__body {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.modal__symbol {
  font-size: 13px;
  font-weight: 600;
}
.t-muted { color: var(--text-muted); font-weight: 400; }
.sr-type { display: flex; gap: 6px; }
.sr-type__btn {
  flex: 1;
  padding: 5px 0;
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-panel-2);
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}
.sr-type__btn.active {
  color: var(--text);
  border-color: var(--accent);
  background: var(--bg-active);
}
.sr-field { display: flex; flex-direction: column; gap: 4px; }
.sr-field__label { font-size: 11px; color: var(--text-muted); }
.sr-input {
  padding: 6px 8px;
  font-size: 12px;
  color: var(--text);
  background: var(--bg);
  border: 1px solid var(--border-strong);
  border-radius: 4px;
  outline: none;
}
.sr-input:focus { border-color: var(--accent); }
.sr-list {
  margin-top: 4px;
  border-top: 1px solid var(--border);
  padding-top: 8px;
}
.sr-list__title { font-size: 11px; color: var(--text-muted); margin-bottom: 6px; }
.sr-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
}
.sr-item__tag {
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
}
.sr-item__tag.support { color: var(--down); background: color-mix(in srgb, var(--down) 15%, transparent); }
.sr-item__tag.pressure { color: var(--up); background: color-mix(in srgb, var(--up) 15%, transparent); }
.sr-item__price { font-weight: 600; font-variant-numeric: tabular-nums; }
.sr-item__note { flex: 1; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sr-item__del { font-size: 11px; color: var(--text-muted); cursor: pointer; }
.sr-item__del:hover { color: var(--up); }

/* 指标选择 */
.picker-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}
.picker-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 6px;
  background: var(--bg-panel-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  position: relative;
}
.picker-item:hover { border-color: var(--accent); }
.picker-item.active {
  border-color: var(--accent);
  background: var(--bg-active);
}
.picker-item__icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
}
.picker-item.active .picker-item__icon { color: var(--accent); }
.picker-item__icon :deep(svg) { width: 24px; height: 24px; }
.picker-item__label { font-size: 12px; color: var(--text); }
.picker-item__check {
  position: absolute;
  top: 4px;
  right: 6px;
  font-size: 12px;
  color: var(--accent);
  font-weight: 700;
}
.picker-hint {
  margin-top: 10px;
  font-size: 11px;
  color: var(--text-muted);
  text-align: center;
}
</style>
