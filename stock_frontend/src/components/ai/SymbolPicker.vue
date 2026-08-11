<script setup lang="ts">
/**
 * 标的选择下拉（AI 输入区）：
 * 数据源 = 固定指数 + 关注列表 + 输入关键词搜索联想（代码/名称）。
 * 显示：名称（类型）。选中后由父组件更新 ai.selectedSymbol。
 */
import { onMounted, ref, watch } from 'vue'
import { fetchSymbols, fetchWatchlist, searchSymbols, type SymbolInfo } from '@/api/market'
import { useMarketStore } from '@/stores/market'

const props = defineProps<{ modelValue: SymbolInfo | null }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: SymbolInfo | null): void }>()

const open = ref(false)
const query = ref('')
const options = ref<SymbolInfo[]>([])
const loading = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null

const TYPE_LABEL: Record<string, string> = { stock: '股票', etf: 'ETF', index: '指数' }

async function loadBase() {
  loading.value = true
  try {
    const [fixed, watch] = await Promise.all([
      fetchSymbols({ type: 'index', is_fixed: 1 }),
      fetchWatchlist(),
    ])
    const map = new Map<number, SymbolInfo>()
    for (const s of fixed) map.set(s.id, s)
    for (const w of watch) {
      if (!map.has(w.symbol_id)) {
        map.set(w.symbol_id, { id: w.symbol_id, code: w.code, name: w.name, type: w.type })
      }
    }
    // 双向标的联动：并入行情页当前标的，保证带出的标的下拉可选
    const mc = useMarketStore().current
    if (mc && !map.has(mc.id)) map.set(mc.id, mc)
    options.value = [...map.values()]
  } catch {
    options.value = []
  } finally {
    loading.value = false
  }
}

watch(query, (q) => {
  if (timer) clearTimeout(timer)
  const kw = q.trim()
  if (!kw) {
    void loadBase()
    return
  }
  timer = setTimeout(async () => {
    try {
      options.value = await searchSymbols(kw)
    } catch {
      options.value = []
    }
  }, 300)
})

function toggle() {
  open.value = !open.value
  if (open.value) {
    query.value = ''
    void loadBase()
  }
}

function pick(s: SymbolInfo) {
  emit('update:modelValue', s)
  open.value = false
}

onMounted(loadBase)
</script>

<template>
  <div class="symbol-picker">
    <button class="symbol-picker__trigger" @click.stop="toggle">
      <template v-if="modelValue">
        <span class="symbol-picker__name">{{ modelValue.name }}</span>
        <span class="symbol-picker__code">{{ modelValue.code }}</span>
        <span class="symbol-picker__type">{{ TYPE_LABEL[modelValue.type] }}</span>
      </template>
      <template v-else>
        <span class="symbol-picker__placeholder">请选择标的</span>
      </template>
      <span class="symbol-picker__caret">▼</span>
    </button>

    <div v-if="open" class="symbol-picker__panel" @click.stop>
      <input
        v-model="query"
        class="symbol-picker__search"
        type="text"
        placeholder="输入代码或名称搜索…"
      />
      <div class="symbol-picker__list">
        <div v-if="loading && !options.length" class="symbol-picker__empty">加载中…</div>
        <button
          v-for="s in options"
          :key="s.id"
          class="symbol-picker__item"
          @click="pick(s)"
        >
          <span class="symbol-picker__name">{{ s.name }}</span>
          <span class="symbol-picker__code">{{ s.code }}</span>
          <span class="symbol-picker__type">{{ TYPE_LABEL[s.type] }}</span>
        </button>
        <div v-if="!options.length && !loading" class="symbol-picker__empty">未找到匹配标的</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.symbol-picker {
  position: relative;
}
.symbol-picker__trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 32px;
  padding: 0 10px;
  background: var(--bg-panel-2);
  border: 1px solid var(--border-strong);
  border-radius: 4px;
  font-size: 13px;
  color: var(--text);
  max-width: 240px;
  transition: border-color 0.15s;
}
.symbol-picker__trigger:hover {
  border-color: var(--accent);
}
.symbol-picker__placeholder {
  color: var(--text-muted);
}
.symbol-picker__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.symbol-picker__code {
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}
.symbol-picker__type {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-hover);
  border-radius: 3px;
  padding: 0 4px;
}
.symbol-picker__caret {
  font-size: 10px;
  color: var(--text-muted);
}
.symbol-picker__panel {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 30;
  width: 300px;
  max-height: 320px;
  display: flex;
  flex-direction: column;
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  box-shadow: var(--shadow);
  overflow: hidden;
}
.symbol-picker__search {
  flex: none;
  height: 34px;
  padding: 0 10px;
  background: var(--bg-panel-2);
  border: none;
  border-bottom: 1px solid var(--border);
  color: var(--text);
  font-size: 13px;
  outline: none;
}
.symbol-picker__list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px;
}
.symbol-picker__item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  border-radius: 4px;
  font-size: 13px;
  text-align: left;
  color: var(--text);
}
.symbol-picker__item:hover {
  background: var(--bg-hover);
}
.symbol-picker__empty {
  padding: 16px;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
