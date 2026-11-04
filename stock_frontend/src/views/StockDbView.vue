<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import StockDbChart from '@/components/stockdb/StockDbChart.vue'
import {
  algorithms, barReturn, categories, percent, stockDbRequest,
  type Bar, type Board, type BoardDetail, type Category, type Member, type Weight,
} from '@/api/stockdb'

interface CustomIndex { id: string; name: string; codes: string[] }
const storageKey = 'stockdb-custom-indices-v1'
function readCustom(): CustomIndex[] {
  try {
    const stored: unknown = JSON.parse(localStorage.getItem(storageKey) ?? '[]')
    return Array.isArray(stored) ? stored.filter((item) =>
      typeof item?.id === 'string' && typeof item?.name === 'string' && Array.isArray(item?.codes) &&
      item.codes.length > 0 && item.codes.length <= 1000 && item.codes.every((code: unknown) => typeof code === 'string' && /^\d{6}$/.test(code)),
    ).slice(0, 20) : []
  } catch { return [] }
}

const category = ref<Category>('sw1')
const weight = ref<Weight>('equal')
const days = ref(1)
const sort = ref<'price' | 'return'>('price')
const memberSort = ref<'return' | 'price' | 'code'>('return')
const memberAscending = ref(false)
const custom = ref(readCustom())
const boards = shallowRef<Board[]>([])
const date = ref(0)
const boardId = ref('')
const pinnedBoard = ref(false)
const detail = shallowRef<BoardDetail | null>(null)
const stockCode = ref('')
const stockBars = shallowRef<Bar[]>([])
const loading = ref(false)
const loadingDetail = ref(false)
const loadingStock = ref(false)
const error = ref('')
const detailError = ref('')
const stockError = ref('')
const reload = ref(0)
const cardScroll = ref(0)
const cards = ref<HTMLElement | null>(null)
const boardList = ref<HTMLElement | null>(null)
const memberList = ref<HTMLElement | null>(null)
const drawer = ref<HTMLDialogElement | null>(null)
const editor = ref<HTMLDialogElement | null>(null)
const compareBoard = shallowRef<Board | null>(null)
const comparison = shallowRef<BoardDetail | null>(null)
const compareError = ref('')
const customId = ref('')
const customName = ref('')
const customCodes = ref('')
const editorError = ref('')
const cache = new Map<string, { date: number; boards: Board[] }>()
const details = new Map<string, BoardDetail>()
const daily = new Map<string, Bar[]>()
const intraday = new Map<string, Bar[]>()
const cardHeight = 338
const windows = [[1, '今日涨幅'], [3, '3日涨幅'], [5, '5日涨幅'], [10, '10日涨幅'], [15, '15日涨幅'], [30, '30日涨幅']] as const

const categoryName = computed(() => categories.find(([id]) => id === category.value)?.[1])
const weightName = computed(() => algorithms.find(([id]) => id === weight.value)?.[1])
const currentBoard = computed(() => boards.value.find((board) => board.id === boardId.value))
const ranked = computed(() => boards.value.map((board) => ({
  ...board, price: board.bars.at(-1)?.[4] ?? null, change: barReturn(board.bars, days.value),
})).sort((a, b) => (b[sort.value === 'price' ? 'price' : 'change'] ?? -Infinity) -
  (a[sort.value === 'price' ? 'price' : 'change'] ?? -Infinity) || a.name.localeCompare(b.name, 'zh-CN')))
const firstCard = computed(() => Math.max(0, Math.floor(cardScroll.value / cardHeight) - 1))
const visibleCards = computed(() => ranked.value.slice(firstCard.value, firstCard.value + 10))
const members = computed(() => [...(detail.value?.members ?? [])].sort((a, b) => {
  const key = memberSort.value
  const value = key === 'code' ? a.code.localeCompare(b.code)
    : key === 'price' ? a.bar[4] - b.bar[4] : (barReturn([a.bar], 1) ?? 0) - (barReturn([b.bar], 1) ?? 0)
  return (memberAscending.value ? value : -value) || a.code.localeCompare(b.code)
}))
const currentStock = computed(() => members.value.find((stock) => stock.code === stockCode.value))

async function loadDetail(id: string, signal: AbortSignal) {
  const saved = details.get(id)
  if (saved) return saved
  const own = custom.value.find((item) => item.id === id)
  const result = await stockDbRequest<BoardDetail>(own ? '/custom' : '/boards/' + encodeURIComponent(id), signal, own?.codes)
  if (!signal.aborted) details.set(id, result)
  return result
}

watch([category, weight, custom, reload], async ([group, method, own], old, onCleanup) => {
  const controller = new AbortController()
  onCleanup(() => controller.abort())
  const { signal } = controller
  if (group !== old?.[0]) {
    boards.value = []
    boardId.value = ''
    pinnedBoard.value = false
  }
  loading.value = true
  error.value = ''
  try {
    if (group === 'custom') {
      const items = await Promise.all(own.map(async (item) => {
        const result = await loadDetail(item.id, signal)
        return { id: item.id, name: item.name, count: result.count, bars: result.indices[method] }
      }))
      if (signal.aborted) return
      boards.value = items
    } else {
      const key = group + ':' + method
      const result = cache.get(key) ?? await stockDbRequest<{ date: number; boards: Board[] }>(
        '/boards?' + new URLSearchParams({ category: group, weight: method }), signal,
      )
      if (signal.aborted) return
      cache.set(key, result)
      date.value = result.date
      boards.value = result.boards
    }
    if (!boards.value.some((board) => board.id === boardId.value)) boardId.value = ranked.value[0]?.id ?? ''
  } catch (cause) {
    if (!signal.aborted) error.value = (cause as Error).message
  } finally {
    if (!signal.aborted) loading.value = false
  }
}, { immediate: true })

watch([boardId, reload], async ([id], _, onCleanup) => {
  const controller = new AbortController()
  onCleanup(() => controller.abort())
  clearHover()
  detail.value = null
  detailError.value = ''
  stockCode.value = ''
  loadingDetail.value = Boolean(id)
  if (!id) return
  try {
    const result = await loadDetail(id, controller.signal)
    if (controller.signal.aborted) return
    detail.value = result
    stockCode.value = members.value[0]?.code ?? ''
    memberList.value?.scrollTo(0, 0)
  } catch (cause) {
    if (!controller.signal.aborted) detailError.value = (cause as Error).message
  } finally {
    if (!controller.signal.aborted) loadingDetail.value = false
  }
})

watch(stockCode, async (code, _, onCleanup) => {
  const controller = new AbortController()
  onCleanup(() => controller.abort())
  stockBars.value = []
  stockError.value = ''
  loadingStock.value = Boolean(code)
  if (!code) return
  try {
    const result = daily.get(code) ?? (await stockDbRequest<{ bars: Bar[] }>('/stocks/' + code, controller.signal)).bars
    if (controller.signal.aborted) return
    daily.set(code, result)
    stockBars.value = result.slice(-45)
  } catch (cause) {
    if (!controller.signal.aborted) stockError.value = (cause as Error).message
  } finally {
    if (!controller.signal.aborted) loadingStock.value = false
  }
})

watch([category, weight, days, sort], () => {
  cardScroll.value = 0
  cards.value?.scrollTo(0, 0)
  boardList.value?.scrollTo(0, 0)
})
watch(ranked, (items) => {
  if (!pinnedBoard.value) boardId.value = items[0]?.id ?? ''
})

function selectBoard(id: string) {
  pinnedBoard.value = true
  boardId.value = id
}
function setMemberSort(key: typeof memberSort.value) {
  memberAscending.value = memberSort.value === key ? !memberAscending.value : key === 'code'
  memberSort.value = key
  memberList.value?.scrollTo(0, 0)
  clearHover()
}
function refresh() {
  cache.clear()
  details.clear()
  daily.clear()
  intraday.clear()
  clearHover()
  reload.value++
}
function color(value: number | null) { return value === null || value === 0 ? '' : value > 0 ? 'up' : 'down' }
function formatReturn(value: number | null) { return value === null ? '—' : percent(value) }

const hover = shallowRef<{ stock: Member; x: number; y: number; bars?: Bar[]; error?: string } | null>(null)
let hoverTimer: ReturnType<typeof setTimeout> | undefined
let hoverController: AbortController | undefined
function clearHover() {
  clearTimeout(hoverTimer)
  hoverController?.abort()
  hover.value = null
}
function showIntraday(stock: Member, event: PointerEvent) {
  if (event.pointerType === 'touch') return
  clearHover()
  const bounds = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const x = Math.max(8, Math.min(innerWidth - Math.min(420, innerWidth - 16) - 8, bounds.left - 290))
  const y = Math.max(8, Math.min(innerHeight - 225, bounds.top - 210))
  hoverTimer = setTimeout(async () => {
    const controller = new AbortController()
    hoverController = controller
    const position = { stock, x, y }
    hover.value = position
    const key = stock.code + ':' + stock.bar[0]
    try {
      const bars = intraday.get(key) ?? await stockDbRequest<Bar[]>(
        `/stocks/${stock.code}/minutes?date=${stock.bar[0]}`, controller.signal,
      )
      if (controller.signal.aborted) return
      intraday.set(key, bars)
      hover.value = { ...position, bars }
    } catch (cause) {
      if (!controller.signal.aborted) hover.value = { ...position, error: (cause as Error).message }
    }
  }, 240)
}

let compareController: AbortController | undefined
async function compare(board: Board) {
  compareController?.abort()
  compareController = new AbortController()
  const { signal } = compareController
  compareBoard.value = board
  comparison.value = null
  compareError.value = ''
  if (!drawer.value?.open) drawer.value?.showModal()
  try {
    const result = await loadDetail(board.id, signal)
    if (!signal.aborted) comparison.value = result
  } catch (cause) {
    if (!signal.aborted) compareError.value = (cause as Error).message
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
  details.delete(customId.value)
  custom.value = next
  editor.value?.close()
  return true
}
async function save() {
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
  if (persist(items)) {
    boardId.value = ''
    await nextTick()
    selectBoard(id)
  }
}
function removeCustom() {
  if (persist(custom.value.filter((item) => item.id !== customId.value))) {
    pinnedBoard.value = false
    boardId.value = ''
  }
}

onBeforeUnmount(() => { clearHover(); compareController?.abort() })
</script>

<template>
  <div class="blueprint">
    <aside class="panel categories">
      <header class="panel-head"><strong>分类</strong></header>
      <div class="categories__list">
        <button v-for="[id, label] in categories" :key="id" :class="{ active: category === id }"
          :aria-pressed="category === id" @click="category = id">{{ label }}</button>
      </div>
    </aside>

    <aside class="panel boards">
      <header class="panel-head"><strong>{{ categoryName }}</strong><small>{{ boards.length }} {{ category === 'custom' ? '个指数' : '个板块' }}</small></header>
      <div v-if="category === 'custom'" class="custom-actions">
        <button :disabled="custom.length >= 20" @click="edit()">＋ 新建指数</button>
        <button v-if="currentBoard" @click="edit(custom.find((item) => item.id === currentBoard?.id))">编辑所选</button>
      </div>
      <div ref="boardList" class="rows">
        <button v-for="board in ranked" :key="board.id" class="board-row" :class="{ active: boardId === board.id }"
          :aria-pressed="boardId === board.id" :title="board.name" @click="selectBoard(board.id)" @dblclick="compare(board)">
          <span class="ellipsis">{{ board.name }}</span><small>{{ board.count }}</small>
          <strong :class="color(board.change)">{{ formatReturn(board.change) }}</strong>
        </button>
        <p v-if="!loading && !error && !boards.length" class="empty">{{ category === 'custom' ? '暂无自定义指数' : '暂无板块' }}</p>
      </div>
    </aside>

    <section class="panel indices">
      <header class="panel-head index-toolbar">
        <div class="algorithms"><strong>⚡ 指数算法</strong>
          <div class="segmented" aria-label="指数算法">
            <button v-for="[id, label] in algorithms" :key="id" :class="{ active: weight === id }"
              :aria-pressed="weight === id" @click="weight = id">{{ label }}</button>
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
      <div v-if="error" class="empty state" role="alert">{{ error }} <button @click="refresh">重试</button></div>
      <div v-else-if="loading" class="empty state" role="status">正在读取本地 RD 数据并计算指数…</div>
      <div v-else-if="!ranked.length" class="empty state">选择板块或新建自定义指数</div>
      <div v-else ref="cards" class="cards" @scroll.passive="cardScroll = ($event.target as HTMLElement).scrollTop">
        <div :style="{ height: ranked.length * cardHeight + 'px', position: 'relative' }">
          <div class="card-window" :style="{ top: firstCard * cardHeight + 'px' }">
            <article v-for="(board, i) in visibleCards" :key="board.id" class="card">
              <header class="card-head">
                <span class="rank" :class="`rank--${firstCard + i + 1}`">TOP {{ firstCard + i + 1 }}</span>
                <button class="card-name ellipsis" :class="{ selected: boardId === board.id }" :title="board.name"
                  @click="selectBoard(board.id)" @dblclick="compare(board)">{{ board.name }}</button>
                <span class="weight-label">{{ weightName }}{{ weight === 'equal' ? '' : '加权' }}</span>
                <button class="compare" :aria-label="`${board.name}五维对比`" @click="compare(board)">五维</button>
                <strong class="quote">{{ board.price?.toFixed(2) ?? '—' }}</strong>
                <strong class="quote" :class="color(board.change)">{{ formatReturn(board.change) }}</strong>
              </header>
              <StockDbChart :bars="board.bars.slice(-44)" :label="`${board.name}指数日 K`" amount />
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
        <div v-if="loadingStock" class="empty">正在加载日 K…</div>
        <div v-else-if="stockError" class="empty">{{ stockError }}</div>
        <StockDbChart v-else :bars="stockBars" :label="`${currentStock?.name ?? ''}日 K`" />
      </div>
      <div class="member-sorts">
        <button v-for="[id, label] in ([['return', '涨跌幅'], ['price', '价格'], ['code', '代码']] as const)" :key="id"
          :class="{ active: memberSort === id }" :aria-pressed="memberSort === id" @click="setMemberSort(id)">
          {{ label }}{{ memberSort === id ? (memberAscending ? '↑' : '↓') : '' }}
        </button>
      </div>
      <div ref="memberList" class="rows" @scroll.passive="clearHover">
        <p v-if="loadingDetail || detailError || !members.length" class="empty">{{ loadingDetail ? '正在读取成分股…' : detailError || '暂无成分股行情' }}</p>
        <button v-for="stock in members" :key="stock.code" class="stock-row" :class="{ active: stockCode === stock.code }"
          :aria-pressed="stockCode === stock.code" @pointerenter="showIntraday(stock, $event)" @pointerleave="clearHover"
          @click="stockCode = stock.code">
          <strong>{{ stock.code }}</strong><span class="ellipsis">{{ stock.name }}</span><span>{{ stock.bar[4].toFixed(2) }}</span>
          <span :class="color(barReturn([stock.bar], 1))">{{ formatReturn(barReturn([stock.bar], 1)) }}</span>
        </button>
      </div>
      <div class="source"><span>本地 stockdb</span><small v-if="date">{{ date }}</small><button @click="refresh">刷新</button></div>
    </aside>

    <div v-if="hover" class="intraday" :style="{ left: hover.x + 'px', top: hover.y + 'px' }">
      <strong>{{ hover.stock.name }} · {{ hover.stock.bar[0] }} 分时</strong>
      <StockDbChart v-if="hover.bars" :bars="hover.bars" :label="`${hover.stock.name}分时`" minute :baseline="hover.stock.bar[7]" />
      <div v-else class="empty">{{ hover.error || '正在加载分时…' }}</div>
    </div>

    <dialog ref="drawer" class="compare-dialog" @close="compareController?.abort()">
      <header class="panel-head"><strong>{{ compareBoard?.name }} · 五维指数全景对比</strong>
        <small>{{ compareBoard?.count }} 只成分股</small><button aria-label="关闭对比" @click="drawer?.close()">✕</button>
      </header>
      <div v-if="comparison" class="compare-grid">
        <article v-for="[id, label] in algorithms" :key="id">
          <header><strong>{{ label }}</strong><span :class="color(barReturn(comparison.indices[id], days))">{{ formatReturn(barReturn(comparison.indices[id], days)) }}</span></header>
          <StockDbChart :bars="comparison.indices[id].slice(-44)" :label="label" amount />
        </article>
      </div>
      <p v-else class="empty">{{ compareError || '正在计算五种指数…' }}</p>
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
.blueprint { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(95px, 10.7%) minmax(170px, 19.3%) minmax(410px, 1fr) minmax(255px, 23.5%); background: #eaf0f3; color: #192c39; color-scheme: light; }
.panel { display: flex; flex-direction: column; min-width: 0; min-height: 0; background: white; border-right: 1px solid #e6edf1; }
.panel-head { flex: none; height: 46px; display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 0 12px; border-bottom: 1px solid #e8eef1; white-space: nowrap; }
small, .source { color: #657882; font-size: 11px; }
button, select { font: inherit; background: transparent; color: inherit; border: 0; cursor: pointer; border-radius: 4px; }
button:disabled { opacity: .45; cursor: default; }
button:focus-visible, select:focus-visible { outline: 2px solid #2665aa; outline-offset: -2px; }
button:hover, .active { background: #e7f2fa; color: #1c638f; }
.categories__list { display: grid; padding: 6px 8px; gap: 5px; }
.categories__list button { padding: 10px; text-align: left; }
.categories__list .active { font-weight: 700; }
.rows { overflow: auto; min-height: 0; flex: 1; }
.board-row, .stock-row { display: grid; align-items: center; text-align: left; gap: 8px; width: 100%; padding: 0 10px; }
.boards .rows { padding: 6px 7px; }
.board-row { grid-template-columns: minmax(0, 1fr) 36px 64px; min-height: 39px; margin-bottom: 2px; }
.board-row.active { font-weight: 700; }
.board-row small { border-radius: 15px; text-align: center; background: #edf2f5; }
.board-row strong, .stock-row span:nth-child(n + 3) { text-align: right; font-size: 12px; font-variant-numeric: tabular-nums; }
.ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.up { color: #bb2544; }
.down { color: #12835e; }
.custom-actions { padding: 6px; display: flex; gap: 5px; border-bottom: 1px solid #e8eef1; }
.custom-actions button, .source button { padding: 4px 7px; color: #216491; background: #edf5fb; }
.index-toolbar { gap: 6px; }
.algorithms, .segmented, .ranking { display: flex; align-items: center; gap: 3px; }
.algorithms strong, .segmented, .ranking { font-size: 11px; }
.segmented { background: #edf2f7; border-radius: 6px; padding: 3px; }
.segmented button, .ranking button, .ranking select { padding: 5px 7px; }
.segmented .active, .primary { background: #2455d7; color: #fff; font-weight: 700; }
.ranking .active, .member-sorts .active { font-weight: 700; text-decoration: underline; text-underline-offset: 4px; }
.indices { background: #e8eff2; }
.index-toolbar { background: white; }
.cards { flex: 1; min-height: 0; overflow: auto; padding: 10px 10px 0; }
.card-window { position: absolute; inset-inline: 0; }
.card { height: 328px; margin-bottom: 10px; padding: 0 9px 5px; display: flex; flex-direction: column; background: #fff; border-radius: 7px; overflow: hidden; }
.card-head { flex: none; height: 43px; display: flex; align-items: center; gap: 6px; border-bottom: 1px solid #eff2f4; }
.rank { align-self: flex-start; margin-left: -9px; padding: 4px 8px; color: #fff; background: #57748e; font-size: 10px; white-space: nowrap; font-weight: 800; }
.rank--1 { background: #b90040; }.rank--2 { background: #bd4a13; }.rank--3 { background: #a76920; }
.card-name { padding: 3px; font-weight: 700; }
.card-name.selected::before { content: '●'; color: #b32744; font-size: 8px; margin-right: 5px; }
.weight-label, .compare { white-space: nowrap; color: #2856a1; background: #edf4fc; border: 1px solid #cfdef5; border-radius: 4px; padding: 3px 5px; font-size: 10px; }
.compare { margin-left: auto; }
.quote { min-width: 66px; text-align: center; background: #f5f8f9; border: 1px solid #e5edf2; padding: 3px 6px; border-radius: 4px; white-space: nowrap; }
.quote.up { background: #fdf0f3; }.quote.down { background: #eaf8f2; }
.stock-chart { flex: none; height: 246px; display: flex; flex-direction: column; padding: 6px 6px 0; overflow: hidden; }
.stock-chart > strong, .intraday > strong { flex: none; padding: 0 3px; }
.member-sorts { display: flex; gap: 5px; padding: 5px 8px; border-block: 1px solid #edf1f4; }
.member-sorts button { padding: 4px 6px; font-size: 12px; }
.stock-row { grid-template-columns: 54px minmax(0, 1fr) 53px 64px; min-height: 34px; border-bottom: 1px solid #f2f5f6; font-size: 12px; }
.stock-row strong { color: #235e86; }
.source { display: flex; gap: 7px; align-items: center; padding: 5px 8px; border-top: 1px solid #edf1f4; }.source button { margin-left: auto; }
.empty { padding: 12px; color: #657882; text-align: center; }.state { margin-top: 24px; }.state button { color: #216491; text-decoration: underline; }
.intraday { position: fixed; z-index: 20; width: min(420px, calc(100vw - 16px)); height: 214px; display: flex; flex-direction: column; gap: 4px; padding: 8px; background: #fff; border: 1px solid #e4ebef; border-radius: 7px; box-shadow: 0 8px 28px #14273935; pointer-events: none; }
dialog { color: #192c39; background: #fff; padding: 0; border: 1px solid #d8e3eb; border-radius: 8px; }
dialog::backdrop { background: #23344950; }.compare-dialog { width: min(96vw, 1650px); max-width: none; margin: auto auto 36px; }
.compare-dialog .panel-head button { padding: 5px 8px; }.compare-dialog .panel-head small { margin-left: auto; }
.compare-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 8px; padding: 8px; background: #eaf0f3; }
.compare-grid article { height: 235px; padding: 8px; display: flex; flex-direction: column; background: white; border-radius: 5px; }
.compare-grid article header { display: flex; justify-content: space-between; }
.edit-dialog { width: min(480px, 92vw); margin: auto; }.edit-dialog label, .edit-dialog footer, .edit-dialog p { display: block; margin: 12px; }
.edit-dialog input, .edit-dialog textarea { display: block; width: 100%; margin-top: 4px; padding: 7px; color: inherit; font: inherit; background: white; border: 1px solid #c9d7df; border-radius: 4px; }
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
