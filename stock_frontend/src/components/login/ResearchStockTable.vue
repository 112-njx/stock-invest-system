<script setup lang="ts">
import { formatAmount, formatPct, formatPrice, trendClass } from '@/utils/color'

const stocks = [
  { code: '000001', name: '平安银行', close: 11.89, change: 0.08, percent: 0.68, volume: 120000000, amount: 1422000000, turnover: 0.62, ratio: 0.75 },
  { code: '000002', name: '万科A', close: 3.19, change: -0.05, percent: -1.54, volume: 127000000, amount: 410000000, turnover: 1.31, ratio: 0.58 },
  { code: '000006', name: '深振业A', close: 6.11, change: -0.02, percent: -0.33, volume: 11894200, amount: 73200000, turnover: 0.88, ratio: 0.65 },
  { code: '000007', name: '全新好', close: 9.39, change: 0.12, percent: 1.29, volume: 5217900, amount: 49230000, turnover: 1.51, ratio: 0.56 },
  { code: '000010', name: '*ST美丽', close: 1.09, change: 0, percent: 0, volume: 18048700, amount: 19650000, turnover: 1.9, ratio: 0.66 },
]
</script>

<template>
  <figure class="research-stock-table">
    <figcaption id="research-stock-caption">
      <strong>候选标的</strong>
      <span>行情样本 · {{ stocks.length }} 只</span>
    </figcaption>
    <div class="scroll-x" tabindex="0" role="region" aria-labelledby="research-stock-caption">
      <table aria-label="候选标的行情对比">
        <thead>
          <tr>
            <th scope="col">名称 / 代码</th>
            <th scope="col">收盘价</th>
            <th scope="col">涨跌幅</th>
            <th scope="col">涨跌额</th>
            <th scope="col">成交量（股）</th>
            <th scope="col">成交额（元）</th>
            <th scope="col">换手率</th>
            <th scope="col">量比</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="stock in stocks" :key="stock.code">
            <th scope="row"><span>{{ stock.name }}</span> <small>{{ stock.code }}</small></th>
            <td :class="trendClass(stock.change)">{{ formatPrice(stock.close) }}</td>
            <td :class="trendClass(stock.change)">{{ formatPct(stock.percent) }}</td>
            <td :class="trendClass(stock.change)">{{ stock.change > 0 ? '+' : '' }}{{ formatPrice(stock.change) }}</td>
            <td>{{ formatAmount(stock.volume) }}</td>
            <td>{{ formatAmount(stock.amount) }}</td>
            <td>{{ stock.turnover.toFixed(2) }}%</td>
            <td>{{ formatPrice(stock.ratio) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </figure>
</template>

<style scoped>
.research-stock-table {
  margin: 0;
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-panel-2);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
figcaption { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 2px 10px; padding: 6px 10px; }
figcaption span, small, thead { color: var(--text-secondary); }
.scroll-x:focus-visible { outline: 2px solid var(--landing-accent); outline-offset: -2px; }
table { width: 100%; min-width: 520px; border-spacing: 0; text-align: right; }
th, td { padding: 4px 8px; border-top: 1px solid var(--border); line-height: 1.35; white-space: nowrap; }
thead th { font-weight: 600; }
th:first-child {
  position: sticky;
  left: 0;
  min-width: 96px;
  border-right: 1px solid var(--border);
  background: var(--bg-panel-2);
  text-align: left;
}
tbody th span { color: var(--quote-highlight); }
tbody th small { font-weight: 400; }
.t-up { color: var(--quote-up); }
.t-down { color: var(--quote-down); }
</style>
