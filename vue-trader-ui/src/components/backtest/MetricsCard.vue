<template>
  <div class="metrics-card">
    <el-card shadow="always" class="metrics-inner">
      <template #header>
        <div class="metrics-header">
          <span class="metrics-title">回测结果（{{ result.strategyCode }}）</span>
          <el-button size="small" text @click="$emit('close')">
            <el-icon color="#fff"><Close /></el-icon>
          </el-button>
        </div>
      </template>
      <div class="metrics-grid">
        <div class="metric-item">
          <span class="metric-label">收益率</span>
          <span class="metric-value" :class="returnClass">{{ returnDisplay }}</span>
        </div>
        <div class="metric-item">
          <span class="metric-label">胜率</span>
          <span class="metric-value">{{ (result.successRate * 100).toFixed(1) }}%</span>
        </div>
        <div class="metric-item">
          <span class="metric-label">交易次数</span>
          <span class="metric-value">{{ result.totalSignals }}</span>
        </div>
        <div class="metric-item">
          <span class="metric-label">盈利信号</span>
          <span class="metric-value">{{ result.winSignals }}</span>
        </div>
        <div class="metric-item">
          <span class="metric-label">数据天数</span>
          <span class="metric-value">{{ result.records }}</span>
        </div>
        <div class="metric-item">
          <span class="metric-label">执行引擎</span>
          <span class="metric-value engine">{{ result.source }}</span>
        </div>
      </div>
      <p v-if="isFallback" class="fallback-hint">{{ result.message }}</p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Close } from '@element-plus/icons-vue';
import { useBacktestStore } from '@/stores/backtest';
import type { MaBacktestResponse } from '@/types/backtest';

const props = defineProps<{ result: MaBacktestResponse }>();
defineEmits<{ close: [] }>();

const backtestStore = useBacktestStore();

const totalReturn = computed(() => backtestStore.totalReturn);
const isFallback = computed(() => props.result.source === 'java-fallback');

const returnDisplay = computed(() => {
  if (isFallback.value) return '--';
  if (totalReturn.value === null) return '--';
  const pct = totalReturn.value * 100;
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(2)}%`;
});

const returnClass = computed(() => {
  if (totalReturn.value === null || isFallback.value) return '';
  return totalReturn.value >= 0 ? 'up' : 'down';
});
</script>

<style scoped>
.metrics-card {
  position: absolute;
  top: 60px;
  right: 340px;
  z-index: 200;
  width: 280px;
}
.metrics-inner {
  background: rgba(26, 26, 46, 0.95);
  border: 1px solid #444;
}
.metrics-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}
.metrics-title { color: #fff; font-weight: 600; }
.metrics-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.metric-item {
  display: flex;
  flex-direction: column;
}
.metric-label { font-size: 11px; color: #888; }
.metric-value { font-size: 15px; font-weight: bold; color: #e0e0e0; }
.metric-value.up { color: #EF5350; }
.metric-value.down { color: #00B050; }
.metric-value.engine { font-size: 12px; font-weight: normal; color: #9e9e9e; }
.fallback-hint {
  margin-top: 8px;
  padding: 6px 8px;
  font-size: 11px;
  color: #F8BBD0;
  background: rgba(239, 83, 80, 0.12);
  border-left: 2px solid #EF5350;
  line-height: 1.4;
}
</style>
