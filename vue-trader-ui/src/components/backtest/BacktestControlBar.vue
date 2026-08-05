<template>
  <div class="backtest-control-bar">
    <div class="control-left">
      <span class="control-label">MA 回测</span>
      <el-select v-model="period" size="small" style="width: 80px">
        <el-option :value="5" label="MA5" />
        <el-option :value="10" label="MA10" />
        <el-option :value="20" label="MA20" />
      </el-select>
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        size="small"
        range-separator="至"
        start-placeholder="开始"
        end-placeholder="结束"
        format="YYYY-MM-DD"
        value-format="YYYY-MM-DD"
        style="width: 240px"
      />
      <el-button
        type="primary"
        size="small"
        :loading="backtestStore.executing"
        @click="run"
      >
        执行回测
      </el-button>
      <el-button
        type="warning"
        size="small"
        :disabled="!backtestStore.result || aiStore.generating"
        :loading="aiStore.generating"
        @click="runAiAnalyze"
      >
        生成AI投资分析报告
      </el-button>
    </div>
    <div class="control-right">
      <el-switch v-model="backtestStore.showSignals" size="small" active-text="显示信号" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useMarketStore } from '@/stores/market';
import { useBacktestStore } from '@/stores/backtest';
import { useAiStore } from '@/stores/ai';

const marketStore = useMarketStore();
const backtestStore = useBacktestStore();
const aiStore = useAiStore();

const period = ref(5);
const dateRange = ref<string[]>([getDefaultStart(), new Date().toISOString().slice(0, 10)]);

function getDefaultStart(): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() - 1);
  return d.toISOString().slice(0, 10);
}

function run() {
  backtestStore.runMaBacktest(
    marketStore.currentSymbol,
    period.value,
    dateRange.value[0],
    dateRange.value[1],
  );
}

function runAiAnalyze() {
  aiStore.generateReport(marketStore.currentSymbol, backtestStore.result);
}
</script>

<style scoped>
.backtest-control-bar {
  position: absolute;
  bottom: 36px;
  left: 0;
  right: 0;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  background: rgba(30, 30, 50, 0.95);
  border-top: 1px solid #333;
  z-index: 50;
}
.control-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.control-label {
  font-size: 13px;
  color: #ccc;
  font-weight: bold;
}
.control-right {
  display: flex;
  align-items: center;
}
</style>
