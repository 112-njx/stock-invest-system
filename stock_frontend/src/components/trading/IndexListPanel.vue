<script setup lang="ts">
/**
 * G/H 区 · 固定指数列表（可复用，第二层市场页）：
 * - props.list：固定指数（marketStore.fixedIndices 分组后传入，按 sort_order 排序）
 * - 每行：名称/最新价/涨跌幅/关联ETF/机会指标（本版置空）
 * - 优化2：表头与数据行统一 grid 布局，数字列间距唯一、整体靠右、居中对齐
 * - 行点击 → marketStore.setCurrent 联动 F 区 K 线；双击打开第一层详情页
 */
import { computed } from 'vue'
import type { SymbolInfo } from '@/api/market'
import { useMarketStore } from '@/stores/market'
import { formatPct, formatPrice, trendClass } from '@/utils/color'

const props = withDefaults(defineProps<{ title: string; list: SymbolInfo[]; loading?: boolean; error?: boolean }>(), {
  loading: false,
  error: false,
})

const emit = defineEmits<{ (e: 'dblclick', symbol: SymbolInfo): void; (e: 'retry'): void }>()

const market = useMarketStore()

const currentId = computed(() => market.current?.id ?? null)

function onSelect(s: SymbolInfo) {
  market.setCurrent(s)
}

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

    <!-- 表头：grid 布局，与数据行列宽完全一致 -->
    <div class="index-panel__cols">
      <span class="col-name">名称</span>
      <span class="col-num">最新价</span>
      <span class="col-num">涨跌幅</span>
      <span class="col-num">ETF</span>
      <span class="col-num">机会</span>
    </div>

    <div class="index-panel__list">
      <div v-if="loading" class="index-panel__skeleton">
        <div v-for="n in 5" :key="n" class="sk-row"><span class="sk-line" /></div>
      </div>
      <div v-else-if="error" class="index-panel__empty index-panel__empty--error">
        <span>加载失败</span>
        <button class="idx-retry" @click="$emit('retry')">重试</button>
      </div>
      <div v-else-if="!list.length" class="index-panel__empty">暂无固定指数</div>
      <template v-else>
        <div
          v-for="s in list"
          :key="s.id"
          class="idx-row"
          :class="{ 'is-active': s.id === currentId }"
          @click="onSelect(s)"
          @dblclick="onDblClick(s)"
        >
          <span class="col-name" :title="s.name">{{ s.name }}</span>
          <span class="col-num" :class="trendClass(market.snapshots[s.id]?.change_pct)">
            {{ formatPrice(market.snapshots[s.id]?.price) }}
          </span>
          <span class="col-num" :class="trendClass(market.snapshots[s.id]?.change_pct)">
            {{ formatPct(market.snapshots[s.id]?.change_pct) }}
          </span>
          <span class="col-num col-etf">{{ s.etf_linked || '--' }}</span>
          <span class="col-num col-opp">--</span>
        </div>
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

/* 优化2：grid 统一列宽，表头与数据行完全对齐；数字列整体靠右，间距唯一 */
.index-panel__cols,
.idx-row {
  display: grid;
  /* 名称自适应，四列数字按内容长度分配固定宽，整体靠右 */
  grid-template-columns: 1fr 62px 58px 48px 36px;
  column-gap: 6px;
  align-items: center;
}
.index-panel__cols {
  flex: none;
  padding: 4px 10px;
  font-size: 11px;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border);
}
.col-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
}
.col-num {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  overflow: hidden;
  text-align: right; /* 数字列统一右对齐，间距唯一 */
}
.col-etf {
  font-size: 11px;
  color: var(--text-muted);
}
.col-opp {
  font-size: 11px;
  color: var(--text-muted);
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
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.index-panel__empty--error { color: var(--up); }
.idx-retry {
  padding: 3px 12px;
  font-size: 11px;
  color: var(--accent);
  border: 1px solid var(--accent);
  border-radius: 3px;
  transition: all 0.15s;
}
.idx-retry:hover {
  background: var(--accent-soft);
}

/* 数据行：替代 ListRow，保持 clickable/active/hover 交互 */
.idx-row {
  padding: 7px 10px;
  font-size: 13px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background-color 0.12s;
}
.idx-row:last-child {
  border-bottom: none;
}
.idx-row:hover {
  background: var(--bg-hover);
}
.idx-row.is-active {
  background: var(--bg-active);
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
