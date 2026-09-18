<script setup lang="ts">
/**
 * 阶段六 6.3 · Agent 运行记录弹窗（M 区「运行记录」菜单项）：
 * 分页拉取 GET /api/v1/agent/runs（结论/耗时/时间），点击单条关闭弹窗并跳转 N 区
 * （AgentRunDetailPanel + AgentTimeline）回看完整决策链。
 *
 * G27（P1-6b）：列表改 RecycleScroller 虚拟滚动 + 滚动到末尾按需续拉（原「上一页/下一页」
 * 分页器移除，改为连续滚动；顶部保留「已加载 X / 共 Y 条」以免用户失去位置感）。
 */
import { onMounted, ref } from 'vue'
import { RecycleScroller } from 'vue-virtual-scroller'
import { useAiStore } from '@/stores/ai'
import { fetchAgentRuns, type AgentRun } from '@/api/ai'
import { useInfiniteList } from '@/composables/useInfiniteList'

const emit = defineEmits<{ (e: 'close'): void }>()

const ai = useAiStore()

const runs = ref<AgentRun[]>([])
const loading = ref(true)
const page = ref(1)
const size = 20
const total = ref(0)

/** 列表项固定高度（与 .run-item 的 height + margin 一致） */
const RUN_ITEM_SIZE = 84

const RUN_TYPE_LABEL: Record<string, string> = {
  diagnose: '诊断符号',
  plan: '交易计划',
  radar: '机会雷达',
  strategy: '创建策略',
  custom: '对话',
}

async function load() {
  loading.value = true
  try {
    const res = await fetchAgentRuns({ page: 1, size })
    runs.value = res.items
    total.value = res.total
    page.value = 1
  } catch {
    runs.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

/** G27：续拉下一页（页码仅在成功后推进；按 id 去重防重复插入） */
async function loadMoreRuns(): Promise<number> {
  const next = page.value + 1
  const res = await fetchAgentRuns({ page: next, size })
  page.value = next
  const seen = new Set(runs.value.map((r) => r.id))
  const fresh = res.items.filter((r) => !seen.has(r.id))
  runs.value = [...runs.value, ...fresh]
  total.value = res.total
  return fresh.length
}

const { loadingMore, onUpdate } = useInfiniteList({
  count: () => runs.value.length,
  hasMore: () => runs.value.length < total.value,
  loadMore: loadMoreRuns,
  name: 'agent_run_list',
})

/** 点击运行记录：关闭弹窗并跳转 N 区展示完整决策链（6.3） */
function openDetail(run: AgentRun) {
  emit('close')
  void ai.openRunDetail(run.id)
}

function formatDuration(ms?: number | null): string {
  if (ms == null) return '--'
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}

function formatTime(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

onMounted(() => void load())
</script>

<template>
  <div class="dialog-mask" @click.self="emit('close')">
    <div class="dialog">
      <header class="dialog__head">
        <h3 class="dialog__title">Agent 运行记录</h3>
        <button class="dialog__close" @click="emit('close')">×</button>
      </header>

      <div class="dialog__body">
        <div v-if="loading" class="dlg-empty">加载中…</div>
        <div v-else-if="!runs.length" class="dlg-empty">暂无运行记录</div>
        <!-- G27：虚拟滚动列表，滚动到末尾自动续拉 -->
        <RecycleScroller
          v-else
          class="run-list"
          :items="runs"
          :item-size="RUN_ITEM_SIZE"
          key-field="id"
          :buffer="240"
          @update="onUpdate"
        >
          <template #default="{ item: run }">
            <div class="run-item" @click="openDetail(run)">
              <div class="run-item__head">
                <span class="run-item__type">
                  {{ RUN_TYPE_LABEL[run.run_type ?? 'custom'] ?? run.run_type }}
                </span>
                <span v-if="run.final_decision" class="run-item__decision">{{ run.final_decision }}</span>
              </div>
              <div class="run-item__input">{{ run.input }}</div>
              <div class="run-item__meta">
                <span>耗时 {{ formatDuration(run.total_duration) }}</span>
                <span class="run-item__dot-sep">·</span>
                <span>{{ formatTime(run.created_at) }}</span>
                <span v-if="run.status === 'failed'" class="run-item__failed">失败</span>
              </div>
            </div>
          </template>
          <template #after>
            <div v-if="loadingMore" class="run-more">加载中…</div>
          </template>
        </RecycleScroller>

        <!-- G27：进度提示（原分页器已由连续滚动取代） -->
        <div v-if="runs.length" class="run-progress">已加载 {{ runs.length }} / 共 {{ total }} 条</div>
      </div>
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
  max-width: 92vw;
  max-height: 82vh;
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
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
.dialog__title {
  font-size: 15px;
  font-weight: 600;
}
.dialog__close {
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
.dialog__body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 12px 16px;
}
.dlg-empty {
  padding: 24px 12px;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
}
/* G27：滚动由 RecycleScroller 接管（自身即滚动容器），需撑满剩余高度 */
.run-list {
  flex: 1;
  min-height: 0;
}
.run-item {
  /* 固定高度：虚拟滚动按 RUN_ITEM_SIZE 定位，两者必须一致 */
  height: 76px;
  margin-bottom: 8px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  overflow: hidden;
  transition: background-color 0.15s;
}
.run-item:hover {
  background: var(--bg-hover);
}
.run-item__head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.run-item__type {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}
.run-item__decision {
  flex: none;
  max-width: 60%;
  font-size: 12px;
  color: var(--down);
  background: var(--down-soft);
  border-radius: 3px;
  padding: 1px 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.run-item__input {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.run-item__meta {
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-muted);
}
.run-item__dot-sep {
  color: var(--text-muted);
}
.run-item__failed {
  margin-left: auto;
  font-size: 11px;
  color: var(--up);
  background: var(--up-soft);
  border-radius: 3px;
  padding: 0 6px;
}
.run-more {
  padding: 6px 0;
  text-align: center;
  font-size: 11px;
  color: var(--text-muted);
}
.run-progress {
  flex: none;
  margin-top: 10px;
  text-align: center;
  font-size: 11px;
  color: var(--text-muted);
}
</style>
