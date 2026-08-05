<template>
  <div class="loading-overlay">
    <el-icon class="loading-icon" :size="32"><Loading /></el-icon>
    <span>{{ message || '数据加载中...' }}</span>
  </div>
</template>

<script setup lang="ts">
import { Loading } from '@element-plus/icons-vue';

defineProps<{ message?: string }>();
</script>

<style scoped>
.loading-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.6);
  z-index: 500;
  gap: 12px;
  color: #ccc;
  font-size: 14px;
  padding: 0 16px;
  text-align: center;
}
.loading-icon {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
