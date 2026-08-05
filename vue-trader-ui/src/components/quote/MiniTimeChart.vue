<template>
  <div class="mini-time-chart">
    <div class="mini-chart-title">分时走势</div>
    <div class="mini-chart-placeholder">
      <span style="color: #9C27B0">━━━</span>
      <span style="color: #2196F3">━━━</span>
    </div>
    <p class="placeholder-hint">阶段6接入真实分时数据</p>
  </div>
</template>

<style scoped>
.mini-time-chart { padding: 8px 12px; border-top: 1px solid #333; }
.mini-chart-title { font-size: 12px; color: #888; margin-bottom: 4px; }
.mini-chart-placeholder { display: flex; justify-content: center; gap: 12px; font-size: 20px; padding: 16px 0; }
.placeholder-hint { font-size: 10px; color: #444; text-align: center; }
</style>
