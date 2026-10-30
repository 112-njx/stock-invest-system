<script setup lang="ts">
/**
 * 行情页 · 第二层（默认首页 E/F/G/H/I 区）：
 * - E 重点关注股票列（WatchlistPanel 只读复用，与第一层 D 区共用 store 数据源）
 * - F 单击 K 线图（KLineChart 复用，双击进入第一层详情页）
 * - G 大盘指数 / H 行业指数（IndexListPanel，按 sort_order 前端分组）
 * - I 通用设置与开发者信息（SettingsPanel）
 * 首屏并行加载：固定指数列表 + 关注列表 + 默认标的 K 线；轮询刷新全部快照。
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { fetchHomeIndices, fetchSyncStatus, type HomeIndex } from '@/api/market'
import { useAuthModalStore } from '@/stores/authModal'
import { useMarketStore } from '@/stores/market'
import { useWsStore } from '@/stores/wsStore'
import { useSnapshotPolling } from '@/composables/useSnapshotPolling'
import { readHomeIndexCache, snapshotTime, writeHomeIndexCache } from '@/utils/homeIndexCache'
import { trackTiming } from '@/utils/monitor'
import KLineChart from '@/components/trading/KLineChart.vue'
import WatchlistPanel from '@/components/trading/WatchlistPanel.vue'
import IndexListPanel from '@/components/trading/IndexListPanel.vue'
import SettingsPanel from '@/components/trading/SettingsPanel.vue'

const router = useRouter()
const market = useMarketStore()
const ws = useWsStore()
const authModal = useAuthModalStore()

const indicesLoading = ref(false)
const indicesError = ref(false)
const cachedIds = ref(new Set<number>())
const { start } = useSnapshotPolling(4000)

/** V0.2：固定指数预同步进度（0-100），null=未在同步 */
const syncProgress = ref<number | null>(null)
const syncLabel = ref('')
let syncTimer: ReturnType<typeof setInterval> | null = null
/** 本轮进入 running 的时间戳（用于超时降级判断） */
let wasSyncing = false
let statusInFlight = false
let indicesInFlight: Promise<void> | null = null
let refreshAfterCurrent = false
let watchlistReady = false
let mounted = false
let cacheTimer: ReturnType<typeof setTimeout> | null = null
const pageStartedAt = performance.now()
let namesTracked = false
let pricesTracked = false

async function recordVisible(source: string) {
  await nextTick()
  if (!namesTracked && market.fixedIndices.length) {
    namesTracked = true
    trackTiming('home_index_names_visible', performance.now() - pageStartedAt, { source })
  }
  if (!pricesTracked && market.fixedIndices.some((i) => market.snapshots[i.id]?.price != null)) {
    pricesTracked = true
    trackTiming('home_index_prices_visible', performance.now() - pageStartedAt, { source })
  }
}

function chooseDefaultSymbol() {
  if (market.current || !watchlistReady) return
  const first = market.watchlist[0]
  if (first) market.setCurrent({ id: first.symbol_id, code: first.code, name: first.name, type: first.type })
  else if (market.fixedIndices.length) market.setCurrent(market.fixedIndices[0])
}

function onWatchlistLoaded() {
  watchlistReady = true
  chooseDefaultSymbol()
}

function applyIndices(rows: HomeIndex[], source: string) {
  market.setFixedIndices(rows)
  market.mergeSnapshots(rows.flatMap((row) => row.snapshot?.price != null ? [row.snapshot] : []))
  cachedIds.value = new Set(rows
    .filter((row) => source === 'cache' || (row.snapshot?.price == null && market.snapshots[row.id]?.price != null))
    .map((row) => row.id))
  chooseDefaultSymbol()
  void recordVisible(source)
}

function loadHomeIndices(): Promise<void> {
  if (indicesInFlight) {
    refreshAfterCurrent = true
    return indicesInFlight
  }
  indicesLoading.value = !market.fixedIndices.length
  indicesError.value = false
  indicesInFlight = (async () => {
    try {
      const rows = await fetchHomeIndices()
      if (!mounted) return
      applyIndices(rows, 'server')
      writeHomeIndexCache(rows, market.snapshots)
    } catch {
      if (mounted) indicesError.value = !market.fixedIndices.length
    } finally {
      indicesLoading.value = false
      indicesInFlight = null
      if (refreshAfterCurrent && mounted) {
        refreshAfterCurrent = false
        void loadHomeIndices()
      }
    }
  })()
  return indicesInFlight
}

async function checkSyncStatus() {
  if (statusInFlight || !mounted) return
  statusInFlight = true
  try {
    const s = await fetchSyncStatus('fixed_indices')
    market.setSyncStatus(s)
    const running = ['pending', 'running', 'queued'].includes(s.status)
    if (running) {
      syncProgress.value = s.total ? Math.round((s.progress / s.total) * 100) : 0
      syncLabel.value = `数据同步中（${s.progress}/${s.total}）`
      wasSyncing = true
      if (!syncTimer) syncTimer = setInterval(checkSyncStatus, 3000)
    } else {
      const shouldRefresh = wasSyncing
      wasSyncing = false
      syncProgress.value = null
      syncLabel.value = ''
      if (syncTimer) { clearInterval(syncTimer); syncTimer = null }
      if (shouldRefresh) void loadHomeIndices()
    }
  } catch {
    // 静默重试
    if (!syncTimer) syncTimer = setInterval(checkSyncStatus, 3000)
  } finally {
    statusInFlight = false
  }
}

/** G/H 固定指数按 sort_order 分组：1~14 大盘（G），15+ 行业（H） */
const marketIndices = computed(() => market.fixedIndices.filter((i) => (i.sort_order ?? 99) <= 14))
const industryIndices = computed(() => market.fixedIndices.filter((i) => (i.sort_order ?? 99) > 14))

function goDetail() {
  router.push('/market/detail')
}

onMounted(() => {
  mounted = true
  const cached = readHomeIndexCache()
  if (cached.length) applyIndices(cached, 'cache')
  void loadHomeIndices()
  void checkSyncStatus()
  void start()
  ws.init()
  ws.syncSubscriptions()
})

// V0.2：标的/关注列表/固定指数变化时同步 WS 订阅
watch(() => market.current?.id, () => ws.syncSubscriptions())
watch(() => market.watchlist.length, () => ws.syncSubscriptions())
watch(() => market.fixedIndices.length, () => ws.syncSubscriptions())
watch(() => market.snapshots, () => {
  if (cacheTimer) clearTimeout(cacheTimer)
  cacheTimer = setTimeout(() => {
    cachedIds.value = new Set([...cachedIds.value].filter((id) => {
      const updated = market.snapshots[id]?.updated_at
      return !updated || Date.now() - snapshotTime(updated) > 5 * 60 * 1000
    }))
    if (market.fixedIndices.length) writeHomeIndexCache(
      market.fixedIndices.map((row) => ({ ...row, snapshot: market.snapshots[row.id] ?? null })),
      market.snapshots,
    )
  }, 500)
  void recordVisible('update')
}, { deep: true })

// V0.2：卸载时清理 sync-status 轮询并重置同步状态，避免切页后后台持续请求、
// 以及 AI 页等其它页面读到残留的"同步中"状态（快照轮询由 useSnapshotPolling 内部 onBeforeUnmount 停止；
// WS 为全局多标签页单例，切页不断开）
onUnmounted(() => {
  mounted = false
  if (syncTimer) { clearInterval(syncTimer); syncTimer = null }
  if (cacheTimer) { clearTimeout(cacheTimer); cacheTimer = null }
  wasSyncing = false
  syncProgress.value = null
  syncLabel.value = ''
  market.setSyncStatus(null)
})
</script>

<template>
  <div class="market">
    <div class="market-grid">
      <div class="grid-e">
        <!-- G35：未登录时面板内展示引导卡片，点击登录入口打开全局登录弹窗 -->
        <WatchlistPanel readonly @dblclick="goDetail" @loaded="onWatchlistLoaded" @require-login="authModal.show('login')" />
      </div>

      <div class="grid-f">
        <KLineChart :symbol="market.current" :recent-months="4" @dblclick="goDetail" />
        <!-- V0.2：固定指数预同步进度条（absolute覆盖层，不改变布局） -->
        <div v-if="syncProgress !== null" class="sync-overlay">
          <div class="sync-overlay__bar"><div class="sync-overlay__fill" :style="{ width: syncProgress + '%' }" /></div>
          <span class="sync-overlay__label">{{ syncLabel }}</span>
        </div>
      </div>

      <div class="grid-g">
        <IndexListPanel title="大盘指数" :list="marketIndices" :loading="indicesLoading" :error="indicesError" :cached-ids="cachedIds" @retry="loadHomeIndices" @dblclick="goDetail" />
      </div>

      <div class="grid-h">
        <IndexListPanel title="行业指数" :list="industryIndices" :loading="indicesLoading" :error="indicesError" :cached-ids="cachedIds" @retry="loadHomeIndices" @dblclick="goDetail" />
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
