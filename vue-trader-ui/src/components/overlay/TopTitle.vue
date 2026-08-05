<template>
  <div class="top-title-overlay">
    {{ name }}（{{ symbol }}）
  </div>
</template>

<script setup lang="ts">
defineProps<{ symbol: string; name: string }>();
</script>

<style scoped>
.top-title-overlay {
  position: absolute;
  top: 4px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
  color: #EF5350;
  font-size: 16px;
  font-weight: bold;
  text-shadow: 1px 1px 0 #000, -1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000;
  pointer-events: none;
  white-space: nowrap;
}
</style>
