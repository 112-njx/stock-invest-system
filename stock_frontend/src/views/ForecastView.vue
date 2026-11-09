<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { isAxiosError } from 'axios'
import { fetchKLine, type KLineBar } from '@/api/market'
import { getForecastHistory, setForecastTracking, startForecast, type ForecastRun } from '@/api/forecast'
import StockSearch from '@/components/layout/StockSearch.vue'
import ForecastEvidence from '@/components/trading/ForecastEvidence.vue'
import { useAuthModalStore } from '@/stores/authModal'
import { useUserStore } from '@/stores/user'

const symbol = ref('')
const bars = ref<KLineBar[]>([])
const state = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const dateFormat = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'medium', timeZone: 'Asia/Shanghai',
})
const priceFormat = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
let requestId = 0
let historyId = 0
let selection = 0
let timer: ReturnType<typeof setInterval>
let lastPoll = 0
const user = useUserStore()
const authModal = useAuthModalStore()
const runs = ref<ForecastRun[]>([])
const selected = ref<number | null>(null)
const tracking = ref(false)
const action = ref<'run' | 'track' | null>(null)
const error = ref('')
const historyError = ref(false)
const historyLoading = ref(false)
const chosen = computed(() => selected.value === null ? runs.value[0] : runs.value.find(run => run.id === selected.value))
const inProgress = (run: ForecastRun) => ['queued', 'diagnosing', 'predicting'].includes(run.status)
const hasActiveRun = computed(() => runs.value.some(inProgress))
const statuses: Record<ForecastRun['status'], string> = {
  queued: '等待分析', diagnosing: '第一阶段 · 正在诊断行情',
  predicting: '第二阶段 · 正在推演走势', completed: '分析完成', failed: '分析中断',
}
const regimes: Record<string, string> = {
  trend: '趋势', tight_channel: '窄通道', broad_channel: '宽通道',
  range: '震荡', breakout: '突破', undetermined: '无法判断',
}
const directions: Record<string, string> = { up: '涨', down: '跌', flat: '平', undetermined: '无法判断' }
const biases: Record<string, string> = { up: '偏多', down: '偏空', neutral: '中性', mixed: '多空信号冲突', undetermined: '无法判断' }
const timeFormat = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Shanghai',
})

async function refreshRuns() {
  if (!user.token || !symbol.value || action.value) return
  const id = ++historyId
  historyLoading.value = true
  lastPoll = Date.now()
  try {
    const result = await getForecastHistory(symbol.value)
    if (id !== historyId) return
    runs.value = result.runs
    tracking.value = result.tracking
    if (!result.runs.some(run => run.id === selected.value)) selected.value = null
    historyError.value = false
  } catch {
    if (id === historyId) historyError.value = true
  } finally {
    if (id === historyId) historyLoading.value = false
  }
}

watch([symbol, () => user.user?.id, () => Boolean(user.token)], () => {
  selection++
  historyId++
  runs.value = []
  selected.value = null
  tracking.value = false
  action.value = null
  error.value = ''
  historyError.value = false
  historyLoading.value = false
  void refreshRuns()
})

onMounted(() => {
  timer = setInterval(() => {
    if (!historyLoading.value && (hasActiveRun.value || tracking.value || historyError.value)
      && Date.now() - lastPoll >= (hasActiveRun.value ? 3500 : 24000)) void refreshRuns()
  }, 4000)
})
onUnmounted(() => {
  clearInterval(timer)
  selection++
  historyId++
  requestId++
})

async function runAction(kind: 'run' | 'track') {
  if (!user.token) {
    authModal.show()
    return
  }
  if (!symbol.value || action.value) return
  const id = selection
  historyId++
  historyLoading.value = false
  action.value = kind
  error.value = ''
  try {
    if (kind === 'track') {
      const response = await setForecastTracking(symbol.value, !tracking.value)
      if (id === selection) tracking.value = response.tracking
    } else {
      const result = await startForecast(symbol.value)
      if (id !== selection) return
      runs.value = [result, ...runs.value.filter(run => run.id !== result.id)].sort((a, b) => b.id - a.id)
      selected.value = result.id === runs.value[0]?.id ? null : result.id
    }
  } catch (cause) {
    if (id === selection) {
      const message = isAxiosError<{ msg?: string }>(cause) ? cause.response?.data?.msg : undefined
      error.value = message || (cause instanceof Error ? cause.message : '操作失败，请稍后重试。')
    }
  } finally {
    if (id === selection) {
      action.value = null
      if (!error.value) void refreshRuns()
    }
  }
}

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
      <p>选择 A 股股票，用已确认收盘的日 K 线分析下一根 K 线和后续走势。</p>
    </header>

    <div class="forecast-picker"><StockSearch browse @select="loadHistory" /></div>

    <section v-if="symbol" class="forecast-history forecast-analysis" aria-labelledby="forecast-analysis-title">
      <h2 id="forecast-analysis-title">{{ symbol }} · 走势分析</h2>
      <p v-if="!user.token">登录后可运行分析、查看历史记录和开启自动跟踪。</p>
      <div class="forecast-actions">
        <button type="button" class="forecast-run" :disabled="Boolean(action) || hasActiveRun" @click="runAction('run')">
          {{ action === 'run' ? '正在提交…' : chosen?.status === 'failed' ? '重新分析' : '分析走势' }}
        </button>
        <button v-if="user.token" type="button" class="forecast-retry" :aria-pressed="tracking"
          :disabled="Boolean(action) || historyLoading && !runs.length" @click="runAction('track')">
          {{ tracking ? '关闭自动跟踪' : '开启自动跟踪' }}
        </button>
      </div>
      <p v-if="tracking">自动跟踪已开启。新日线确认后会提交分析。</p>
      <p v-if="error" role="alert">{{ error }}</p>
      <p v-if="historyError" role="status">暂时无法刷新分析记录，将自动重试。</p>
      <label v-if="runs.length > 1" class="forecast-select">
        分析记录
        <select v-model="selected">
          <option :value="null">最新记录</option>
          <option v-for="run in runs" :key="run.id" :value="run.id">
            {{ timeFormat.format(new Date(run.created_at)) }} · {{ run.trigger === 'auto' ? '自动' : '手动' }} · {{ statuses[run.status] }}
          </option>
        </select>
      </label>
      <template v-if="chosen">
        <p role="status" class="forecast-status">{{ statuses[chosen.status] }}</p>
        <p>行情截至 {{ chosen.snapshot.latest_session || '暂无已确认日线' }} · {{ chosen.snapshot.bar_count }} 根日线</p>
        <p v-if="chosen.error" role="alert">{{ chosen.error }}</p>
        <section v-if="chosen.diagnosis">
          <h3>当前行情 · {{ regimes[chosen.diagnosis.regime] }} · {{ biases[chosen.diagnosis.bias] }}</h3>
          <p>{{ chosen.diagnosis.summary }}</p>
          <ForecastEvidence :items="chosen.diagnosis.evidence" />
        </section>
        <div v-if="chosen.prediction" class="forecast-results">
          <section>
            <h3>下一根日 K 线 · {{ directions[chosen.prediction.next_candle.direction] }}</h3>
            <p>{{ chosen.prediction.next_candle.reason }}</p>
            <ForecastEvidence :items="chosen.prediction.next_candle.evidence" />
          </section>
          <section>
            <h3>下一阶段走势 · {{ regimes[chosen.prediction.next_regime.regime] }}</h3>
            <p>{{ chosen.prediction.next_regime.reason }}</p>
            <ForecastEvidence :items="chosen.prediction.next_regime.evidence" />
          </section>
        </div>
        <details>
          <summary>分析数据与模型</summary>
          <p>快照时间 {{ timeFormat.format(new Date(chosen.snapshot.as_of)) }}（上海时间）</p>
          <p>来源 {{ chosen.snapshot.source ?? '—' }} · 特征版本 {{ chosen.snapshot.feature_version }}</p>
          <p v-if="chosen.snapshot.data_version">数据版本 {{ chosen.snapshot.data_version }}</p>
          <p v-if="chosen.models.diagnosis">诊断模型 {{ chosen.models.diagnosis.name }} {{ chosen.models.diagnosis.revision }}</p>
          <p v-if="chosen.models.prediction">预测模型 {{ chosen.models.prediction.name }} {{ chosen.models.prediction.revision }}</p>
        </details>
      </template>
    </section>

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
.forecast-page { box-sizing: border-box; flex: 1; min-height: 0; overflow-y: auto; width: min(100%, 960px); margin-inline: auto; padding: clamp(12px, 3vw, 32px); }
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
.forecast-analysis { margin-bottom: 16px; overflow-wrap: anywhere; }
.forecast-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.forecast-run { min-height: var(--touch-target); padding-inline: 16px; border-radius: 4px; background: var(--accent); color: white; }
.forecast-actions button:disabled { opacity: .6; }
.forecast-select { display: grid; gap: 4px; margin-block: 12px; }
.forecast-select select { width: 100%; min-width: 0; min-height: var(--touch-target); }
.forecast-status { font-weight: 700; }
.forecast-results { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); gap: 12px; }
.forecast-results section { min-width: 0; padding: 12px; border: 1px solid var(--border); border-radius: 6px; }
.forecast-analysis summary { min-height: var(--touch-target); padding-block: 12px; cursor: pointer; }
</style>
