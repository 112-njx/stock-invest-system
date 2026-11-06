<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { request } from '@/api/http'
import { syntheticWickFactor } from '@/composables/useSyntheticWicks'

interface Provider { name: string; used: number; health: { state: string; failures: number; last_success_at: string | null } }
interface QueueState { ready: number; active: number; delayed: number; reserved: number; abnormal: number }
interface Traffic { day: string; interval_seconds: number; retry_interval_seconds: number; daily_budget: number; poll_interval_seconds: number; probe_interval_seconds: number; providers: Provider[]; sync_status: Record<string, { status: string; message: string } | null> }
interface TaskQueues { queues: Record<string, QueueState>; workers: Record<string, boolean> }
interface ProviderRequest {
  id: string; task_id: string; queue: string; provider: string; interface: string
  symbol: string | null; symbol_name?: string; symbols: { code: string; name: string }[]
  symbol_count: number | null; period: string | null; start: string | null; end: string | null
  phase: string; attempt: number; attempts: number; retry_after: number | null
  started_at: string; updated_at: string
}
const queueNames: Record<string, { label: string; description: string }> = {
  watchlist: { label: '重点关注股票', description: '初始化关注股票的前复权 K 线' },
  fixed_indices: { label: '固定指数', description: '补齐大盘和行业指数的行情数据' },
  backfill: { label: '历史补拉', description: '处理用户请求的历史 K 线区间' },
  control: { label: '任务协调', description: '检查关注股任务并恢复中断的投递' },
  sync: { label: '常规同步', description: '处理日常行情、目录和实时轮询' },
  backtest: { label: '策略回测', description: '执行策略回测任务' },
  ai: { label: 'AI 与导出', description: '处理 AI、记忆维护和数据导出' },
  backup: { label: '数据备份', description: '执行备份、异地同步和恢复验证' },
}
const data = ref<Traffic | null>(null)
const taskQueues = ref<TaskQueues | null>(null)
const interval = ref(2)
const retryInterval = ref(10)
const budget = ref(2000)
const error = ref('')
const saving = ref(false)
const loading = ref(false)
const queueLoading = ref(false)
const queueError = ref('')
const activeRequests = ref<ProviderRequest[]>([])
const activityError = ref('')
const activityLoading = ref(true)
const displayFactor = ref(0.5)
const displayLoaded = ref(false)
const displaySaving = ref(false)
const displayError = ref('')
async function loadDisplaySettings() {
  try {
    const value = await request<{ synthetic_wick_factor: number }>({ url: '/admin/market-display' })
    displayFactor.value = value.synthetic_wick_factor
    syntheticWickFactor.value = value.synthetic_wick_factor
    displayLoaded.value = true
  } catch { displayError.value = '显示设置读取失败' }
}
async function saveDisplaySettings() {
  if (!Number.isFinite(displayFactor.value) || displayFactor.value < 0 || displayFactor.value > 1) {
    displayError.value = '请输入 0 到 1 之间的系数'
    return
  }
  displaySaving.value = true
  displayError.value = ''
  try {
    const value = await request<{ synthetic_wick_factor: number }>({ url: '/admin/market-display', method: 'put', data: { synthetic_wick_factor: displayFactor.value } })
    syntheticWickFactor.value = value.synthetic_wick_factor
    displayFactor.value = value.synthetic_wick_factor
  } catch { displayError.value = '显示设置保存失败' }
  finally { displaySaving.value = false }
}
const sourcePolicy = ref({ akshare_enabled: false, snapshots_enabled: false })
const sourcePolicyLoaded = ref(false)
const sourcePolicySaving = ref(false)
const sourcePolicyError = ref('')
async function loadSourcePolicy() {
  try {
    sourcePolicy.value = await request<typeof sourcePolicy.value>({ url: '/admin/market-source-policy' })
    sourcePolicyLoaded.value = true
  } catch { sourcePolicyError.value = '数据源设置读取失败' }
}
async function saveSourcePolicy() {
  sourcePolicySaving.value = true
  sourcePolicyError.value = ''
  if (!sourcePolicy.value.akshare_enabled) sourcePolicy.value.snapshots_enabled = false
  try {
    sourcePolicy.value = await request<typeof sourcePolicy.value>({ url: '/admin/market-source-policy', method: 'put', data: sourcePolicy.value })
  } catch { sourcePolicyError.value = '数据源设置保存失败' }
  finally { sourcePolicySaving.value = false }
}
interface LocalSync { status: string; task_id: string | null; error: string | null; progress: number; message: string }
const localSync = ref<LocalSync | null>(null)
const localSyncSubmitting = ref(false)
const localSyncError = ref('')
async function loadLocalSync() {
  try {
    localSync.value = await request<LocalSync>({ url: '/admin/local-market/sync', silent: true })
    localSyncError.value = ''
  } catch { localSyncError.value = '本地行情同步状态读取失败' }
}
async function syncLocalMarket() {
  localSyncSubmitting.value = true
  try {
    await request({ url: '/admin/local-market/sync', method: 'post' })
    await loadLocalSync()
  } catch { localSyncError.value = '提交同步失败，请稍后重试' }
  finally { localSyncSubmitting.value = false }
}
let activityTimer: ReturnType<typeof setInterval> | undefined
let activityInFlight = false

function requestTarget(item: ProviderRequest): string {
  if (item.symbol) {
    return item.symbol_name && item.symbol_name !== item.symbol
      ? `${item.symbol_name}（${item.symbol}）` : item.symbol
  }
  if (item.symbols?.length) {
    const names = item.symbols.slice(0, 5).map(symbol => `${symbol.name}（${symbol.code}）`).join('、')
    return `${names}${(item.symbol_count || 0) > 5 ? ` 等 ${item.symbol_count} 个标的` : ''}`
  }
  return '全市场或目录数据'
}

function requestRange(item: ProviderRequest): string {
  if (!item.start || !item.end) return '实时数据或接口未指定日期'
  const format = (value: string) => item.period === '15m'
    ? value.replace('T', ' ').slice(0, 16) : value.slice(0, 10)
  return `${format(item.start)} ～ ${format(item.end)}`
}

function phaseLabel(phase: string): string {
  const labels: Record<string, string> = { throttling: '等待限流', requesting: '请求中', retry_wait: '等待内部重试' }
  return labels[phase] || phase
}

async function loadActivity() {
  if (activityInFlight) return
  activityInFlight = true
  try {
    const result = await request<{ requests: ProviderRequest[] }>({ url: '/admin/provider-requests', silent: true })
    activeRequests.value = result.requests
    activityError.value = ''
  } catch {
    activeRequests.value = []
    activityError.value = '请求状态暂时不可用'
  } finally { activityLoading.value = false; activityInFlight = false }
}

async function loadQueues() {
  queueLoading.value = true
  try {
    taskQueues.value = await request<TaskQueues>({ url: '/admin/task-queues', silent: true })
    queueError.value = ''
  } catch { queueError.value = '队列状态读取失败，请稍后刷新' }
  finally { queueLoading.value = false }
}

async function load() {
  loading.value = true
  void loadQueues()
  try {
    data.value = await request<Traffic>({ url: '/admin/traffic' })
    interval.value = data.value.interval_seconds
    retryInterval.value = data.value.retry_interval_seconds
    budget.value = data.value.daily_budget
    error.value = ''
  } catch { error.value = '管理指标读取失败' }
  finally { loading.value = false }
}
async function save() {
  saving.value = true
  try {
    await request<Traffic>({ url: '/admin/traffic/limits', method: 'put', data: { interval_seconds: interval.value, retry_interval_seconds: retryInterval.value, daily_budget: budget.value } })
    await load()
  } catch { error.value = '限流配置保存失败' }
  finally { saving.value = false }
}
onMounted(() => {
  void load()
  void loadActivity()
  void loadDisplaySettings()
  void loadSourcePolicy()
  void loadLocalSync()
  activityTimer = setInterval(() => { void loadActivity(); void loadLocalSync() }, 3000)
})
onUnmounted(() => { if (activityTimer) clearInterval(activityTimer) })
</script>

<template>
  <main class="admin">
    <header><h1>系统管理</h1><button @click="load">刷新指标</button></header>
    <p v-if="error" class="error">{{ error }}</p>
    <section>
      <h2>合成指数影线显示</h2>
      <p>行情页行业指数与指数蓝图共用。默认 0.5；0 隐藏影线，1 显示原影线。仅改变图形及图上高低值，不改变原始行情、指标或策略计算。</p>
      <label>影线系数<input v-model.number="displayFactor" type="number" min="0" max="1" step="0.05" :disabled="!displayLoaded || displaySaving"></label>
      <button :disabled="!displayLoaded || displaySaving" @click="saveDisplaySettings">{{ displaySaving ? '保存中…' : '保存显示设置' }}</button>
      <p v-if="displayError" class="error">{{ displayError }}</p>
    </section>
    <section>
      <h2>行情数据源</h2>
      <p>默认仅使用 Free-StockDB；实时快照需要同时开启 AkShare。</p>
      <label><input v-model="sourcePolicy.akshare_enabled" type="checkbox" :disabled="!sourcePolicyLoaded || sourcePolicySaving" @change="saveSourcePolicy">启用 AkShare 兜底补充</label>
      <label><input v-model="sourcePolicy.snapshots_enabled" type="checkbox" :disabled="!sourcePolicyLoaded || !sourcePolicy.akshare_enabled || sourcePolicySaving" @change="saveSourcePolicy">启用实时快照</label>
      <p v-if="sourcePolicyError" class="error">{{ sourcePolicyError }}</p>
    </section>
    <section>
      <h2>本地行情手动同步</h2>
      <p>先手动运行数据更新.exe，等待 Free-StockDB 更新完成，再同步证券目录、固定指数和关注标的的前复权 K 线。</p>
      <button :disabled="localSyncSubmitting || localSync?.status === 'queued' || localSync?.status === 'running'" @click="syncLocalMarket">
        {{ localSyncSubmitting || localSync?.status === 'queued' ? '等待同步…' : localSync?.status === 'running' ? '同步中…' : '同步本地行情数据' }}
      </button>
      <p v-if="localSync">{{ localSync.message }} · {{ localSync.progress }}%</p>
      <p v-if="localSync?.task_id">任务 {{ localSync.task_id }}</p>
      <p v-if="localSyncError || localSync?.error" class="error">{{ localSyncError || localSync?.error }}</p>
    </section>
    <section v-if="!data"><h2>基础指标</h2><p>{{ loading ? '正在读取基础指标…' : '暂无基础指标，请刷新重试' }}</p></section>
    <template v-if="data">
      <section><h2>外部行情调用 · {{ data.day }}</h2>
        <p>按数据源统计外部调用尝试次数；一次调用内部可能产生多次 HTTP 请求。</p>
        <div class="grid"><article v-for="p in data.providers" :key="p.name">
          <h3>{{ p.name }}</h3><strong>{{ p.used }} / {{ data.daily_budget }}</strong>
          <p>API 进程状态：{{ p.health.state }} · 连续失败：{{ p.health.failures }}</p>
        </article></div>
      </section>
      <section><h2>请求保护</h2>
        <label>同一数据源最小请求间隔（秒）<input v-model.number="interval" type="number" min="1" max="60"></label>
        <label>请求失败后重试间隔（秒）<input v-model.number="retryInterval" type="number" min="1" max="120"></label>
        <label>单数据源每日请求预算<input v-model.number="budget" type="number" min="100" max="100000"></label>
        <button :disabled="saving" @click="save">保存</button>
        <p>实时行情任务间隔：{{ data.poll_interval_seconds }} 秒；熔断源探测间隔：{{ data.probe_interval_seconds }} 秒。达到预算后该数据源当日暂停外部调用。</p>
      </section>
    </template>
    <section><h2>任务队列 <span v-if="queueLoading" class="muted">· 更新中…</span></h2>
      <p v-if="queueError" class="error">{{ queueError }}</p>
      <p v-if="!taskQueues">正在读取队列状态…</p>
      <div v-else class="grid"><article v-for="(state, name) in taskQueues.queues" :key="name">
        <h3>{{ queueNames[name]?.label || name }} <small>{{ name }}</small></h3>
        <p>{{ queueNames[name]?.description }}</p>
        <p>就绪 {{ state.ready }} · 执行中 {{ state.active }}</p>
        <p>已取走 {{ state.reserved }} · 延迟重试 {{ state.delayed }}</p>
        <p :class="{ error: state.abnormal > 0 }">异常 {{ state.abnormal }}</p>
      </article></div>
    </section>
    <section><h2>当前上游行情请求 <span class="muted">· 每 3 秒更新</span></h2>
      <p v-if="activityError" class="error">{{ activityError }}</p>
      <p v-else-if="activityLoading">正在读取请求状态…</p>
      <p v-else-if="!activeRequests.length">当前没有正在进行的上游行情请求</p>
      <div v-else class="request-list"><article v-for="item in activeRequests" :key="item.id">
        <h3>{{ requestTarget(item) }}</h3>
        <p>队列：{{ queueNames[item.queue]?.label || item.queue }} · 数据源：{{ item.provider }}</p>
        <p>上游接口（Akshare）：<code>{{ item.interface }}</code></p>
        <p v-if="item.period">K 线周期：{{ item.period }} · 涵盖日期：{{ requestRange(item) }}</p>
        <p v-else>数据范围：{{ requestRange(item) }}</p>
        <p>状态：{{ phaseLabel(item.phase) }}
          · 第 {{ item.attempt }}/{{ item.attempts }} 次尝试
          <span v-if="item.phase === 'retry_wait' && item.retry_after"> · 重试间隔 {{ item.retry_after }} 秒</span></p>
        <p>开始：{{ new Date(item.started_at).toLocaleString('zh-CN') }}
          · 最近状态：{{ new Date(item.updated_at).toLocaleTimeString('zh-CN') }}
          · 任务 {{ item.task_id.slice(0, 8) }}</p>
      </article></div>
    </section>
    <section><h2>Worker 健康</h2>
      <p v-if="!taskQueues">正在读取 Worker 状态…</p>
      <div v-else class="grid"><article v-for="(healthy, name) in taskQueues.workers" :key="name">
        <h3>{{ queueNames[name]?.label || name }} <small>{{ name }}</small></h3>
        <p>{{ queueNames[name]?.description }}</p>
        <strong :class="{ error: !healthy }">{{ healthy ? '在线' : '未响应' }}</strong>
      </article></div>
    </section>
    <section v-if="data"><h2>数据同步</h2><p v-for="(item, name) in data.sync_status" :key="name">{{ name }}：{{ item?.status || '无记录' }} · {{ item?.message || '' }}</p></section>
  </main>
</template>

<style scoped>
.admin{width:100%;max-width:1100px;min-height:0;flex:1;overflow-y:auto;margin:0 auto;padding:24px;color:var(--text)}
header{display:flex;align-items:center;justify-content:space-between}h1{font-size:22px}h2{font-size:17px;margin:0 0 12px}
section{background:var(--bg-panel);border:1px solid var(--border);border-radius:8px;padding:20px;margin:16px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}article{padding:14px;background:var(--bg-hover);border-radius:6px}article h3{font-size:14px;margin:0 0 8px}strong{font-size:22px}p{color:var(--text-secondary);font-size:13px}
label{display:block;margin:12px 0;font-size:13px}input{display:block;margin-top:6px;padding:7px;background:var(--bg-hover);color:var(--text);border:1px solid var(--border);border-radius:4px;width:180px}
input[type=checkbox]{display:inline-block;width:16px;height:16px;margin:0 8px 0 0;padding:0;vertical-align:middle;accent-color:var(--accent)}
button{padding:7px 14px;border-radius:5px;background:var(--accent);color:white}.error{color:#e55}
small{font-size:11px;color:var(--text-secondary);font-weight:normal}.muted{font-size:13px;color:var(--text-secondary)}
.request-list{display:grid;gap:10px}.request-list article{padding:14px;background:var(--bg-hover);border-radius:6px}.request-list h3{font-size:15px;margin:0 0 8px}.request-list p{margin:5px 0}code{font-size:12px;overflow-wrap:anywhere}
</style>
