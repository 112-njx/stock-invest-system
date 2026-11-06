<script setup lang="ts">
/** C 区 · 基本数据面板：最新本地行情与个股基础字段。 */
import { computed, onMounted, ref, watch } from 'vue'
import { fetchLatestQuotes } from '@/api/market'
import { useMarketStore } from '@/stores/market'
import { formatAmount, formatPct, formatPrice, trendClass } from '@/utils/color'

const market = useMarketStore()

const current = computed(() => market.current)
const quote = computed(() =>
  current.value ? market.quotes[current.value.id] ?? null : null
)

/** V0.2：加载错误状态（统一三态） */
const loadError = ref(false)

/** 当前标的基础行情缺失时主动查询 */
async function ensureQuote() {
  if (!current.value || quote.value) return
  loadError.value = false
  try {
    const list = await fetchLatestQuotes([current.value.id])
    market.mergeQuotes(list)
  } catch {
    loadError.value = true
  }
}

/** V0.2：错误重试 */
function retryLoad() {
  ensureQuote()
}

watch(current, () => ensureQuote())
onMounted(ensureQuote)

const fields = computed(() => {
  const s = quote.value
  if (!s) return []
  const isIndex = s.type === 'index'
  const list = [
    { label: '名称', value: s.name, cls: '' },
    { label: '代码', value: s.code, cls: '' },
    { label: '最新收盘价', value: formatPrice(s.price), cls: trendClass(s.change), big: true },
    { label: '涨跌额', value: (s.change ?? 0) > 0 ? `+${s.change?.toFixed(2)}` : s.change?.toFixed(2), cls: trendClass(s.change) },
    { label: '涨跌幅', value: formatPct(s.change_pct), cls: trendClass(s.change_pct) },
    { label: '昨收', value: formatPrice(s.pre_close) },
    { label: '今开', value: formatPrice(s.open) },
    { label: '最高', value: formatPrice(s.high), cls: 't-up' },
    { label: '最低', value: formatPrice(s.low), cls: 't-down' },
    { label: '成交量（股）', value: formatAmount(s.volume) },
  ]
  // 指数通常无成交额、换手率数据，隐藏（bug6）
  if (!isIndex) {
    list.push({ label: '成交额', value: formatAmount(s.amount) })
    list.push({ label: '换手率', value: formatPct(s.turnover) })
  }
  list.push({ label: '振幅', value: formatPct(s.amplitude) })
  // V0.2：数据新鲜度标注（交易时段绿色/延迟黄色/非交易灰色收盘）
  list.push({ label: '数据日期', value: s.data_date ?? '--', cls: '' })
  return list
})

/** 按标的类型渲染特殊字段（本地 extra） */
const specialFields = computed(() => {
  const s = quote.value
  if (!s) return []
  const e = s.extra || {}
  if (s.type === 'stock') {
    return [
      { label: '总市值', value: formatAmount(e.market_cap as number) },
      { label: '流通市值', value: formatAmount(e.float_mv as number) },
      { label: '总股本', value: formatAmount(e.total_share as number) },
      { label: '流通股本', value: formatAmount(e.float_share as number) },
      { label: '市盈率 PE TTM', value: formatPrice(e.pe_ttm as number) },
      { label: '市净率 PB', value: formatPrice(e.pb as number) },
      { label: '量比', value: formatPrice(e.vol_ratio as number) },
      { label: 'ST 状态', value: e.is_st == null ? '--' : e.is_st ? '是' : '否' },
    ]
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
    <div v-else-if="loadError && !quote" class="basic-info__empty basic-info__empty--error">
      <span>数据加载失败</span>
      <button class="basic-info__retry" @click="retryLoad">点击重试</button>
    </div>
    <div v-else-if="!quote" class="basic-info__empty">数据加载中…</div>
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
