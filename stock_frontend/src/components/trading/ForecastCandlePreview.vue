<script setup lang="ts">
import { computed } from 'vue'
import type { KLineBar } from '@/api/market'

const props = defineProps<{ bars: KLineBar[] }>()
const prices = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 })
const dates = new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', timeZone: 'Asia/Shanghai' })
const chart = computed(() => {
  const bars = [...props.bars].reverse()
  const low = Math.min(...bars.map(bar => bar.low))
  const high = Math.max(...bars.map(bar => bar.high))
  const padding = (high - low || Math.max(1, high * 0.02)) * 0.12
  const top = high + padding
  const bottom = low - padding
  const step = 540 / Math.max(bars.length, 1)
  const y = (price: number) => 18 + (top - price) / (top - bottom) * 174
  return {
    ticks: Array.from({ length: 4 }, (_, index) => {
      const price = top - (top - bottom) * index / 3
      return { y: y(price), label: prices.format(price) }
    }),
    candles: bars.map((bar, index) => ({
      ts: bar.ts,
      x: 18 + step * (index + 0.5),
      width: Math.min(20, step * 0.42),
      high: y(bar.high),
      low: y(bar.low),
      top: y(Math.max(bar.open, bar.close)),
      height: Math.max(1.5, Math.abs(y(bar.open) - y(bar.close))),
      tone: bar.close > bar.open ? 'up' : bar.close < bar.open ? 'down' : 'flat',
      label: dates.format(new Date(bar.ts)),
      close: prices.format(bar.close),
    })),
  }
})
</script>

<template>
  <div class="candle-preview">
    <svg viewBox="0 0 640 215" role="img" aria-label="最近的日 K 线图，详细价格见下方表格">
      <g v-for="tick in chart.ticks" :key="tick.y">
        <line x1="18" x2="558" :y1="tick.y" :y2="tick.y" class="candle-grid" />
        <text x="570" :y="tick.y + 4" class="candle-tick">{{ tick.label }}</text>
      </g>
      <g v-for="candle in chart.candles" :key="candle.ts" :class="`candle-${candle.tone}`">
        <title>{{ candle.label }} 收盘 {{ candle.close }}</title>
        <line :x1="candle.x" :x2="candle.x" :y1="candle.high" :y2="candle.low" />
        <rect :x="candle.x - candle.width / 2" :width="candle.width" :y="candle.top" :height="candle.height" rx="1.5" />
      </g>
    </svg>
    <div class="candle-dates">
      <span>{{ chart.candles[0]?.label }}</span>
      <span>{{ chart.candles.at(-1)?.label }}</span>
    </div>
  </div>
</template>

<style scoped>
.candle-preview { padding: 8px 10px 10px; border: 1px solid var(--forecast-rule); border-radius: 12px; background: var(--forecast-inset); }
svg { display: block; width: 100%; overflow: visible; }
.candle-grid { stroke: var(--forecast-rule); stroke-dasharray: 4 4; vector-effect: non-scaling-stroke; }
.candle-tick { fill: var(--text-secondary); font-size: 13px; font-variant-numeric: tabular-nums; }
.candle-up { color: var(--up); }
.candle-down { color: var(--down); }
.candle-flat { color: var(--flat); }
g line:not(.candle-grid) { stroke: currentColor; vector-effect: non-scaling-stroke; }
rect { fill: currentColor; }
.candle-dates { display: flex; justify-content: space-between; padding-inline: 3% 13%; color: var(--text-secondary); font-size: 12px; font-variant-numeric: tabular-nums; }
</style>
