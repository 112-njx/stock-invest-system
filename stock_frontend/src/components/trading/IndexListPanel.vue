<script setup lang="ts">
/**
 * G/H 区 · 固定指数列表（可复用，第二层市场页）：
 * - props.list：固定指数（marketStore.fixedIndices 分组后传入，按 sort_order 排序）
 * - 每行：名称/最新价/涨跌幅/关联ETF/机会指标（本版置空）
 * - 行点击 → marketStore.setCurrent 联动 F 区 K 线；实时价取快照缓存随轮询刷新
 */
import { computed } from 'vue'
import type { SymbolInfo } from '@/api/market'
import { useMarketStore } from '@/stores/market'
import { formatPct, formatPrice, trendClass } from '@/utils/color'
import ListRow from '@/components/base/ListRow.vue'

const props = withDefaults(defineProps<{ title: string; list: SymbolInfo[]; loading?: boolean }>(), {
  loading: false,
})

const emit = defineEmits<{ (e: 'dblclick', symbol: SymbolInfo): void }>()

const market = useMarketStore()

const currentId = computed(() => market.current?.id ?? null)

function onSelect(s: SymbolInfo) {
  market.setCurrent(s)
}

/** 双击打开第一层详情页（A/B/C/D 区），由父级决定是否跳转 */
function onDblClick(s: SymbolInfo) {
  emit('dblclick', s)
}
</script>

<template>
  <div class="index-panel">
    <header class="index-panel__header">
      <span class="index-panel__title">{{ title }}</span>
      <span class="index-panel__count">{{ list.length }}</span>
    </header>

    <div class="index-panel__cols">
      <span>名称</span>
      <span class="ta-r">最新价</span>
      <span class="ta-r">涨跌幅</span>
      <span class="ta-c">ETF</span>
      <span class="ta-c">机会</span>
    </div>

    <div class="index-panel__list">
      <div v-if="loading" class="index-panel__skeleton">
        <div v-for="n in 5" :key="n" class="sk-row"><span class="sk-line" /></div>
      </div>
      <div v-else-if="!list.length" class="index-panel__empty">暂无固定指数</div>
      <template v-else>
        <ListRow
          v-for="s in list"
          :key="s.id"
          clickable
          :active="s.id === currentId"
          @click="onSelect(s)"
          @dblclick="onDblClick(s)"
        >
          <span class="idx-name" :title="s.name">{{ s.name }}</span>
          <span class="idx-price ta-r" :class="trendClass(market.snapshots[s.id]?.change_pct)">
            {{ formatPrice(market.snapshots[s.id]?.price) }}
          </span>
          <span class="idx-pct ta-r" :class="trendClass(market.snapshots[s.id]?.change_pct)">
            {{ formatPct(market.snapshots[s.id]?.change_pct) }}
          </span>
          <span class="idx-etf ta-c">{{ s.etf_linked || '--' }}</span>
          <span class="idx-opp ta-c">--</span>
        </ListRow>
      </template>
    </div>
  </div>
</template>

<style scoped>
.index-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
.index-panel__header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
}
.index-panel__title {
  font-size: 13px;
  color: var(--text-secondary);
}
.index-panel__count {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-panel-2);
  padding: 0 6px;
  border-radius: 8px;
}
.index-panel__cols {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
  padding: 4px 10px;
  font-size: 11px;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border);
}
.index-panel__cols > span:nth-child(1) {
  flex: 1;
  min-width: 0;
}
.index-panel__cols > span:nth-child(2) {
  flex: none;
  width: 66px;
}
.index-panel__cols > span:nth-child(3) {
  flex: none;
  width: 60px;
}
.index-panel__cols > span:nth-child(4) {
  flex: none;
  width: 40px;
}
.index-panel__cols > span:nth-child(5) {
  flex: none;
  width: 32px;
}
.index-panel__list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.index-panel__empty {
  padding: 20px 12px;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
}
.idx-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.idx-price {
  flex: none;
  width: 66px;
  font-variant-numeric: tabular-nums;
}
.idx-pct {
  flex: none;
  width: 60px;
  font-variant-numeric: tabular-nums;
}
.idx-etf {
  flex: none;
  width: 40px;
  font-size: 11px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}
.idx-opp {
  flex: none;
  width: 32px;
  font-size: 11px;
  color: var(--text-muted);
}
.ta-r {
  text-align: right;
}
.ta-c {
  text-align: center;
}

/* ---------- 骨架加载态 ---------- */
.index-panel__skeleton {
  padding: 2px 0;
}
.sk-row {
  padding: 7px 10px;
}
.sk-line {
  display: block;
  height: 12px;
  border-radius: 3px;
  background: linear-gradient(90deg, var(--bg-panel-2) 25%, var(--bg-hover) 50%, var(--bg-panel-2) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.2s infinite;
}
@keyframes shimmer {
  to {
    background-position: -200% 0;
  }
}
</style>
