<script setup lang="ts">
/**
 * 行情页 · 第一层（A/B/C/D 区）：
 * - A K 线图（KLineChart，含成交量副图与周期切换）
 * - B 技术指标（IndicatorPanel，支撑/压力位设置联动 A 区横线）
 * - C 基本数据（BasicInfoPanel）
 * - D 重点关注列表（WatchlistPanel，行点击切换 A 区标的）
 * - 交互：Esc / 左上角按钮退出返回 /market；轮询刷新实时行情
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchSymbols, fetchWatchlist } from '@/api/market'
import { useMarketStore } from '@/stores/market'
import { useSnapshotPolling } from '@/composables/useSnapshotPolling'
import KLineChart from '@/components/trading/KLineChart.vue'
import IndicatorPanel from '@/components/trading/IndicatorPanel.vue'
import BasicInfoPanel from '@/components/trading/BasicInfoPanel.vue'
import WatchlistPanel from '@/components/trading/WatchlistPanel.vue'

const router = useRouter()
const market = useMarketStore()
const klineRef = ref<InstanceType<typeof KLineChart> | null>(null)

const { start } = useSnapshotPolling(4000)

/** 无当前标的时兜底：优先取关注第一项，否则取固定大盘指数第一项（上证指数） */
async function ensureDefaultSymbol() {
  if (market.current) return
  try {
    const wl = await fetchWatchlist()
    if (wl.length) {
      market.setWatchlist(wl)
      const w = wl[0]
      market.setCurrent({ id: w.symbol_id, code: w.code, name: w.name, type: w.type })
      return
    }
  } catch {
    /* 继续走指数兜底 */
  }
  try {
    const list = await fetchSymbols({ type: 'index', is_fixed: 1 })
    if (list.length) market.setCurrent(list[0])
  } catch {
    /* 静默：页面显示未选择标的 */
  }
}

function goBack() {
  router.push('/market')
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') goBack()
}

/** B 区添加/删除支撑压力位后，刷新 A 区 K 线横线 */
function onSrChanged() {
  klineRef.value?.refreshSRLines()
}

onMounted(() => {
  ensureDefaultSymbol()
  window.addEventListener('keydown', onKeydown)
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
        <KLineChart ref="klineRef" :symbol="market.current" />
        <IndicatorPanel @sr-changed="onSrChanged" />
      </div>
      <div class="col-right">
        <BasicInfoPanel />
        <WatchlistPanel />
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
  display: grid;
  grid-template-rows: minmax(0, 1.7fr) minmax(0, 1fr);
  gap: 8px;
}
.col-right {
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, auto) minmax(0, 1fr);
  gap: 8px;
}
</style>
