<template>
  <div class="quote-data-table">
    <div class="quote-row" v-for="row in rows" :key="row.label">
      <span class="label">{{ row.label }}</span>
      <span class="value" :class="row.highlight">{{ row.value }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { MarketQuote } from '@/types/market';

const props = defineProps<{ quote: MarketQuote | null; symbol: string }>();

const rows = computed(() => {
  if (!props.quote) {
    return [
      { label: '最新价', value: '--' },
      { label: '开盘价', value: '--' },
      { label: '最高价', value: '--' },
      { label: '最低价', value: '--' },
      { label: '收盘价', value: '--' },
      { label: '成交量', value: '--' },
      { label: '成交额', value: '--' },
      { label: '涨幅', value: '--' },
      { label: '振幅', value: '--' },
    ];
  }

  const q = props.quote;
  const changeColor = q.changePercent >= 0 ? 'up' : 'down';

  return [
    { label: '最新价', value: q.lastPrice?.toFixed(2) ?? '--', highlight: changeColor },
    { label: '开盘价', value: `${q.openPrice?.toFixed(2)}(${((q.openPrice - q.prevClosePrice) / q.prevClosePrice * 100).toFixed(2)}%)` },
    { label: '最高价', value: `${q.highPrice?.toFixed(2)}(${((q.highPrice - q.prevClosePrice) / q.prevClosePrice * 100).toFixed(2)}%)` },
    { label: '最低价', value: `${q.lowPrice?.toFixed(2)}(${((q.lowPrice - q.prevClosePrice) / q.prevClosePrice * 100).toFixed(2)}%)` },
    { label: '收盘价', value: q.lastPrice?.toFixed(2) },
    { label: '成交量', value: formatVolume(q.volume) },
    { label: '成交额', value: formatTurnover(q.turnover) },
    { label: '涨幅', value: `${q.changePercent?.toFixed(2)}%`, highlight: changeColor },
    { label: '振幅', value: q.highPrice && q.lowPrice ? `${((q.highPrice - q.lowPrice) / q.prevClosePrice * 100).toFixed(2)}%` : '--' },
  ];
});

function formatVolume(v: number): string {
  if (v >= 1e8) return (v / 1e8).toFixed(1) + '亿';
  if (v >= 1e4) return (v / 1e4).toFixed(0) + '万';
  return String(v);
}

function formatTurnover(v: number): string {
  if (v >= 1e8) return (v / 1e8).toFixed(1) + '亿';
  if (v >= 1e4) return (v / 1e4).toFixed(0) + '万';
  return String(v);
}
</script>

<style scoped>
.quote-data-table {
  padding: 8px 12px;
}
.quote-row {
  display: flex;
  justify-content: space-between;
  padding: 3px 0;
  border-bottom: 1px solid #1a1a36;
}
.label {
  color: #888;
}
.value {
  color: #ccc;
  text-align: right;
}
.value.up { color: #EF5350; }
.value.down { color: #00B050; }
</style>
