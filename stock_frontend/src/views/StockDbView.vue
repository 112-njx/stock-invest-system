<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import TrendView from '@/views/TrendView.vue'
import StockDbChart from '@/components/stockdb/StockDbChart.vue'
import StockSummary from '@/components/stockdb/StockSummary.vue'
import { memberSortKeys, sortMembers, memberValue, compact, numberText, type MemberSort } from '@/utils/blueprint'
import {
  algorithms, barReturn, categories, percent,
  type Bar, type Board, type BoardDetail, type Category, type Home, type Member,
  type Members, type Ranking, type Weight, type Workspace,
} from '@/api/stockdb'
import { cachedStockDb, fetchStockDb, peekCache, putCache, readCache, StockDbHttpError } from '@/api/stockdbCache'

const trendMode = ref(useRoute()?.query.view === 'trends')
function selectCategory(id: Category) { trendMode.value = false; category.value = id; clearHover() }
function openTrends() { trendMode.value = true; category.value = 'sw1'; clearHover(); drawer.value?.close() }

function supportedWorkspace(value: Workspace | undefined) {
  return value && categories.some(([id]) => id === value.category) && (!trendMode.value || value.category === 'sw1') ? value : undefined
}
const screen = shallowRef(supportedWorkspace(peekCache<Workspace>('last-workspace')))
function readPreferences() {
  try {
    const saved = JSON.parse(localStorage.getItem('stockdb-workspace-preferences-v2') ?? '{}')
    return {
      days: [1, 3, 5, 10, 15, 30].includes(saved.days) ? saved.days as number : 1,
      sort: saved.sort === 'return' ? 'return' as const : 'price' as const,
      memberSort: memberSortKeys.includes(saved.memberSort) ? saved.memberSort as MemberSort : 'return' as const,
      memberAscending: saved.memberAscending === true,
    }
  } catch {
    return { days: 1, sort: 'price' as const, memberSort: 'return' as const, memberAscending: false }
  }
}
const preferences = readPreferences()
const category = ref<Category>(screen.value?.category ?? 'sw1')
const weight = ref<Weight>(screen.value?.weight ?? 'equal')
const days = ref(preferences.days)
const sort = ref<'price' | 'return'>(preferences.sort)
interface IndexOrder { days: number; sort: 'price' | 'return' }
const displayedOrder = ref<IndexOrder>({ days: preferences.days, sort: preferences.sort })
const memberSort = ref<MemberSort>(preferences.memberSort)
const memberAscending = ref(preferences.memberAscending)
const ready = ref(false)
const loading = ref(false)
const refreshing = ref(false)
const summaryRevision = ref(0)
const error = ref('')
const pinnedBoard = ref(screen.value?.pinnedBoard ?? false)
const boardList = ref<HTMLElement | null>(null)
const memberList = ref<HTMLElement | null>(null)
const drawer = ref<HTMLDialogElement | null>(null)
const compareBoard = shallowRef<Board | null>(null)
const comparison = shallowRef<BoardDetail | null>(null)
const windows = [[1, '今日涨幅'], [3, '3日涨幅'], [5, '5日涨幅'], [10, '10日涨幅'], [15, '15日涨幅'], [30, '30日涨幅']] as const

const shownCategory = computed(() => screen.value?.category ?? category.value)
const shownWeight = computed(() => screen.value?.weight ?? weight.value)
const categoryName = computed(() => categories.find(([id]) => id === shownCategory.value)?.[1])
const weightName = computed(() => algorithms.find(([id]) => id === shownWeight.value)?.[1])
const boards = computed(() => screen.value?.boards ?? [])
const boardId = computed(() => screen.value?.boardId ?? '')
const detail = computed(() => screen.value?.detail)
const stockCode = computed(() => detail.value?.stockCode ?? '')
const stockBars = computed(() => detail.value?.stockBars ?? [])
const date = computed(() => screen.value?.date)
const currentBoard = computed(() => boards.value.find((board) => board.id === boardId.value))

function sameOrder(left: IndexOrder, right: IndexOrder) {
  return left.days === right.days && left.sort === right.sort
}
function rank(items: Board[], order = displayedOrder.value) {
  return items.map((board) => ({ ...board, change: board.changes[String(order.days)] ?? null })).sort((a, b) =>
    (b[order.sort === 'price' ? 'price' : 'change'] ?? -Infinity) -
    (a[order.sort === 'price' ? 'price' : 'change'] ?? -Infinity) || a.name.localeCompare(b.name, 'zh-CN'),
  )
}
const ranked = computed(() => rank(boards.value))
const selectedIndex = computed(() => ranked.value.find((board) => board.id === boardId.value))
const indexBars = computed(() => screen.value?.charts[boardId.value] ?? [])
const members = computed(() => sortMembers(detail.value?.members ?? [], memberSort.value, memberAscending.value))
const memberColumns = [['code', '代码'], ['price', '收盘价'], ['return', '涨跌幅'], ['change', '涨跌额'], ['amount', '成交额'], ['turnover', '换手率'], ['float_mv', '流通市值']] as const
function memberText(stock: Member, key: Exclude<MemberSort, 'code'>) {
  const value = memberValue(stock, key)
  return key === 'return' ? formatReturn(value) : key === 'turnover' ? (value === null ? '—' : numberText(value) + '%') : key === 'amount' || key === 'float_mv' ? compact(value) : numberText(value)
}
const currentStock = computed(() => members.value.find((stock) => stock.code === stockCode.value))

let disposed = false
let workspaceRequest = 0
let memberRequest = 0
let stockRequest = 0
let compareRequest = 0
let persistTimer: ReturnType<typeof setTimeout> | undefined
let statusTimer: ReturnType<typeof setInterval> | undefined

function workspaceKey(group: Category, method: Weight) {
  return 'workspace:' + group + ':' + method
}
function rememberWorkspace(value: Workspace) {
  const saved = { ...value, pinnedBoard: pinnedBoard.value }
  screen.value = saved
  summaryRevision.value++
  clearTimeout(persistTimer)
  persistTimer = setTimeout(() => {
    putCache('last-workspace', saved)
    putCache(workspaceKey(saved.category, saved.weight), saved)
  }, 150)
}
function versionQuery(version: string) { return new URLSearchParams({ version }) }

async function curves(version: string, method: Weight, ids: string[]) {
  const result: Record<string, Bar[]> = {}
  const missing: string[] = []
  for (const id of ids) {
    const saved = await readCache<Bar[]>(`curve:${version}:${method}:${id}`)
    if (saved) result[id] = saved
    else missing.push(id)
  }
  if (missing.length) {
    const query = new URLSearchParams({ ids: missing.join(','), weight: method, version })
    const response = await cachedStockDb<{ charts: Record<string, Bar[]> }>('/charts?' + query)
    for (const [id, bars] of Object.entries(response.charts)) {
      putCache(`curve:${version}:${method}:${id}`, bars)
      result[id] = bars
    }
  }
  return result
}

function bundlePath(id: string, version: string, selected = '') {
  return '/members/' + encodeURIComponent(id) + '?' + new URLSearchParams({
    version, selected, order: ['code', 'price'].includes(memberSort.value) ? memberSort.value : 'return', ascending: String(memberAscending.value),
  })
}

async function loadDetail(id: string, version: string) {
  return cachedStockDb<BoardDetail>('/boards/' + encodeURIComponent(id) + '?' + versionQuery(version))
}

async function buildWorkspace(group: Category, method: Weight, order: IndexOrder): Promise<Workspace> {
  if (group === 'sw1' && method === 'equal' && order.sort === 'price' && !pinnedBoard.value) {
    const home = await fetchStockDb<Home>('/home')
    for (const [id, bars] of Object.entries(home.charts)) putCache(`curve:${home.version}:equal:${id}`, bars)
    return { ...home, category: group, weight: method }
  }
  const ranking = await fetchStockDb<Ranking>(
    '/ranking?' + new URLSearchParams({ category: group, weight: method }),
  )
  const ordered = rank(ranking.boards, order)
  const selected = pinnedBoard.value && ranking.boards.some((board) => board.id === boardId.value)
    ? boardId.value : ordered[0]?.id ?? ''
  const selectedStock = selected === boardId.value ? stockCode.value : ''
  const [charts, detail] = await Promise.all([
    curves(ranking.version, method, selected ? [selected] : []),
    selected ? cachedStockDb<Members>(bundlePath(selected, ranking.version, selectedStock))
      : Promise.resolve({ members: [], count: 0, stockCode: '', stockBars: [] }),
  ])
  return { ...ranking, category: group, weight: method, charts, boardId: selected, detail }
}

async function loadWorkspace(retry = true) {
  const request = ++workspaceRequest
  memberRequest++
  stockRequest++
  const group = category.value
  const method = weight.value
  const order: IndexOrder = { days: days.value, sort: sort.value }
  loading.value = true
  error.value = ''
  clearHover()
  try {
    const saved = await readCache<Workspace>(workspaceKey(group, method))
    if (request !== workspaceRequest || disposed) return
    if (saved && saved.charts[saved.boardId] &&
      saved.boardId === (pinnedBoard.value ? boardId.value : rank(saved.boards, order)[0]?.id ?? '') &&
      (saved.category !== shownCategory.value || saved.weight !== shownWeight.value || !screen.value)) {
      boardList.value?.scrollTo(0, 0)
      screen.value = saved
      displayedOrder.value = order
    }
    const value = await buildWorkspace(group, method, order)
    if (request !== workspaceRequest || disposed) return
    const changed = shownCategory.value !== group || shownWeight.value !== method ||
      !sameOrder(order, displayedOrder.value)
    const previous = screen.value
    displayedOrder.value = order
    rememberWorkspace({
      ...value,
      charts: previous?.version === value.version && previous.weight === value.weight
        ? { ...previous.charts, ...value.charts } : value.charts,
    })
    if (changed) {
      boardList.value?.scrollTo(0, 0)
    }
  } catch (cause) {
    if (request !== workspaceRequest || disposed) return
    if (cause instanceof StockDbHttpError && cause.status === 409 && retry) {
      await loadWorkspace(false)
      return
    }
    error.value = screen.value ? '暂未更新，保留上次数据。' : (cause as Error).message
  } finally {
    if (request === workspaceRequest && !disposed) loading.value = false
  }
}

async function selectBoard(id: string) {
  const current = screen.value
  if (!current) return
  if (loading.value && (current.category !== category.value || current.weight !== weight.value ||
    !sameOrder({ days: days.value, sort: sort.value }, displayedOrder.value))) return
  const request = ++memberRequest
  workspaceRequest++
  loading.value = false
  stockRequest++
  pinnedBoard.value = true
  clearHover()
  if (current.boardId === id) {
    rememberWorkspace(current)
    return
  }
  try {
    const [next, charts] = await Promise.all([cachedStockDb<Members>(bundlePath(id, current.version)), curves(current.version, current.weight, [id])])
    if (request !== memberRequest || disposed || screen.value?.version !== current.version ||
      screen.value.category !== current.category || screen.value.weight !== current.weight) return
    rememberWorkspace({ ...screen.value, boardId: id, detail: next, charts: { ...screen.value.charts, ...charts } })
    memberList.value?.scrollTo(0, 0)
  } catch (cause) {
    if (request !== memberRequest || disposed) return
    if (cause instanceof StockDbHttpError && cause.status === 409) void loadWorkspace()
    else error.value = (cause as Error).message
  }
}

async function selectStock(code: string) {
  const current = screen.value
  if (!current) return
  if (loading.value && (current.category !== category.value || current.weight !== weight.value ||
    !sameOrder({ days: days.value, sort: sort.value }, displayedOrder.value))) return
  const request = ++stockRequest
  memberRequest++
  workspaceRequest++
  loading.value = false
  if (current.detail.stockCode === code) return
  try {
    const response = await cachedStockDb<{ bars: Bar[] }>('/stocks/' + code + '?' + versionQuery(current.version))
    if (request !== stockRequest || disposed || screen.value?.version !== current.version ||
      screen.value.boardId !== current.boardId) return
    rememberWorkspace({ ...screen.value, detail: { ...screen.value.detail, stockCode: code, stockBars: response.bars } })
  } catch (cause) {
    if (request !== stockRequest || disposed) return
    if (cause instanceof StockDbHttpError && cause.status === 409) void loadWorkspace()
    else error.value = (cause as Error).message
  }
}

watch([category, weight], ([group], previous) => {
  if (!ready.value) return
  if (group !== previous[0]) pinnedBoard.value = false
  void loadWorkspace()
})
watch([days, sort], () => {
  if (ready.value) void loadWorkspace()
})
watch([days, sort, memberSort, memberAscending], () => {
  try {
    localStorage.setItem('stockdb-workspace-preferences-v2', JSON.stringify({
      days: days.value, sort: sort.value, memberSort: memberSort.value, memberAscending: memberAscending.value,
    }))
  } catch { /* Browsing remains available when preference storage is disabled. */ }
})

function setMemberSort(key: typeof memberSort.value) {
  memberAscending.value = memberSort.value === key ? !memberAscending.value : key === 'code'
  memberSort.value = key
  memberList.value?.scrollTo(0, 0)
  clearHover()
}

async function refresh() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    const response = await fetch('/api/v1/stockdb/refresh', { method: 'POST' })
    if (!response.ok) throw new Error('暂时无法刷新本地数据')
    for (let i = 0; i < 120; i++) {
      if (disposed) return
      const state = await fetchStockDb<{ refreshing: boolean; error: string }>('/status')
      if (!state.refreshing) {
        if (state.error) throw new Error(state.error)
        await loadWorkspace()
        return
      }
      await new Promise((resolve) => setTimeout(resolve, 500))
    }
    error.value = '后台仍在更新，可继续浏览当前数据。'
  } catch {
    error.value = '暂未更新，保留上次数据。'
  } finally { refreshing.value = false }
}

function color(value: number | null) { return value === null || value === 0 ? '' : value > 0 ? 'up' : 'down' }
function formatReturn(value: number | null) { return value === null ? '—' : percent(value) }

const hover = shallowRef<{ stock: Member; x: number; y: number; bars: Bar[] } | null>(null)
let hoverTimer: ReturnType<typeof setTimeout> | undefined
let hoverRequest = 0
function clearHover() {
  clearTimeout(hoverTimer)
  hoverRequest++
  hover.value = null
}
function showIntraday(stock: Member, event: PointerEvent) {
  if (event.pointerType === 'touch' || !screen.value) return
  clearHover()
  const request = hoverRequest
  const version = screen.value.version
  const bounds = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const x = Math.max(8, Math.min(innerWidth - Math.min(420, innerWidth - 16) - 8, bounds.left - 290))
  const y = Math.max(8, Math.min(innerHeight - 225, bounds.top - 210))
  hoverTimer = setTimeout(async () => {
    try {
      const bars = await cachedStockDb<Bar[]>(
        `/stocks/${stock.code}/minutes?date=${stock.bar[0]}&version=${version}`,
        60000,
      )
      if (!disposed && request === hoverRequest) hover.value = { stock, x, y, bars }
    } catch {
      if (!disposed && request === hoverRequest) error.value = '该股票分时暂不可用。'
    }
  }, 240)
}

async function compare(board: Board) {
  if (!screen.value) return
  const request = ++compareRequest
  const version = screen.value.version
  try {
    const payload = await loadDetail(board.id, version)
    if (disposed || request !== compareRequest || screen.value?.version !== version) return
    compareBoard.value = board
    comparison.value = payload
    if (!drawer.value?.open) drawer.value?.showModal()
  } catch (cause) {
    if (!disposed && request === compareRequest) {
      if (cause instanceof StockDbHttpError && cause.status === 409) void loadWorkspace()
      else error.value = (cause as Error).message
    }
  }
}

onMounted(async () => {
  const previous = screen.value ?? supportedWorkspace(await readCache<Workspace>('last-workspace'))
  const preparedHome = previous ? undefined : await readCache<Home>('api:/home')
  const saved = previous ?? (preparedHome ? { ...preparedHome, category: 'sw1' as const, weight: 'equal' as const } : undefined)
  if (disposed) return
  if (saved && category.value === (screen.value?.category ?? 'sw1') && weight.value === (screen.value?.weight ?? 'equal')) {
    screen.value = saved
    category.value = saved.category
    weight.value = saved.weight
    pinnedBoard.value = previous?.pinnedBoard ?? false
  }
  await nextTick()
  ready.value = true
  void loadWorkspace()
  statusTimer = setInterval(() => {
    if (document.visibilityState === 'visible' && !loading.value && !refreshing.value) void loadWorkspace()
  }, 60000)
})
onBeforeUnmount(() => {
  disposed = true
  clearHover()
  clearTimeout(persistTimer)
  clearInterval(statusTimer)
  if (screen.value) {
    putCache('last-workspace', screen.value)
    putCache(workspaceKey(screen.value.category, screen.value.weight), screen.value)
  }
})
</script>
<template>
  <div class="blueprint" :class="{ 'blueprint--trends': trendMode }">
    <aside class="panel categories">
      <header class="panel-head"><strong>分类</strong></header>
      <div class="categories__list">
        <template v-for="[id, label] in categories" :key="id">
          <button :class="{ active: !trendMode && shownCategory === id }"
            :aria-pressed="!trendMode && shownCategory === id" @click="selectCategory(id)">{{ label }}</button>
          <button v-if="id === 'sw1'" class="trend-entry" :class="{ active: trendMode }"
            :aria-pressed="trendMode" @click="openTrends">└ 波段追踪</button>
        </template>
      </div>
    </aside>

    <aside class="panel boards">
      <header class="panel-head"><strong>{{ categoryName }}</strong><small>{{ boards.length }} 个板块</small></header>
      <select class="mobile-only board-picker" :value="boardId" aria-label="选择板块" @change="selectBoard(($event.target as HTMLSelectElement).value)">
        <option v-if="!ranked.length" value="" disabled>暂无板块</option>
        <option v-for="board in ranked" :key="board.id" :value="board.id">{{ board.name }} · {{ formatReturn(board.change) }}</option>
      </select>
      <div ref="boardList" class="rows">
        <button v-for="board in ranked" :key="board.id" class="board-row" :class="{ active: boardId === board.id }"
          :aria-pressed="boardId === board.id" :title="board.name" @click="selectBoard(board.id)" @dblclick="!trendMode && compare(board)">
          <span class="ellipsis">{{ board.name }}</span><small>{{ board.count }}</small>
          <strong :class="color(board.change)">{{ formatReturn(board.change) }}</strong>
        </button>
        <p v-if="!loading && !error && !boards.length" class="empty">暂无板块</p>
      </div>
    </aside>

    <TrendView v-if="trendMode && shownCategory === 'sw1' && boardId" class="embedded-trends"
      embedded :industry="boardId" />
    <section v-else-if="trendMode" class="embedded-trends empty">正在准备申万一级行业…</section>
    <section v-else class="panel indices">
      <header class="panel-head index-toolbar">
        <div class="algorithms"><strong>⚡ 指数算法</strong>
          <div class="segmented" aria-label="指数算法">
            <button v-for="[id, label] in algorithms" :key="id" :class="{ active: shownWeight === id }"
              :aria-pressed="shownWeight === id" @click="weight = id">{{ label }}</button>
          </div>
        </div>
        <div class="ranking">
          <button :class="{ active: sort === 'price' }" :aria-pressed="sort === 'price'" @click="sort = 'price'">最新价</button>
          <select v-model.number="days" :class="{ active: sort === 'return' }" aria-label="选择涨幅周期"
            @click="sort = 'return'" @change="sort = 'return'">
            <option v-for="[period, label] in windows" :key="period" :value="period">{{ label }}</option>
          </select>
        </div>
      </header>
      <div v-if="!screen && error" class="empty state" role="alert">{{ error }} <button @click="refresh">重试</button></div>
      <div v-if="screen && !loading && !ranked.length" class="empty state">请选择板块</div>
      <article v-if="selectedIndex" class="card selected-index">
        <header class="card-head">
          <strong class="card-name ellipsis">{{ selectedIndex.name }}</strong>
          <span class="weight-label">{{ weightName }}{{ shownWeight === 'equal' ? '' : '加权' }}</span>
          <button class="compare" :aria-label="`${selectedIndex.name}五维对比`" @click="compare(selectedIndex)">五维</button>
          <strong class="quote">{{ numberText(selectedIndex.price) }}</strong>
          <strong class="quote" :class="color(selectedIndex.change)">{{ formatReturn(selectedIndex.change) }}</strong>
        </header>
        <StockDbChart v-if="indexBars.length" :bars="indexBars.slice(-44)" :label="`${selectedIndex.name}指数日 K`" amount synthetic />
      </article>
      <section class="member-panel">
        <header class="panel-head"><strong>{{ currentBoard?.name }} · 成分股</strong><small v-if="detail">{{ members.length }}/{{ detail.count }} 只 · 最新收盘行情</small></header>
        <a class="member-detail-link mobile-only" href="#constituent-details">查看选中个股详情 ↓</a>
        <div ref="memberList" class="member-table scroll-x" @scroll.passive="clearHover">
          <div class="member-sorts member-grid">
            <template v-for="[id, label] in memberColumns" :key="id">
              <button :class="{ active: memberSort === id }" :aria-pressed="memberSort === id" @click="setMemberSort(id)">{{ label }}{{ memberSort === id ? (memberAscending ? '↑' : '↓') : '' }}</button>
              <span v-if="id === 'code'">股票名称</span>
            </template>
          </div>
          <button v-for="stock in members" :key="stock.code" class="stock-row member-grid" :class="{ active: stockCode === stock.code }" :aria-pressed="stockCode === stock.code"
            @pointerenter="showIntraday(stock, $event)" @pointerleave="clearHover" @click="selectStock(stock.code)">
            <strong>{{ stock.code }}</strong><span class="ellipsis" :title="stock.name">{{ stock.name }}</span>
            <span v-for="key in (['price', 'return', 'change', 'amount', 'turnover', 'float_mv'] as const)" :key="key" :class="['price', 'return', 'change'].includes(key) ? color(key === 'price' ? memberValue(stock, 'return') : memberValue(stock, key)) : key === 'amount' ? 'quote-highlight' : ''">{{ memberText(stock, key) }}</span>
          </button>
          <p v-if="detail && !members.length" class="empty">暂无成分股行情</p>
        </div>
      </section>
    </section>

    <aside v-if="!trendMode" id="constituent-details" class="panel constituents">
      <header class="panel-head"><strong class="ellipsis">{{ currentBoard?.name ?? '板块股票' }}</strong><small>个股详情</small></header>
      <div class="stock-chart">
        <strong v-if="currentStock">{{ currentStock.code }} · {{ currentStock.name }} 日 K</strong>
        <StockDbChart v-if="detail" :bars="stockBars" :label="`${currentStock?.name ?? ''}日 K`" />
      </div>
      <div class="stock-insights"><StockSummary :stock="currentStock" :version="screen?.version" :refresh-key="summaryRevision" @stale="loadWorkspace()" /></div>
      <div class="source"><small v-if="date">{{ date }}</small>
        <small v-if="error" role="status" :title="error">暂未更新</small><small v-else-if="loading || refreshing" role="status">后台更新中</small>
        <button :disabled="refreshing" @click="refresh">刷新</button>
      </div>
    </aside>

    <div v-if="hover" class="intraday" :style="{ left: hover.x + 'px', top: hover.y + 'px' }">
      <strong>{{ hover.stock.name }} · {{ hover.stock.bar[0] }} 分时</strong>
      <StockDbChart :bars="hover.bars" :label="`${hover.stock.name}分时`" minute :baseline="hover.stock.bar[7]" />
    </div>

    <dialog ref="drawer" class="compare-dialog viewport-dialog" aria-label="五维指数对比" @close="compareRequest++">
      <header class="panel-head"><strong>{{ compareBoard?.name }} · 五维指数全景对比</strong>
        <small>{{ compareBoard?.count }} 只成分股</small><button aria-label="关闭对比" @click="drawer?.close()">✕</button>
      </header>
      <div v-if="comparison" class="compare-grid">
        <article v-for="[id, label] in algorithms" :key="id">
          <header><strong>{{ label }}</strong><span :class="color(barReturn(comparison.indices[id], days))">{{ formatReturn(barReturn(comparison.indices[id], days)) }}</span></header>
          <StockDbChart :bars="comparison.indices[id].slice(-44)" :label="label" amount synthetic />
        </article>
      </div>
    </dialog>

  </div>
</template>

<style scoped>
.blueprint {
  --blueprint-workspace: var(--bg);
  --blueprint-active: var(--bg-active);
  --blueprint-link: #93c5fd;
  --blueprint-up: #f87171;
  --blueprint-down: #4ade80;
  --blueprint-candle-up: var(--up);
  --blueprint-candle-down: var(--down);
}
[data-theme='light'] .blueprint {
  --blueprint-workspace: #eaf0f3;
  --blueprint-active: #e7f2fa;
  --blueprint-link: #1c638f;
  --blueprint-up: #bb2544;
  --blueprint-down: #12835e;
  --blueprint-candle-up: #d53750;
  --blueprint-candle-down: #13a479;
}
.blueprint { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(90px, 8%) minmax(155px, 16%) minmax(0, 1fr) minmax(300px, 27%); background: var(--blueprint-workspace); color: var(--text); }
.panel { display: flex; flex-direction: column; min-width: 0; min-height: 0; background: var(--bg-panel); border-right: 1px solid var(--border); }
.panel-head { flex: none; height: 46px; display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 0 12px; border-bottom: 1px solid var(--border); white-space: nowrap; }
small, .source { color: var(--text-secondary); font-size: 11px; }
button, select { font: inherit; background: transparent; color: inherit; border: 0; cursor: pointer; border-radius: 4px; }
button:disabled { opacity: .45; cursor: default; }
button:focus-visible, select:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
button:hover, .active { background: var(--blueprint-active); color: var(--blueprint-link); }
.categories__list { display: grid; padding: 6px 8px; gap: 5px; }
.categories__list button { padding: 10px; text-align: left; }
.categories__list .active { font-weight: 700; }
.categories__list .trend-entry { padding: 6px 10px 10px 24px; text-align: left; font-size: 12px; color: var(--blueprint-link); border-radius: 4px; text-decoration: none; }
.trend-entry:hover { background: var(--blueprint-active); }
.rows { overflow: auto; min-height: 0; flex: 1; }
.board-row, .stock-row { display: grid; align-items: center; text-align: left; gap: 8px; width: 100%; padding: 0 10px; }
.boards .rows { padding: 6px 7px; }
.board-row { grid-template-columns: minmax(0, 1fr) 36px 64px; min-height: 39px; margin-bottom: 2px; }
.board-row.active { font-weight: 700; }
.board-row small { border-radius: 15px; text-align: center; background: var(--bg-hover); }
.board-row strong, .stock-row span:nth-child(n + 3) { text-align: right; font-size: 12px; font-variant-numeric: tabular-nums; }
.ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.up { color: var(--blueprint-up); }
.down { color: var(--blueprint-down); }
.source button { padding: 4px 7px; color: var(--blueprint-link); background: var(--accent-soft); }
.index-toolbar { gap: 6px; }
.algorithms, .segmented, .ranking { display: flex; align-items: center; gap: 3px; }
.algorithms strong, .segmented, .ranking { font-size: 11px; }
.segmented { background: var(--bg-hover); border-radius: 6px; padding: 3px; }
.segmented button, .ranking button, .ranking select { padding: 5px 7px; }
.segmented .active, .primary { background: #2455d7; color: #fff; font-weight: 700; }
.ranking .active, .member-sorts .active { font-weight: 700; text-decoration: underline; text-underline-offset: 4px; }
.indices { background: var(--blueprint-workspace); }
.index-toolbar { background: var(--bg-panel); }
.selected-index { flex: 1.1; min-height: 210px; margin: 0; padding: 0; display: flex; flex-direction: column; background: var(--bg-panel); border-radius: 7px; overflow: hidden; }
.selected-index > :deep(.chart) { flex: 1; height: auto; min-height: 0; }
.stock-row > strong, .stock-row > .ellipsis, .quote-highlight { color: var(--quote-highlight); }
.stock-row .up { color: var(--quote-up); }.stock-row .down { color: var(--quote-down); }
.card-head { flex: none; height: 43px; display: flex; align-items: center; gap: 6px; border-bottom: 1px solid var(--border); }
.member-panel { flex: 1; display: flex; flex-direction: column; min-height: 180px; overflow: hidden; background: var(--bg-panel); }
.member-table { overflow: auto; flex: 1; min-height: 0; }
.member-grid { display: grid; grid-template-columns: 62px minmax(100px, 1fr) 70px 76px 70px 83px 75px 88px; min-width: 800px; align-items: center; gap: 8px; padding: 0 12px; }
.member-sorts { position: sticky; top: 0; z-index: 1; height: 36px; background: var(--bg-panel-2); color: var(--text-secondary); }
.member-sorts button { text-align: right; padding: 0; font-size: 11px; }.member-sorts button:first-child { text-align: left; }
.stock-insights { overflow: auto; flex: 1; min-height: 0; border-top: 1px solid var(--border); }
.card-name { padding: 3px; font-weight: 700; }
.card-name.selected::before { content: '●'; color: var(--blueprint-up); font-size: 8px; margin-right: 5px; }
.weight-label, .compare { white-space: nowrap; color: var(--blueprint-link); background: var(--accent-soft); border: 1px solid var(--border-strong); border-radius: 4px; padding: 3px 5px; font-size: 10px; }
.compare { margin-left: auto; }
.quote { min-width: 66px; text-align: center; background: var(--bg-panel-2); border: 1px solid var(--border); padding: 3px 6px; border-radius: 4px; white-space: nowrap; }
.quote.up { background: var(--up-soft); }.quote.down { background: var(--down-soft); }
.stock-chart { flex: 0 0 43%; min-height: 225px; display: flex; flex-direction: column; padding: 6px 6px 0; overflow: hidden; }
.stock-chart > strong, .intraday > strong { flex: none; padding: 0 3px; }
.stock-row.member-grid { min-height: 39px; border-bottom: 1px solid var(--border); font-size: 12px; }
.stock-row strong { color: var(--quote-highlight); }
.source { display: flex; gap: 7px; align-items: center; padding: 5px 8px; border-top: 1px solid var(--border); }.source button { margin-left: auto; }
.empty { padding: 12px; color: var(--text-secondary); text-align: center; }.state { margin-top: 24px; }.state button { color: var(--blueprint-link); text-decoration: underline; }
.intraday { position: fixed; z-index: 20; width: min(420px, calc(100vw - 16px)); height: 214px; display: flex; flex-direction: column; gap: 4px; padding: 8px; background: var(--bg-panel); border: 1px solid var(--border-strong); border-radius: 7px; box-shadow: var(--shadow); pointer-events: none; }
dialog { color: var(--text); background: var(--bg-panel); padding: 0; border: 1px solid var(--border-strong); border-radius: 8px; }
dialog::backdrop { background: #23344950; }.compare-dialog { width: min(96vw, 1650px); max-width: none; margin: auto auto 36px; }
.compare-dialog .panel-head button { padding: 5px 8px; }.compare-dialog .panel-head small { margin-left: auto; }
.compare-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 8px; padding: 8px; background: var(--blueprint-workspace); }
.compare-grid article { height: 235px; padding: 8px; display: flex; flex-direction: column; background: var(--bg-panel); border-radius: 5px; }
.compare-grid article header { display: flex; justify-content: space-between; }
@media (max-width: 1080px) {
  .blueprint { grid-template-columns: 105px minmax(150px, 22%) minmax(0, 1fr); overflow: auto; grid-template-rows: minmax(650px, 1fr) 750px; }
  .constituents { grid-column: 1 / -1; }.algorithms strong { display: none; }
}
@media (max-width: 650px) {
  .blueprint { display: flex; flex-direction: column; }
  .categories { flex: none; }.categories__list { display: flex; flex-wrap: wrap; }
  .boards { flex: none; max-height: 230px; }.indices { flex: none; height: 760px; }.constituents { flex: none; height: 800px; }
  .index-toolbar { padding: 0 4px; }.segmented button, .ranking button, .ranking select { padding-inline: 3px; }
}
</style>

<style scoped>
.embedded-trends { grid-column: 3 / -1; min-width: 0; min-height: 0; overflow: hidden; }
@media (max-width: 1080px) {
  .blueprint.blueprint--trends { grid-template-rows: minmax(510px, 1fr); }
}
@media (max-width: 767px), (max-width: 1023px) and (max-height: 500px) and (pointer: coarse) {
  .blueprint { display: flex; flex-direction: column; gap: 8px; overflow: visible; }
  .blueprint > .panel { height: auto; flex: none; }
  .categories__list { display: flex; flex-wrap: wrap; }
  .categories__list button, .board-picker, .compare { min-height: var(--touch-target); }
  .boards .rows { display: none; }
  .board-picker { margin: 4px 12px; border: 1px solid var(--border); font-size: 16px; }
  .index-toolbar, .card-head, .compare-dialog .panel-head { height: auto; min-height: 44px; flex-wrap: wrap; white-space: normal; }
  .index-toolbar { padding: 4px 8px; }
  .algorithms, .segmented, .ranking { flex-wrap: wrap; }
  .segmented button, .ranking button, .ranking select { min-height: var(--touch-target); }
  .selected-index { min-height: 290px; }
  .selected-index > :deep(.chart) { min-height: 235px; }
  .member-panel { flex: none; }
  .member-table { max-height: 420px; }
  .member-detail-link { color: var(--accent); padding: 10px 12px; }
  .stock-row.member-grid { min-height: var(--touch-target); }
  .stock-chart { flex: none; height: 270px; }
  .stock-insights { overflow: visible; }
  .compare-dialog { width: calc(100% - 24px); margin: auto; }
  .compare-grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
