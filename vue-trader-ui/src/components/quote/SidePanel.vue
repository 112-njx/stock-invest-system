<template>
  <div class="side-panel">
    <StockInfoHeader
      :symbol="marketStore.currentSymbol"
      :name="marketStore.stockName"
      @close="$router.push('/')"
    />
    <QuoteDataTable :quote="marketStore.realtimeQuote" :symbol="marketStore.currentSymbol" />
    <FiveLevelQuotes />
    <MiniTimeChart />
  </div>
</template>

<script setup lang="ts">
import { useMarketStore } from '@/stores/market';
import StockInfoHeader from './StockInfoHeader.vue';
import QuoteDataTable from './QuoteDataTable.vue';
import FiveLevelQuotes from './FiveLevelQuotes.vue';
import MiniTimeChart from './MiniTimeChart.vue';

const marketStore = useMarketStore();
</script>

<style scoped>
.side-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #12122a;
  font-size: 12px;
}
</style>
