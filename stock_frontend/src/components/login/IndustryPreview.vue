<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { heatColor, tiles } from '@/api/heatmap'
import snapshot from './industry-preview.json'

const host = ref<HTMLDivElement>()
const width = ref(420)
const height = ref(200)
const date = String(snapshot.date).replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3')
const percent = (value: number) => (value > 0 ? '+' : '') + value.toFixed(2) + '%'

const groups = computed(() => tiles(snapshot.boards, { x: 0, y: 0, w: width.value, h: height.value }).map(({ item, box }) => {
  const headerHeight = Math.min(21, box.h)
  const nameAndChange = item.name + ' ' + percent(item.change)
  const changeLabelWidth = item.name.length * 10 + percent(item.change).length * 6 + 13
  const countLabelWidth = 32 + (String(item.up).length + String(item.down).length) * 6
  const header = box.w >= changeLabelWidth + countLabelWidth
    ? nameAndChange + '  涨' + item.up + ' 跌' + item.down
    : box.w >= changeLabelWidth ? nameAndChange : item.name
  const stocks = tiles(item.children, {
    x: box.x + 1, y: box.y + headerHeight,
    w: box.w - 2, h: box.h - headerHeight - 1,
  }).map(({ item: stock, box: tile }) => {
    const nameFont = Math.min(15, (tile.w - 4) / stock.name.length, tile.h - 5)
    const font = Math.min(nameFont, (tile.w - 4) / (percent(stock.change).length * .6), (tile.h - 3) / 2.35)
    return { stock, tile, font, nameFont, center: tile.x + tile.w / 2, middle: tile.y + tile.h / 2 }
  })
  return { item, box, header, headerHeight, stocks }
}))

let observer: ResizeObserver | undefined
onMounted(() => {
  if (!host.value) return
  observer = new ResizeObserver(([entry]) => {
    if (!entry) return
    width.value = Math.max(1, entry.contentRect.width)
    height.value = Math.max(1, entry.contentRect.height)
  })
  observer.observe(host.value)
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <figure class="industry-preview">
    <figcaption class="preview-heading">
      <strong>申万一级行业云图</strong><small>{{ date }} 收盘样本</small>
    </figcaption>
    <div ref="host" class="preview-map">
      <svg :viewBox="`0 0 ${width} ${height}`" role="img"
        :aria-label="`${date} 收盘行业云图，包含 ${snapshot.boards.map(board => board.name).join('、')}及代表成分股。红涨绿跌。`">
        <svg v-for="{ item, box, header, headerHeight, stocks } in groups" :key="item.name"
          :x="box.x" :y="box.y" :width="box.w" :height="box.h"
          :viewBox="`${box.x} ${box.y} ${box.w} ${box.h}`" overflow="hidden">
          <title>{{ item.name }} {{ percent(item.change) }}，涨 {{ item.up }}，跌 {{ item.down }}</title>
          <rect :x="box.x + 1" :y="box.y + 1" :width="Math.max(0, box.w - 2)" :height="Math.max(0, headerHeight - 1)"
            :fill="heatColor(item.change)" />
          <text v-if="box.w > 26 && headerHeight >= 16" :x="box.x + 5" :y="box.y + 14" class="board-label">{{ header }}</text>
          <g v-for="{ stock, tile, font, nameFont, center, middle } in stocks" :key="stock.code">
            <title>{{ stock.name }} {{ stock.code }} {{ percent(stock.change) }}</title>
            <rect :x="tile.x" :y="tile.y" :width="Math.max(0, tile.w - .7)" :height="Math.max(0, tile.h - .7)"
              :fill="heatColor(stock.change)" />
            <text v-if="font >= 9" :x="center" :y="middle - font * .2" :font-size="font" text-anchor="middle">
              <tspan :x="center">{{ stock.name }}</tspan>
              <tspan :x="center" :dy="font * 1.12">{{ percent(stock.change) }}</tspan>
            </text>
            <text v-else-if="nameFont >= 9" :x="center" :y="middle" :font-size="nameFont" text-anchor="middle"
              dominant-baseline="central">{{ stock.name }}</text>
          </g>
        </svg>
      </svg>
    </div>
    <div class="preview-caption">
      <span>面积按市值增减额绝对值 · 代表成分股</span>
      <span class="preview-legend"><i class="up" />涨 <i class="down" />跌</span>
    </div>
  </figure>
</template>

<style scoped>
.industry-preview { min-width: 0; overflow: hidden; border: 1px solid var(--border-strong); border-radius: 8px; background: var(--bg-panel-2); }
.preview-heading, .preview-caption { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 4px 8px; padding: 7px 9px; }
.preview-heading strong { font-size: 12px; }
.preview-heading small, .preview-caption { font-size: 11px; color: var(--text-secondary); }
.preview-map { height: clamp(216px, 21vw, 300px); background: #0b1519; }
.preview-map > svg { display: block; width: 100%; height: 100%; }
.preview-map text { fill: #fff; font-weight: 700; paint-order: stroke; stroke: #08121988; stroke-width: 1.6; pointer-events: none; }
.board-label { font-size: 10px; }
.preview-legend { display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
.preview-legend i { width: 8px; height: 8px; border-radius: 2px; background: var(--up); }
.preview-legend .down { background: var(--down); margin-left: 3px; }
</style>
