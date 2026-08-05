import { ref, onMounted, onUnmounted, type Ref } from 'vue';
import { init, dispose, LineType, type Chart } from 'klinecharts';

export function useKLineChart(containerRef: Ref<HTMLDivElement | null>) {
  const chart = ref<Chart | null>(null);

  function initChart() {
    if (!containerRef.value) return;
    const instance = init(containerRef.value, {
      styles: {
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
        },
        xAxis: { axisLine: { color: '#555' }, tickText: { color: '#aaa' } },
        yAxis: { axisLine: { color: '#555' }, tickText: { color: '#aaa' } },
        separator: { color: '#333' },
      },
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
  }

  function disposeChart() {
    if (chart.value && containerRef.value) {
      dispose(containerRef.value);
      chart.value = null;
    }
  }

  onMounted(() => { initChart(); });
  onUnmounted(() => { disposeChart(); });

  return { chart, updateData, disposeChart };
}
