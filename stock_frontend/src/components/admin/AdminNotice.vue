<script setup lang="ts">
defineProps<{ resource: { loading: boolean; error: string; updated: string }; empty?: boolean }>()
</script>
<template>
  <p v-if="resource.error" class="notice danger" role="alert">{{ resource.error }}</p>
  <p v-else-if="resource.loading" class="notice" role="status">正在更新…</p>
  <p v-else-if="empty" class="notice">暂无记录</p>
  <p v-else-if="resource.updated" class="updated">更新于 {{ resource.updated }}</p>
</template>
