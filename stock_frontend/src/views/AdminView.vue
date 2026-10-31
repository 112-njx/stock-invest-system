<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { request } from '@/api/http'

interface Provider { name: string; used: number; health: { state: string; failures: number; last_success_at: string | null } }
interface QueueState { ready: number; active: number; delayed: number; reserved: number; abnormal: number }
interface Traffic { day: string; interval_seconds: number; retry_interval_seconds: number; daily_budget: number; poll_interval_seconds: number; probe_interval_seconds: number; providers: Provider[]; sync_status: Record<string, { status: string; message: string } | null> }
interface TaskQueues { queues: Record<string, QueueState>; workers: Record<string, boolean> }
const queueNames: Record<string, { label: string; description: string }> = {
  watchlist: { label: '重点关注股票', description: '同步关注股票的 K 线与历史缺口' },
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
onMounted(load)
</script>

<template>
  <main class="admin">
    <header><h1>系统管理</h1><button @click="load">刷新指标</button></header>
    <p v-if="error" class="error">{{ error }}</p>
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
button{padding:7px 14px;border-radius:5px;background:var(--accent);color:white}.error{color:#e55}
small{font-size:11px;color:var(--text-secondary);font-weight:normal}.muted{font-size:13px;color:var(--text-secondary)}
</style>
