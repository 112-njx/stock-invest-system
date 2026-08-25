<script setup lang="ts">
/**
 * 阶段八 7.4 · 策略模板库弹窗：
 * GET /strategy-templates 展示 5 个内置模板卡片（名称+描述），点击调详情（含完整 code）→
 * 基于模板创建草稿策略 → 打开 N 区代码编辑器供用户修改保存/回测。
 * 参数「高亮可编辑」由 N 区现有编辑器（textarea）承载，本阶段不引入语法高亮依赖。
 */
import { onMounted, ref } from 'vue'
import { useAiStore } from '@/stores/ai'
import { createStrategy, fetchStrategyTemplate, fetchStrategyTemplates, type StrategyTemplate } from '@/api/ai'
import { toast } from '@/utils/toast'

const emit = defineEmits<{ (e: 'close'): void }>()

const ai = useAiStore()
const templates = ref<StrategyTemplate[]>([])
const loading = ref(true)
const selectingId = ref<number | null>(null)

onMounted(async () => {
  try {
    templates.value = await fetchStrategyTemplates()
  } catch {
    templates.value = []
  } finally {
    loading.value = false
  }
})

async function onSelect(t: StrategyTemplate) {
  if (selectingId.value !== null) return
  selectingId.value = t.id
  try {
    const detail = await fetchStrategyTemplate(t.id)
    const s = await createStrategy({
      title: detail.name,
      description: detail.description ?? '',
      code: detail.code ?? '',
      params: detail.params_schema ?? {},
      status: 'draft',
    })
    toast.success('已基于模板创建草稿')
    emit('close')
    await ai.openStrategy(s.id)
  } catch {
    toast.error('模板创建失败')
  } finally {
    selectingId.value = null
  }
}
</script>

<template>
  <div class="dialog-mask" @click.self="emit('close')">
    <div class="dialog">
      <header class="dialog__head">
        <h3 class="dialog__title">从模板创建策略</h3>
        <button class="dialog__close" @click="emit('close')">×</button>
      </header>

      <div class="dialog__body">
        <div v-if="loading" class="dlg-empty">加载中…</div>
        <div v-else-if="!templates.length" class="dlg-empty">暂无可用模板</div>
        <div v-else class="tpl-list">
          <button
            v-for="t in templates"
            :key="t.id"
            class="tpl-card"
            :disabled="selectingId !== null"
            @click="onSelect(t)"
          >
            <span class="tpl-card__name">{{ t.name }}</span>
            <span class="tpl-card__desc">{{ t.description }}</span>
            <span class="tpl-card__hint">{{ selectingId === t.id ? '创建中…' : '点击创建' }}</span>
          </button>
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
.tpl-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.tpl-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  text-align: left;
  border: 1px solid var(--border);
  border-radius: 6px;
  transition: background-color 0.15s, border-color 0.15s;
}
.tpl-card:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--border-strong);
}
.tpl-card:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
.tpl-card__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.tpl-card__desc {
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
}
.tpl-card__hint {
  font-size: 11px;
  color: var(--accent);
}
</style>
