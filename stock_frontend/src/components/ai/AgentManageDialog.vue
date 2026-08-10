<script setup lang="ts">
/**
 * 4.6 · 我的 Agent：定制交易 Agent 管理弹窗。
 * 列表 / 创建（名称+预设模板+system_prompt）/ 启停（status）/ 删除；UI 保持轻量。
 */
import { onMounted, reactive, ref } from 'vue'
import { useAiStore } from '@/stores/ai'
import { createAgent, deleteAgent, updateAgent, type AgentConfig } from '@/api/ai'
import { toast } from '@/utils/toast'

const emit = defineEmits<{ (e: 'close'): void }>()

const ai = useAiStore()
const showForm = ref(false)
const form = reactive({ name: '', template: 'custom', system_prompt: '', status: 'active' })

const TEMPLATES = [
  { value: 'custom', label: '自定义' },
  { value: 'technical', label: '技术分析模板' },
  { value: 'fundamental', label: '基本面模板' },
  { value: 'risk_control', label: '风控模板' },
]

onMounted(() => void ai.loadAgents())

async function onSubmit() {
  if (!form.name.trim()) {
    toast.error('请输入 Agent 名称')
    return
  }
  try {
    await createAgent({
      name: form.name.trim(),
      template: form.template,
      system_prompt: form.template === 'custom' ? form.system_prompt : undefined,
      status: form.status,
    })
    toast.success('Agent 创建成功')
    showForm.value = false
    form.name = ''
    form.system_prompt = ''
    await ai.loadAgents()
  } catch {
    /* 错误已 toast */
  }
}

async function toggleStatus(a: AgentConfig) {
  try {
    await updateAgent(a.id, { status: a.status === 'active' ? 'draft' : 'active' })
    await ai.loadAgents()
  } catch {
    /* 错误已 toast */
  }
}

async function onDelete(a: AgentConfig) {
  if (!window.confirm(`确认删除 Agent「${a.name}」？`)) return
  try {
    await deleteAgent(a.id)
    await ai.loadAgents()
  } catch {
    /* 错误已 toast */
  }
}
</script>

<template>
  <div class="dialog-mask" @click.self="emit('close')">
    <div class="dialog">
      <header class="dialog__head">
        <h3 class="dialog__title">我的 Agent</h3>
        <button class="dialog__close" @click="emit('close')">×</button>
      </header>

      <div class="dialog__body">
        <!-- 列表 -->
        <div class="agent-list">
          <div v-if="!ai.agents.length" class="dlg-empty">
            暂无定制 Agent，可创建专属交易 Agent
          </div>
          <div v-for="a in ai.agents" :key="a.id" class="agent-item">
            <div class="agent-item__info">
              <div class="agent-item__head">
                <span class="agent-item__name">{{ a.name }}</span>
                <span class="agent-item__status" :class="a.status === 'active' ? 'is-active' : ''">
                  {{ a.status === 'active' ? '启用中' : '已停用' }}
                </span>
              </div>
              <div class="agent-item__meta">{{ a.agent_type || 'custom' }}</div>
            </div>
            <div class="agent-item__ops">
              <button class="op-btn" @click="toggleStatus(a)">
                {{ a.status === 'active' ? '停用' : '启用' }}
              </button>
              <button class="op-btn op-btn--danger" @click="onDelete(a)">删除</button>
            </div>
          </div>
        </div>

        <!-- 创建表单 -->
        <button v-if="!showForm" class="dlg-add" @click="showForm = true">＋ 创建定制 Agent</button>
        <div v-else class="agent-form">
          <label class="af-field">
            <span class="af-label">名称</span>
            <input v-model="form.name" class="af-input" type="text" placeholder="例如：我的技术面风控" />
          </label>
          <label class="af-field">
            <span class="af-label">预设模板</span>
            <select v-model="form.template" class="af-input">
              <option v-for="t in TEMPLATES" :key="t.value" :value="t.value">{{ t.label }}</option>
            </select>
          </label>
          <label v-if="form.template === 'custom'" class="af-field">
            <span class="af-label">System Prompt（交易体系/规则）</span>
            <textarea
              v-model="form.system_prompt"
              class="af-input af-input--area"
              rows="3"
              placeholder="描述你的交易体系，AI 将按此辅助决策…"
            />
          </label>
          <label class="af-field">
            <span class="af-label">初始状态</span>
            <select v-model="form.status" class="af-input">
              <option value="active">启用</option>
              <option value="draft">停用</option>
            </select>
          </label>
          <div class="af-ops">
            <button class="op-btn op-btn--primary" @click="onSubmit">创建</button>
            <button class="op-btn" @click="showForm = false">取消</button>
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
  width: 480px;
  max-width: 92vw;
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
.agent-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.agent-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.agent-item__info {
  flex: 1;
  min-width: 0;
}
.agent-item__head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.agent-item__name {
  font-size: 13px;
  font-weight: 600;
}
.agent-item__status {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-panel-2);
  border-radius: 3px;
  padding: 0 6px;
}
.agent-item__status.is-active {
  color: var(--down);
  background: var(--down-soft);
}
.agent-item__meta {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}
.agent-item__ops {
  flex: none;
  display: flex;
  gap: 6px;
}
.op-btn {
  height: 26px;
  padding: 0 10px;
  border-radius: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-panel-2);
  border: 1px solid var(--border-strong);
  transition: background-color 0.15s, color 0.15s;
}
.op-btn:hover {
  background: var(--bg-hover);
  color: var(--text);
}
.op-btn--danger:hover {
  color: var(--up);
  background: var(--up-soft);
}
.op-btn--primary {
  background: var(--accent);
  border-color: transparent;
  color: #fff;
}
.op-btn--primary:hover {
  filter: brightness(1.1);
  color: #fff;
}
.dlg-add {
  width: 100%;
  height: 34px;
  margin-top: 12px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--accent);
  background: var(--accent-soft);
  border: 1px dashed var(--accent);
  transition: background-color 0.15s;
}
.dlg-add:hover {
  background: var(--bg-hover);
}
.agent-form {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.af-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.af-label {
  font-size: 12px;
  color: var(--text-secondary);
}
.af-input {
  height: 32px;
  padding: 0 8px;
  background: var(--bg-panel-2);
  color: var(--text);
  border: 1px solid var(--border-strong);
  border-radius: 4px;
  font-size: 13px;
  outline: none;
}
.af-input--area {
  height: auto;
  resize: none;
  padding: 8px;
  line-height: 1.5;
}
.af-input:focus {
  border-color: var(--accent);
}
.af-ops {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
