<script setup lang="ts">
/**
 * D/E 区 · 重点关注列表（可复用）：
 * - 行：代码/名称/最新价/涨跌幅（红涨绿跌），行点击切换 K 线标的
 * - 底部搜索栏：6 位代码实时联想（GET /symbols/search），选中添加关注
 * - 行内删除（DELETE /watchlist）
 */
import { computed, onMounted, ref, watch } from 'vue'
import {
  addWatchlist,
  fetchWatchlist,
  removeWatchlist,
  searchSymbols,
  type SymbolInfo,
  type WatchlistItem,
} from '@/api/market'
import { useMarketStore } from '@/stores/market'
import { formatPct, formatPrice, trendClass } from '@/utils/color'
import { toast } from '@/utils/toast'
import ListRow from '@/components/base/ListRow.vue'

const market = useMarketStore()

const loading = ref(false)
const query = ref('')
const suggestions = ref<SymbolInfo[]>([])
const searching = ref(false)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

/** 关注行合并实时快照（轮询写入 store），无快照回退列表原值 */
const displayList = computed(() =>
  market.watchlist.map((w) => {
    const s = market.snapshots[w.symbol_id]
    return {
      ...w,
      price: s?.price ?? w.price,
      change: s?.change ?? w.change,
      change_pct: s?.change_pct ?? w.change_pct,
    }
  })
)

const currentId = computed(() => market.current?.id ?? null)

async function load() {
  loading.value = true
  try {
    market.setWatchlist(await fetchWatchlist())
  } catch {
    /* 错误已 toast */
  } finally {
    loading.value = false
  }
}

function onSelect(item: WatchlistItem) {
  market.setCurrent({
    id: item.symbol_id,
    code: item.code,
    name: item.name,
    type: item.type,
  } as SymbolInfo)
}

async function onDelete(item: WatchlistItem) {
  try {
    await removeWatchlist(item.id)
    market.removeWatchlistItem(item.id)
  } catch {
    /* 错误已 toast */
  }
}

/* ---------- 搜索联想：仅 6 位 A 股代码触发 ---------- */
watch(query, (q) => {
  if (debounceTimer) clearTimeout(debounceTimer)
  const digits = q.trim()
  if (!/^\d{6}$/.test(digits)) {
    suggestions.value = []
    searching.value = false
    return
  }
  searching.value = true
  debounceTimer = setTimeout(async () => {
    try {
      suggestions.value = await searchSymbols(digits)
    } catch {
      suggestions.value = []
    } finally {
      searching.value = false
    }
  }, 300)
})

async function onPickSuggestion(s: SymbolInfo) {
  try {
    const item = await addWatchlist(s.id)
    market.addWatchlistItem(item)
    query.value = ''
    suggestions.value = []
    toast.success(`已添加 ${s.name}`)
  } catch {
    /* 错误已 toast */
  }
}

function onInputBlur() {
  // 延迟清空，允许点击联想项
  setTimeout(() => {
    suggestions.value = []
  }, 150)
}

onMounted(load)
</script>

<template>
  <div class="watchlist-panel">
    <header class="watchlist-panel__header">
      <span class="watchlist-panel__title">重点关注</span>
      <span class="watchlist-panel__count">{{ market.watchlist.length }}</span>
    </header>

    <div class="watchlist-panel__list">
      <div v-if="loading" class="watchlist-panel__empty">加载中…</div>
      <div v-else-if="!displayList.length" class="watchlist-panel__empty">
        暂无重点关注，可在下方搜索添加
      </div>
      <template v-else>
        <ListRow
          v-for="item in displayList"
          :key="item.id"
          clickable
          :active="item.symbol_id === currentId"
          @click="onSelect(item)"
        >
          <span class="wl-code">{{ item.code }}</span>
          <span class="wl-name">{{ item.name }}</span>
          <span class="wl-price" :class="trendClass(item.change_pct)">
            {{ formatPrice(item.price) }}
          </span>
          <span class="wl-pct" :class="trendClass(item.change_pct)">
            {{ formatPct(item.change_pct) }}
          </span>
          <button class="wl-del" title="删除" @click.stop="onDelete(item)">×</button>
        </ListRow>
      </template>
    </div>

    <div class="watchlist-panel__search">
      <div class="search-box">
        <input
          v-model="query"
          class="search-box__input"
          type="text"
          inputmode="numeric"
          maxlength="6"
          placeholder="输入 6 位股票代码搜索添加"
          @blur="onInputBlur"
        />
        <span v-if="searching" class="search-box__hint">…</span>
      </div>
      <div v-if="suggestions.length" class="search-suggest">
        <button
          v-for="s in suggestions"
          :key="s.id"
          class="search-suggest__item"
          @mousedown.prevent="onPickSuggestion(s)"
        >
          <span class="search-suggest__name">{{ s.name }}</span>
          <span class="search-suggest__code">{{ s.code }}</span>
          <span class="search-suggest__type">{{ s.type }}</span>
        </button>
        <div v-if="!suggestions.length && !searching && /^\d{6}$/.test(query)" class="search-suggest__empty">
          未找到匹配标的
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.watchlist-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
.watchlist-panel__header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
}
.watchlist-panel__title {
  font-size: 13px;
  color: var(--text-secondary);
}
.watchlist-panel__count {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-panel-2);
  padding: 0 6px;
  border-radius: 8px;
}
.watchlist-panel__list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.watchlist-panel__empty {
  padding: 20px 12px;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
}
.wl-code {
  flex: none;
  width: 52px;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}
.wl-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wl-price {
  flex: none;
  width: 62px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.wl-pct {
  flex: none;
  width: 62px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.wl-del {
  flex: none;
  width: 20px;
  height: 20px;
  font-size: 15px;
  line-height: 1;
  color: var(--text-muted);
  border-radius: 3px;
  visibility: hidden;
}
.list-row:hover .wl-del {
  visibility: visible;
}
.wl-del:hover {
  color: var(--up);
  background: var(--up-soft);
}
.watchlist-panel__search {
  flex: none;
  padding: 8px;
  border-top: 1px solid var(--border);
  position: relative;
}
.search-box {
  position: relative;
}
.search-box__input {
  width: 100%;
  height: 30px;
  padding: 0 26px 0 10px;
  background: var(--bg-panel-2);
  border: 1px solid var(--border-strong);
  border-radius: 4px;
  color: var(--text);
  font-size: 12px;
  outline: none;
  transition:
    border-color 0.15s,
    box-shadow 0.15s;
}
.search-box__input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}
.search-box__input::placeholder {
  color: var(--text-muted);
}
.search-box__hint {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
  font-size: 12px;
}
.search-suggest {
  position: absolute;
  left: 8px;
  right: 8px;
  bottom: calc(100% - 8px);
  z-index: 20;
  max-height: 200px;
  overflow-y: auto;
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 4px;
  box-shadow: var(--shadow);
}
.search-suggest__item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  font-size: 13px;
  text-align: left;
}
.search-suggest__item:hover {
  background: var(--bg-hover);
}
.search-suggest__name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.search-suggest__code {
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}
.search-suggest__type {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
}
.search-suggest__empty {
  padding: 10px;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
