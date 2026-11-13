<script setup lang="ts">
import { ref } from 'vue'

const panels = [
  { id: 'quote', label: '行情' },
  { id: 'sector', label: '板块' },
  { id: 'adjustment', label: '复权' },
] as const
const selected = ref<(typeof panels)[number]['id']>('quote')

// 行情和板块来自 stockdb 的 2026-11-06 收盘数据。
const quoteMetrics = [
  ['今开', '40.86'],
  ['最高', '41.68'], ['最低', '40.52'],
  ['成交额', '60.33 亿元'],
]
const constituents = [
  ['601138', '工业富联', '40.71', '-8.08%'],
  ['688256', '寒武纪', '802.90', '-4.98%'],
]
const adjustmentRows = [
  ['除息前一日', '10.00', '1.0000', '9.00'],
  ['除息日', '9.20', '1.1111', '9.20'],
]
</script>

<template>
  <section class="dataset-accordion" aria-label="数据字段示例">
    <div v-for="panel in panels" :key="panel.id" class="dataset-slice" :class="{ 'is-active': selected === panel.id }">
      <button type="button"
        :id="'dataset-button-' + panel.id" :aria-expanded="selected === panel.id"
        :aria-controls="'dataset-' + panel.id" @click="selected = panel.id">{{ panel.label }}</button>

      <div :id="'dataset-' + panel.id" :inert="selected !== panel.id" role="region"
        :aria-labelledby="'dataset-button-' + panel.id" class="dataset-panel">
        <template v-if="panel.id === 'quote'">
          <header class="dataset-heading">
            <span><strong>工业富联</strong> <small>601138.SH</small></span>
          </header>
          <div class="dataset-quote">
            <div><small>收盘价 · 元</small><strong class="dataset-number is-down">40.71</strong></div>
            <dl class="dataset-move">
              <div><dt>涨跌额</dt><dd class="is-down">−3.58 元</dd></div>
              <div><dt>涨跌幅</dt><dd class="is-down">−8.08%</dd></div>
            </dl>
          </div>
          <dl class="dataset-metrics">
            <div v-for="[label, value] in quoteMetrics" :key="label">
              <dt>{{ label }}</dt><dd>{{ value }}</dd>
            </div>
          </dl>
        </template>

        <template v-else-if="panel.id === 'sector'">
          <header class="dataset-heading">
            <span><strong>电子</strong> <small>申万一级 · 801080.SL</small></span>
          </header>
          <dl class="dataset-metrics dataset-sector-metrics">
            <div><dt>板块涨跌</dt><dd class="is-down">−3.57%</dd></div>
            <div><dt>上涨 / 下跌</dt><dd><span class="is-up">32</span> / <span class="is-down">454</span> 只</dd></div>
          </dl>
          <div class="scroll-x" tabindex="0" role="region" aria-label="代表成分股表格">
            <table class="dataset-table">
              <caption>代表成分股</caption>
              <thead><tr><th scope="col">股票</th><th scope="col">收盘价（元）</th><th scope="col">涨跌幅</th></tr></thead>
              <tbody>
                <tr v-for="[code, name, close, change] in constituents" :key="code">
                  <th scope="row">{{ name }} <small>{{ code }}</small></th><td>{{ close }}</td><td class="is-down">{{ change }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>

        <template v-else>
          <header class="dataset-heading">
            <span><strong>现金分红示例</strong> <small>每股派息 1.00 元</small></span>
          </header>
          <div class="scroll-x" tabindex="0" role="region" aria-label="收盘价对照表格">
            <table class="dataset-table">
              <caption>同一只股票的收盘价对照（元）</caption>
              <thead><tr><th scope="col">交易日</th><th scope="col">原始价</th><th scope="col">复权因子</th><th scope="col">前复权价</th></tr></thead>
              <tbody>
                <tr v-for="[day, close, factor, adjusted] in adjustmentRows" :key="day">
                  <th scope="row">{{ day }}</th><td>{{ close }}</td><td>{{ factor }}</td><td class="dataset-adjusted">{{ adjusted }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
    </div>
  </section>
</template>

<style scoped>
.dataset-accordion {
  --dataset-tab-width: 46px;
  --dataset-gap: 5px;
  display: flex;
  flex: 1;
  gap: var(--dataset-gap);
  min-height: 150px;
  container-type: inline-size;
}
.dataset-slice {
  display: flex;
  flex: 0 0 var(--dataset-tab-width);
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  background: var(--bg-panel-2);
  transition: flex .36s ease, border-color .2s;
}
.dataset-slice.is-active { flex: 1 1 0; border-color: var(--landing-rule); }
.dataset-slice button {
  flex: 0 0 calc(var(--dataset-tab-width) - 2px);
  min-height: 44px;
  writing-mode: vertical-rl;
  letter-spacing: .13em;
  font-weight: 720;
}
.dataset-slice button:hover,
.dataset-slice.is-active button { background: var(--accent-soft); color: var(--landing-accent); }
.dataset-slice button:focus-visible { outline-offset: -3px; }
.dataset-panel {
  /* Keep every panel at its expanded width so the tallest one sets a stable height. */
  flex: 0 0 calc(100cqi - 3 * var(--dataset-tab-width) - 2 * var(--dataset-gap));
  align-self: center;
  min-width: 0;
  box-sizing: border-box;
  padding: clamp(8px, 1.5vw, 18px);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}
.dataset-panel[inert] { visibility: hidden; }
.dataset-heading strong { margin-inline-end: 4px; font-size: 16px; }
.dataset-panel :is(small, dt, caption, thead) { color: var(--text-secondary); font-size: 12px; }
.dataset-quote { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 4px 14px; margin-block: 12px; }
.dataset-quote small, .dataset-number { display: block; }
.dataset-number { font-size: 30px; line-height: 1.15; }
.dataset-move { display: flex; flex-wrap: wrap; gap: 4px 12px; margin: 0; padding-bottom: 3px; }
.dataset-move dd { margin: 0; font-weight: 700; }
.dataset-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 110px), 1fr)); column-gap: 12px; margin: 0; }
.dataset-metrics > div { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 1px 6px; border-top: 1px solid var(--border); padding-block: 7px; }
.dataset-metrics dd { margin: 0; font-weight: 650; }
.dataset-sector-metrics { margin-top: 12px; }
.dataset-table { width: 100%; border-collapse: collapse; text-align: right; margin-top: 6px; }
.dataset-table caption { text-align: left; padding-block: 4px; }
.dataset-table :is(th, td) { border-bottom: 1px solid var(--border); padding: 6px 4px; white-space: nowrap; }
.dataset-table th:first-child { text-align: left; }
.dataset-table tbody th { font-weight: 600; }
.dataset-table tbody small { display: inline-block; margin-inline-start: 3px; }
.dataset-adjusted { color: var(--landing-accent); font-weight: 700; }
.is-down { color: var(--quote-down); }
.is-up { color: var(--quote-up); }
@media (prefers-reduced-motion: reduce) { .dataset-slice { transition: none; } }
</style>
