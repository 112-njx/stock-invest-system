<script setup lang="ts">
/**
 * 行情页 · 第二层（默认首页 E/F/G/H/I 区）：
 * - E 重点关注股票列（WatchlistPanel 只读复用，与第一层 D 区共用 store 数据源）
 * - F 单击 K 线图（KLineChart 复用，双击进入第一层详情页）
 * - G 大盘指数 / H 行业指数（IndexListPanel，按 sort_order 前端分组）
 * - I 通用设置与开发者信息（SettingsPanel）
 * 首屏并行加载：固定指数列表 + 关注列表 + 默认标的 K 线；轮询刷新全部快照。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchSymbols } from '@/api/market'
import { useMarketStore } from '@/stores/market'
import { ensureDefaultSymbol } from '@/composables/useDefaultSymbol'
import { useSnapshotPolling } from '@/composables/useSnapshotPolling'
import KLineChart from '@/components/trading/KLineChart.vue'
import WatchlistPanel from '@/components/trading/WatchlistPanel.vue'
import IndexListPanel from '@/components/trading/IndexListPanel.vue'
import SettingsPanel from '@/components/trading/SettingsPanel.vue'

const router = useRouter()
const market = useMarketStore()

const indicesLoading = ref(false)
const { start } = useSnapshotPolling(4000)

/** G/H 固定指数按 sort_order 分组：1~14 大盘（G），15+ 行业（H） */
const marketIndices = computed(() => market.fixedIndices.filter((i) => (i.sort_order ?? 99) <= 14))
const industryIndices = computed(() => market.fixedIndices.filter((i) => (i.sort_order ?? 99) > 14))

async function loadFixedIndices() {
  indicesLoading.value = true
  try {
    market.setFixedIndices(await fetchSymbols({ type: 'index', is_fixed: 1 }))
  } catch {
    /* 错误已 toast；留空态由面板兜底 */
  } finally {
    indicesLoading.value = false
  }
}

function goDetail() {
  router.push('/market/detail')
}

onMounted(async () => {
  // 首屏并行：固定指数（G/H）→ 默认标的（F）；关注列表由 E 区 WatchlistPanel 自取
  await loadFixedIndices()
  await ensureDefaultSymbol()
  start()
})
</script>

<template>
  <div class="market">
    <div class="market-grid">
      <div class="grid-e">
        <WatchlistPanel readonly @dblclick="goDetail" />
      </div>

      <div class="grid-f">
        <KLineChart :symbol="market.current" @dblclick="goDetail" />
      </div>

      <div class="grid-g">
        <IndexListPanel title="大盘指数" :list="marketIndices" :loading="indicesLoading" @dblclick="goDetail" />
      </div>

      <div class="grid-h">
        <IndexListPanel title="行业指数" :list="industryIndices" :loading="indicesLoading" @dblclick="goDetail" />
      </div>

      <div class="grid-i">
        <SettingsPanel />
      </div>
    </div>
  </div>
</template>

<style scoped>
.market {
  flex: 1;
  min-height: 0;
  padding: 8px;
  background: var(--bg);
}
.market-grid {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr) 280px;
  grid-template-rows: minmax(0, 1.5fr) minmax(0, 1fr);
  gap: 8px;
  height: 100%;
  min-height: 0;
}
.grid-e {
  grid-column: 1;
  grid-row: 1;
  min-height: 0;
}
.grid-f {
  grid-column: 2 / 4;
  grid-row: 1;
  min-height: 0;
}
.grid-g {
  grid-column: 1;
  grid-row: 2;
  min-height: 0;
}
.grid-h {
  grid-column: 2;
  grid-row: 2;
  min-height: 0;
}
.grid-i {
  grid-column: 3;
  grid-row: 2;
  min-height: 0;
}
</style>
