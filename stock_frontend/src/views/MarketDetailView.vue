<script setup lang="ts">
/**
 * 行情页 · 第一层（A+B/C/D 区）：
 * - A+B 区：KLineChart（蜡烛图主图 + 技术指标多 pane，共享时间轴同步缩放）
 * - C 区：基本数据（BasicInfoPanel）
 * - D 区：重点关注列表（WatchlistPanel，行点击切换标的）/ 回测策略指标（StrategyMetricsPanel）
 * - 交互：Esc / 左上角按钮退出返回 /market；轮询刷新实时行情
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { searchSymbols } from '@/api/market'
import { useMarketStore } from '@/stores/market'
import { ensureDefaultSymbol } from '@/composables/useDefaultSymbol'
import { useSnapshotPolling } from '@/composables/useSnapshotPolling'
import KLineChart from '@/components/trading/KLineChart.vue'
import BasicInfoPanel from '@/components/trading/BasicInfoPanel.vue'
import WatchlistPanel from '@/components/trading/WatchlistPanel.vue'
import StrategyMetricsPanel from '@/components/trading/StrategyMetricsPanel.vue'

const router = useRouter()
const route = useRoute()
const market = useMarketStore()

/** 回测显示跳转：带 strategy_id 时 D 区替换为策略指标面板（4.5） */
const strategyId = computed(() => (route.query.strategy_id ? Number(route.query.strategy_id) : null))
const klineRef = ref<InstanceType<typeof KLineChart> | null>(null)

const { start } = useSnapshotPolling(4000)

function goBack() {
  router.push('/market')
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
  if (market.current && (String(market.current.code) === kw || String(market.current.id) === kw)) return
  try {
    const list = await searchSymbols(kw)
    const found = list.find((s) => s.code === kw || String(s.id) === kw)
    if (found) market.setCurrent(found)
  } catch {
    /* 解析失败保持当前标的，不阻塞页面 */
  }
}

onMounted(async () => {
  window.addEventListener('keydown', onKeydown)
  await ensureDefaultSymbol()
  await resolveSymbolParam()
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
    </div>

    <div class="detail-body">
      <div class="col-left">
        <!-- A+B 合并：K 线 + 技术指标多 pane，共享时间轴 -->
        <KLineChart
          ref="klineRef"
          :symbol="market.current"
          :show-sr-button="true"
          :show-indicators="true"
        />
      </div>
      <div class="col-right">
        <BasicInfoPanel />
        <StrategyMetricsPanel v-if="strategyId" :strategy-id="strategyId" />
        <WatchlistPanel v-else />
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
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 8px;
}
.col-left {
  min-height: 0;
  min-width: 0;
  /* A+B 合并为单个 KLineChart，占满左侧 */
  display: block;
}
.col-right {
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, auto) minmax(0, 1fr);
  gap: 8px;
}
</style>
