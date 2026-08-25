<script setup lang="ts">
/**
 * 阶段六 6.3 · Agent 运行记录弹窗（M 区「运行记录」菜单项）：
 * 分页展示 GET /api/v1/agent/runs（标的/结论/耗时/时间），点击单条复用 AgentTimeline
 * 回看完整 5 节点决策链（历史数据，非 SSE 实时）。
 * 保持现有弹窗式交互（界面固定约束，不改造为 N 区标签页）。
 */
import { computed, onMounted, ref } from 'vue'
import {
  fetchAgentRuns,
  fetchAgentRunSteps,
  type AgentRun,
  type AgentStep,
  type TimelineNode,
} from '@/api/ai'
import AgentTimeline from '@/components/ai/AgentTimeline.vue'

const emit = defineEmits<{ (e: 'close'): void }>()

const runs = ref<AgentRun[]>([])
const loading = ref(true)
const page = ref(1)
const size = 20
const total = ref(0)

const detail = ref<AgentRun | null>(null)
const detailNodes = ref<TimelineNode[]>([])
const detailLoading = ref(false)

const RUN_TYPE_LABEL: Record<string, string> = {
  diagnose: '诊断符号',
  plan: '交易计划',
  radar: '机会雷达',
  strategy: '创建策略',
  custom: '对话',
}

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / size)))

async function load() {
  loading.value = true
  try {
    const res = await fetchAgentRuns({ page: page.value, size })
    runs.value = res.items
    total.value = res.total
  } catch {
    runs.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function nextPage() {
  if (page.value >= totalPages.value) return
  page.value++
  void load()
}

function prevPage() {
  if (page.value <= 1) return
  page.value--
  void load()
}

/** AgentStep → 时间线节点（历史步骤均为 done/failed；error 存于 meta.error） */
function stepToNode(s: AgentStep): TimelineNode {
  return {
    node: s.node || s.step_name,
    status: s.status === 'failed' ? 'failed' : 'done',
    summary: s.summary ?? undefined,
    content: s.content ?? undefined,
    duration_ms: s.duration_ms ?? undefined,
    error: typeof s.meta?.error === 'string' ? (s.meta.error as string) : undefined,
  }
}

async function openDetail(run: AgentRun) {
  detail.value = run
  detailNodes.value = []
  detailLoading.value = true
  try {
    const steps = await fetchAgentRunSteps(run.id)
    detailNodes.value = steps.map(stepToNode)
  } catch {
    detailNodes.value = []
  } finally {
    detailLoading.value = false
  }
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
        <div v-else class="run-list">
          <div v-for="run in runs" :key="run.id" class="run-item" @click="openDetail(run)">
            <div class="run-item__head">
              <span class="run-item__type">{{ RUN_TYPE_LABEL[run.run_type ?? 'custom'] ?? run.run_type }}</span>
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
        </div>

        <!-- 分页 -->
        <div v-if="totalPages > 1" class="run-pager">
          <button class="run-pager__btn" :disabled="page <= 1" @click="prevPage">上一页</button>
          <span class="run-pager__info">{{ page }} / {{ totalPages }}</span>
          <button class="run-pager__btn" :disabled="page >= totalPages" @click="nextPage">下一页</button>
        </div>

        <!-- 详情：复用 AgentTimeline 回看决策链 -->
        <div v-if="detail" class="run-detail">
          <div class="run-detail__bar">
            <span>决策链（{{ detailNodes.length }} 节点）</span>
            <button class="run-detail__close" @click="detail = null">收起</button>
          </div>
          <div v-if="detailLoading" class="dlg-empty">加载中…</div>
          <div v-else-if="!detailNodes.length" class="dlg-empty">该记录暂无步骤输出</div>
          <AgentTimeline v-else :nodes="detailNodes" />
        </div>
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
  width: 640px;
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
  overflow-y: auto;
  padding: 12px 16px;
}
.dlg-empty {
  padding: 24px 12px;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
}
.run-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.run-item {
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
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
.run-pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 12px;
}
.run-pager__btn {
  height: 28px;
  padding: 0 12px;
  font-size: 12px;
  color: var(--text-secondary);
  border: 1px solid var(--border-strong);
  border-radius: 4px;
}
.run-pager__btn:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text);
}
.run-pager__btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.run-pager__info {
  font-size: 12px;
  color: var(--text-muted);
}
.run-detail {
  margin-top: 12px;
  border-top: 1px solid var(--border);
  padding-top: 10px;
}
.run-detail__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}
.run-detail__close {
  font-size: 12px;
  color: var(--accent);
}
</style>
