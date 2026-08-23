<script setup lang="ts">
/**
 * 5.1 · M区记忆文件面板：查看/删除/清空 AI 记忆事实（阶段六 6.4 记忆管理 API）。
 * - GET  /api/v1/memory/facts?page=&size=&importance_min=  分页列表（内容/重要性/来源/时间）
 * - DELETE /api/v1/memory/facts/{id}   删除单条
 * - DELETE /api/v1/memory/facts        清空全部（二次确认）
 * 每条卡片：内容摘要（最多 2 行，点击展开全文）、重要性星级（1-5，颜色区分）、来源时间、删除按钮。
 * 复用 4.6 弹窗骨架（dialog-mask），替代原 /memory/files 只读占位展示。
 */
import { computed, onMounted, ref } from 'vue'
import { clearMemoryFacts, deleteMemoryFact, fetchMemoryFacts, type MemoryFact } from '@/api/ai'
import { toast } from '@/utils/toast'

const emit = defineEmits<{ (e: 'close'): void }>()

/* ---------- 状态 ---------- */
const facts = ref<MemoryFact[]>([])
const total = ref(0)
const page = ref(1)
const size = 20
const loading = ref(true)
const loadError = ref(false)
/** 重要性筛选：全部 / 高(≥7) / 中(≥4) / 低(≥1) */
type ImportanceFilter = 'all' | 'high' | 'mid' | 'low'
const filter = ref<ImportanceFilter>('all')
/** 展开全文的记忆 id 集合 */
const expanded = ref<Set<number>>(new Set())
/** 清空二次确认 */
const confirmingClear = ref(false)
const clearing = ref(false)

const IMPORTANCE_MIN: Record<ImportanceFilter, number | undefined> = {
  all: undefined,
  high: 7,
  mid: 4,
  low: 1,
}

/* ---------- 数据 ---------- */
async function load() {
  loading.value = true
  loadError.value = false
  try {
    const data = await fetchMemoryFacts({ page: page.value, size, importance_min: IMPORTANCE_MIN[filter.value] })
    facts.value = data.items
    total.value = data.total
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

onMounted(load)

/* ---------- 筛选 / 分页 ---------- */
function onFilterChange(f: ImportanceFilter) {
  if (filter.value === f) return
  filter.value = f
  page.value = 1
  expanded.value = new Set()
  void load()
}

function goPage(p: number) {
  page.value = p
  expanded.value = new Set()
  void load()
}

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / size)))

/* ---------- 删除 / 清空 ---------- */
async function onDelete(id: number) {
  try {
    await deleteMemoryFact(id)
    expanded.value.delete(id)
    toast.success('已删除该记忆')
    void load()
  } catch {
    toast.error('删除失败，请重试')
  }
}

async function onClearAll() {
  if (!confirmingClear.value) {
    confirmingClear.value = true
    return
  }
  clearing.value = true
  try {
    const data = await clearMemoryFacts()
    facts.value = []
    total.value = 0
    page.value = 1
    toast.success(`已清空 ${data?.deleted ?? 0} 条记忆`)
  } catch {
    toast.error('清空失败，请重试')
  } finally {
    clearing.value = false
    confirmingClear.value = false
  }
}

/* ---------- 展示辅助 ---------- */
/** 重要性 → 星级（1-5） */
function starCount(importance: number): number {
  return Math.min(5, Math.max(1, Math.round(importance / 2)))
}

/** 星级颜色：高红 / 中黄 / 低灰 */
function starClass(importance: number): string {
  if (importance >= 7) return 't-up'
  if (importance >= 4) return 't-warn'
  return 't-muted'
}

function toggleExpand(id: number) {
  const s = new Set(expanded.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  expanded.value = s
}

function formatTime(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const SOURCE_LABEL: Record<string, string> = {
  rule: '规则',
  preference: '偏好',
  experience: '经验',
  strategy: '策略',
}
</script>

<template>
  <div class="dialog-mask" @click.self="emit('close')">
    <div class="dialog">
      <header class="dialog__head">
        <h3 class="dialog__title">记忆文件</h3>
        <span class="dialog__count">{{ total }} 条</span>
        <button class="dialog__close" @click="emit('close')">×</button>
      </header>

      <!-- 工具栏：筛选 + 清空 -->
      <div class="mem-toolbar">
        <div class="mem-filter">
          <button
            v-for="opt in ([['all', '全部'], ['high', '高'], ['mid', '中'], ['low', '低']] as const)"
            :key="opt[0]"
            class="mem-filter__btn"
            :class="{ active: filter === opt[0] }"
            @click="onFilterChange(opt[0])"
          >
            {{ opt[1] }}
          </button>
        </div>
        <button class="mem-clear" :class="{ 'is-confirm': confirmingClear }" @click="onClearAll" :disabled="clearing">
          {{ confirmingClear ? '确认清空？' : '清空全部记忆' }}
        </button>
      </div>

      <div class="dialog__body">
        <!-- 加载态 -->
        <div v-if="loading" class="dlg-empty">加载中…</div>
        <!-- 错误态 -->
        <div v-else-if="loadError" class="dlg-empty">
          <p>记忆列表加载失败</p>
          <button class="mem-retry" @click="load">重试</button>
        </div>
        <!-- 空态 -->
        <div v-else-if="!facts.length" class="dlg-empty">暂无记忆</div>
        <!-- 列表 -->
        <div v-else class="mem-list">
          <div v-for="f in facts" :key="f.id" class="mem-card">
            <div class="mem-card__content" :class="{ expanded: expanded.has(f.id) }" @click="toggleExpand(f.id)">
              {{ f.content }}
            </div>
            <div class="mem-card__meta">
              <span class="mem-card__stars" :class="starClass(f.importance)">
                {{ '★'.repeat(starCount(f.importance)) }}{{ '☆'.repeat(5 - starCount(f.importance)) }}
              </span>
              <span class="mem-card__type">{{ SOURCE_LABEL[f.source_type] ?? f.source_type }}</span>
              <span class="mem-card__time">{{ formatTime(f.created_at) }}</span>
              <button class="mem-card__del" title="删除该记忆" @click="onDelete(f.id)">删除</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 分页 -->
      <footer v-if="total > 0" class="dialog__foot">
        <button class="mem-page" :disabled="page <= 1" @click="goPage(page - 1)">上一页</button>
        <span class="mem-page__info">{{ page }} / {{ totalPages }}</span>
        <button class="mem-page" :disabled="page >= totalPages" @click="goPage(page + 1)">下一页</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.dialog-mask {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.45);
}
.dialog {
  width: 560px;
  max-width: 90vw;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  box-shadow: var(--shadow);
  overflow: hidden;
}
.dialog__head {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
.dialog__title {
  font-size: 15px;
  font-weight: 600;
}
.dialog__count {
  font-size: 12px;
  color: var(--text-muted);
}
.dialog__close {
  margin-left: auto;
  width: 26px;
  height: 26px;
  font-size: 18px;
  color: var(--text-muted);
  border-radius: 4px;
}
.dialog__close:hover {
  background: var(--bg-hover);
  color: var(--text);
}
/* 工具栏 */
.mem-toolbar {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
}
.mem-filter {
  display: flex;
  gap: 4px;
}
.mem-filter__btn {
  height: 26px;
  padding: 0 12px;
  border-radius: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  border: 1px solid var(--border-strong);
  transition: all 0.15s;
}
.mem-filter__btn:hover {
  color: var(--text);
}
.mem-filter__btn.active {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-soft);
}
.mem-clear {
  margin-left: auto;
  height: 26px;
  padding: 0 12px;
  border-radius: 4px;
  font-size: 12px;
  color: var(--text-muted);
  border: 1px solid var(--border-strong);
  transition: all 0.15s;
}
.mem-clear:hover {
  color: var(--up);
  border-color: var(--up);
}
.mem-clear.is-confirm {
  color: #fff;
  background: var(--up);
  border-color: var(--up);
}
.mem-clear:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.dialog__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 16px;
}
.dlg-empty {
  padding: 28px 12px;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
}
.mem-retry {
  margin-top: 8px;
  height: 28px;
  padding: 0 14px;
  border-radius: 4px;
  font-size: 12px;
  color: var(--accent);
  border: 1px solid var(--accent);
  background: transparent;
}
.mem-retry:hover {
  background: var(--accent-soft);
}
/* 记忆卡片 */
.mem-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.mem-card {
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
  background: var(--bg-panel-2);
}
.mem-card__content {
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text);
  cursor: pointer;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
  transition: background-color 0.15s;
}
.mem-card__content:hover {
  background: var(--bg-hover);
}
.mem-card__content.expanded {
  -webkit-line-clamp: unset;
  overflow: visible;
}
.mem-card__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-muted);
}
.mem-card__stars {
  font-size: 12px;
  letter-spacing: 1px;
}
.t-warn {
  color: var(--ind-dea);
}
.mem-card__type {
  color: var(--accent);
  background: var(--accent-soft);
  border-radius: 3px;
  padding: 0 6px;
}
.mem-card__time {
  flex: 1;
  text-align: right;
}
.mem-card__del {
  flex: none;
  height: 22px;
  padding: 0 8px;
  border-radius: 4px;
  font-size: 11px;
  color: var(--text-muted);
  border: 1px solid var(--border-strong);
  transition: all 0.15s;
}
.mem-card__del:hover {
  color: var(--up);
  border-color: var(--up);
  background: var(--up-soft);
}
/* 分页 */
.dialog__foot {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 10px 16px;
  border-top: 1px solid var(--border);
}
.mem-page {
  height: 26px;
  padding: 0 12px;
  border-radius: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  border: 1px solid var(--border-strong);
  transition: all 0.15s;
}
.mem-page:hover:not(:disabled) {
  color: var(--text);
  border-color: var(--accent);
}
.mem-page:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.mem-page__info {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
