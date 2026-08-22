<script setup lang="ts">
/**
 * 行情页 · 第二层（默认首页 E/F/G/H/I 区）：
 * - E 重点关注股票列（WatchlistPanel 只读复用，与第一层 D 区共用 store 数据源）
 * - F 单击 K 线图（KLineChart 复用，双击进入第一层详情页）
 * - G 大盘指数 / H 行业指数（IndexListPanel，按 sort_order 前端分组）
 * - I 通用设置与开发者信息（SettingsPanel）
 * 首屏并行加载：固定指数列表 + 关注列表 + 默认标的 K 线；轮询刷新全部快照。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { fetchSymbols, fetchSyncStatus } from '@/api/market'
import { useMarketStore } from '@/stores/market'
import { useWsStore } from '@/stores/wsStore'
import { ensureDefaultSymbol } from '@/composables/useDefaultSymbol'
import { useSnapshotPolling } from '@/composables/useSnapshotPolling'
import KLineChart from '@/components/trading/KLineChart.vue'
import WatchlistPanel from '@/components/trading/WatchlistPanel.vue'
import IndexListPanel from '@/components/trading/IndexListPanel.vue'
import SettingsPanel from '@/components/trading/SettingsPanel.vue'

const router = useRouter()
const market = useMarketStore()
const ws = useWsStore()

const indicesLoading = ref(false)
const { start } = useSnapshotPolling(4000)

/** V0.2：固定指数预同步进度（0-100），null=未在同步 */
const syncProgress = ref<number | null>(null)
const syncLabel = ref('')
let syncTimer: ReturnType<typeof setInterval> | null = null

async function checkSyncStatus() {
  try {
    const s = await fetchSyncStatus('fixed_indices')
    market.setSyncStatus(s)
    const running = ['pending', 'running', 'queued'].includes(s.status)
    if (running) {
      syncProgress.value = s.total ? Math.round((s.progress / s.total) * 100) : 0
      syncLabel.value = `数据同步中（${s.progress}/${s.total}）`
      indicesLoading.value = true
      if (!syncTimer) syncTimer = setInterval(checkSyncStatus, 3000)
    } else {
      syncProgress.value = null
      syncLabel.value = ''
      if (syncTimer) { clearInterval(syncTimer); syncTimer = null }
      // 同步完成后加载数据
      if (indicesLoading.value) {
        indicesLoading.value = false
        await loadFixedIndices()
        await ensureDefaultSymbol()
        start()
      }
    }
  } catch {
    // 静默重试
    if (!syncTimer) syncTimer = setInterval(checkSyncStatus, 3000)
  }
}

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
  // V0.2：先查固定指数预同步状态，同步中显示进度条+骨架屏，done后加载数据
  await checkSyncStatus()
  // 无同步进行（已完成/无记录），直接加载
  if (syncProgress.value === null) {
    await loadFixedIndices()
    await ensureDefaultSymbol()
    start()
  }
  // V0.2：初始化 WS 实时行情连接
  ws.init()
  ws.syncSubscriptions()
})

// V0.2：标的/关注列表/固定指数变化时同步 WS 订阅
watch(() => market.current?.id, () => ws.syncSubscriptions())
watch(() => market.watchlist.length, () => ws.syncSubscriptions())
watch(() => market.fixedIndices.length, () => ws.syncSubscriptions())
</script>

<template>
  <div class="market">
    <div class="market-grid">
      <div class="grid-e">
        <WatchlistPanel readonly @dblclick="goDetail" />
      </div>

      <div class="grid-f">
        <KLineChart :symbol="market.current" @dblclick="goDetail" />
        <!-- V0.2：固定指数预同步进度条（absolute覆盖层，不改变布局） -->
        <div v-if="syncProgress !== null" class="sync-overlay">
          <div class="sync-overlay__bar"><div class="sync-overlay__fill" :style="{ width: syncProgress + '%' }" /></div>
          <span class="sync-overlay__label">{{ syncLabel }}</span>
        </div>
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
  /* 左列 E/G 加宽至 300~320px，保证指数名称完整显示；右列 I 区 260~280px */
  grid-template-columns: minmax(300px, 320px) minmax(0, 1fr) minmax(260px, 280px);
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
  position: relative;
}
/* V0.2：同步进度条覆盖层（absolute，不改变布局） */
.sync-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 12px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-secondary);
}
.sync-overlay__bar {
  flex: none;
  width: 120px;
  height: 3px;
  background: var(--bg-panel-2);
  border-radius: 2px;
  overflow: hidden;
}
.sync-overlay__fill {
  height: 100%;
  background: var(--accent);
  border-radius: 2px;
  transition: width 0.4s ease;
}
.sync-overlay__label {
  white-space: nowrap;
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
