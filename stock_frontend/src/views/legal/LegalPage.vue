<script setup lang="ts">
/**
 * G03：法律页面公共骨架（用户协议 / 隐私政策 / 免责声明）。
 * 统一标题、生效日期、正文排版与「返回」入口，三个页面只提供内容插槽。
 */
import { useRouter } from 'vue-router'

defineProps<{ title: string; updatedAt: string }>()

const router = useRouter()

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push({ name: 'market' })
}
</script>

<template>
  <div class="legal-page">
    <article class="legal-card">
      <header class="legal-head">
        <h1 class="legal-head__title">{{ title }}</h1>
        <p class="legal-head__meta">生效日期：{{ updatedAt }}</p>
      </header>

      <div class="legal-body">
        <slot />
      </div>

      <footer class="legal-foot">
        <button class="legal-foot__back" @click="goBack">返回</button>
      </footer>
    </article>
  </div>
</template>

<style scoped>
.legal-page {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  background: var(--bg);
  padding: 24px 16px 40px;
}
.legal-card {
  max-width: 760px;
  margin: 0 auto;
  padding: 32px 36px 24px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.legal-head {
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 20px;
}
.legal-head__title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text);
}
.legal-head__meta {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-muted);
}
.legal-body {
  font-size: 13px;
  line-height: 1.9;
  color: var(--text-secondary);
}
.legal-body :deep(h2) {
  margin: 20px 0 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}
.legal-body :deep(h2:first-child) {
  margin-top: 0;
}
.legal-body :deep(h3) {
  margin: 14px 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.legal-body :deep(p) {
  margin: 0 0 10px;
}
.legal-body :deep(ul),
.legal-body :deep(ol) {
  margin: 0 0 10px;
  padding-left: 20px;
}
.legal-body :deep(li) {
  margin-bottom: 4px;
}
.legal-body :deep(strong) {
  color: var(--text);
}
.legal-body :deep(.legal-note) {
  margin: 12px 0;
  padding: 10px 12px;
  background: var(--bg-panel-2);
  border-left: 3px solid var(--accent);
  border-radius: 4px;
  font-size: 12.5px;
}
.legal-foot {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}
.legal-foot__back {
  padding: 6px 16px;
  border: 1px solid var(--border-strong);
  border-radius: 4px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  transition: background-color 0.15s;
}
.legal-foot__back:hover {
  background: var(--bg-hover);
}
</style>
