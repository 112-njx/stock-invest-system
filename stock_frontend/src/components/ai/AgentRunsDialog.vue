<script setup lang="ts">
/**
 * 4.8.4 · Agent 运行记录弹窗：
 * 列表展示 GET /api/v1/agent/runs，点击单条可查看完整 agent_steps 各节点原始输出。
 * 后端接口尚待实现（编排缺失，见 fixed.md），请求失败时展示占位说明，接口就绪后自动生效。
 */
import { onMounted, ref } from 'vue'
import { fetchAgentRunDetail, fetchAgentRuns, type AgentRun, type AgentStep } from '@/api/ai'

const emit = defineEmits<{ (e: 'close'): void }>()

const runs = ref<AgentRun[]>([])
const loading = ref(true)
const available = ref(true)
const detail = ref<(AgentRun & { steps?: AgentStep[] }) | null>(null)
const detailLoading = ref(false)

const NODE_LABEL: Record<string, string> = {
  technical_analyst: '技术分析师',
  bull_researcher: '看多研究员',
  bear_researcher: '看空研究员',
  risk_manager: '风控经理',
  trader: '交易决策',
}

const RUN_TYPE_LABEL: Record<string, string> = {
  diagnose: '诊断符号',
  plan: '交易计划',
  radar: '机会雷达',
  strategy: '创建策略',
  custom: '对话',
}

const STATUS_TEXT: Record<string, string> = { queued: '排队中', running: '运行中', success: '成功', failed: '失败' }

onMounted(async () => {
  try {
    runs.value = await fetchAgentRuns()
  } catch {
    available.value = false
  } finally {
    loading.value = false
  }
})

function stepLabel(s: AgentStep): string {
  if (s.step_name.startsWith('tool:')) return `工具：${s.step_name.slice(5)}`
  if (s.step_name.startsWith('tool_result:')) return '工具结果'
  return NODE_LABEL[s.step_name] ?? s.step_name
}

async function openDetail(run: AgentRun) {
  detailLoading.value = true
  try {
    detail.value = await fetchAgentRunDetail(run.id)
  } catch {
    detail.value = { ...run, steps: [] }
  } finally {
    detailLoading.value = false
  }
}

function formatTime(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
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
        <div v-else-if="!available" class="dlg-empty">
          <p>运行记录接口（GET /api/v1/agent/runs）后端尚未实现，暂无可展示内容。</p>
          <p class="dlg-empty__hint">深度分析（诊断/交易计划/机会雷达）执行的技术分析→多空辩论→风控→决策步骤将记录于此，待后端补齐后自动展示。</p>
        </div>
        <div v-else-if="!runs.length" class="dlg-empty">暂无运行记录</div>
        <div v-else class="run-list">
          <div v-for="run in runs" :key="run.id" class="run-item" @click="openDetail(run)">
            <div class="run-item__head">
              <span class="run-item__type">{{ RUN_TYPE_LABEL[run.run_type ?? 'custom'] ?? run.run_type }}</span>
              <span class="run-item__status" :class="`is-${run.status}`">{{ STATUS_TEXT[run.status ?? ''] ?? run.status }}</span>
            </div>
            <div class="run-item__input">{{ run.input }}</div>
            <div class="run-item__meta">
              {{ formatTime(run.created_at) }}
              <template v-if="run.tokens"> · {{ run.tokens }} tokens</template>
            </div>
          </div>
        </div>

        <!-- 运行详情：agent_steps 时间线 -->
        <div v-if="detail" class="run-detail">
          <div class="run-detail__bar">
            <span>节点输出</span>
            <button class="run-detail__close" @click="detail = null">收起</button>
          </div>
          <div v-if="detailLoading" class="dlg-empty">加载中…</div>
          <div v-else-if="!detail.steps?.length" class="dlg-empty">该记录暂无步骤输出</div>
          <div v-else class="run-steps">
            <div v-for="(s, i) in detail.steps" :key="i" class="run-step">
              <span class="run-step__dot" />
              <div class="run-step__body">
                <div class="run-step__name">{{ stepLabel(s) }}</div>
                <pre class="run-step__content">{{ s.content }}</pre>
              </div>
            </div>
          </div>
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
  overflow-y: auto;
  padding: 12px 16px;
}
.dlg-empty {
  padding: 24px 12px;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
}
.dlg-empty__hint {
  margin-top: 8px;
  font-size: 12px;
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
}
.run-item__status {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-panel-2);
  border-radius: 3px;
  padding: 0 6px;
}
.run-item__status.is-success {
  color: var(--down);
  background: var(--down-soft);
}
.run-item__status.is-failed {
  color: var(--up);
  background: var(--up-soft);
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
  font-size: 11px;
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
.run-steps {
  border-left: 2px solid var(--border);
  padding-left: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.run-step {
  display: flex;
  gap: 8px;
}
.run-step__dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--down);
  margin-top: 5px;
}
.run-step__body {
  flex: 1;
  min-width: 0;
}
.run-step__name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}
.run-step__content {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
  background: var(--bg-panel-2);
  border-radius: 4px;
  padding: 8px;
  margin-top: 4px;
  max-height: 180px;
  overflow-y: auto;
  font-family: inherit;
}
</style>
