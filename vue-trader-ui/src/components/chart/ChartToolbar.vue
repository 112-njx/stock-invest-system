<template>
  <div class="chart-toolbar">
    <span class="toolbar-symbol">{{ symbol }}</span>
    <div class="toolbar-btns">
      <el-button size="small" text>复权</el-button>
      <el-button size="small" text>叠加</el-button>
      <el-button size="small" text>多股</el-button>
      <el-button size="small" text>统计</el-button>
      <el-button size="small" text>画线</el-button>
      <el-button size="small" text>F10</el-button>
      <el-button size="small" text @click="$router.push('/')">返回</el-button>
      <el-button size="small" text>自选</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ symbol: string }>();
</script>

<style scoped>
.chart-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 32px;
  padding: 0 8px;
  background: #1e1e32;
  border-bottom: 1px solid #333;
}
.toolbar-symbol {
  font-size: 13px;
  font-weight: bold;
  color: #e0e0e0;
}
.toolbar-btns {
  display: flex;
  gap: 2px;
}
.toolbar-btns .el-button {
  color: #aaa;
  padding: 2px 8px;
  font-size: 12px;
}
</style>
