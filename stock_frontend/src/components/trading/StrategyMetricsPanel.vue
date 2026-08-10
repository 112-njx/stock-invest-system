<script setup lang="ts">
/**
 * 4.5 · 策略指标显示面板（全景 K 线第一层 D 区替换组件）：
 * 展示所选策略的回测指标：胜率/盈亏比/夏普/累计买入/累计卖出/年化收益率/最大回撤。
 * 数据：GET /api/v1/backtest/results?strategy_id=
 */
import { onMounted, ref, watch } from 'vue'
import { fetchBacktestResults, type BacktestResult } from '@/api/ai'

const props = defineProps<{ strategyId: number }>()

const results = ref<BacktestResult[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    results.value = await fetchBacktestResults(props.strategyId)
  } catch {
    results.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.strategyId, () => load())
onMounted(load)

/** 展示最新一条结果 */
function latest(): BacktestResult | null {
  return results.value[0] ?? null
}

function pct(v?: number | null): string {
  if (v == null) return '--'
  const sign = v > 0 ? '+' : ''
  return `${sign}${(v * 100).toFixed(2)}%`
}
function num(v?: number | null): string {
  return v == null ? '--' : v.toFixed(2)
}
</script>

<template>
  <div class="sm-panel">
    <header class="sm-panel__header">
      <span class="sm-panel__title">策略指标</span>
    </header>

    <div v-if="loading" class="sm-panel__empty">加载中…</div>
    <div v-else-if="!latest()" class="sm-panel__empty">暂无回测结果</div>
    <div v-else class="sm-panel__grid">
      <span class="sm-panel__label">策略胜率</span>
      <span class="sm-panel__value">{{ pct(latest()?.win_rate) }}</span>

      <span class="sm-panel__label">盈亏比</span>
      <span class="sm-panel__value">{{ num(latest()?.profit_loss_ratio) }}</span>

      <span class="sm-panel__label">夏普比率</span>
      <span class="sm-panel__value">{{ num(latest()?.sharpe) }}</span>

      <span class="sm-panel__label">累计买入</span>
      <span class="sm-panel__value">{{ latest()?.total_buys ?? '--' }}</span>

      <span class="sm-panel__label">累计卖出</span>
      <span class="sm-panel__value">{{ latest()?.total_sells ?? '--' }}</span>

      <span class="sm-panel__label">年化收益率</span>
      <span class="sm-panel__value" :class="(latest()?.annual_return ?? 0) >= 0 ? 't-up' : 't-down'">
        {{ pct(latest()?.annual_return) }}
      </span>

      <span class="sm-panel__label">最大回撤</span>
      <span class="sm-panel__value t-down">{{ pct(latest()?.max_drawdown) }}</span>
    </div>
  </div>
</template>

<style scoped>
.sm-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
.sm-panel__header {
  flex: none;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
}
.sm-panel__title {
  font-size: 13px;
  color: var(--text-secondary);
}
.sm-panel__empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--text-muted);
  padding: 16px;
}
.sm-panel__grid {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: grid;
  grid-template-columns: auto 1fr;
  align-content: start;
  padding: 4px 0;
  font-size: 12px;
}
.sm-panel__label {
  padding: 6px 8px 6px 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}
.sm-panel__value {
  padding: 6px 10px 6px 0;
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
</style>
