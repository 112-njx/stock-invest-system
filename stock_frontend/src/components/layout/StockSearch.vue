<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { addWatchlist, searchSymbols, type SymbolInfo } from '@/api/market'
import { useMarketStore } from '@/stores/market'
import { useUserStore } from '@/stores/user'
import { useWsStore } from '@/stores/wsStore'
import { useAuthModalStore } from '@/stores/authModal'
import { toast } from '@/utils/toast'
const market = useMarketStore()
const user = useUserStore()
const ws = useWsStore()
const authModal = useAuthModalStore()
const query = ref('')
const suggestions = ref<SymbolInfo[]>([])
const searching = ref(false)
let debounceTimer: ReturnType<typeof setTimeout> | null = null
function requireLogin() {
  if (user.token) return false
  authModal.show()
  return true
}
/** V0.2：搜索结果分组：已同步（has_kline=true）/ 未同步（is_catalog=true） */
const groupedSuggestions = computed(() => {
  const synced = suggestions.value.filter((s) => s.has_kline === true || s.is_catalog !== true)
  const unsynced = suggestions.value.filter((s) => s.is_catalog === true && s.has_kline !== true)
  return { synced, unsynced }
})

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
  if (requireLogin()) return
  try {
    const item = await addWatchlist(s.code)
    market.addWatchlistItem(item)
    query.value = ''
    suggestions.value = []
    toast.success(`已添加 ${s.name}`)
    // V0.2：添加关注后同步 WS 订阅
    ws.syncSubscriptions()
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

onUnmounted(() => { if (debounceTimer) clearTimeout(debounceTimer) })
</script>
<template>
    <div class="stock-search">
      <div class="search-box">
        <input
          v-model="query"
          class="search-box__input"
          aria-label="股票代码搜索添加" type="text"
          inputmode="numeric"
          maxlength="6"
          placeholder="输入 6 位股票代码搜索添加"
          @blur="onInputBlur"
        />
        <span v-if="searching" class="search-box__hint">…</span>
      </div>
      <div v-if="suggestions.length" class="search-suggest">
        <!-- V0.2：已同步组 -->
        <div v-if="groupedSuggestions.synced.length" class="search-suggest__group">
          <div class="search-suggest__group-title">已同步</div>
          <button
            v-for="s in groupedSuggestions.synced"
            :key="s.id"
            class="search-suggest__item"
            @mousedown.prevent="onPickSuggestion(s)"
          >
            <span class="search-suggest__name">{{ s.name }}</span>
            <span class="search-suggest__code">{{ s.code }}</span>
            <span class="search-suggest__type">{{ s.type }}</span>
          </button>
        </div>
        <!-- V0.2：未同步组（灰色标注"添加后同步"） -->
        <div v-if="groupedSuggestions.unsynced.length" class="search-suggest__group">
          <div class="search-suggest__group-title search-suggest__group-title--muted">未同步 · 添加后同步</div>
          <button
            v-for="s in groupedSuggestions.unsynced"
            :key="s.id"
            class="search-suggest__item search-suggest__item--muted"
            @mousedown.prevent="onPickSuggestion(s)"
          >
            <span class="search-suggest__name">{{ s.name }}</span>
            <span class="search-suggest__code">{{ s.code }}</span>
            <span class="search-suggest__type">{{ s.type }}</span>
          </button>
        </div>
        <div v-if="!suggestions.length && !searching && /^\d{6}$/.test(query)" class="search-suggest__empty">
          未找到匹配标的
        </div>
      </div>
    </div>
</template>
<style scoped>
.stock-search { position: relative; width: clamp(180px, 20vw, 300px); min-width: 160px; }
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
  left: 0;
  right: 0;
  top: calc(100% + 6px);
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
/* V0.2：搜索结果分组 */
.search-suggest__group-title {
  padding: 4px 10px;
  font-size: 10px;
  color: var(--text-muted);
  background: var(--bg-panel-2);
  border-bottom: 1px solid var(--border);
}
.search-suggest__group-title--muted {
  color: var(--text-muted);
}
.search-suggest__item--muted {
  opacity: 0.6;
}
.search-suggest__item--muted:hover {
  opacity: 1;
  background: var(--bg-hover);
}
</style>
