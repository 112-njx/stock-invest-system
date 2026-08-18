<script setup lang="ts">
/**
 * 轻量 SVG 迷你图：line（折线，支持多系列）/ bar（柱状，支持负值零轴）。
 * 用于 B 区技术指标紧凑展示。
 */
import { computed } from 'vue'

export interface LineSeries {
  values: number[]
  color: string
}

const props = withDefaults(
  defineProps<{
    /** 单系列数值（line/bar 通用） */
    values?: number[]
    /** 多折线系列（优先级高于 values，仅 line 模式有效） */
    lines?: LineSeries[]
    /** 线条/柱体颜色；bar 模式可传数组按值分别着色 */
    color?: string | string[]
    type?: 'line' | 'bar'
    height?: number
    /** 最大值上限，缺省取数据绝对值最大值 */
    max?: number
    /** 最小值下限，缺省根据是否有负值自动取 -max 或 0 */
    min?: number
  }>(),
  { color: '#3b82f6', type: 'line', height: 32 }
)

const W = 120

/** 所有参与计算的数值（多折线合并） */
const allValues = computed(() => {
  if (props.lines?.length) return props.lines.flatMap((l) => l.values)
  return props.values || []
})

/** 归一化范围：有负值时零轴居中，无负值时从 0 开始 */
const norm = computed(() => {
  const vals = allValues.value.filter((v) => Number.isFinite(v))
  const absMax = vals.length ? Math.max(...vals.map((v) => Math.abs(v)), 0.0001) : 1
  const hasNeg = vals.some((v) => v < 0)
  const max = props.max ?? absMax
  const min = props.min ?? (hasNeg ? -max : 0)
  return { max, min, range: max - min || 1 }
})

function toPoints(values: number[]) {
  const n = values.length
  if (!n) return ''
  const { min, range } = norm.value
  return values
    .map((v, i) => {
      const x = n === 1 ? W / 2 : (i / (n - 1)) * W
      const y = (1 - (v - min) / range) * (props.height - 2)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}

/** 多折线系列点集 */
const lineSeries = computed(() => {
  if (props.lines?.length) {
    return props.lines.map((l) => ({ points: toPoints(l.values), color: l.color }))
  }
  return [{ points: toPoints(props.values || []), color: props.color as string }]
})

/** 柱状图（支持负值：从零轴向上下延伸） */
const bars = computed(() => {
  const vals = props.values || []
  const n = vals.length
  if (!n) return []
  const { min, range } = norm.value
  const zeroY = (1 - (0 - min) / range) * (props.height - 2)
  const bw = Math.max(W / n - 1, 1)
  return vals.map((v, i) => {
    const bh = Math.max((Math.abs(v) / range) * (props.height - 2), 1)
    return {
      x: (i / n) * W,
      y: v >= 0 ? zeroY - bh : zeroY,
      w: bw,
      h: bh,
      c: Array.isArray(props.color) ? props.color[i % props.color.length] : (props.color as string),
    }
  })
})

/** 零轴位置（有负值时显示） */
const zeroLineY = computed(() => {
  const { min, range } = norm.value
  return (1 - (0 - min) / range) * (props.height - 2)
})
const showZeroLine = computed(() => norm.value.min < 0)
</script>

<template>
  <svg
    class="sparkline"
    :width="W"
    :height="height"
    :viewBox="`0 0 ${W} ${height}`"
    preserveAspectRatio="none"
  >
    <!-- 零轴（负值指标） -->
    <line
      v-if="showZeroLine && type === 'bar'"
      :x1="0"
      :y1="zeroLineY"
      :x2="W"
      :y2="zeroLineY"
      stroke="currentColor"
      stroke-width="0.5"
      opacity="0.3"
    />
    <!-- 折线（支持多系列） -->
    <g v-if="type === 'line'">
      <polyline
        v-for="(s, i) in lineSeries"
        :key="i"
        :points="s.points"
        fill="none"
        :stroke="s.color"
        stroke-width="1.2"
      />
    </g>
    <!-- 柱状 -->
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
