<script setup lang="ts">
/**
 * 4.5 · 策略指标显示面板（全景 K 线第一层 D 区替换组件）。
 * G32（P1-11）扩展：在原 7 个汇总数字之外，同区追加
 * ① 资金曲线面积图（BacktestEquityChart）② 交易明细表（BacktestTradesTable）
 * ③ 「在行情页查看买卖点」入口（跳转 /market/detail?symbol=&strategy_id=）。
 *
 * 数据：GET /api/v1/backtest/results?strategy_id=（列表，不含大字段）
 *       GET /api/v1/backtest/results/{id}（详情，含 equity_curve/trades）
 * 数值口径：一律用后端 G20 修复后的净盈亏/胜率，前端只渲染不重算。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  fetchBacktestResultDetail,
  fetchBacktestResults,
  type BacktestResult,
  type BacktestResultDetail,
} from '@/api/ai'
import BacktestEquityChart from '@/components/trading/BacktestEquityChart.vue'
import BacktestTradesTable from '@/components/trading/BacktestTradesTable.vue'

const props = defineProps<{ strategyId: number }>()

const router = useRouter()
const results = ref<BacktestResult[]>([])
const detail = ref<BacktestResultDetail | null>(null)
const loading = ref(false)
const detailLoading = ref(false)

async function load() {
  loading.value = true
  detail.value = null
  try {
    results.value = await fetchBacktestResults(props.strategyId)
    const latest = results.value[0]
    if (latest) await loadDetail(latest.id)
  } catch {
    results.value = []
  } finally {
    loading.value = false
  }
}

async function loadDetail(resultId: number) {
  detailLoading.value = true
  try {
    detail.value = await fetchBacktestResultDetail(resultId)
  } catch {
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

watch(() => props.strategyId, () => void load())
onMounted(() => void load())

/** 展示最新一条结果 */
function latest(): BacktestResult | null {
  return results.value[0] ?? null
}

const equityPoints = computed(() => detail.value?.equity_curve ?? [])
const trades = computed(() => detail.value?.trades ?? [])
/** 初始资金：曲线首点的现金口径（后端 G20 输出，前端不重算） */
const initialCash = computed(() => equityPoints.value[0]?.cash ?? 0)
/** metrics_json 的 G20 新增字段（平手/期末浮盈），无则为 null */
const draws = computed(() => (latest()?.metrics_json?.draws as number | undefined) ?? null)
const unrealizedPnl = computed(
  () => (latest()?.metrics_json?.unrealized_pnl as number | undefined) ?? null
)

function pct(v?: number | null): string {
  if (v == null) return '--'
  const sign = v > 0 ? '+' : ''
  return `${sign}${(v * 100).toFixed(2)}%`
}
function num(v?: number | null): string {
  return v == null ? '--' : v.toFixed(2)
}

/** G32：跳转行情页查看买卖点（K 线上叠加 B/S 标记） */
function goMarkerDetail() {
  const r = latest()
  if (!r) return
  router.push({
    path: '/market/detail',
    query: { strategy_id: String(props.strategyId), symbol: String(r.symbol_id ?? '') },
  })
}
</script>

<template>
  <div class="sm-panel">
    <header class="sm-panel__header">
      <span class="sm-panel__title">策略指标</span>
      <button
        v-if="latest()"
        class="sm-panel__link"
        title="在行情页 K 线上查看买卖点"
        @click="goMarkerDetail"
      >
        查看买卖点
      </button>
    </header>

    <div v-if="loading" class="sm-panel__empty">加载中…</div>
    <div v-else-if="!latest()" class="sm-panel__empty">暂无回测结果</div>
    <div v-else class="sm-panel__body">
      <div class="sm-panel__grid">
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

        <template v-if="draws != null">
          <span class="sm-panel__label">平手回合</span>
          <span class="sm-panel__value">{{ draws }}</span>
        </template>
        <template v-if="unrealizedPnl != null">
          <span class="sm-panel__label">期末浮盈</span>
          <span class="sm-panel__value" :class="unrealizedPnl >= 0 ? 't-up' : 't-down'">
            {{ unrealizedPnl.toFixed(2) }}
          </span>
        </template>
      </div>

      <!-- G32：资金曲线 -->
      <section class="sm-panel__section">
        <div class="sm-panel__section-head">
          <span>资金曲线</span>
          <span v-if="detailLoading" class="sm-panel__hint">加载中…</span>
          <span v-else-if="equityPoints.length" class="sm-panel__hint">虚线为标的买入持有基准</span>
        </div>
        <div class="sm-panel__chart">
          <BacktestEquityChart :points="equityPoints" :initial-cash="initialCash" />
        </div>
      </section>

      <!-- G32：交易明细 -->
      <section class="sm-panel__section">
        <BacktestTradesTable :trades="trades" max-height="160px" />
      </section>
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
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
}
.sm-panel__title {
  font-size: 13px;
  color: var(--text-secondary);
}
.sm-panel__link {
  margin-left: auto;
  font-size: 11px;
  color: var(--accent);
  cursor: pointer;
}
.sm-panel__link:hover { text-decoration: underline; }
.sm-panel__empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--text-muted);
  padding: 16px;
}
.sm-panel__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}
.sm-panel__grid {
  flex: none;
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
/* G32：资金曲线 / 明细 分区 */
.sm-panel__section {
  flex: none;
  padding: 0 8px 8px;
}
.sm-panel__section-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 2px 4px;
  font-size: 12px;
  color: var(--text-secondary);
}
.sm-panel__hint {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-muted);
}
.sm-panel__chart {
  height: 130px;
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
}
</style>
