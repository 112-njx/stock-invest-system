<template>
  <div ref="chartContainer" class="kline-chart-container" />
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue';
import { useMarketStore } from '@/stores/market';
import { useBacktestStore } from '@/stores/backtest';
import { init, dispose, LineType, type Chart } from 'klinecharts';

const marketStore = useMarketStore();
const backtestStore = useBacktestStore();
const chartContainer = ref<HTMLDivElement | null>(null);
const chart = ref<Chart | null>(null);
const overlayIds = ref<string[]>([]);

const CHART_STYLES = {
  grid: {
    horizontal: { style: LineType.Dashed, color: '#333' },
    vertical: { style: LineType.Dashed, color: '#333' },
  },
  candle: {
    bar: {
      upColor: '#EF5350',
      downColor: '#00B050',
      noChangeColor: '#888888',
      upBorderColor: '#EF5350',
      downBorderColor: '#00B050',
      upWickColor: '#EF5350',
      downWickColor: '#00B050',
      noChangeWickColor: '#888888',
    },
    priceMark: {
      last: {
        show: true,
        upColor: '#EF5350',
        downColor: '#00B050',
        noChangeColor: '#888888',
      },
    },
  },
  xAxis: {
    axisLine: { color: '#555' },
    tickText: { color: '#aaa', size: 10 },
    tickLine: { color: '#555' },
  },
  yAxis: {
    axisLine: { color: '#555' },
    tickText: { color: '#aaa', size: 10 },
    tickLine: { color: '#555' },
  },
  separator: { color: '#333' },
  indicator: {
    lines: [
      { color: '#EF5350' },
      { color: '#8B8B00' },
      { color: '#9C27B0' },
    ],
    bars: [
      { upColor: '#EF5350', downColor: '#00B050', noChangeColor: '#888888' },
    ],
  },
};

function initChart() {
  if (!chartContainer.value) return;

  const instance = init(chartContainer.value, {
    styles: CHART_STYLES,
  });
  if (!instance) return;

  instance.createIndicator('MA', true, { id: 'candle_pane' });
  instance.createIndicator('VOL');
  instance.createIndicator('MACD');

  chart.value = instance as Chart;
}

function updateData(rawData: {
  tradeDate: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}[]) {
  if (!chart.value || rawData.length === 0) return;
  const klineData = rawData.map((d) => ({
    timestamp: new Date(d.tradeDate + 'T00:00:00').getTime(),
    open: d.open,
    high: d.high,
    low: d.low,
    close: d.close,
    volume: d.volume,
  }));
  chart.value.applyNewData(klineData);
  renderSignalMarks();
}

function clearSignalMarks() {
  const c = chart.value;
  if (!c) return;
  for (const id of overlayIds.value) {
    c.removeOverlay(id);
  }
  overlayIds.value = [];
}

function renderSignalMarks() {
  const c = chart.value;
  if (!c) return;
  clearSignalMarks();

  const result = backtestStore.result;
  if (!result || !backtestStore.showSignals) return;

  const signals = result.signals || [];
  if (signals.length === 0) return;

  signals.forEach((sig) => {
    const ts = new Date(sig.date + 'T00:00:00').getTime();
    const isBuy = sig.signalCode === 'CROSS_UP';
    const text = isBuy ? 'B' : 'S';
    const color = isBuy ? '#EF5350' : '#00B050';

    const overlayId = c.createOverlay({
      name: 'simpleAnnotation',
      groupId: 'ma-signals',
      points: [{ timestamp: ts, value: sig.closePrice }],
      extendData: text,
      styles: {
        text: {
          color: '#ffffff',
          backgroundColor: color,
          size: 11,
          weight: 'bold',
          borderRadius: 2,
          paddingLeft: 4,
          paddingRight: 4,
          paddingTop: 2,
          paddingBottom: 2,
        },
        line: { color, size: 1 },
      },
    });

    if (typeof overlayId === 'string' && overlayId.length > 0) {
      overlayIds.value.push(overlayId);
    }
  });
}

onMounted(() => {
  initChart();
  if (marketStore.klineData.length > 0) {
    updateData(marketStore.klineData);
  }
});

watch(
  () => marketStore.klineData,
  (data) => {
    if (data.length > 0) updateData(data);
  },
  { deep: true },
);

watch(
  () => backtestStore.result,
  () => renderSignalMarks(),
);

watch(
  () => backtestStore.showSignals,
  () => renderSignalMarks(),
);

watch(
  () => marketStore.currentSymbol,
  () => clearSignalMarks(),
);

onUnmounted(() => {
  if (chart.value && chartContainer.value) {
    clearSignalMarks();
    dispose(chartContainer.value);
  }
});
</script>

<style scoped>
.kline-chart-container {
  width: 100%;
  height: 100%;
}
</style>
