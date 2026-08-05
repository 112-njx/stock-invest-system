<template>
  <div class="stock-detail-page">
    <TopTitle :symbol="marketStore.currentSymbol" :name="marketStore.stockName" />
    <StockSearchInput />

    <AppShell>
      <template #left>
        <div class="chart-area">
          <ChartToolbar :symbol="marketStore.currentSymbol" />
          <KLineChartPanel />
        </div>
      </template>
      <template #right>
        <SidePanel />
      </template>
    </AppShell>

    <BottomSubtitle />

    <BacktestControlBar />

    <MetricsCard
      v-if="backtestStore.result"
      :result="backtestStore.result"
      @close="backtestStore.clearResult"
    />

    <AiReportCard
      v-if="aiStore.report"
      :report="aiStore.report"
      @close="aiStore.clearReport"
    />

    <div v-if="aiStore.error" class="ai-error-banner">
      AI 分析失败：{{ aiStore.error }}
      <el-button size="small" text @click="aiStore.clearReport">关闭</el-button>
    </div>

    <LoadingOverlay v-if="marketStore.loading" :message="marketStore.loadMessage" />
    <ErrorState
      v-if="marketStore.error"
      :message="marketStore.error"
      @retry="marketStore.loadStockData(marketStore.currentSymbol)"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useMarketStore } from '@/stores/market';
import { useBacktestStore } from '@/stores/backtest';
import { useAiStore } from '@/stores/ai';
import AppShell from '@/components/layout/AppShell.vue';
import KLineChartPanel from '@/components/chart/KLineChartPanel.vue';
import ChartToolbar from '@/components/chart/ChartToolbar.vue';
import SidePanel from '@/components/quote/SidePanel.vue';
import TopTitle from '@/components/overlay/TopTitle.vue';
import BottomSubtitle from '@/components/overlay/BottomSubtitle.vue';
import BacktestControlBar from '@/components/backtest/BacktestControlBar.vue';
import MetricsCard from '@/components/backtest/MetricsCard.vue';
import AiReportCard from '@/components/ai/AiReportCard.vue';
import StockSearchInput from '@/components/common/StockSearchInput.vue';
import LoadingOverlay from '@/components/common/LoadingOverlay.vue';
import ErrorState from '@/components/common/ErrorState.vue';

const route = useRoute();
const marketStore = useMarketStore();
const backtestStore = useBacktestStore();
const aiStore = useAiStore();

onMounted(() => {
  const symbol = (route.params.symbol as string) || 'sh600519';
  marketStore.loadStockData(symbol);
});

watch(
  () => route.params.symbol,
  (newSymbol) => {
    if (newSymbol) {
      backtestStore.clearResult();
      aiStore.clearReport();
      marketStore.loadStockData(newSymbol as string);
    }
  },
);
</script>

<style scoped>
.stock-detail-page {
  position: relative;
  width: 100%;
  height: 100vh;
  overflow: hidden;
}
.chart-area {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.ai-error-banner {
  position: absolute;
  top: 60px;
  right: 340px;
  z-index: 210;
  padding: 8px 12px;
  background: rgba(239, 83, 80, 0.15);
  border: 1px solid #EF5350;
  color: #F8BBD0;
  font-size: 12px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
  width: 340px;
}
</style>
