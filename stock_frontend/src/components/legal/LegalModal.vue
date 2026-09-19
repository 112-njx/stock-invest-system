<script setup lang="ts">
/**
 * G03 改造 · 法律文档轻量弹窗（免责声明 / 隐私政策）。
 *
 * 不再使用独立路由页面：由 legalModal store 控制显隐，暗色遮罩盖住触发时的当前页，
 * 关闭后停留在原页面（不发生路由跳转）。关闭方式：ESC、点击遮罩、右上角 ×、底部按钮。
 *
 * 层级 z-index 1600，高于登录弹窗（1500），以便在登录弹窗内点协议链接时叠在其上层；
 * 此时 ESC 由本弹窗优先消费（LoginModal 的 ESC 处理会检测本弹窗开启状态而跳过）。
 */
import { computed, onBeforeUnmount, onMounted } from 'vue'
import type { Component } from 'vue'
import LegalDisclaimerContent from '@/components/legal/LegalDisclaimerContent.vue'
import LegalPrivacyContent from '@/components/legal/LegalPrivacyContent.vue'
import { useLegalModalStore, type LegalDocKey } from '@/stores/legalModal'
import '@/components/legal/legal-doc.css'

const legal = useLegalModalStore()

interface DocMeta {
  title: string
  updatedAt: string
  component: Component
}

const DOCS: Record<LegalDocKey, DocMeta> = {
  disclaimer: { title: '免责声明', updatedAt: '2026-09-17', component: LegalDisclaimerContent },
  privacy: { title: '隐私政策', updatedAt: '2026-09-17', component: LegalPrivacyContent },
}

const current = computed<DocMeta | null>(() => (legal.doc ? DOCS[legal.doc] : null))

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') legal.hide()
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <div v-if="current" class="legal-mask" @click.self="legal.hide()">
      <div
        class="legal-modal"
        role="dialog"
        aria-modal="true"
        :aria-label="current.title"
      >
        <header class="legal-modal__head">
          <div class="legal-modal__heading">
            <h2 class="legal-modal__title">{{ current.title }}</h2>
            <p class="legal-modal__meta">生效日期：{{ current.updatedAt }}</p>
          </div>
          <button class="legal-modal__close" type="button" title="关闭（ESC）" @click="legal.hide()">
            ×
          </button>
        </header>

        <div class="legal-modal__body legal-doc-body">
          <component :is="current.component" />
        </div>

        <footer class="legal-modal__foot">
          <button type="button" class="legal-modal__ok" @click="legal.hide()">我知道了</button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.legal-mask {
  position: fixed;
  inset: 0;
  z-index: 1600;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  background: rgba(0, 0, 0, 0.55);
}
.legal-modal {
  display: flex;
  flex-direction: column;
  width: 760px;
  max-width: 100%;
  max-height: calc(100vh - 64px);
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 12px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.45);
}
.legal-modal__head {
  flex: none;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 20px 24px 16px;
  border-bottom: 1px solid var(--border);
}
.legal-modal__title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text);
}
.legal-modal__meta {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}
.legal-modal__close {
  flex: none;
  width: 28px;
  height: 28px;
  font-size: 18px;
  line-height: 1;
  color: var(--text-muted);
  border-radius: 4px;
}
.legal-modal__close:hover {
  background: var(--bg-hover);
  color: var(--text);
}
.legal-modal__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 20px 24px;
}
.legal-modal__foot {
  flex: none;
  display: flex;
  justify-content: flex-end;
  padding: 14px 24px;
  border-top: 1px solid var(--border);
}
.legal-modal__ok {
  padding: 7px 20px;
  font-size: 13px;
  color: #fff;
  background: var(--accent);
  border-radius: 6px;
  transition: opacity 0.15s;
}
.legal-modal__ok:hover {
  opacity: 0.9;
}
</style>
