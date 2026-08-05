import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { executeMaBacktest, fetchBacktestResults } from '@/api/backtest';
import type { MaBacktestResponse, BacktestResultView, KLineSignalMark } from '@/types/backtest';

export const useBacktestStore = defineStore('backtest', () => {
  const executing = ref(false);
  const result = ref<MaBacktestResponse | null>(null);
  const showSignals = ref(true);

  function buildSignalMarks(): KLineSignalMark[] {
    if (!result.value) return [];
    const marks: KLineSignalMark[] = [];
    for (const d of result.value.crossUpDates) {
      marks.push({ date: d, text: 'B', color: '#EF5350', position: 'below' });
    }
    for (const d of result.value.crossDownDates) {
      marks.push({ date: d, text: 'S', color: '#00B050', position: 'above' });
    }
    return marks;
  }

  const totalReturn = computed<number | null>(() => {
    const r = result.value;
    if (!r || !r.signals || r.signals.length === 0) return null;

    const ordered = [...r.signals].sort((a, b) => a.date.localeCompare(b.date));
    let acc = 0;
    let hasTrade = false;
    let holdingPrice: number | null = null;

    for (const s of ordered) {
      if (s.signalCode === 'CROSS_UP') {
        if (holdingPrice === null && s.closePrice > 0) {
          holdingPrice = s.closePrice;
        }
      } else if (s.signalCode === 'CROSS_DOWN') {
        if (holdingPrice !== null && holdingPrice > 0 && s.closePrice > 0) {
          acc += (s.closePrice - holdingPrice) / holdingPrice;
          hasTrade = true;
          holdingPrice = null;
        }
      }
    }
    return hasTrade ? acc : null;
  });

  async function runMaBacktest(symbol: string, period: number, startDate: string, endDate: string) {
    executing.value = true;
    try {
      const res = await executeMaBacktest({ symbol, period, startDate, endDate });
      result.value = res;
    } finally {
      executing.value = false;
    }
  }

  function clearResult() {
    result.value = null;
  }

  return {
    executing,
    result,
    showSignals,
    totalReturn,
    buildSignalMarks,
    runMaBacktest,
    clearResult,
  };
});
