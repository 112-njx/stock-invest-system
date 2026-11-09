<script setup lang="ts">
import type { ForecastEvidence } from '@/api/forecast'

defineProps<{ items: ForecastEvidence[] }>()

const labels: Record<string, string> = {
  open: '开盘价', high: '最高价', low: '最低价', close: '收盘价', volume: '成交量', amount: '成交额',
  ema20: 'EMA20', atr14: 'ATR14', true_range: '真实波幅', volume_ratio20: '量比',
  body_ratio: '实体比例', upper_wick_ratio: '上影线比例', lower_wick_ratio: '下影线比例',
  close_position: '收盘位置', range_atr_ratio: '波幅 / ATR', overlap_ratio: 'K 线重叠率',
  inside_bar: '内包线', outside_bar: '外包线', breakout20: '20 日突破',
  confirmed_pivots: '已确认高低点', support: '支撑', resistance: '压力', pullback: '回撤',
}
const valueLabels: Record<string, string> = {
  close_up: '收盘向上突破', close_down: '收盘向下突破', wick_up: '上影线越界',
  wick_down: '下影线越界', wick_both: '上下影线均越界', none: '无突破',
}
const numbers = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 4 })

function format(item: ForecastEvidence): string {
  const value = item.value
  if (typeof value === 'number') return numbers.format(value)
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'string') return valueLabels[value] ?? value
  if (Array.isArray(value)) return value.map(pivot =>
    `${pivot.session} ${pivot.kind === 'high' ? '高点' : '低点'} ${numbers.format(pivot.price)}`,
  ).join('、')
  if (item.feature === 'pullback' && value && typeof value === 'object' && 'swing_fraction' in value) {
    return `回撤比例 ${numbers.format(Number(value.swing_fraction) * 100)}%`
  }
  return '—'
}
</script>

<template>
  <ul v-if="items.length" class="forecast-evidence">
    <li v-for="item in items" :key="`${item.session}:${item.feature}`">
      <strong>{{ item.session }} · {{ labels[item.feature] ?? item.feature }} {{ format(item) }}</strong>
    </li>
  </ul>
</template>

<style scoped>
.forecast-evidence { padding-inline-start: 18px; overflow-wrap: anywhere; }
.forecast-evidence li + li { margin-block-start: 8px; }
</style>
