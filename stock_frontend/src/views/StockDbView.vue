<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import StockDbChart from '@/components/stockdb/StockDbChart.vue'
import {
  algorithms, barReturn, categories, percent,
  type Bar, type Board, type BoardDetail, type Category, type Home, type Member,
  type Members, type Ranking, type Weight, type Workspace,
} from '@/api/stockdb'
import { cachedStockDb, fetchStockDb, peekCache, putCache, readCache, StockDbHttpError } from '@/api/stockdbCache'

interface CustomIndex { id: string; name: string; codes: string[] }
const storageKey = 'stockdb-custom-indices-v1'
function readCustom(): CustomIndex[] {
  try {
    const stored: unknown = JSON.parse(localStorage.getItem(storageKey) ?? '[]')
    return Array.isArray(stored) ? stored.filter((item) =>
      typeof item?.id === 'string' && typeof item?.name === 'string' && Array.isArray(item?.codes) &&
      item.codes.length > 0 && item.codes.length <= 1000 &&
      item.codes.every((code: unknown) => typeof code === 'string' && /^\d{6}$/.test(code)),
    ).slice(0, 20) : []
  } catch { return [] }
}

const screen = shallowRef(peekCache<Workspace>('last-workspace'))
function readPreferences() {
  try {
    const saved = JSON.parse(localStorage.getItem('stockdb-workspace-preferences-v2') ?? '{}')
    return {
      days: [1, 3, 5, 10, 15, 30].includes(saved.days) ? saved.days as number : 1,
      sort: saved.sort === 'return' ? 'return' as const : 'price' as const,
      memberSort: saved.memberSort === 'code' || saved.memberSort === 'price' ? saved.memberSort as 'code' | 'price' : 'return' as const,
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
const memberSort = ref<'return' | 'price' | 'code'>(preferences.memberSort)
const memberAscending = ref(preferences.memberAscending)
const custom = ref(readCustom())
const ready = ref(false)
const loading = ref(false)
const refreshing = ref(false)
const error = ref('')
const pinnedBoard = ref(Boolean(screen.value?.boardId))
const cardScroll = ref(0)
const cards = ref<HTMLElement | null>(null)
const boardList = ref<HTMLElement | null>(null)
const memberList = ref<HTMLElement | null>(null)
const drawer = ref<HTMLDialogElement | null>(null)
const editor = ref<HTMLDialogElement | null>(null)
const compareBoard = shallowRef<Board | null>(null)
const comparison = shallowRef<BoardDetail | null>(null)
const customId = ref('')
const customName = ref('')
const customCodes = ref('')
const editorError = ref('')
const cardHeight = 338
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

function rank(items: Board[]) {
  return items.map((board) => ({ ...board, change: board.changes[String(days.value)] ?? null })).sort((a, b) =>
    (b[sort.value === 'price' ? 'price' : 'change'] ?? -Infinity) -
    (a[sort.value === 'price' ? 'price' : 'change'] ?? -Infinity) || a.name.localeCompare(b.name, 'zh-CN'),
  )
}
const ranked = computed(() => rank(boards.value))
const firstCard = computed(() => Math.max(0, Math.floor(cardScroll.value / cardHeight) - 1))
const visibleCards = computed(() => ranked.value.slice(firstCard.value, firstCard.value + 10).map((board) => ({
  ...board, bars: screen.value?.charts[board.id] ?? [],
})))
const members = computed(() => [...(detail.value?.members ?? [])].sort((a, b) => {
  const key = memberSort.value
  const value = key === 'code' ? a.code.localeCompare(b.code)
    : key === 'price' ? a.bar[4] - b.bar[4] : (barReturn([a.bar], 1) ?? 0) - (barReturn([b.bar], 1) ?? 0)
  return (memberAscending.value ? value : -value) || a.code.localeCompare(b.code)
}))
const currentStock = computed(() => members.value.find((stock) => stock.code === stockCode.value))

let disposed = false
let workspaceRequest = 0
let memberRequest = 0
let stockRequest = 0
let chartRequest = 0
let compareRequest = 0
let persistTimer: ReturnType<typeof setTimeout> | undefined
let statusTimer: ReturnType<typeof setInterval> | undefined

function workspaceKey(group: Category, method: Weight) {
  return 'workspace:' + group + ':' + method + (group === 'custom' ? ':' + JSON.stringify(custom.value) : '')
}
function rememberWorkspace(value: Workspace) {
  screen.value = value
  clearTimeout(persistTimer)
  persistTimer = setTimeout(() => {
    putCache('last-workspace', value)
    putCache(workspaceKey(value.category, value.weight), value)
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
    version, selected, order: memberSort.value, ascending: String(memberAscending.value),
  })
}

function ownIndex(id: string) { return custom.value.find((item) => item.id === id) }

async function loadDetail(id: string, version: string) {
  const own = ownIndex(id)
  return cachedStockDb<BoardDetail & { date: number; detail: Members }>(
    own ? '/custom?' + versionQuery(version) : '/boards/' + encodeURIComponent(id) + '?' + versionQuery(version),
    own?.codes,
  )
}

async function buildWorkspace(group: Category, method: Weight): Promise<Workspace> {
  if (group === 'sw1' && method === 'equal' && sort.value === 'price' && !pinnedBoard.value) {
    const home = await fetchStockDb<Home>('/home')
    for (const [id, bars] of Object.entries(home.charts)) putCache(`curve:${home.version}:equal:${id}`, bars)
    return { ...home, category: group, weight: method }
  }
  if (group === 'custom') {
    if (!custom.value.length) return {
      version: screen.value?.version ?? '', date: screen.value?.date ?? 0,
      category: group, weight: method, boards: [], charts: {}, boardId: '',
      detail: { members: [], count: 0, stockCode: '', stockBars: [] },
    }
    const localBoards: Board[] = []
    const charts: Record<string, Bar[]> = {}
    let version = ''
    let sessionDate = 0
    let firstDetail: Members | undefined
    const wanted = ownIndex(boardId.value)?.id ?? custom.value[0]!.id
    // User-created sets are evaluated only while this category is open.
    for (const item of custom.value) {
      const payload = await fetchStockDb<BoardDetail & { date: number; detail: Members }>(
        '/custom' + (version ? '?' + versionQuery(version) : ''), item.codes,
      )
      version = payload.version
      sessionDate = payload.date
      const bars = payload.indices[method]
      charts[item.id] = bars
      const changes: Record<string, number | null> = {}
      for (const [period] of windows) changes[String(period)] = barReturn(bars, period)
      localBoards.push({ id: item.id, name: item.name, count: item.codes.length, price: bars.at(-1)?.[4] ?? null, changes })
      if (item.id === wanted) firstDetail = payload.detail
    }
    return {
      version, date: sessionDate, category: group, weight: method, boards: localBoards, charts,
      boardId: wanted, detail: firstDetail!,
    }
  }

  const ranking = await fetchStockDb<Ranking>(
    '/ranking?' + new URLSearchParams({ category: group, weight: method }),
  )
  const ordered = rank(ranking.boards)
  const selected = pinnedBoard.value && ranking.boards.some((board) => board.id === boardId.value)
    ? boardId.value : ordered[0]?.id ?? ''
  const selectedStock = selected === boardId.value ? stockCode.value : ''
  const start = screen.value?.category === group && screen.value.weight === method ? firstCard.value : 0
  const [charts, detail] = await Promise.all([
    curves(ranking.version, method, ordered.slice(start, start + 10).map((board) => board.id)),
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
  loading.value = true
  error.value = ''
  clearHover()
  try {
    const saved = await readCache<Workspace>(workspaceKey(group, method))
    if (request !== workspaceRequest || disposed) return
    if (saved && rank(saved.boards).slice(0, 10).every((board) => saved.charts[board.id]) &&
      (saved.category !== shownCategory.value || saved.weight !== shownWeight.value || !screen.value)) {
      screen.value = saved
    }
    const value = await buildWorkspace(group, method)
    if (request !== workspaceRequest || disposed) return
    const changed = shownCategory.value !== group || shownWeight.value !== method
    const previous = screen.value
    rememberWorkspace({
      ...value,
      charts: previous?.version === value.version && previous.weight === value.weight
        ? { ...previous.charts, ...value.charts } : value.charts,
    })
    if (changed) {
      cardScroll.value = 0
      cards.value?.scrollTo(0, 0)
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
  if (!current || current.boardId === id) return
  if (loading.value && (current.category !== category.value || current.weight !== weight.value)) return
  const request = ++memberRequest
  workspaceRequest++
  loading.value = false
  stockRequest++
  pinnedBoard.value = true
  clearHover()
  try {
    const own = ownIndex(id)
    const next = own ? (await loadDetail(id, current.version)).detail
      : await cachedStockDb<Members>(bundlePath(id, current.version))
    if (request !== memberRequest || disposed || screen.value?.version !== current.version ||
      screen.value.category !== current.category || screen.value.weight !== current.weight) return
    rememberWorkspace({ ...screen.value, boardId: id, detail: next })
    memberList.value?.scrollTo(0, 0)
  } catch (cause) {
    if (request !== memberRequest || disposed) return
    if (cause instanceof StockDbHttpError && cause.status === 409) void loadWorkspace()
    else error.value = (cause as Error).message
  }
}

async function selectStock(code: string) {
  const current = screen.value
  if (!current || current.detail.stockCode === code) return
  if (loading.value && (current.category !== category.value || current.weight !== weight.value)) return
  const request = ++stockRequest
  workspaceRequest++
  loading.value = false
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

async function visibleCurves() {
  const current = screen.value
  if (!current || current.category === 'custom') return
  const request = ++chartRequest
  try {
    const data = await curves(current.version, current.weight, visibleCards.value.map((board) => board.id))
    if (disposed || request !== chartRequest || screen.value?.version !== current.version ||
      screen.value.category !== current.category || screen.value.weight !== current.weight) return
    if (Object.keys(data).some((id) => !screen.value!.charts[id])) {
      rememberWorkspace({ ...screen.value, charts: { ...screen.value.charts, ...data } })
    }
  } catch (cause) {
    if (disposed || request !== chartRequest) return
    if (cause instanceof StockDbHttpError && cause.status === 409) void loadWorkspace()
    else error.value = '部分曲线暂未更新。'
  }
}

watch([category, weight, custom], ([group], previous) => {
  if (!ready.value) return
  if (group !== previous[0]) pinnedBoard.value = false
  void loadWorkspace()
})
watch([days, sort], () => {
  cardScroll.value = 0
  cards.value?.scrollTo(0, 0)
  boardList.value?.scrollTo(0, 0)
  void visibleCurves()
})
watch(firstCard, () => { void visibleCurves() })
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
        undefined, 60000,
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

function edit(item?: CustomIndex) {
  customId.value = item?.id ?? ''
  customName.value = item?.name ?? ''
  customCodes.value = item?.codes.join(' ') ?? ''
  editorError.value = ''
  editor.value?.showModal()
}
function persist(next: CustomIndex[]) {
  try { localStorage.setItem(storageKey, JSON.stringify(next)) }
  catch { editorError.value = '浏览器无法保存自定义指数。'; return false }
  custom.value = next
  editor.value?.close()
  return true
}
function save() {
  const name = customName.value.trim()
  const codes = [...new Set(customCodes.value.trim().split(/[\s,，;；、]+/).filter(Boolean))]
  if (!name || !codes.length || codes.length > 1000 || codes.some((code) => !/^\d{6}$/.test(code))) {
    editorError.value = '请输入名称和 1 至 1000 个六位股票代码。'
    return
  }
  const id = customId.value || 'custom-' + crypto.randomUUID()
  const own = { id, name, codes }
  const items = custom.value.some((item) => item.id === id)
    ? custom.value.map((item) => item.id === id ? own : item) : [...custom.value, own]
  persist(items)
}
function removeCustom() { persist(custom.value.filter((item) => item.id !== customId.value)) }

onMounted(async () => {
  const saved = screen.value ?? await readCache<Workspace>('last-workspace')
  if (disposed) return
  if (saved && category.value === (screen.value?.category ?? 'sw1') && weight.value === (screen.value?.weight ?? 'equal')) {
    screen.value = saved
    category.value = saved.category
    weight.value = saved.weight
    pinnedBoard.value = Boolean(saved.boardId)
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
  <div class="blueprint">
    <aside class="panel categories">
      <header class="panel-head"><strong>分类</strong></header>
      <div class="categories__list">
        <button v-for="[id, label] in categories" :key="id" :class="{ active: shownCategory === id }"
          :aria-pressed="shownCategory === id" @click="category = id">{{ label }}</button>
      </div>
    </aside>

    <aside class="panel boards">
      <header class="panel-head"><strong>{{ categoryName }}</strong><small>{{ boards.length }} {{ shownCategory === 'custom' ? '个指数' : '个板块' }}</small></header>
      <div v-if="shownCategory === 'custom'" class="custom-actions">
        <button :disabled="custom.length >= 20" @click="edit()">＋ 新建指数</button>
        <button v-if="currentBoard" @click="edit(custom.find((item) => item.id === currentBoard?.id))">编辑所选</button>
      </div>
      <div ref="boardList" class="rows">
        <button v-for="board in ranked" :key="board.id" class="board-row" :class="{ active: boardId === board.id }"
          :aria-pressed="boardId === board.id" :title="board.name" @click="selectBoard(board.id)" @dblclick="compare(board)">
          <span class="ellipsis">{{ board.name }}</span><small>{{ board.count }}</small>
          <strong :class="color(board.change)">{{ formatReturn(board.change) }}</strong>
        </button>
        <p v-if="!loading && !error && !boards.length" class="empty">{{ shownCategory === 'custom' ? '暂无自定义指数' : '暂无板块' }}</p>
      </div>
    </aside>

    <section class="panel indices">
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
      <div v-if="screen && !loading && !ranked.length" class="empty state">选择板块或新建自定义指数</div>
      <div ref="cards" class="cards" @scroll.passive="cardScroll = ($event.target as HTMLElement).scrollTop">
        <div :style="{ height: ranked.length * cardHeight + 'px', position: 'relative' }">
          <div class="card-window" :style="{ top: firstCard * cardHeight + 'px' }">
            <article v-for="(board, i) in visibleCards" :key="board.id" class="card">
              <header class="card-head">
                <span class="rank" :class="`rank--${firstCard + i + 1}`">TOP {{ firstCard + i + 1 }}</span>
                <button class="card-name ellipsis" :class="{ selected: boardId === board.id }" :title="board.name"
                  @click="selectBoard(board.id)" @dblclick="compare(board)">{{ board.name }}</button>
                <span class="weight-label">{{ weightName }}{{ shownWeight === 'equal' ? '' : '加权' }}</span>
                <button class="compare" :aria-label="`${board.name}五维对比`" @click="compare(board)">五维</button>
                <strong class="quote">{{ board.price?.toFixed(2) ?? '—' }}</strong>
                <strong class="quote" :class="color(board.change)">{{ formatReturn(board.change) }}</strong>
              </header>
              <StockDbChart v-if="board.bars.length" :bars="board.bars.slice(-44)" :label="`${board.name}指数日 K`" amount />
            </article>
          </div>
        </div>
      </div>
    </section>

    <aside class="panel constituents">
      <header class="panel-head"><strong class="ellipsis">{{ currentBoard?.name ?? '板块股票' }}</strong>
        <small v-if="detail">{{ detail.members.length }}/{{ detail.count }} 只</small>
      </header>
      <div class="stock-chart">
        <strong v-if="currentStock">{{ currentStock.code }} · {{ currentStock.name }} 日 K</strong>
        <StockDbChart v-if="detail" :bars="stockBars" :label="`${currentStock?.name ?? ''}日 K`" />
      </div>
      <div class="member-sorts">
        <button v-for="[id, label] in ([['return', '涨跌幅'], ['price', '价格'], ['code', '代码']] as const)" :key="id"
          :class="{ active: memberSort === id }" :aria-pressed="memberSort === id" @click="setMemberSort(id)">
          {{ label }}{{ memberSort === id ? (memberAscending ? '↑' : '↓') : '' }}
        </button>
      </div>
      <div ref="memberList" class="rows" @scroll.passive="clearHover">
        <p v-if="detail && !members.length" class="empty">暂无成分股行情</p>
        <button v-for="stock in members" :key="stock.code" class="stock-row" :class="{ active: stockCode === stock.code }"
          :aria-pressed="stockCode === stock.code" @pointerenter="showIntraday(stock, $event)" @pointerleave="clearHover"
          @click="selectStock(stock.code)">
          <strong>{{ stock.code }}</strong><span class="ellipsis">{{ stock.name }}</span><span>{{ stock.bar[4].toFixed(2) }}</span>
          <span :class="color(barReturn([stock.bar], 1))">{{ formatReturn(barReturn([stock.bar], 1)) }}</span>
        </button>
      </div>
      <div class="source"><span>本地 stockdb</span><small v-if="date">{{ date }}</small>
        <small v-if="error" role="status" :title="error">暂未更新</small>
        <small v-else-if="loading || refreshing" role="status">后台更新中</small>
        <button :disabled="refreshing" @click="refresh">刷新</button>
      </div>
    </aside>

    <div v-if="hover" class="intraday" :style="{ left: hover.x + 'px', top: hover.y + 'px' }">
      <strong>{{ hover.stock.name }} · {{ hover.stock.bar[0] }} 分时</strong>
      <StockDbChart :bars="hover.bars" :label="`${hover.stock.name}分时`" minute :baseline="hover.stock.bar[7]" />
    </div>

    <dialog ref="drawer" class="compare-dialog" @close="compareRequest++">
      <header class="panel-head"><strong>{{ compareBoard?.name }} · 五维指数全景对比</strong>
        <small>{{ compareBoard?.count }} 只成分股</small><button aria-label="关闭对比" @click="drawer?.close()">✕</button>
      </header>
      <div v-if="comparison" class="compare-grid">
        <article v-for="[id, label] in algorithms" :key="id">
          <header><strong>{{ label }}</strong><span :class="color(barReturn(comparison.indices[id], days))">{{ formatReturn(barReturn(comparison.indices[id], days)) }}</span></header>
          <StockDbChart :bars="comparison.indices[id].slice(-44)" :label="label" amount />
        </article>
      </div>
    </dialog>

    <dialog ref="editor" class="edit-dialog">
      <form @submit.prevent="save">
        <header class="panel-head"><strong>{{ customId ? '编辑自定义指数' : '新建自定义指数' }}</strong></header>
        <label>指数名称 <input v-model="customName" maxlength="40" required /></label>
        <label>股票代码 <textarea v-model="customCodes" rows="5" required placeholder="例如 000001 600519，支持空格、逗号或换行" /></label>
        <p v-if="editorError" class="up" role="alert">{{ editorError }}</p>
        <footer>
          <button v-if="customId" class="up" type="button" @click="removeCustom">删除指数</button>
          <button type="button" @click="editor?.close()">取消</button><button class="primary" type="submit">保存</button>
        </footer>
      </form>
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
.blueprint { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(95px, 10.7%) minmax(170px, 19.3%) minmax(410px, 1fr) minmax(255px, 23.5%); background: var(--blueprint-workspace); color: var(--text); }
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
.custom-actions { padding: 6px; display: flex; gap: 5px; border-bottom: 1px solid var(--border); }
.custom-actions button, .source button { padding: 4px 7px; color: var(--blueprint-link); background: var(--accent-soft); }
.index-toolbar { gap: 6px; }
.algorithms, .segmented, .ranking { display: flex; align-items: center; gap: 3px; }
.algorithms strong, .segmented, .ranking { font-size: 11px; }
.segmented { background: var(--bg-hover); border-radius: 6px; padding: 3px; }
.segmented button, .ranking button, .ranking select { padding: 5px 7px; }
.segmented .active, .primary { background: #2455d7; color: #fff; font-weight: 700; }
.ranking .active, .member-sorts .active { font-weight: 700; text-decoration: underline; text-underline-offset: 4px; }
.indices { background: var(--blueprint-workspace); }
.index-toolbar { background: var(--bg-panel); }
.cards { flex: 1; min-height: 0; overflow: auto; padding: 10px 10px 0; }
.card-window { position: absolute; inset-inline: 0; }
.card { height: 328px; margin-bottom: 10px; padding: 0 9px 5px; display: flex; flex-direction: column; background: var(--bg-panel); border-radius: 7px; overflow: hidden; }
.card-head { flex: none; height: 43px; display: flex; align-items: center; gap: 6px; border-bottom: 1px solid var(--border); }
.rank { align-self: flex-start; margin-left: -9px; padding: 4px 8px; color: #fff; background: #57748e; font-size: 10px; white-space: nowrap; font-weight: 800; }
.rank--1 { background: #b90040; }.rank--2 { background: #bd4a13; }.rank--3 { background: #a76920; }
.card-name { padding: 3px; font-weight: 700; }
.card-name.selected::before { content: '●'; color: var(--blueprint-up); font-size: 8px; margin-right: 5px; }
.weight-label, .compare { white-space: nowrap; color: var(--blueprint-link); background: var(--accent-soft); border: 1px solid var(--border-strong); border-radius: 4px; padding: 3px 5px; font-size: 10px; }
.compare { margin-left: auto; }
.quote { min-width: 66px; text-align: center; background: var(--bg-panel-2); border: 1px solid var(--border); padding: 3px 6px; border-radius: 4px; white-space: nowrap; }
.quote.up { background: var(--up-soft); }.quote.down { background: var(--down-soft); }
.stock-chart { flex: none; height: 246px; display: flex; flex-direction: column; padding: 6px 6px 0; overflow: hidden; }
.stock-chart > strong, .intraday > strong { flex: none; padding: 0 3px; }
.member-sorts { display: flex; gap: 5px; padding: 5px 8px; border-block: 1px solid var(--border); }
.member-sorts button { padding: 4px 6px; font-size: 12px; }
.stock-row { grid-template-columns: 54px minmax(0, 1fr) 53px 64px; min-height: 34px; border-bottom: 1px solid var(--border); font-size: 12px; }
.stock-row strong { color: var(--blueprint-link); }
.source { display: flex; gap: 7px; align-items: center; padding: 5px 8px; border-top: 1px solid var(--border); }.source button { margin-left: auto; }
.empty { padding: 12px; color: var(--text-secondary); text-align: center; }.state { margin-top: 24px; }.state button { color: var(--blueprint-link); text-decoration: underline; }
.intraday { position: fixed; z-index: 20; width: min(420px, calc(100vw - 16px)); height: 214px; display: flex; flex-direction: column; gap: 4px; padding: 8px; background: var(--bg-panel); border: 1px solid var(--border-strong); border-radius: 7px; box-shadow: var(--shadow); pointer-events: none; }
dialog { color: var(--text); background: var(--bg-panel); padding: 0; border: 1px solid var(--border-strong); border-radius: 8px; }
dialog::backdrop { background: #23344950; }.compare-dialog { width: min(96vw, 1650px); max-width: none; margin: auto auto 36px; }
.compare-dialog .panel-head button { padding: 5px 8px; }.compare-dialog .panel-head small { margin-left: auto; }
.compare-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 8px; padding: 8px; background: var(--blueprint-workspace); }
.compare-grid article { height: 235px; padding: 8px; display: flex; flex-direction: column; background: var(--bg-panel); border-radius: 5px; }
.compare-grid article header { display: flex; justify-content: space-between; }
.edit-dialog { width: min(480px, 92vw); margin: auto; }.edit-dialog label, .edit-dialog footer, .edit-dialog p { display: block; margin: 12px; }
.edit-dialog input, .edit-dialog textarea { display: block; width: 100%; margin-top: 4px; padding: 7px; color: inherit; font: inherit; background: var(--bg-panel); border: 1px solid var(--border-strong); border-radius: 4px; }
.edit-dialog footer { display: flex; justify-content: flex-end; gap: 7px; }.edit-dialog button { padding: 6px 10px; }
@media (max-width: 1080px) {
  .blueprint { grid-template-columns: 105px minmax(150px, 22%) minmax(0, 1fr); overflow: auto; grid-template-rows: minmax(510px, 1fr) 440px; }
  .constituents { grid-column: 1 / -1; }.algorithms strong { display: none; }
}
@media (max-width: 650px) {
  .blueprint { display: flex; flex-direction: column; }
  .categories { flex: none; }.categories__list { display: flex; flex-wrap: wrap; }
  .boards { flex: none; max-height: 230px; }.indices { flex: none; height: 550px; }.constituents { flex: none; height: 440px; }
  .index-toolbar { padding: 0 4px; }.segmented button, .ranking button, .ranking select { padding-inline: 3px; }
}
</style>
