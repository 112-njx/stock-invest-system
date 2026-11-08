<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { type Member, type StockPerformance, barReturn, percent } from '@/api/stockdb'
import { fetchStockDb, StockDbHttpError } from '@/api/stockdbCache'
import { compact, dateText, metric, numberText } from '@/utils/blueprint'

const props = defineProps<{ stock?: Member; version?: string; refreshKey?: number }>()
const emit = defineEmits<{ stale: [] }>()
const performance = shallowRef<StockPerformance | null>(null)
const loading = ref(false)
const failed = ref(false)
const retry = ref(0)
let requestId = 0
let disposed = false
const changePct = computed(() => props.stock ? barReturn([props.stock.bar], 1) : null)
const change = computed(() => props.stock && props.stock.bar[7] > 0 ? props.stock.bar[4] - props.stock.bar[7] : null)
const fields = computed(() => {
  const s = props.stock
  if (!s) return []
  const previous = s.bar[7] > 0 ? s.bar[7] : null
  return [
    ['开盘价', numberText(s.bar[1])], ['昨收价', numberText(previous)],
    ['最高价', numberText(s.bar[2])], ['最低价', numberText(s.bar[3])],
    ['成交量（股）', compact(metric(s, 'volume'))], ['成交额（元）', compact(metric(s, 'amount'))],
    ['换手率', metric(s, 'turnover') === null ? '—' : numberText(metric(s, 'turnover')) + '%'],
    ['振幅', previous ? numberText((s.bar[2] - s.bar[3]) / previous * 100) + '%' : '—'],
    ['流通市值（元）', compact(metric(s, 'float_mv'))], ['总市值（元）', compact(metric(s, 'total_mv'))],
  ]
})
function fieldColor(label: string) {
  if (['成交量（股）', '成交额（元）', '总市值（元）'].includes(label)) return 'highlight'
  return ''
}
function trend(value: number | null | undefined) { return value == null || value === 0 ? '' : value > 0 ? 'up' : 'down' }
watch(() => [props.stock?.code, props.stock?.bar[0], props.version, props.refreshKey, retry.value] as const, async () => {
  const id = ++requestId
  performance.value = null
  failed.value = false
  if (!props.stock || !props.version) { loading.value = false; return }
  loading.value = true
  try {
    const result = await fetchStockDb<StockPerformance>(`/stocks/${props.stock.code}/performance?${new URLSearchParams({ version: props.version })}`)
    if (!disposed && id === requestId) performance.value = result
  } catch (cause) {
    if (!disposed && id === requestId) {
      failed.value = true
      if (cause instanceof StockDbHttpError && cause.status === 409) emit('stale')
    }
  } finally { if (!disposed && id === requestId) loading.value = false }
}, { immediate: true })
onBeforeUnmount(() => { disposed = true; requestId++ })
</script>

<template>
  <div v-if="stock" class="stock-summary">
    <div class="summary-quote"><strong :class="trend(changePct)">{{ numberText(stock.bar[4]) }}</strong><span :class="trend(changePct)">{{ change === null ? '—' : (change > 0 ? '+' : '') + numberText(change) }}</span><span :class="trend(changePct)">{{ changePct === null ? '—' : percent(changePct) }}</span></div>
    <dl class="summary-fields"><div v-for="[label, value] in fields" :key="label"><dt>{{ label }}</dt><dd :class="fieldColor(label)">{{ value }}</dd></div></dl>
    <section class="performance"><strong>阶段表现</strong><p v-if="loading" role="status">正在读取阶段行情…</p><p v-else-if="failed" role="status">阶段行情暂不可用。<button @click="retry++">重试</button></p><div class="performance-grid"><article v-for="days in [5, 20, 60]" :key="days" :title="`${dateText(performance?.returns[String(days)]?.start_date)} ～ ${dateText(performance?.as_of)}`"><small>近 {{ days }} 日</small><b :class="trend(performance?.returns[String(days)]?.value)">{{ performance?.returns[String(days)]?.value == null ? '—' : percent(performance!.returns[String(days)]!.value!) }}</b></article></div><small>按最近有效交易日收盘价前复权计算；悬停查看起止日期。历史不足显示“—”。</small></section>
    <p class="summary-date">个股数据日期 {{ dateText(stock.bar[0]) }}</p>
  </div>
  <p v-else class="summary-empty">请选择成分股查看行情摘要</p>
</template>

<style scoped>
.stock-summary { padding: 14px; font-size: 12px; }
.summary-title { display: flex; align-items: center; justify-content: space-between; }
small, dt, .summary-date, .performance p, .summary-empty { color: var(--text-secondary); font-size: 11px; }
.summary-quote { display: flex; align-items: baseline; gap: 12px; padding: 15px 0; font-variant-numeric: tabular-nums; }
.summary-quote>strong { font-size: 25px; }
.summary-fields { display: grid; grid-template-columns: 1fr 1fr; margin: 0; gap: 0 18px; }
.summary-fields>div { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; padding: 10px 0; border-bottom: 1px solid var(--border); }
dd { margin: 0; font-variant-numeric: tabular-nums; }
.performance { margin-top: 20px; }
.performance-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 12px 0; }
.performance-grid article { display: grid; gap: 9px; text-align: center; background: var(--bg-panel-2); padding: 12px 4px; border-radius: 5px; }
.summary-date { margin-top: 18px; }.summary-empty { padding: 14px; }
.highlight { color: var(--quote-highlight); }
.up { color: var(--quote-up); }.down { color: var(--quote-down); }
</style>
