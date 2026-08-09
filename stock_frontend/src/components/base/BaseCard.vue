<script setup lang="ts">
defineOptions({ name: 'BaseCard' })

withDefaults(defineProps<{ title?: string }>(), { title: '' })
</script>

<template>
  <section class="base-card">
    <header v-if="title || $slots.extra" class="base-card__header">
      <h3 v-if="title" class="base-card__title">{{ title }}</h3>
      <div class="base-card__extra"><slot name="extra" /></div>
    </header>
    <div class="base-card__body"><slot /></div>
  </section>
</template>

<style scoped>
.base-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
}
.base-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex: none;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
}
.base-card__title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}
.base-card__extra {
  display: flex;
  align-items: center;
  gap: 8px;
}
.base-card__body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
</style>
