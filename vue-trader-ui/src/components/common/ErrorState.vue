<template>
  <div class="error-state">
    <el-icon :size="40" color="#EF5350"><WarningFilled /></el-icon>
    <p class="error-msg">{{ message }}</p>
    <el-button size="small" @click="$emit('retry')">重试</el-button>
  </div>
</template>

<script setup lang="ts">
import { WarningFilled } from '@element-plus/icons-vue';

defineProps<{ message: string }>();
defineEmits<{ retry: [] }>();
</script>

<style scoped>
.error-state {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.7);
  z-index: 500;
  gap: 12px;
}
.error-msg {
  color: #EF5350;
  font-size: 14px;
}
</style>
