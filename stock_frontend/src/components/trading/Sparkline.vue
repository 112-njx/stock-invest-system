<script setup lang="ts">
/** 轻量 SVG 迷你图：line（折线）/ bar（柱状），用于 B 区技术指标紧凑展示。 */
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    values: number[]
    /** 线条/柱体颜色；bar 模式可传数组按值分别着色 */
    color?: string | string[]
    type?: 'line' | 'bar'
    height?: number
    /** 最大值上限（如成交额固定上限），缺省取数据最大值 */
    max?: number
  }>(),
  { color: '#3b82f6', type: 'line', height: 32 }
)

const W = 120

const norm = computed(() => {
  const max = props.max ?? Math.max(...props.values.map((v) => Math.abs(v)), 1)
  return { max }
})

const linePoints = computed(() => {
  const n = props.values.length
  if (!n) return ''
  return props.values
    .map((v, i) => {
      const x = n === 1 ? W / 2 : (i / (n - 1)) * W
      const y = (1 - v / norm.value.max) * (props.height - 2)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
})

const bars = computed(() => {
  const n = props.values.length
  return props.values.map((v, i) => {
    const bw = Math.max(W / n - 1, 1)
    const bh = Math.max((Math.abs(v) / norm.value.max) * (props.height - 2), 1)
    return {
      x: (i / n) * W,
      y: props.height - 2 - bh,
      w: bw,
      h: bh,
      c: Array.isArray(props.color) ? props.color[i % props.color.length] : (props.color as string),
    }
  })
})
</script>

<template>
  <svg
    class="sparkline"
    :width="W"
    :height="height"
    :viewBox="`0 0 ${W} ${height}`"
    preserveAspectRatio="none"
  >
    <g v-if="type === 'line'">
      <polyline :points="linePoints" fill="none" :stroke="color as string" stroke-width="1.2" />
    </g>
    <g v-else>
      <rect
        v-for="(b, i) in bars"
        :key="i"
        :x="b.x"
        :y="b.y"
        :width="b.w"
        :height="b.h"
        :fill="b.c"
      />
    </g>
  </svg>
</template>

<style scoped>
.sparkline {
  display: block;
  width: 100%;
  height: auto;
}
</style>
