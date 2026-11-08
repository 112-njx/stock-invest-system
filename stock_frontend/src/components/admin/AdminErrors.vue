<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ error: string }>()
const entries = computed(() => props.error.split(/[；;\r\n]+/).map(value => value.trim()).filter(Boolean).map(value => {
  const match = value.match(/^([^:：]{1,40})[:：]\s*(.+)$/s)
  if (!match) return { title: '', message: value }
  const title = match[1]!.trim()
  let message = match[2]!.trim()
  if (message.startsWith(title)) {
    const rest = message.slice(title.length)
    if (/^\s*的/.test(rest)) message = rest.replace(/^\s*的\s*/, '')
  }
  return { title, message }
}))
</script>
<template>
  <section v-if="entries.length" class="admin-errors" aria-label="错误信息">
    <h4>错误信息<span v-if="entries.length > 1"> · {{ entries.length }} 条</span></h4>
    <ul tabindex="0" aria-label="错误明细，可滚动查看">
      <li v-for="(entry, index) in entries" :key="index">
        <strong v-if="entry.title">{{ entry.title }}</strong>
        <span>{{ entry.message }}</span>
      </li>
    </ul>
  </section>
</template>
