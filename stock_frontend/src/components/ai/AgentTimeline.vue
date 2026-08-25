<script setup lang="ts">
/**
 * 阶段六 6.1/6.2 · 深度分析 5 节点时间线：
 * 技术分析师 → 多头研究员 → 空头研究员 → 风控经理 → 交易决策者
 * - 节点状态：等待中(灰) → 运行中(蓝旋转) → 完成(绿对勾+耗时) → 失败(红感叹号)
 * - 节点间连线：已完成连线变绿
 * - 完成节点可点击展开完整输出（markdown 渲染 + 复制）；失败节点展开错误 + 默认观点标注
 * - 全部节点完成后显示结论区；有失败节点时黄色提示「部分节点异常，结论仅供参考」
 *
 * live 流式（store.timeline）与历史回看（AgentRunsDialog 传入）共用本组件。
 */
import { computed, ref } from 'vue'
import { AGENT_NODE_LABEL, type TimelineNode } from '@/api/ai'
import { renderMarkdown } from '@/utils/markdown'
import { toast } from '@/utils/toast'

const props = defineProps<{ nodes: TimelineNode[]; running?: boolean }>()

const expanded = ref<string | null>(null)

const hasFailed = computed(() => props.nodes.some((n) => n.status === 'failed'))
const allDone = computed(
  () => props.nodes.length > 0 && props.nodes.every((n) => n.status === 'done' || n.status === 'failed')
)

function label(key: string): string {
  return AGENT_NODE_LABEL[key] ?? key
}

function statusText(n: TimelineNode): string {
  switch (n.status) {
    case 'waiting':
      return '等待中'
    case 'running':
      return '分析中…'
    case 'done':
      return formatDuration(n.duration_ms)
    case 'failed':
      return '失败'
    default:
      return ''
  }
}

function formatDuration(ms?: number): string {
  if (ms == null) return '完成'
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}

/** 仅完成/失败节点可展开 */
function toggle(n: TimelineNode) {
  if (n.status !== 'done' && n.status !== 'failed') return
  expanded.value = expanded.value === n.node ? null : n.node
}

function expandedNode(): TimelineNode | undefined {
  return props.nodes.find((n) => n.node === expanded.value)
}

async function copyContent() {
  const n = expandedNode()
  if (!n) return
  try {
    await navigator.clipboard.writeText(n.content ?? n.summary ?? '')
    toast.success('已复制')
  } catch {
    toast.error('复制失败')
  }
}
</script>

<template>
  <div class="tl">
    <!-- 5 节点时间线 -->
    <div class="tl__row">
      <div v-for="(n, i) in nodes" :key="n.node" class="tl__step">
        <div class="tl__step-top">
          <div
            class="tl__line"
            :class="{ 'is-done': i > 0 && nodes[i - 1].status === 'done' }"
          />
          <button
            class="tl__dot"
            :class="[`is-${n.status}`, { 'is-clickable': n.status === 'done' || n.status === 'failed' }]"
            :disabled="n.status !== 'done' && n.status !== 'failed'"
            @click="toggle(n)"
          >
            <span v-if="n.status === 'running'" class="tl__spin" />
            <span v-else-if="n.status === 'done'" class="tl__check">✓</span>
            <span v-else-if="n.status === 'failed'" class="tl__exclaim">!</span>
          </button>
          <div class="tl__line" :class="{ 'is-done': n.status === 'done' }" />
        </div>
        <div class="tl__label" :class="{ 'is-active': n.status !== 'waiting' }">{{ label(n.node) }}</div>
        <div class="tl__status" :class="`is-${n.status}`">{{ statusText(n) }}</div>
      </div>
    </div>

    <!-- 节点展开详情 -->
    <div v-if="expandedNode()" class="tl__detail">
      <div class="tl__detail-bar">
        <span class="tl__detail-title">{{ label(expandedNode()!.node) }}</span>
        <button v-if="expandedNode()!.status === 'done'" class="tl__copy" @click="copyContent">复制</button>
      </div>
      <template v-if="expandedNode()!.status === 'failed'">
        <div class="tl__fail-note">该节点使用默认观点</div>
        <pre class="tl__content">{{ expandedNode()!.error || '节点执行异常' }}</pre>
      </template>
      <div v-else class="tl__content md-body" v-html="renderMarkdown(expandedNode()!.content || expandedNode()!.summary || '（无输出）')" />
    </div>

    <!-- 结论区（所有节点完成后显示） -->
    <div v-if="allDone" class="tl__footer" :class="{ 'is-warn': hasFailed }">
      <span v-if="hasFailed" class="tl__footer-warn">部分节点异常，结论仅供参考</span>
      <span v-else class="tl__footer-ok">分析完成</span>
    </div>
  </div>
</template>

<style scoped>
.tl {
  margin: 6px 0 4px;
  padding: 8px 10px;
  background: var(--bg-panel-2);
  border: 1px solid var(--border);
  border-radius: 6px;
}
.tl__row {
  display: flex;
  align-items: flex-start;
}
.tl__step {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.tl__step-top {
  display: flex;
  align-items: center;
  width: 100%;
}
.tl__line {
  flex: 1;
  height: 2px;
  background: var(--border-strong);
  transition: background-color 0.2s;
}
.tl__line.is-done {
  background: var(--down);
}
.tl__dot {
  flex: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  border: 2px solid var(--border-strong);
  background: var(--bg-panel);
  color: var(--text-muted);
  transition: all 0.2s;
}
.tl__dot.is-clickable {
  cursor: pointer;
}
.tl__dot.is-clickable:hover {
  border-color: var(--text-secondary);
}
.tl__dot.is-waiting {
  /* 默认灰 */
}
.tl__dot.is-running {
  border-color: var(--accent);
}
.tl__dot.is-done {
  border-color: var(--down);
  color: var(--down);
  background: var(--down-soft);
}
.tl__dot.is-failed {
  border-color: var(--up);
  color: var(--up);
  background: var(--up-soft);
}
.tl__spin {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid var(--accent);
  border-top-color: transparent;
  animation: tl-spin 0.8s linear infinite;
}
@keyframes tl-spin {
  to {
    transform: rotate(360deg);
  }
}
.tl__check {
  line-height: 1;
}
.tl__exclaim {
  line-height: 1;
}
.tl__label {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.tl__label.is-active {
  color: var(--text-secondary);
}
.tl__status {
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}
.tl__status.is-running {
  color: var(--accent);
}
.tl__status.is-done {
  color: var(--down);
}
.tl__status.is-failed {
  color: var(--up);
}
/* 展开详情 */
.tl__detail {
  margin-top: 10px;
  padding: 8px 10px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 4px;
}
.tl__detail-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.tl__detail-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}
.tl__copy {
  font-size: 12px;
  color: var(--accent);
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid var(--accent);
}
.tl__copy:hover {
  background: var(--accent-soft);
}
.tl__fail-note {
  font-size: 12px;
  color: var(--up);
  margin-bottom: 6px;
}
.tl__content {
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
  word-break: break-word;
  max-height: 240px;
  overflow-y: auto;
}
/* 结论区 */
.tl__footer {
  margin-top: 8px;
  padding-top: 6px;
  border-top: 1px dashed var(--border);
  font-size: 12px;
  text-align: center;
}
.tl__footer-ok {
  color: var(--down);
}
.tl__footer-warn {
  color: #f59e0b;
}
</style>
