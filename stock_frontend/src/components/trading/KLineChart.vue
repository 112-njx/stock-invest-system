<script setup lang="ts">
/**
 * K 线图组件（第一层 A 区 / 第二层 F 区共用）。
 * - lightweight-charts：蜡烛图（pane 0）+ 成交量副图（pane 1）
 * - 周期 Tab：日K/周K/月K/15min，切换写 marketStore.period 并重拉 K 线
 * - 支撑/压力横线：内部按标的加载，暴露 setSRLines / refreshSRLines 供 B 区调用
 * - 双击 emit，由父级决定是否进入详情页
 * - 实时行情：监听 marketStore.snapshots 更新最后一根 K 线收盘
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  CandlestickSeries,
  ColorType,
  createChart,
  CrosshairMode,
  HistogramSeries,
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts'
import { fetchKLine, fetchSupportResistance, type KLineBar, type SupportResistanceItem } from '@/api/market'
import type { SymbolInfo } from '@/api/market'
import { useMarketStore, type Period } from '@/stores/market'
import { useThemeStore } from '@/stores/theme'

const props = defineProps<{ symbol: SymbolInfo | null }>()
const emit = defineEmits<{ (e: 'dblclick'): void }>()

const market = useMarketStore()
const theme = useThemeStore()

const container = ref<HTMLDivElement | null>(null)
const loading = ref(false)
const error = ref('')

let chart: IChartApi | null = null
let candleSeries: ISeriesApi<'Candlestick'> | null = null
let volumeSeries: ISeriesApi<'Histogram'> | null = null
let srLines: IPriceLine[] = []
/** 最近一根 K 线（原始数据），供实时更新 */
let lastBar: KLineBar | null = null

const PERIODS: { label: string; value: Period }[] = [
  { label: '日K', value: '1d' },
  { label: '周K', value: '1w' },
  { label: '月K', value: '1mon' },
  { label: '15min', value: '15m' },
]

const symbolTitle = computed(() =>
  props.symbol ? `${props.symbol.name} ${props.symbol.code}` : '未选择标的'
)

/** 从 CSS 变量读取图表配色（随主题即时切换） */
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
  }
}

/** 解析后端 UTC ISO（无时区后缀按 UTC 处理）为秒级时间戳 */
function toUtcSeconds(ts: string): UTCTimestamp {
  const iso = /(Z|[+-]\d{2}:?\d{2})$/.test(ts) ? ts : `${ts}Z`
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp
}

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

  // 成交量副图：独立 pane
  volumeSeries = chart.addSeries(
    HistogramSeries,
    { priceFormat: { type: 'volume' }, color: c.accent },
    1
  )
  chart.panes()[1]?.setHeight(90)

  // 双击图表 → 进入详情页（由父级决定）
  container.value.addEventListener('dblclick', onDblClick)
}

/** 应用主题配色（布局/网格/蜡烛/成交量） */
function applyTheme() {
  if (!chart || !candleSeries || !volumeSeries) return
  const c = cssColors()
  chart.applyOptions({
    layout: { background: { type: ColorType.Solid, color: c.bg }, textColor: c.text },
    grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
    rightPriceScale: { borderColor: c.grid },
    timeScale: { borderColor: c.grid },
  })
  candleSeries.applyOptions({
    upColor: c.up,
    downColor: c.down,
    borderUpColor: c.up,
    borderDownColor: c.down,
    wickUpColor: c.up,
    wickDownColor: c.down,
  })
  volumeSeries.applyOptions({ color: c.accent })
  redrawSRLines()
}

function onDblClick() {
  emit('dblclick')
}

function toCandleData(bars: KLineBar[]) {
  return bars.map((b) => ({
    time: toUtcSeconds(b.ts),
    open: b.open,
    high: b.high,
    low: b.low,
    close: b.close,
  }))
}

function toVolumeData(bars: KLineBar[]) {
  const c = cssColors()
  return bars.map((b) => ({
    time: toUtcSeconds(b.ts),
    value: b.volume,
    color: b.close >= b.open ? c.up : c.down,
  }))
}

async function loadKline() {
  if (!props.symbol) return
  loading.value = true
  error.value = ''
  try {
    const bars = await fetchKLine({ symbol: props.symbol.id, period: market.period })
    if (!chart) initChart()
    candleSeries?.setData(toCandleData(bars))
    volumeSeries?.setData(toVolumeData(bars))
    lastBar = bars.length ? bars[bars.length - 1] : null
    chart?.timeScale().fitContent()
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
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
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
  } catch {
    /* 静默：无权限/未登录等不阻塞图表 */
  }
}

defineExpose({
  /** B 区添加后直接替换横线 */
  setSRLines: (list: SupportResistanceItem[]) => drawSRLines(list),
  /** 从后端重拉支撑/压力位（刷新后仍在） */
  refreshSRLines: () => loadSRLines(),
})

/* ---------- 实时行情：监听快照更新最后一根 K 线 ---------- */
watch(
  () => (props.symbol ? market.snapshots[props.symbol.id]?.price : undefined),
  (price) => {
    if (price == null || !lastBar || !candleSeries || !volumeSeries) return
    const next: KLineBar = {
      ...lastBar,
      close: price,
      high: Math.max(lastBar.high, price),
      low: Math.min(lastBar.low, price),
    }
    candleSeries.update({
      time: toUtcSeconds(next.ts),
      open: next.open,
      high: next.high,
      low: next.low,
      close: next.close,
    })
  }
)

watch(
  () => props.symbol,
  () => {
    if (!props.symbol) {
      lastBar = null
      candleSeries?.setData([])
      volumeSeries?.setData([])
      clearSRLines()
      return
    }
    loadKline()
    loadSRLines()
  }
)

watch(
  () => market.period,
  () => {
    loadKline()
  }
)

watch(
  () => theme.mode,
  () => applyTheme()
)

onMounted(() => {
  if (props.symbol) {
    initChart()
    loadKline()
    loadSRLines()
  }
})

onBeforeUnmount(() => {
  container.value?.removeEventListener('dblclick', onDblClick)
  chart?.remove()
  chart = null
  candleSeries = null
  volumeSeries = null
  srLines = []
})
</script>

<template>
  <div class="kline-chart">
    <header class="kline-chart__header">
      <span class="kline-chart__symbol">{{ symbolTitle }}</span>
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
    </header>

    <div ref="container" class="kline-chart__body" @dblclick.stop="emit('dblclick')" />

    <div v-if="loading" class="kline-chart__state">加载中…</div>
    <div v-else-if="error" class="kline-chart__state kline-chart__state--error">{{ error }}</div>
    <div v-else-if="!symbol" class="kline-chart__state">请选择标的</div>
  </div>
</template>

<style scoped>
.kline-chart {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
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
}
.kline-chart__symbol {
  font-size: 13px;
  font-weight: 600;
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
  transition:
    background-color 0.15s,
    color 0.15s;
}
.period-tab:hover {
  color: var(--text);
}
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
.kline-chart__state--error {
  color: var(--up);
}
</style>
