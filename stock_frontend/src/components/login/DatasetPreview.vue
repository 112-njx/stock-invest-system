<script setup lang="ts">
import { ref } from 'vue'

const panels = [
  { id: 'quote', label: '行情' },
  { id: 'sector', label: '板块' },
  { id: 'adjustment', label: '复权' },
] as const
const selected = ref<(typeof panels)[number]['id']>('quote')

// 收盘样本来自 stockdb 的个股日 K 与行业云图，取相同交易日。
const sampleDate = '2026-11-06'
const quoteMetrics = [
  ['昨收', '44.29'], ['今开', '40.86'],
  ['最高', '41.68'], ['最低', '40.52'],
  ['成交量', '1.47 亿股'], ['成交额', '60.33 亿元'],
  ['振幅', '2.62%'], ['总市值', '8,078.53 亿元'],
]
const constituents = [
  ['601138', '工业富联', '40.71', '-8.08%'],
  ['688256', '寒武纪', '802.90', '-4.98%'],
  ['688008', '澜起科技', '150.10', '-8.36%'],
  ['002463', '沪电股份', '73.21', '-9.62%'],
]
const adjustmentRows = [
  ['除息前一日', '10.00', '1.0000', '9.00'],
  ['除息日', '9.20', '1.1111', '9.20'],
]
</script>

<template>
  <section class="dataset-preview" aria-label="数据字段示例">
    <div class="dataset-switch">
      <button v-for="panel in panels" :key="panel.id" type="button"
        :id="'dataset-button-' + panel.id" :aria-expanded="selected === panel.id"
        :aria-controls="'dataset-' + panel.id" @click="selected = panel.id">{{ panel.label }}</button>
    </div>

    <div id="dataset-quote" v-show="selected === 'quote'" role="region" aria-labelledby="dataset-button-quote" class="dataset-panel">
      <header class="dataset-heading">
        <span><strong>工业富联</strong> <small>601138.SH</small></span>
        <time :datetime="sampleDate">{{ sampleDate }} 收盘样本</time>
      </header>
      <div class="dataset-quote">
        <div><small>收盘价 · 元</small><strong class="dataset-number is-down">40.71</strong></div>
        <span class="dataset-move is-down" aria-label="涨跌额负3.58元，涨跌幅负8.08%">−3.58 <b>−8.08%</b></span>
      </div>
      <dl class="dataset-metrics">
        <div v-for="[label, value] in quoteMetrics" :key="label">
          <dt>{{ label }}</dt><dd>{{ value }}</dd>
        </div>
      </dl>
    </div>

    <div id="dataset-sector" v-show="selected === 'sector'" role="region" aria-labelledby="dataset-button-sector" class="dataset-panel">
      <header class="dataset-heading">
        <span><strong>电子</strong> <small>申万一级 · 801080.SL</small></span>
        <time :datetime="sampleDate">{{ sampleDate }} 收盘样本</time>
      </header>
      <dl class="dataset-metrics dataset-sector-metrics">
        <div><dt>板块涨跌</dt><dd class="is-down">−3.57%</dd></div>
        <div><dt>上涨 / 下跌</dt><dd><span class="is-up">32</span> / <span class="is-down">454</span> 只</dd></div>
      </dl>
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

    <div id="dataset-adjustment" v-show="selected === 'adjustment'" role="region" aria-labelledby="dataset-button-adjustment" class="dataset-panel">
      <header class="dataset-heading">
        <span><strong>现金分红示例</strong> <small>每股派息 1.00 元</small></span>
        <small>模拟数据</small>
      </header>
      <table class="dataset-table">
        <caption>同一只股票的收盘价对照（元）</caption>
        <thead><tr><th scope="col">交易日</th><th scope="col">原始价</th><th scope="col">复权因子</th><th scope="col">前复权价</th></tr></thead>
        <tbody>
          <tr v-for="[day, close, factor, adjusted] in adjustmentRows" :key="day">
            <th scope="row">{{ day }}</th><td>{{ close }}</td><td>{{ factor }}</td><td class="dataset-adjusted">{{ adjusted }}</td>
          </tr>
        </tbody>
      </table>
      <p class="dataset-note">前复权以除息日价格为基准，把前一日收盘价折算为 9.00 元。这样跨除息日比较时，可以看到 9.00 → 9.20 元的变化。</p>
    </div>
  </section>
</template>

<style scoped>
.dataset-preview { flex: 1; min-width: 0; border: 1px solid var(--border-strong); border-radius: 8px; background: var(--bg-panel-2); }
.dataset-switch { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border-bottom: 1px solid var(--border-strong); }
.dataset-switch button { min-height: 44px; border-bottom: 2px solid transparent; color: var(--text-secondary); font-weight: 700; }
.dataset-switch button:hover,
.dataset-switch button[aria-expanded="true"] { background: var(--accent-soft); color: var(--landing-accent); }
.dataset-switch button[aria-expanded="true"] { border-color: var(--landing-accent); }
.dataset-switch button:focus-visible { outline-offset: -3px; }
.dataset-panel { padding: clamp(10px, 1.5vw, 18px); font-size: 13px; font-variant-numeric: tabular-nums; }
.dataset-heading { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 4px 10px; }
.dataset-heading strong { margin-inline-end: 4px; font-size: 16px; }
.dataset-panel :is(small, time, dt, caption, thead) { color: var(--text-secondary); font-size: 12px; }
.dataset-quote { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 4px 14px; margin-block: 12px; }
.dataset-quote small, .dataset-number { display: block; }
.dataset-number { font-size: 30px; line-height: 1.15; }
.dataset-move { padding-bottom: 3px; }
.dataset-move b { margin-inline-start: 4px; }
.dataset-metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 12px; margin: 0; }
.dataset-metrics > div { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 1px 6px; border-top: 1px solid var(--border); padding-block: 7px; }
.dataset-metrics dd { margin: 0; font-weight: 650; }
.dataset-sector-metrics { margin-top: 12px; }
.dataset-table { width: 100%; border-collapse: collapse; text-align: right; margin-top: 6px; }
.dataset-table caption { text-align: left; padding-block: 4px; }
.dataset-table :is(th, td) { border-bottom: 1px solid var(--border); padding: 6px 2px; }
.dataset-table th:first-child { text-align: left; }
.dataset-table tbody th { font-weight: 600; }
.dataset-table tbody small { display: inline-block; margin-inline-start: 3px; }
.dataset-adjusted { color: var(--landing-accent); font-weight: 700; }
.dataset-panel .dataset-note { margin-top: 12px; font-size: 12px; }
.is-down { color: var(--quote-down); }
.is-up { color: var(--quote-up); }
</style>
