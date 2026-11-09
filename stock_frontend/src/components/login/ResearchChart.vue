<script setup lang="ts">
import { useId } from 'vue'

defineProps<{ mode: 'forecast' | 'backtest' }>()
const fillId = useId()
const closes = [35, 38, 36, 43, 40, 39, 46, 49, 48, 53, 51, 46, 47, 52, 58, 56, 60, 64, 62, 57, 59, 66, 70, 67, 72, 77, 74]
const y = (price: number) => 167 - price * 1.46
const candles = closes.map((close, index) => {
  const open = closes[index - 1] ?? 32
  return {
    x: 18 + index * 13,
    body: y(Math.max(open, close)),
    height: Math.max(2, Math.abs(close - open) * 1.46),
    high: y(Math.max(open, close) + 3 + index % 3),
    low: y(Math.min(open, close) - 3),
    volume: 4 + (index * 11) % 17,
    color: close >= open ? 'var(--up)' : 'var(--down)',
  }
})
const equity = 'M12 139 L36 136 L58 141 L79 125 L101 120 L126 125 L151 110 L177 106 L200 112 L228 91 L252 92 L275 79 L297 80 L320 59 L343 64 L369 43 L396 47 L419 32 L450 35 L478 21'
</script>

<template>
  <svg class="research-chart" viewBox="0 0 500 184" aria-hidden="true">
    <defs>
      <linearGradient :id="fillId" x2="0%" y2="100%">
        <stop stop-color="#6fbbff" stop-opacity=".31" />
        <stop offset="1" stop-color="#6fbbff" stop-opacity="0" />
      </linearGradient>
    </defs>
    <path d="M0 28H500 M0 66H500 M0 104H500 M0 142H500 M0 165H500 M100 0V184 M200 0V184 M300 0V184 M400 0V184"
      stroke="currentColor" opacity=".16" />
    <template v-if="mode === 'backtest'">
      <path :d="equity + ' V184 H12Z'" :fill="'url(#' + fillId + ')'" />
      <path d="M12 146 L90 140 L170 131 L246 128 L329 107 L399 110 L478 91"
        fill="none" stroke="currentColor" opacity=".65" stroke-dasharray="4 5" />
      <path :d="equity" fill="none" stroke="var(--landing-accent)" stroke-width="2" vector-effect="non-scaling-stroke" />
    </template>
    <template v-else>
      <g v-for="bar in candles" :key="bar.x" :fill="bar.color">
        <line :x1="bar.x" :x2="bar.x" :y1="bar.high" :y2="bar.low" :stroke="bar.color" />
        <rect :x="bar.x - 3.5" :y="bar.body" width="7" :height="bar.height" rx="1" />
        <rect :x="bar.x - 3.5" :y="184 - bar.volume" width="7" :height="bar.volume" opacity=".27" />
      </g>
      <path d="M356 59 L389 27 L428 30 L468 12 L493 14 L493 111 L468 101 L428 104 L389 83 Z"
        :fill="'url(#' + fillId + ')'" />
      <path d="M356 0V184 M356 59 L389 55 L428 67 L468 54 L493 58"
        stroke="var(--landing-accent)" stroke-dasharray="4 5" fill="none" />
    </template>
  </svg>
</template>

<style scoped>
.research-chart {
  display: block;
  width: 100%;
  height: auto;
  color: var(--text-secondary);
}
</style>
