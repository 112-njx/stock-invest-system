<script setup lang="ts">
import { ref } from 'vue'
import { fetchKLine, type KLineBar } from '@/api/market'
import StockSearch from '@/components/layout/StockSearch.vue'

const symbol = ref('')
const bars = ref<KLineBar[]>([])
const state = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const dateFormat = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'medium', timeZone: 'Asia/Shanghai',
})
const priceFormat = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
let requestId = 0

async function loadHistory(code: string) {
  const id = ++requestId
  symbol.value = code
  state.value = 'loading'
  bars.value = []
  try {
    const rows = await fetchKLine({ symbol: code, period: '1d', limit: 10 })
    if (id !== requestId) return
    bars.value = [...rows].sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts))
    state.value = 'ready'
  } catch {
    if (id === requestId) state.value = 'error'
  }
}
</script>

<template>
  <section class="forecast-page" aria-labelledby="forecast-title">
    <header>
      <h1 id="forecast-title">预测走势</h1>
      <p>选择 A 股股票，查看最近的日 K 线。下一根 K 线与下一阶段走势分析正在开发。</p>
    </header>

    <div class="forecast-picker"><StockSearch browse @select="loadHistory" /></div>

    <section v-if="symbol" class="forecast-history" aria-labelledby="forecast-history-title" :aria-busy="state === 'loading'">
      <h2 id="forecast-history-title">{{ symbol }} · 最近日 K 线</h2>
      <p v-if="state === 'loading'" role="status">正在读取历史行情…</p>
      <template v-else-if="state === 'error'">
        <p role="status">暂时无法读取历史行情。</p>
        <button type="button" class="forecast-retry" @click="loadHistory(symbol)">重试</button>
      </template>
      <p v-else-if="!bars.length" role="status">该股票暂无可用的日 K 线。</p>
      <div v-else class="scroll-x" role="region" aria-label="最近的日 K 线数据" tabindex="0">
        <table>
          <thead><tr><th scope="col">日期</th><th scope="col">开盘</th><th scope="col">最高</th><th scope="col">最低</th><th scope="col">收盘</th></tr></thead>
          <tbody>
            <tr v-for="bar in bars" :key="bar.ts">
              <th scope="row">{{ dateFormat.format(new Date(bar.ts)) }}</th>
              <td>{{ priceFormat.format(bar.open) }}</td><td>{{ priceFormat.format(bar.high) }}</td>
              <td>{{ priceFormat.format(bar.low) }}</td><td>{{ priceFormat.format(bar.close) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>

<style scoped>
.forecast-page { box-sizing: border-box; width: min(100%, 960px); margin-inline: auto; padding: clamp(12px, 3vw, 32px); }
.forecast-page h1 { margin: 0 0 8px; }
.forecast-page p { color: var(--text-secondary); }
.forecast-picker { margin-block: 20px; max-width: 420px; }
.forecast-picker :deep(.stock-search), .forecast-picker :deep(.stock-search__dropdown) { width: 100%; min-width: 0; }
.forecast-picker :deep(.stock-search__input), .forecast-retry { min-height: var(--touch-target); }
.forecast-history { padding: 16px; background: var(--bg-panel); border: 1px solid var(--border); border-radius: 8px; }
.forecast-history h2 { font-size: 16px; margin: 0 0 12px; }
.forecast-history table { width: 100%; border-collapse: collapse; white-space: nowrap; font-variant-numeric: tabular-nums; }
.forecast-history th, .forecast-history td { padding: 8px; text-align: end; border-bottom: 1px solid var(--border); }
.forecast-history th:first-child { text-align: start; }
.forecast-retry { padding-inline: 16px; border: 1px solid var(--border); border-radius: 4px; }
</style>
