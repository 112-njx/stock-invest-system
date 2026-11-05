<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { addWatchlist } from '@/api/market'
import { fetchStockDirectory, type StockDirectory } from '@/api/stockSearch'
import type { IndexedStock } from '@/utils/stockSearch'
import { useMarketStore } from '@/stores/market'
import { useUserStore } from '@/stores/user'
import { useWsStore } from '@/stores/wsStore'
import { useAuthModalStore } from '@/stores/authModal'
import { toast } from '@/utils/toast'

const market = useMarketStore()
const user = useUserStore()
const ws = useWsStore()
const authModal = useAuthModalStore()
const root = ref<HTMLElement>()
const list = ref<HTMLElement>()
const query = ref('')
const open = ref(false)
const composing = ref(false)
const loading = ref(false)
const error = ref(false)
const stale = ref(false)
const adding = ref('')
const active = ref(-1)
const scrollTop = ref(0)
const stocks = shallowRef<IndexedStock[]>([])
const directory = shallowRef<StockDirectory>()
let matcher: typeof import('@/utils/stockSearch') | undefined
let inflight: Promise<void> | undefined
let lastFetched = 0
let alive = true
const CACHE_KEY = 'stock-search-directory-v1'
const ROW_HEIGHT = 36
const VIEW_HEIGHT = 324
const results = computed(() => matcher ? matcher.filterStocks(stocks.value, query.value) : [])
const start = computed(() => Math.max(0, Math.floor(scrollTop.value / ROW_HEIGHT) - 4))
const visible = computed(() => results.value.slice(start.value, start.value + 18))
const watched = computed(() => new Set(market.watchlist.filter((s) => s.type === 'stock').map((s) => s.code)))
const markets = { SSE: '沪', SZSE: '深', BSE: '北' }

async function loadDirectory(force = false) {
  if (inflight) return inflight
  if (!force && Date.now() - lastFetched < 300000) return
  inflight = (async () => {
    loading.value = true
    error.value = false
    try {
      matcher = await import('@/utils/stockSearch')
      if (!directory.value) {
        try {
          const cached = JSON.parse(localStorage.getItem(CACHE_KEY) ?? 'null') as StockDirectory | null
          if (cached?.source === 'stockdb' && Array.isArray(cached.items) && cached.items.length &&
              cached.items.every((s) => s.type === 'stock' && typeof s.code === 'string' && typeof s.name === 'string')) {
            directory.value = cached
            stocks.value = matcher.indexStocks(cached.items)
            stale.value = true
          }
        } catch { /* An unavailable browser cache must not prevent the live request. */ }
      }
      const fresh = await fetchStockDirectory()
      if (!alive) return
      if (directory.value?.version !== fresh.version) stocks.value = matcher.indexStocks(fresh.items)
      directory.value = fresh
      stale.value = fresh.stale
      lastFetched = Date.now()
      try { localStorage.setItem(CACHE_KEY, JSON.stringify(fresh)) } catch { /* Storage can be disabled. */ }
    } catch {
      if (alive) { error.value = true; stale.value = stocks.value.length > 0 }
    } finally {
      loading.value = false
      inflight = undefined
    }
  })()
  return inflight
}

function show() {
  open.value = true
  void loadDirectory()
}
function closeOutside(event: PointerEvent) {
  if (!root.value?.contains(event.target as Node)) open.value = false
}
function onFocusOut(event: FocusEvent) {
  if (!root.value?.contains(event.relatedTarget as Node | null)) open.value = false
}
async function move(direction: number) {
  show()
  if (!results.value.length) return
  active.value = Math.max(0, Math.min(results.value.length - 1, active.value + direction))
  await nextTick()
  if (!list.value) return
  const top = active.value * ROW_HEIGHT
  if (top < list.value.scrollTop) list.value.scrollTop = top
  else if (top + ROW_HEIGHT > list.value.scrollTop + VIEW_HEIGHT) list.value.scrollTop = top + ROW_HEIGHT - VIEW_HEIGHT
  scrollTop.value = list.value.scrollTop
}
function onKey(event: KeyboardEvent) {
  if (event.isComposing || composing.value) return
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    void move(event.key === 'ArrowDown' ? 1 : -1)
  } else if (event.key === 'Escape') {
    open.value = false
  } else if (event.key === 'Enter' && open.value) {
    event.preventDefault()
    const item = results.value[active.value >= 0 ? active.value : 0]
    if (item) void pick(item)
  }
}
async function pick(stock: IndexedStock) {
  if (adding.value || watched.value.has(stock.code)) return
  if (!user.token) { authModal.show(); open.value = false; return }
  adding.value = stock.code
  try {
    const item = await addWatchlist(`stock:${stock.code}`)
    market.addWatchlistItem(item)
    ws.syncSubscriptions()
    query.value = ''
    open.value = false
    toast.success(`已添加 ${stock.name}`)
  } catch { /* The request handler displays the error. */ }
  finally { adding.value = '' }
}
watch(query, () => {
  active.value = -1
  scrollTop.value = 0
  if (list.value) list.value.scrollTop = 0
})
watch(() => directory.value?.version, () => { active.value = -1; scrollTop.value = 0; if (list.value) list.value.scrollTop = 0 })
onMounted(() => { document.addEventListener('pointerdown', closeOutside); void loadDirectory() })
onUnmounted(() => { alive = false; document.removeEventListener('pointerdown', closeOutside) })
</script>

<template>
  <div ref="root" class="stock-search" @focusout="onFocusOut">
    <input
      v-model="query" class="stock-search__input" type="text" maxlength="64"
      placeholder="股票名称 / 拼音 / 代码" aria-label="搜索股票名称、拼音或代码"
      role="combobox" aria-autocomplete="list" aria-controls="stock-search-options"
      :aria-expanded="open" :aria-activedescendant="open && active >= 0 && results[active] ? `stock-option-${results[active]?.code}` : undefined"
      autocomplete="off" @focus="show" @click="show" @keydown="onKey"
      @compositionstart="composing = true" @compositionend="composing = false"
    />
    <div v-if="open" class="stock-search__dropdown">
      <div class="stock-search__summary">
        <span>股票 {{ results.length }} / {{ stocks.length }}</span>
        <span v-if="loading">更新中…</span>
        <span v-else-if="stale" class="stock-search__warning">缓存目录 · 数据可能已更新</span>
        <span v-else>按代码排序</span>
      </div>
      <div v-if="error" class="stock-search__message" role="status">
        {{ stocks.length ? '本地服务暂不可用，正在使用缓存目录' : '无法加载股票目录，请确认 stockdb 已启动' }}
        <button type="button" class="stock-search__retry" @click="loadDirectory(true)">重试</button>
      </div>
      <div v-if="!stocks.length && loading" class="stock-search__message" role="status">正在加载本地股票目录…</div>
      <div v-else-if="stocks.length && !results.length" class="stock-search__message" role="status">未找到匹配股票</div>
      <div class="stock-search__heading" aria-hidden="true"><span>序号</span><span>代码</span><span>股票名称</span><span>市场</span><span>关注</span></div>
      <div
        id="stock-search-options" ref="list" class="stock-search__list" role="listbox" aria-label="本地股票"
        :style="{ height: `${Math.min(results.length * ROW_HEIGHT, VIEW_HEIGHT)}px` }"
        @scroll="scrollTop = ($event.target as HTMLElement).scrollTop"
      >
        <div :style="{ height: `${results.length * ROW_HEIGHT}px`, position: 'relative' }">
          <button
            v-for="(stock, offset) in visible" :id="`stock-option-${stock.code}`" :key="stock.code"
            class="stock-search__row" :class="{ 'is-active': active === start + offset }" type="button"
            role="option" :aria-selected="active === start + offset" :aria-disabled="watched.has(stock.code) || Boolean(adding)"
            tabindex="-1" :style="{ top: `${(start + offset) * ROW_HEIGHT}px` }"
            :title="`${stock.name} · 本地日 K 截至 ${stock.latest_date}`"
            @pointermove="active = start + offset" @mousedown.prevent @click="pick(stock)"
          >
            <span class="stock-search__muted">{{ stock.ordinal }}</span>
            <span>{{ stock.code }}</span><span class="stock-search__name">{{ stock.name }}</span>
            <span class="stock-search__muted">{{ markets[stock.market] }}</span>
            <span class="stock-search__action">{{ watched.has(stock.code) ? '已关注' : adding === stock.code ? '添加中' : '＋关注' }}</span>
          </button>
        </div>
      </div>
      <div v-if="directory" class="stock-search__footer">本地股票目录 · 最新交易日 {{ directory.latest_session }}</div>
    </div>
  </div>
</template>

<style scoped>
.stock-search { position: relative; width: clamp(180px, 20vw, 300px); min-width: 160px; }
.stock-search__input { width: 100%; height: 30px; padding: 0 10px; background: var(--bg-panel-2); border: 1px solid var(--border-strong); border-radius: 4px; color: var(--text); font-size: 12px; outline: none; }
.stock-search__input:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-soft); }
.stock-search__input::placeholder { color: var(--text-muted); }
.stock-search__dropdown { position: absolute; right: 0; top: calc(100% + 6px); z-index: 100; width: min(460px, calc(100vw - 32px)); background: var(--bg-panel); border: 1px solid var(--border-strong); border-radius: 6px; box-shadow: var(--shadow); overflow: hidden; }
.stock-search__summary { display: flex; justify-content: space-between; padding: 9px 12px; color: var(--text-secondary); font-size: 12px; border-bottom: 1px solid var(--border); }
.stock-search__heading, .stock-search__row { display: grid; grid-template-columns: 38px 64px minmax(0, 1fr) 30px 48px; align-items: center; gap: 8px; padding: 0 12px; text-align: left; }
.stock-search__heading { height: 28px; background: var(--bg-panel-2); color: var(--text-muted); font-size: 11px; }
.stock-search__list { overflow-y: auto; overscroll-behavior: contain; }
.stock-search__row { position: absolute; left: 0; width: 100%; height: 36px; font-size: 12px; color: var(--text); font-variant-numeric: tabular-nums; }
.stock-search__row:hover, .stock-search__row.is-active { background: var(--bg-hover); }
.stock-search__name { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.stock-search__muted { color: var(--text-muted); }
.stock-search__action, .stock-search__retry { color: var(--accent); font-size: 11px; }
.stock-search__message { padding: 12px; color: var(--text-secondary); font-size: 12px; }
.stock-search__retry { margin-left: 8px; }
.stock-search__warning { color: #d99b32; }
.stock-search__footer { padding: 7px 12px; font-size: 11px; color: var(--text-muted); border-top: 1px solid var(--border); }
</style>
