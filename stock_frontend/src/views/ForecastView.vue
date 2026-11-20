<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { isAxiosError } from 'axios'
import { fetchKLine, searchSymbols, type KLineBar, type SymbolInfo } from '@/api/market'
import {
  getForecastHistory, getForecastRunSnapshot, retryForecast, setForecastTracking, startForecast, type ForecastRun,
} from '@/api/forecast'
import StockSearch from '@/components/layout/StockSearch.vue'
import KLineChart from '@/components/trading/KLineChart.vue'
import ForecastEvidence from '@/components/trading/ForecastEvidence.vue'
import ForecastReplay from '@/components/trading/ForecastReplay.vue'
import { useAuthModalStore } from '@/stores/authModal'
import { useUserStore } from '@/stores/user'

const user = useUserStore()
const auth = useAuthModalStore()
const code = ref('')
const stock = ref<SymbolInfo | null>(null)
const stockLoading = ref(false)
const stockError = ref('')
const latest = ref<KLineBar | null>(null)
const runs = ref<ForecastRun[]>([])
const runId = ref<number | null>(null)
const tracking = ref(false)
const historyError = ref('')
const actionError = ref('')
const action = ref<'start' | 'retry' | 'track' | null>(null)
const resultTab = ref<'prediction' | 'replay'>('prediction')
const visiblePane = ref<'chart' | 'results'>('chart')
const chartPanel = ref<HTMLElement>()
const chartMode = ref<'latest' | 'snapshot' | 'replay'>('latest')
const chartRows = ref<KLineBar[] | null>(null)
const chartLoading = ref(false)
const chartError = ref('')
const focusSession = ref<{ day: string }>()
const chosen = computed(() => runId.value === null ? runs.value[0] : runs.value.find(run => run.id === runId.value))
const activeRun = computed(() => runs.value.find(run => ['queued', 'diagnosing', 'predicting'].includes(run.status)))
const displayedBar = computed(() => chartMode.value === 'latest' ? latest.value : chartRows.value?.at(-1))
const source = computed(() => chartMode.value === 'snapshot' ? chosen.value?.snapshot.source : displayedBar.value?.source)
const cutoff = computed(() => chartMode.value === 'snapshot' ? chosen.value?.snapshot.latest_session : displayedBar.value?.ts.slice(0, 10))
const statusText: Record<ForecastRun['status'], string> = {
  queued: '等待分析', diagnosing: '正在诊断行情', predicting: '正在推演走势', completed: '分析完成', failed: '分析失败',
}
const progressSteps = ['queued', 'diagnosing', 'predicting', 'completed'] as const
const progressIndex = computed(() => progressSteps.findIndex(step => step === activeRun.value?.status))
const regimes: Record<string, string> = {
  trend: '趋势', tight_channel: '窄通道', broad_channel: '宽通道', range: '震荡', breakout: '突破', undetermined: '无法判断',
}
const directions: Record<string, string> = { up: '↑ 涨', down: '↓ 跌', flat: '→ 平', undetermined: '？无法判断' }
const biases: Record<string, string> = { up: '偏多', down: '偏空', neutral: '中性', mixed: '多空信号冲突', undetermined: '无法判断' }
const dateTime = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Shanghai' })
let selectionVersion = 0
let historyVersion = 0
let historyPending = false
let stockVersion = 0
let chartVersion = 0
let timer: ReturnType<typeof setInterval>

function message(error: unknown, fallback: string) {
  return isAxiosError<{ msg?: string }>(error) ? error.response?.data?.msg || fallback : fallback
}

async function selectStock(value: string) {
  const version = ++stockVersion
  code.value = value
  stock.value = null
  latest.value = null
  stockError.value = ''
  stockLoading.value = true
  visiblePane.value = 'chart'
  showLatest()
  try {
    const found = await searchSymbols(value, { type: 'stock' })
    if (version !== stockVersion) return
    stock.value = found.find(item => item.code === value) ?? null
    if (!stock.value) stockError.value = '找不到该股票'
  } catch {
    if (version === stockVersion) stockError.value = '股票载入失败'
  } finally {
    if (version === stockVersion) stockLoading.value = false
  }
}

async function refreshHistory() {
  if (!code.value || !user.token || action.value || historyPending) return
  const version = ++historyVersion
  historyPending = true
  try {
    const history = await getForecastHistory(code.value)
    if (version !== historyVersion) return
    runs.value = history.runs
    tracking.value = history.tracking
    if (!runs.value.some(run => run.id === runId.value)) runId.value = null
    historyError.value = ''
  } catch {
    if (version === historyVersion) historyError.value = '分析记录读取失败'
  } finally {
    if (version === historyVersion) historyPending = false
  }
}

watch([code, () => user.user?.id, () => Boolean(user.token)], () => {
  selectionVersion++
  historyVersion++
  historyPending = false
  runId.value = null
  runs.value = []
  tracking.value = false
  historyError.value = actionError.value = ''
  action.value = null
  showLatest()
  void refreshHistory()
})

watch(() => chosen.value?.id, () => {
  if (chartMode.value === 'snapshot') showLatest()
})

onMounted(() => {
  timer = setInterval(() => {
    if (activeRun.value || tracking.value || historyError.value) void refreshHistory()
  }, 5000)
})

onUnmounted(() => {
  clearInterval(timer)
  selectionVersion++
  historyVersion++
  stockVersion++
  chartVersion++
})

async function runAction(kind: NonNullable<typeof action.value>) {
  if (!user.token) { auth.show('login'); return }
  if (!stock.value || action.value) return
  const version = selectionVersion
  historyVersion++
  action.value = kind
  historyPending = false
  actionError.value = ''
  try {
    if (kind === 'track') {
      const result = await setForecastTracking(code.value, !tracking.value)
      if (version === selectionVersion) tracking.value = result.tracking
    } else {
      const retryId = chosen.value?.id
      const run = kind === 'retry' && retryId ? await retryForecast(retryId) : await startForecast(code.value)
      if (version !== selectionVersion) return
      runs.value = [run, ...runs.value.filter(item => item.id !== run.id)].sort((a, b) => b.id - a.id)
      runId.value = run.id
      resultTab.value = 'prediction'
      visiblePane.value = 'results'
    }
  } catch (error) {
    if (version === selectionVersion) actionError.value = message(error, '操作失败，请重试')
  } finally {
    if (version === selectionVersion) {
      action.value = null
      void refreshHistory()
    }
  }
}

function showLatest() {
  chartVersion++
  chartMode.value = 'latest'
  chartRows.value = null
  chartLoading.value = false
  chartError.value = ''
  focusSession.value = undefined
}

async function revealChart(day: string) {
  visiblePane.value = 'chart'
  focusSession.value = { day }
  await nextTick()
  chartPanel.value?.scrollIntoView({ block: 'nearest' })
}

async function showSnapshot(day?: string) {
  const run = chosen.value
  if (!run) return
  if (chartMode.value === 'snapshot' && chartRows.value) {
    if (day) await revealChart(day)
    return
  }
  const version = ++chartVersion
  chartMode.value = 'snapshot'
  chartRows.value = null
  chartLoading.value = true
  chartError.value = ''
  focusSession.value = day ? { day } : undefined
  try {
    const { rows } = await getForecastRunSnapshot(run.id)
    if (version !== chartVersion) return
    chartRows.value = rows
    if (day) await revealChart(day)
  } catch (error) {
    if (version === chartVersion) chartError.value = message(error, '分析快照读取失败')
  } finally {
    if (version === chartVersion) chartLoading.value = false
  }
}

async function showReplayDay(day: string) {
  const symbolId = stock.value?.id
  if (symbolId === undefined) return
  const version = ++chartVersion
  chartMode.value = 'replay'
  chartRows.value = null
  chartLoading.value = true
  chartError.value = ''
  await revealChart(day)
  const date = new Date(`${day}T00:00:00Z`)
  const start = new Date(date)
  const end = new Date(date)
  start.setUTCDate(start.getUTCDate() - 60)
  end.setUTCDate(end.getUTCDate() + 16)
  if (version !== chartVersion) return
  try {
    const rows = await fetchKLine({ symbol: symbolId, period: '1d', start: start.toISOString(), end: end.toISOString() })
    if (version === chartVersion) chartRows.value = rows
  } catch (error) {
    if (version === chartVersion) chartError.value = message(error, '回放日期附近的行情读取失败')
  } finally {
    if (version === chartVersion) chartLoading.value = false
  }
}

function focusedDayMissing(day: string) {
  chartError.value = `当前图表缺少 ${day} 的日 K 线`
}

function retryChart() {
  if (stockError.value) void selectStock(code.value)
  else if (chartMode.value === 'snapshot') void showSnapshot(focusSession.value?.day)
  else if (focusSession.value) void showReplayDay(focusSession.value.day)
}
</script>

<template>
  <section class="forecast-page" aria-labelledby="forecast-title">
    <header class="forecast-toolbar">
      <div class="forecast-identity">
        <h1 id="forecast-title">预测走势</h1>
        <strong v-if="stock">{{ stock.name }} <span>{{ stock.code }}</span></strong>
      </div>
      <StockSearch browse @select="selectStock" />
      <div class="forecast-actions">
        <button type="button" class="forecast-primary" :disabled="!stock || !!action || !!activeRun" @click="runAction('start')">
          {{ action === 'start' ? '正在提交…' : activeRun ? '分析中' : '开始分析' }}
        </button>
        <button type="button" :aria-pressed="tracking" :disabled="!stock || !!action" @click="runAction('track')">
          {{ tracking ? '关闭自动跟踪' : '开启自动跟踪' }}
        </button>
      </div>
      <div v-if="activeRun" class="forecast-progress">
        <span role="status">{{ statusText[activeRun.status] }}</span>
        <progress aria-label="分析阶段" :value="progressIndex + 1" :max="progressSteps.length" />
      </div>
      <p v-if="actionError" class="forecast-error" role="alert">{{ actionError }}</p>
    </header>

    <div v-if="stock" class="forecast-pane-picker" role="group" aria-label="工作台面板">
      <button type="button" :aria-pressed="visiblePane === 'chart'" @click="visiblePane = 'chart'">图表</button>
      <button type="button" :aria-pressed="visiblePane === 'results'" @click="visiblePane = 'results'">结果</button>
    </div>
    <div class="forecast-grid" :data-pane="visiblePane">
      <section ref="chartPanel" class="forecast-panel forecast-chart" aria-labelledby="forecast-chart-title">
        <div class="forecast-panel-bar">
          <h2 id="forecast-chart-title">日 K 线</h2>
          <div v-if="stock" class="forecast-switch" role="group" aria-label="图表数据">
            <button type="button" :aria-pressed="chartMode === 'latest'" @click="showLatest">最新行情</button>
            <button type="button" :aria-pressed="chartMode === 'snapshot'" :disabled="!chosen" @click="showSnapshot()">分析快照</button>
          </div>
        </div>
        <p v-if="stock" class="forecast-caption">
          {{ { latest: '最新行情', snapshot: '分析快照', replay: '回放日期附近行情' }[chartMode] }}
          · {{ source === 'stockdb' ? 'StockDB' : source === 'akshare' ? 'AkShare' : '来源待确认' }}
          · 截至 {{ cutoff || '—' }}<template v-if="focusSession"> · 定位 {{ focusSession.day }}</template>
        </p>
        <p v-if="stockLoading || chartLoading" class="forecast-placeholder" role="status">正在读取{{ stockLoading ? '股票信息' : '日线数据' }}…</p>
        <div v-else-if="stockError || (chartError && !chartRows)" class="forecast-placeholder">
          <p role="alert">{{ stockError || chartError }}</p>
          <button type="button" @click="retryChart">重试</button>
        </div>
        <template v-else-if="stock">
          <p v-if="chartError" class="forecast-error" role="status">{{ chartError }}</p>
          <KLineChart v-if="chartMode === 'latest' || chartRows?.length"
            :key="`${stock.id}:${chartMode}`" :symbol="stock" fixed-period="1d" :recent-months="4" show-indicators
            :snapshot-bars="chartRows ?? undefined" :focus-session="focusSession"
            @loaded="chartMode === 'latest' && (latest = $event)" @focus-missing="focusedDayMissing" />
          <p v-else class="forecast-placeholder" role="status">没有可显示的日 K 线</p>
        </template>
        <p v-else class="forecast-placeholder">搜索股票名称或代码，查看日 K 线。</p>
      </section>

      <section class="forecast-panel forecast-results" aria-label="走势分析">
        <div class="forecast-panel-bar forecast-switch" role="group" aria-label="分析视图">
          <button type="button" :aria-pressed="resultTab === 'prediction'" @click="resultTab = 'prediction'">预测结果</button>
          <button type="button" :aria-pressed="resultTab === 'replay'" @click="resultTab = 'replay'">历史回放</button>
        </div>
        <div v-if="!stock" class="forecast-result-body"><p class="forecast-muted">选股后查看分析结果或发起历史回放。</p></div>
        <div v-else-if="!user.token" class="forecast-result-body">
          <p class="forecast-muted">登录后可保存分析并查看历史记录。</p>
          <button type="button" @click="auth.show('login')">登录</button>
        </div>
        <template v-else>
          <div v-show="resultTab === 'prediction'" class="forecast-result-body">
            <p v-if="historyError" class="forecast-error" role="alert">{{ historyError }} <button type="button" @click="refreshHistory">重试</button></p>
            <template v-if="chosen">
              <label class="forecast-record">分析记录
                <select v-model="runId">
                  <option :value="null">最新记录</option>
                  <option v-for="run in runs" :key="run.id" :value="run.id">{{ dateTime.format(new Date(run.created_at)) }} · {{ statusText[run.status] }}</option>
                </select>
              </label>
              <p class="forecast-caption" role="status">{{ statusText[chosen.status] }} · 快照截至 {{ chosen.snapshot.latest_session || '—' }} · {{ chosen.snapshot.bar_count }} 根日线</p>
              <p v-if="chosen.error" class="forecast-error" role="alert">{{ chosen.error }}</p>
              <button v-if="chosen.status === 'failed'" type="button" :disabled="!!action || !!activeRun" @click="runAction('retry')">重试此记录</button>
              <section v-if="chosen.diagnosis" class="forecast-result-card">
                <h3>市场诊断</h3>
                <strong>{{ regimes[chosen.diagnosis.regime] }} · {{ biases[chosen.diagnosis.bias] }}</strong>
                <p>{{ chosen.diagnosis.summary }}</p>
                <ForecastEvidence :items="chosen.diagnosis.evidence" @locate="showSnapshot" />
              </section>
              <template v-if="chosen.prediction">
                <section class="forecast-result-card">
                  <h3>下一根 K 线</h3>
                  <strong :data-direction="chosen.prediction.next_candle.direction">{{ directions[chosen.prediction.next_candle.direction] }}</strong>
                  <p>{{ chosen.prediction.next_candle.reason }}</p>
                  <ForecastEvidence :items="chosen.prediction.next_candle.evidence" @locate="showSnapshot" />
                </section>
                <section class="forecast-result-card">
                  <h3>下一阶段走势</h3>
                  <strong>{{ regimes[chosen.prediction.next_regime.regime] }}</strong>
                  <p v-if="chosen.regime_horizon" class="forecast-muted">未来 {{ chosen.regime_horizon }} 根有成交日 K 线</p>
                  <p v-else-if="chosen.models.prediction" class="forecast-muted">旧版预测，观察窗口未固定。</p>
                  <p>{{ chosen.prediction.next_regime.reason }}</p>
                  <ForecastEvidence :items="chosen.prediction.next_regime.evidence" @locate="showSnapshot" />
                </section>
              </template>
              <details class="forecast-result-card">
                <summary>数据与模型版本</summary>
                <dl>
                  <dt>数据</dt><dd>{{ chosen.snapshot.data_version || '—' }}</dd>
                  <dt>特征</dt><dd>{{ chosen.snapshot.feature_version }}</dd>
                  <template v-for="key in (['diagnosis', 'prediction'] as const)" :key="key">
                    <dt>{{ key === 'diagnosis' ? '诊断模型' : '预测模型' }}</dt>
                    <dd>{{ chosen.models[key]?.name || '—' }} {{ chosen.models[key]?.revision }}</dd>
                  </template>
                </dl>
              </details>
            </template>
            <p v-else class="forecast-muted">暂无分析记录。点击「开始分析」提交任务。</p>
          </div>
          <ForecastReplay v-if="resultTab === 'replay'" :key="user.user?.id" :symbol="stock.code" @locate="showReplayDay" />
        </template>
      </section>
    </div>
  </section>
</template>

<style scoped src="./forecast-workbench.css"></style>
