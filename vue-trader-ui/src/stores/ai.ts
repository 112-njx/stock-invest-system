import { defineStore } from 'pinia';
import { ref } from 'vue';
import { postAiAnalyze } from '@/api/ai';
import type { AiAnalyzeResponse } from '@/types/ai';
import type { MaBacktestResponse } from '@/types/backtest';

function buildPrompt(symbol: string, backtest: MaBacktestResponse | null): string {
  if (!backtest) {
    return `请分析一下 ${symbol} 最近走势，结合近30天K线和MA5上穿下穿信号给出看法`;
  }
  const period = backtest.period;
  const total = backtest.totalSignals;
  const win = backtest.winSignals;
  const rate = (backtest.successRate * 100).toFixed(1);
  return (
    `请分析 ${symbol} 最近走势，并结合刚刚跑完的 MA${period} 均线交叉回测结果给出投资建议。` +
    `回测数据：${backtest.records} 个交易日，共 ${total} 个信号，其中盈利 ${win} 个，胜率 ${rate}%。` +
    `请围绕近30天K线、MA${period}上穿/下穿信号、胜率含义和风险控制进行说明。`
  );
}

export const useAiStore = defineStore('ai', () => {
  const generating = ref(false);
  const report = ref<AiAnalyzeResponse | null>(null);
  const error = ref<string | null>(null);

  async function generateReport(symbol: string, backtest: MaBacktestResponse | null) {
    generating.value = true;
    error.value = null;
    try {
      const prompt = buildPrompt(symbol, backtest);
      report.value = await postAiAnalyze({ prompt });
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'AI 分析请求失败';
      report.value = null;
    } finally {
      generating.value = false;
    }
  }

  function clearReport() {
    report.value = null;
    error.value = null;
  }

  return { generating, report, error, generateReport, clearReport };
});
