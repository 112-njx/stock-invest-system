<script setup lang="ts">
/** C 区 · 基本数据面板：快照通用字段 + 按类型特殊字段（股票 market_cap/pe、ETF premium、指数 pe）。 */
import { computed, onMounted, ref, watch } from 'vue'
import { fetchSnapshot } from '@/api/market'
import { useMarketStore } from '@/stores/market'
import { formatAmount, formatPct, formatPrice, trendClass } from '@/utils/color'
import { getFreshness } from '@/utils/tradingTime'

const market = useMarketStore()

const current = computed(() => market.current)
const snapshot = computed(() =>
  current.value ? market.snapshots[current.value.id] ?? null : null
)

/** V0.2：加载错误状态（统一三态） */
const loadError = ref(false)

/** 当前标的快照缺失时主动拉取一次（后续由轮询刷新） */
async function ensureSnapshot() {
  if (!current.value || snapshot.value) return
  loadError.value = false
  try {
    const list = await fetchSnapshot([current.value.id])
    market.mergeSnapshots(list)
  } catch {
    loadError.value = true
  }
}

/** V0.2：错误重试 */
function retryLoad() {
  ensureSnapshot()
}

watch(current, () => ensureSnapshot())
onMounted(ensureSnapshot)

const fields = computed(() => {
  const s = snapshot.value
  if (!s) return []
  const isIndex = s.type === 'index'
  const list = [
    { label: '名称', value: s.name, cls: '' },
    { label: '代码', value: s.code, cls: '' },
    { label: '现价', value: formatPrice(s.price), cls: trendClass(s.change), big: true },
    { label: '涨跌额', value: (s.change ?? 0) > 0 ? `+${s.change?.toFixed(2)}` : s.change?.toFixed(2), cls: trendClass(s.change) },
    { label: '涨跌幅', value: formatPct(s.change_pct), cls: trendClass(s.change_pct) },
    { label: '昨收', value: formatPrice(s.pre_close) },
    { label: '今开', value: formatPrice(s.open) },
    { label: '最高', value: formatPrice(s.high), cls: 't-up' },
    { label: '最低', value: formatPrice(s.low), cls: 't-down' },
    { label: '成交量', value: formatAmount(s.volume) },
  ]
  // 指数通常无成交额、换手率数据，隐藏（bug6）
  if (!isIndex) {
    list.push({ label: '成交额', value: formatAmount(s.amount) })
    list.push({ label: '换手率', value: formatPct(s.turnover) })
  }
  list.push({ label: '振幅', value: formatPct(s.amplitude) })
  // V0.2：数据新鲜度标注（交易时段绿色/延迟黄色/非交易灰色收盘）
  const fresh = getFreshness(s.updated_at, s.data_age_seconds)
  list.push({ label: '更新时间', value: fresh.label, cls: `fresh-${fresh.level}` })
  return list
})

/** 按标的类型渲染特殊字段（快照 extra） */
const specialFields = computed(() => {
  const s = snapshot.value
  if (!s) return []
  const e = s.extra || {}
  if (s.type === 'stock') {
    return [
      { label: '总市值', value: formatAmount(e.market_cap as number) },
      { label: '市盈率 PE', value: formatPrice(e.pe as number) },
    ]
  }
  if (s.type === 'etf') {
    const items: { label: string; value: string }[] = []
    if (e.nav != null) items.push({ label: '净值', value: formatPrice(e.nav as number) })
    if (e.premium != null) items.push({ label: '溢价率', value: formatPct(e.premium as number) })
    return items
  }
  if (s.type === 'index') {
    return [{ label: '指数PE', value: formatPrice(e.pe as number) }]
  }
  return []
})
</script>

<template>
  <div class="basic-info">
    <header class="basic-info__header">
      <span class="basic-info__title">基本数据</span>
    </header>

    <div v-if="!current" class="basic-info__empty">未选择标的</div>
    <div v-else-if="loadError && !snapshot" class="basic-info__empty basic-info__empty--error">
      <span>数据加载失败</span>
      <button class="basic-info__retry" @click="retryLoad">点击重试</button>
    </div>
    <div v-else-if="!snapshot" class="basic-info__empty">数据加载中…</div>
    <div v-else class="basic-info__grid">
      <template v-for="f in fields" :key="f.label">
        <span class="basic-info__label">{{ f.label }}</span>
        <span class="basic-info__value" :class="[f.cls, { 'is-big': f.big }]">{{ f.value }}</span>
      </template>

      <template v-if="specialFields.length">
        <span class="basic-info__sep" />
        <span class="basic-info__sep" />
        <template v-for="f in specialFields" :key="f.label">
          <span class="basic-info__label">{{ f.label }}</span>
          <span class="basic-info__value">{{ f.value }}</span>
        </template>
      </template>
    </div>
  </div>
</template>

<style scoped>
.basic-info {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
.basic-info__header {
  flex: none;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
}
.basic-info__title {
  font-size: 13px;
  color: var(--text-secondary);
}
.basic-info__empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  font-size: 13px;
  color: var(--text-muted);
  padding: 16px;
}
.basic-info__empty--error { color: var(--up); }
.basic-info__retry {
  padding: 4px 14px;
  font-size: 12px;
  color: var(--accent);
  border: 1px solid var(--accent);
  border-radius: 3px;
  transition: all 0.15s;
}
.basic-info__retry:hover {
  background: var(--accent-soft);
}
/* V0.2：数据新鲜度颜色 */
.fresh-live { color: var(--down); }
.fresh-stale { color: #eab308; }
.fresh-closed { color: var(--text-muted); }
.fresh-unknown { color: var(--text-muted); }
.basic-info__grid {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0;
  padding: 4px 0;
  font-size: 12px;
}
.basic-info__label {
  padding: 5px 8px 5px 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}
.basic-info__value {
  padding: 5px 10px 5px 0;
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.basic-info__value.is-big {
  font-size: 16px;
  font-weight: 600;
}
.basic-info__sep {
  grid-column: 1 / -1;
  height: 6px;
  border-top: 1px dashed var(--border);
}
</style>
