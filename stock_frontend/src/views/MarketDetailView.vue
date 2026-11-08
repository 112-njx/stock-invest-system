<script setup lang="ts">
/**
 * 行情页 · 第一层（A+B/C/D 区）：
 * - A+B 区：KLineChart（蜡烛图主图 + 技术指标多 pane，共享时间轴同步缩放）
 * - C 区：基本数据（BasicInfoPanel）
 * - D 区：最新分时行情及成交量 / 回测策略指标（StrategyMetricsPanel）
 * - 交互：Esc / 左上角按钮退出返回 /market；轮询刷新实时行情
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { searchSymbols, fetchSymbols } from '@/api/market'
import {
  fetchBacktestResultDetail,
  fetchBacktestResults,
  fetchBacktestTask,
  type BacktestTrade,
} from '@/api/ai'
import { useMarketStore, type Period } from '@/stores/market'
import { useWsStore } from '@/stores/wsStore'
import { ensureDefaultSymbol } from '@/composables/useDefaultSymbol'
import { useLatestQuotes } from '@/composables/useLatestQuotes'
import StockFlowPanel from '@/components/trading/StockFlowPanel.vue'
import KLineChart from '@/components/trading/KLineChart.vue'
import BasicInfoPanel from '@/components/trading/BasicInfoPanel.vue'
import StockMinutePanel from '@/components/trading/StockMinutePanel.vue'
import StrategyMetricsPanel from '@/components/trading/StrategyMetricsPanel.vue'

const router = useRouter()
const route = useRoute()
const market = useMarketStore()
const ws = useWsStore()
const chartView = ref<'quotes'|'flows'>('quotes')

/** 回测显示跳转：带 strategy_id 时 D 区替换为策略指标面板（4.5） */
const strategyId = computed(() => (route.query.strategy_id ? Number(route.query.strategy_id) : null))

const { start } = useLatestQuotes()

/* ---------- G32：回测买卖点标注 ---------- */
/** 最新一条回测结果的买卖流水（后端已算好，前端只渲染） */
const btTrades = ref<BacktestTrade[]>([])
/** 买卖点所属 symbol_id：切换标的后不再叠加（避免张冠李戴） */
const btSymbolId = ref<number | null>(null)
/** 无法标注时的提示文案 */
const markerNote = ref('')

const PERIODS: Period[] = ['15m', '1d', '1w', '1mon']

/**
 * 拉取最新回测结果的买卖流水用于 K 线标注。
 * 周期对齐：回测周期与行情页周期不同则切换，否则时间轴对不上、买卖点会错位。
 */
async function loadBacktestMarkers() {
  if (!strategyId.value) {
    btTrades.value = []
    btSymbolId.value = null
    markerNote.value = ''
    return
  }
  try {
    const list = await fetchBacktestResults(strategyId.value)
    const latest = list[0]
    if (!latest) {
      btTrades.value = []
      markerNote.value = '该策略暂无回测结果'
      return
    }
    if (latest.task_id) {
      const task = await fetchBacktestTask(latest.task_id)
      if (task.period && PERIODS.includes(task.period as Period) && task.period !== market.period) {
        market.setPeriod(task.period as Period)
      }
    }
    const detail = await fetchBacktestResultDetail(latest.id)
    btSymbolId.value = detail.symbol_id ?? null
    btTrades.value = detail.trades ?? []
    markerNote.value = btTrades.value.length
      ? ''
      : '该回测结果无买卖流水（升级前生成，或策略未产生交易）'
  } catch {
    btTrades.value = []
    markerNote.value = '买卖点加载失败'
  }
}

/** 仅当 K 线标的与回测标的相同时叠加买卖点 */
const visibleMarkers = computed(() =>
  btSymbolId.value != null && market.current?.id === btSymbolId.value ? btTrades.value : []
)

watch(strategyId, () => void loadBacktestMarkers())

function goBack() {
  router.push('/')
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') goBack()
}

/**
 * 双向标的联动：AI 页「回测显示」跳转时携带 ?symbol=code，
 * 若与当前标的不同则解析并切换，保证 K 线区展示的策略回测标的一致。
 */
async function resolveSymbolParam() {
  const q = route.query.symbol
  if (q == null) return
  const kw = String(q)
  const stockOnly = route.query.asset_type === 'stock'
  if (market.current && (!stockOnly || market.current.type === 'stock') && (String(market.current.code) === kw || String(market.current.id) === kw)) return
  try {
    const list = stockOnly ? await fetchSymbols({ search: kw }) : await searchSymbols(kw)
    const found = list.find((s) => (!stockOnly || s.type === 'stock') && (s.code === kw || String(s.id) === kw))
    if (found) market.setCurrent(found)
  } catch {
    /* 解析失败保持当前标的，不阻塞页面 */
  }
}

onMounted(async () => {
  window.addEventListener('keydown', onKeydown)
  await ensureDefaultSymbol()
  await resolveSymbolParam()
  // G32：解析完标的后再拉买卖点，保证 btSymbolId 与 market.current 可比对
  await loadBacktestMarkers()
  // V0.2：初始化 WS 实时行情（直接刷新/直达详情页时保证连接）
  ws.init()
  ws.syncSubscriptions()
  start()
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="detail">
    <div class="detail-topbar">
      <button class="detail-back" @click="goBack">← 返回</button>
      <span class="detail-hint">按 Esc 返回行情页</span>
      <div class="chart-tabs" role="group" aria-label="详情图表视图"><button :aria-pressed="chartView==='quotes'" @click="chartView='quotes'">行情图</button><button :aria-pressed="chartView==='flows'" :disabled="market.current?.type!=='stock'" @click="chartView='flows'">资金流向</button></div>
    </div>

    <div class="detail-body">
      <div class="col-left">
        <div v-show="chartView==='quotes'" class="chart-content">
        <!-- A+B 合并：K 线 + 技术指标多 pane，共享时间轴；G32：叠加回测买卖点 -->
        <KLineChart
          :symbol="market.current"
          :recent-months="4"
          :show-sr-button="true"
          :show-indicators="true"
          :customize-indicators="true"
          :markers="visibleMarkers"
        />
        </div>
        <StockFlowPanel v-if="chartView==='flows' && market.current?.type==='stock'" :code="market.current.code" :name="market.current.name" />
        <p v-else-if="chartView==='flows'">当前标的暂无个股资金流数据</p>
        <div v-if="strategyId && chartView==='quotes'" class="bt-marker-bar">
          <template v-if="visibleMarkers.length">
            <span class="bt-marker-bar__dot bt-marker-bar__dot--buy" />买入
            <span class="bt-marker-bar__dot bt-marker-bar__dot--sell" />卖出
            <span class="bt-marker-bar__sep" />
            <span class="bt-marker-bar__count">共 {{ visibleMarkers.length }} 个买卖点</span>
          </template>
          <span v-else class="bt-marker-bar__note">{{ markerNote || '当前标的无买卖点' }}</span>
        </div>
      </div>
      <div class="col-right">
        <BasicInfoPanel />
        <StrategyMetricsPanel v-if="strategyId" :strategy-id="strategyId" />
        <StockMinutePanel v-if="market.current?.type==='stock'" :code="market.current.code" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--bg);
  padding: 8px;
  gap: 8px;
}
.detail-topbar {
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 2px;
}
.detail-back {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 4px 10px;
  border-radius: 4px;
  border: 1px solid var(--border-strong);
  transition:
    background-color 0.15s,
    color 0.15s;
}
.detail-back:hover {
  background: var(--bg-hover);
  color: var(--text);
}
.detail-hint {
  font-size: 12px;
  color: var(--text-muted);
}
.detail-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) clamp(360px, 32vw, 480px);
  gap: 8px;
}
.col-left {
  min-height: 0;
  min-width: 0;
  /* A+B 合并为单个 KLineChart，占满左侧；G32：下方追加买卖点图例条 */
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.chart-content {
  flex: 1;
  min-height: 0;
}
.chart-content{display:flex;flex-direction:column}.chart-content>*{flex:1;min-height:0}.chart-tabs{display:flex;gap:5px;flex:none}.chart-tabs button{padding:5px 12px;border:1px solid var(--border);color:var(--text-secondary);border-radius:4px}.chart-tabs button[aria-pressed='true']{color:var(--accent);background:var(--bg-active)}.chart-tabs button:disabled{opacity:.4}
@media(max-width: 800px){.detail-body{grid-template-columns:minmax(0,1fr) 340px}}
/* G32：买卖点图例/空态条 */
.bt-marker-bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 4px;
  font-size: 11px;
  color: var(--text-secondary);
}
.bt-marker-bar__dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  display: inline-block;
}
.bt-marker-bar__dot--buy { background: var(--up); }
.bt-marker-bar__dot--sell { background: var(--down); }
.bt-marker-bar__sep { flex: 1; }
.bt-marker-bar__count { color: var(--text-muted); }
.bt-marker-bar__note { color: var(--text-muted); }
.col-right {
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1.7fr) minmax(220px, 1fr);
  overflow-y: auto;
  gap: 8px;
}
</style>
