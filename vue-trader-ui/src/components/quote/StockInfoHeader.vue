<template>
  <div class="stock-info-header">
    <span class="stock-name">{{ name }}</span>
    <span class="stock-symbol">{{ symbol }}</span>
    <el-button size="small" text class="close-btn" @click="$emit('close')">
      <el-icon><Close /></el-icon>
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { Close } from '@element-plus/icons-vue';

defineProps<{ symbol: string; name: string }>();
defineEmits<{ close: [] }>();
</script>

<style scoped>
.stock-info-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid #333;
  background: #1a1a36;
}
.stock-name {
  font-size: 14px;
  font-weight: bold;
  color: #e0e0e0;
}
.stock-symbol {
  font-size: 11px;
  color: #888;
}
.close-btn {
  margin-left: auto;
}
</style>
