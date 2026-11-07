<script setup lang="ts">
defineProps<{ resource: { loading: boolean; error: string; updated: string }; empty?: boolean }>()
</script>
<template>
  <div class="resource-notice">
    <p class="resource-status" :aria-busy="resource.loading">
      <span>{{ resource.updated ? `更新于 ${resource.updated}` : resource.loading ? '首次读取中…' : '等待读取' }}</span>
      <span class="resource-refresh" :class="{ visible: resource.loading }" :aria-hidden="!resource.loading">正在刷新…</span>
    </p>
    <p v-if="resource.error" class="notice danger" role="alert">{{ resource.error }}</p>
    <p v-else-if="empty && !resource.loading" class="notice">暂无记录</p>
  </div>
</template>
