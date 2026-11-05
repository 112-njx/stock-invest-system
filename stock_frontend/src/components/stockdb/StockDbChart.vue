<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { percent, type Bar } from '@/api/stockdb'

const props = defineProps<{ bars: Bar[]; label: string; minute?: boolean; baseline?: number; amount?: boolean }>()
const width = 720
const height = 250
const top = 12
const bottom = 177
const volumeBottom = 233
const averages = [[5, '#cda745'], [10, '#9571d1'], [20, '#48c7cf']] as const
const cursor = ref<{ index: number; x: number; y: number } | null>(null)
watch(() => props.bars, () => { cursor.value = null })

const step = computed(() => width / Math.max(1, props.bars.length))
const candleWidth = computed(() => Math.max(1, step.value * 0.73))
const range = computed(() => {
  const min = Math.min(...props.bars.map((bar) => props.minute ? bar[4] : bar[3]))
  const max = Math.max(...props.bars.map((bar) => props.minute ? bar[4] : bar[2]))
  const base = props.baseline
  if (props.minute && base) {
    const spread = Math.max(max - base, base - min, base * 0.005) * 1.08
    return { min: base - spread, max: base + spread }
  }
  const margin = Math.max((max - min) * 0.08, max * 0.001, 0.01)
  return { min: min - margin, max: max + margin }
})
const volumeMax = computed(() => Math.max(1, ...props.bars.map((bar) => bar[5])))
const active = computed(() => cursor.value ? props.bars[cursor.value.index] : undefined)
const ticks = computed(() => Array.from({ length: 6 }, (_, i) => ({
  y: top + i * (bottom - top) / 5,
  value: range.value.max - i * (range.value.max - range.value.min) / 5,
})))
const timeTicks = computed(() => {
  if (props.minute) {
    const labels = ['09:30', '10:30', '11:30', '14:00', '15:00']
    return labels.flatMap((label) => {
      const index = props.bars.findIndex((bar) => dateLabel(bar[0]) === label)
      return index >= 0 ? [{ label, x: x(index) }] : []
    })
  }
  const count = Math.min(props.bars.length, props.amount ? 8 : 7)
  return Array.from({ length: count }, (_, i) => {
    const index = Math.round(i * (props.bars.length - 1) / Math.max(1, count - 1))
    return { label: dateLabel(props.bars[index]![0]).slice(5), x: x(index) }
  })
})

function x(index: number) { return (index + 0.5) * step.value }
function y(value: number) {
  return top + (range.value.max - value) / (range.value.max - range.value.min) * (bottom - top)
}
function dateLabel(date: number) {
  const s = String(date)
  return props.minute ? s.slice(8, 10) + ':' + s.slice(10, 12) : s.slice(0, 4) + '-' + s.slice(4, 6) + '-' + s.slice(6, 8)
}
function shortNumber(value: number) {
  if (value >= 1e8) return (value / 1e8).toFixed(2) + '亿'
  if (value >= 1e4) return (value / 1e4).toFixed(2) + '万'
  return value.toFixed(0)
}
function volumeHeight(bar: Bar) { return bar[5] / volumeMax.value * 42 }
function candleColor(bar: Bar, index: number) {
  return bar[4] >= (props.minute ? (props.bars[index - 1]?.[4] ?? props.baseline ?? bar[1]) : bar[1])
    ? 'var(--blueprint-candle-up)' : 'var(--blueprint-candle-down)'
}
function move(event: PointerEvent) {
  const bounds = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const px = Math.max(0, Math.min(0.9999, (event.clientX - bounds.left) / bounds.width))
  cursor.value = { index: Math.floor(px * props.bars.length), x: px, y: (event.clientY - bounds.top) / bounds.height }
}
const minuteLine = computed(() => props.bars.map((bar, i) => `${x(i)},${y(bar[4])}`).join(' '))
const movingAverages = computed(() => averages.map(([period, color]) => ({
  color,
  points: props.bars.map((_, i) => i + 1 < period ? '' : `${x(i)},${y(
    props.bars.slice(i + 1 - period, i + 1).reduce((sum, bar) => sum + bar[4], 0) / period,
  )}`).filter(Boolean).join(' '),
})))
</script>

<template>
  <div v-if="!bars.length" class="chart-empty">暂无{{ minute ? '分时' : '日 K' }}数据</div>
  <div v-else class="chart" :aria-label="label" role="img" @pointermove="move" @pointerleave="cursor = null">
    <svg :viewBox="`0 0 ${width} ${height}`" preserveAspectRatio="none" aria-hidden="true">
      <path :d="`M0 ${bottom + 9}H${width} M0 ${volumeBottom}H${width}`" stroke="var(--border)" />
      <template v-if="minute">
        <polygon :points="`${x(0)},${bottom} ${minuteLine} ${x(bars.length - 1)},${bottom}`" fill="var(--accent-soft)" />
        <line v-if="baseline" x1="0" :x2="width" :y1="y(baseline)" :y2="y(baseline)"
          stroke="var(--text-secondary)" stroke-dasharray="4 4" />
        <polyline :points="minuteLine" fill="none" stroke="var(--blueprint-link)" vector-effect="non-scaling-stroke" />
      </template>
      <template v-for="(bar, i) in bars" :key="bar[0]">
        <g :fill="candleColor(bar, i)">
          <template v-if="!minute">
            <line :x1="x(i)" :x2="x(i)" :y1="y(bar[2])" :y2="y(bar[3])"
              :stroke="candleColor(bar, i)" vector-effect="non-scaling-stroke" />
            <rect :x="x(i) - candleWidth / 2" :y="y(Math.max(bar[1], bar[4]))" :width="candleWidth"
              :height="Math.max(1, Math.abs(y(bar[1]) - y(bar[4])))" />
          </template>
          <rect :x="x(i) - candleWidth / 2" :y="volumeBottom - volumeHeight(bar)"
            :width="candleWidth" :height="volumeHeight(bar)" opacity=".73" />
        </g>
      </template>
      <polyline v-for="ma in minute ? [] : movingAverages" :key="ma.color" :points="ma.points"
        fill="none" :stroke="ma.color" vector-effect="non-scaling-stroke" />
      <path v-if="cursor" :d="`M${x(cursor.index)} 0V${volumeBottom} M0 ${cursor.y * height}H${width}`"
        fill="none" stroke="var(--text-secondary)" stroke-dasharray="4 4" vector-effect="non-scaling-stroke" />
    </svg>
    <span v-for="tick in ticks" :key="tick.y" class="tick" :style="{ top: tick.y / height * 100 + '%' }">{{ tick.value.toFixed(2) }}</span>
    <template v-if="minute && baseline">
      <span v-for="tick in ticks" :key="'percent' + tick.y" class="tick tick--right"
        :class="tick.value >= baseline ? 'up' : 'down'" :style="{ top: tick.y / height * 100 + '%' }">
        {{ percent((tick.value / baseline - 1) * 100) }}
      </span>
    </template>
    <span class="volume-label">VOL {{ shortNumber(volumeMax) }}</span>
    <span v-for="tick in timeTicks" :key="tick.label" class="time"
      :style="{ left: Math.max(5, Math.min(95, tick.x / width * 100)) + '%' }">{{ tick.label }}</span>
    <template v-if="active && cursor">
      <span class="cursor-date" :style="{ left: Math.max(13, Math.min(87, x(cursor.index) / width * 100)) + '%' }">{{ dateLabel(active[0]) }}</span>
      <dl class="tooltip" :class="{ 'tooltip--left': cursor.x > 0.55 }" :style="{ left: cursor.x * 100 + '%' }">
        <dt>时间</dt><dd>{{ dateLabel(active[0]) }}</dd>
        <template v-if="!minute">
          <dt>开盘</dt><dd>{{ active[1].toFixed(2) }}</dd>
          <dt>最高</dt><dd>{{ active[2].toFixed(2) }}</dd>
          <dt>最低</dt><dd>{{ active[3].toFixed(2) }}</dd>
        </template>
        <dt>{{ minute ? '价格' : '收盘' }}</dt><dd>{{ active[4].toFixed(2) }}</dd>
        <template v-if="active[7]">
          <dt>涨跌</dt><dd :class="active[4] >= active[7] ? 'up' : 'down'">{{ (active[4] - active[7]).toFixed(2) }}</dd>
          <dt>涨幅</dt><dd :class="active[4] >= active[7] ? 'up' : 'down'">{{ percent((active[4] / active[7] - 1) * 100) }}</dd>
        </template>
        <dt>{{ amount ? '成交额' : '成交量' }}</dt><dd>{{ shortNumber(amount ? active[6] : active[5]) }}</dd>
      </dl>
    </template>
  </div>
</template>

<style scoped>
.chart { position: relative; width: 100%; height: 100%; min-height: 110px; background: var(--bg-panel); color: var(--text-secondary); cursor: crosshair; }
.chart-empty { display: grid; place-items: center; min-height: 110px; height: 100%; color: var(--text-secondary); }
svg { position: absolute; width: 100%; height: 100%; inset: 0; }
.tick, .volume-label, .time, .cursor-date { position: absolute; font: 11px/1.1 system-ui, sans-serif; pointer-events: none; }
.tick { left: 3px; transform: translateY(-50%); }
.tick--right { left: auto; right: 3px; }
.volume-label { top: 75%; left: 3px; }
.time, .cursor-date { bottom: 1px; transform: translateX(-50%); white-space: nowrap; }
.cursor-date { background: var(--bg-active); color: var(--text); padding: 2px 4px; border-radius: 2px; }
.tooltip { position: absolute; z-index: 2; top: 5px; display: grid; grid-template-columns: auto auto; gap: 3px 8px; margin: 0 0 0 9px; padding: 7px; background: var(--bg-panel-2); border: 1px solid var(--border-strong); border-radius: 5px; box-shadow: var(--shadow); font-size: 11px; pointer-events: none; white-space: nowrap; }
.tooltip--left { transform: translateX(-100%); margin-left: -9px; }
dd { margin: 0; text-align: right; color: var(--text); }
.up { color: var(--blueprint-up); }
.down { color: var(--blueprint-down); }
</style>
