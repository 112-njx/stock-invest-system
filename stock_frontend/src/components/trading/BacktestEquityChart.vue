<script setup lang="ts">
/**
 * G32（P1-11）· 回测资金曲线面积图（lightweight-charts v5）。
 *
 * 数据全部来自后端（G20 口径），前端只渲染、不重算任何绩效指标：
 * - 主面积线：equity_curve.equity（逐 bar 权益，含期末未平仓浮动市值）
 * - 基准横线：初始资金（equity_curve 起点的 cash 口径）
 * - 对比虚线：买入持有基准——把后端已给的 `price` 序列按首点线性归一到初始资金，
 *   属**纯展示归一化**（不是技术指标计算），用于直观看策略是否跑赢标的本身
 *
 * 复用于：全景 K 线 D 区策略指标面板、AI 页 N 区策略详情。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  AreaSeries,
  ColorType,
  createChart,
  CrosshairMode,
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type IPriceLine,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { EquityPoint } from '@/api/ai'
import { useThemeStore } from '@/stores/theme'

const props = withDefaults(
  defineProps<{
    points: EquityPoint[]
    initialCash: number
    /** 是否展示时间轴（面板内嵌时隐藏，省纵向空间） */
    showTimeAxis?: boolean
    /** 是否叠加买入持有基准线 */
    showBenchmark?: boolean
  }>(),
  { showTimeAxis: false, showBenchmark: true }
)

const theme = useThemeStore()
const container = ref<HTMLDivElement | null>(null)

let chart: IChartApi | null = null
let equitySeries: ISeriesApi<'Area'> | null = null
let benchSeries: ISeriesApi<'Line'> | null = null
let cashLine: IPriceLine | null = null

function cssColors() {
  const g = getComputedStyle(document.documentElement)
  const get = (name: string, fallback: string) => g.getPropertyValue(name).trim() || fallback
  return {
    bg: get('--bg-panel', '#111827'),
    text: get('--text-secondary', '#9ca3af'),
    grid: get('--border', '#1f2937'),
    up: get('--up', '#ef4444'),
    down: get('--down', '#22c55e'),
    accent: get('--accent', '#3b82f6'),
    muted: get('--text-muted', '#6b7280'),
  }
}

/** ISO8601 → lightweight-charts UTC 秒（与 KLineChart 的 toUtcSeconds 同口径） */
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
      fontSize: 10,
      attributionLogo: false,
    },
    grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
    rightPriceScale: { borderColor: c.grid, scaleMargins: { top: 0.12, bottom: 0.08 } },
    timeScale: {
      borderColor: c.grid,
      visible: props.showTimeAxis,
      timeVisible: false,
      secondsVisible: false,
    },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { color: c.accent, labelBackgroundColor: c.accent },
      horzLine: { color: c.accent, labelBackgroundColor: c.accent },
    },
    handleScale: false,
    handleScroll: false,
  })

  equitySeries = chart.addSeries(AreaSeries, {
    lineColor: c.accent,
    topColor: `${c.accent}55`,
    bottomColor: `${c.accent}05`,
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: true,
  })

  benchSeries = chart.addSeries(LineSeries, {
    color: c.muted,
    lineWidth: 1,
    lineStyle: LineStyle.Dashed,
    priceLineVisible: false,
    lastValueVisible: false,
  })

  // 初始资金基准横线（涨跌分界）
  cashLine = equitySeries.createPriceLine({
    price: props.initialCash,
    color: c.muted,
    lineWidth: 1,
    lineStyle: LineStyle.Dotted,
    axisLabelVisible: true,
    title: '初始资金',
  })

  setData()
}

function setData() {
  if (!equitySeries || !benchSeries) return
  const pts = props.points
  if (!pts.length) {
    equitySeries.setData([])
    benchSeries.setData([])
    return
  }
  equitySeries.setData(pts.map((p) => ({ time: toUtcSeconds(p.ts), value: p.equity })))

  // 买入持有基准：以后端给的 price 序列首点为基准线性归一到初始资金（纯展示归一化）
  const firstPrice = pts[0].price
  if (props.showBenchmark && firstPrice > 0) {
    benchSeries.setData(
      pts.map((p) => ({ time: toUtcSeconds(p.ts), value: (props.initialCash * p.price) / firstPrice }))
    )
  } else {
    benchSeries.setData([])
  }
  chart?.timeScale().fitContent()
}

function applyTheme() {
  if (!chart || !equitySeries || !benchSeries) return
  const c = cssColors()
  chart.applyOptions({
    layout: { background: { type: ColorType.Solid, color: c.bg }, textColor: c.text },
    grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
    rightPriceScale: { borderColor: c.grid },
    timeScale: { borderColor: c.grid },
  })
  equitySeries.applyOptions({ lineColor: c.accent, topColor: `${c.accent}55`, bottomColor: `${c.accent}05` })
  benchSeries.applyOptions({ color: c.muted })
  if (cashLine) {
    const opts = cashLine.options()
    equitySeries.removePriceLine(cashLine)
    cashLine = equitySeries.createPriceLine({ ...opts, color: c.muted })
  }
}

watch(() => props.points, () => (chart ? setData() : initChart()), { deep: false })
watch(() => props.showBenchmark, () => setData())
watch(() => theme.mode, () => applyTheme())

onMounted(initChart)

onBeforeUnmount(() => {
  chart?.remove()
  chart = null
  equitySeries = null
  benchSeries = null
  cashLine = null
})
</script>

<template>
  <div class="eq">
    <div ref="container" class="eq__canvas" />
    <div v-if="!points.length" class="eq__empty">暂无资金曲线数据</div>
  </div>
</template>

<style scoped>
.eq {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
  background: var(--bg-panel);
  overflow: hidden;
}
.eq__canvas {
  width: 100%;
  height: 100%;
}
.eq__empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-panel);
  pointer-events: none;
}
</style>
