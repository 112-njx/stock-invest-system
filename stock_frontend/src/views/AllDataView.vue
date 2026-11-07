<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { request } from '@/api/http'
const types = [
  ['get_last_tick', '实时逐笔'],
  ['get_ticks', '历史逐笔'],
  ['get_fundamentals', '财务报表'],
  ['get_billboard_list', '龙虎榜'],
  ['get_locked_shares', '限售解禁'],
  ['get_money_flow', '资金流向'],
  ['get_mtss', '融资融券'],
]
const method = ref('get_last_tick')
const form = reactive({
  code: '000001',
  count: 20,
  end_dt: '',
  start_date: '',
  end_date: '',
  report: 'cash_flow',
  quarter: '2024q4',
})
const whole = ref(false)
const optionalCode = computed(() =>
  ['get_fundamentals', 'get_billboard_list'].includes(method.value)
)
const tick = computed(() => ['get_last_tick', 'get_ticks'].includes(method.value))
const busy = ref(false),
  error = ref(''),
  remaining = ref(0),
  interval = ref(30)
interface Result {
  warnings?: string[]
  data: unknown
  fetched_at: string
  saved_path: string
  retry_after: number
  interval_seconds: number
}
const result = ref<Result | null>(null)
const resultTitle = ref('')
const rows = computed<Record<string, unknown>[]>(() => {
  const data = result.value?.data
  if (data == null) return []
  const list = Array.isArray(data) ? data : [data]
  return list.map((item) =>
    item && typeof item === 'object' ? (item as Record<string, unknown>) : { value: item }
  )
})
const columns = computed(() => [...new Set(rows.value.flatMap((row) => Object.keys(row)))])
const page = ref(1)
const visible = computed(() => rows.value.slice((page.value - 1) * 100, page.value * 100))
let timer: ReturnType<typeof setInterval> | undefined
let cooldownUntil = 0
function updateRemaining() {
  remaining.value = Math.max(0, Math.ceil((cooldownUntil - Date.now()) / 1000))
}
function setCooldown(seconds: number) {
  cooldownUntil = Date.now() + seconds * 1000
  updateRemaining()
}
function onVisibilityChange() {
  if (document.visibilityState === 'visible') {
    updateRemaining()
    // Only checks the local quota; never requests upstream market data.
    void status()
  }
}
async function status() {
  try {
    const data = await request<{ retry_after: number; interval_seconds: number }>({
      url: '/all-data/status',
      silent: true,
    })
    setCooldown(data.retry_after)
    interval.value = data.interval_seconds
  } catch {
    error.value = '无法读取在线服务状态，可稍后手动重试'
  }
}
onMounted(() => {
  void status()
  timer = setInterval(updateRemaining, 1000)
  document.addEventListener('visibilitychange', onVisibilityChange)
})
onUnmounted(() => {
  clearInterval(timer)
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
async function run() {
  if (busy.value || remaining.value > 0) return
  busy.value = true
  error.value = ''
  try {
    const data = await request<Result>({
      method: 'POST',
      url: '/all-data/query',
      // Backend SDK bridge: 180s; Nginx: 200s; browser: 210s.
      timeout: 210000,
      silent: true,
      data: {
        method: method.value,
        code: optionalCode.value && whole.value ? '' : form.code,
        ...(tick.value ? { count: form.count } : {}),
        ...(method.value === 'get_ticks'
          ? { end_dt: form.end_dt.replace('T', ' ') + (form.end_dt.length === 16 ? ':00' : '') }
          : {}),
        ...(method.value === 'get_fundamentals'
          ? { report: form.report, quarter: form.quarter }
          : tick.value ? {} : { start_date: form.start_date, end_date: form.end_date }),
      },
    })
    result.value = data
    resultTitle.value = types.find((t) => t[0] === method.value)?.[1] || ''
    page.value = 1
    setCooldown(data.retry_after)
    interval.value = data.interval_seconds
  } catch (e: unknown) {
    const response = (e as { response?: { data?: { detail?: unknown; msg?: string } } }).response
    const detail = response?.data?.detail
    error.value =
      typeof detail === 'string'
        ? detail
        : response?.data?.msg ||
          (detail as { detail?: string })?.detail ||
          '查询失败，请检查参数或服务状态；系统不会自动重试'
    await status()
  } finally {
    busy.value = false
  }
}
function display(value: unknown) {
  return value == null ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value)
}
function download() {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(result.value, null, 2)], { type: 'application/json' })
  )
  const a = document.createElement('a')
  a.href = url
  a.download = `${resultTitle.value}.json`
  a.click()
  URL.revokeObjectURL(url)
}
</script>
<template>
  <main class="workspace">
    <header>
      <div>
        <small>MARKET DATA TERMINAL</small>
        <h1>全数据 <span>在线查询工作台</span></h1>
      </div>
      <b>{{ busy ? '● 请求处理中' : remaining ? `● 冷却 ${remaining}s` : '● 等待手动查询' }}</b>
    </header>
    <div class="layout">
      <aside>
        <h3>数据目录</h3>
        <button
          v-for="item in types"
          :key="item[0]"
          :class="{ active: method === item[0] }"
          :disabled="busy"
          @click="method = item[0]!"
        >
          {{ item[1] }}
        </button>
        <p>远程数据 · 按需获取<br />共享请求间隔 {{ interval }} 秒<br />查询成功后自动本地保存</p>
      </aside>
      <section>
        <form @submit.prevent="run">
          <h2>
            {{ types.find((t) => t[0] === method)?.[1] }} <small>{{ method }}</small>
          </h2>
          <div class="fields">
            <label v-if="optionalCode"
              >查询范围<select v-model="whole">
                <option :value="false">指定股票</option>
                <option :value="true">全市场</option>
              </select></label
            >
            <label v-if="!optionalCode || !whole"
              >股票代码<input
                v-model="form.code"
                required
                pattern="[0-9]{6}"
                placeholder="六位股票代码"
            /></label>
            <label v-if="tick"
              >返回条数<input v-model.number="form.count" required type="number" min="1" max="1000"
            /></label>
            <label v-if="method === 'get_ticks'"
              >截止时间<input v-model="form.end_dt" required type="datetime-local"
            /></label>
            <template v-if="!tick && method !== 'get_fundamentals'"
              ><label>开始日期<input v-model="form.start_date" required type="date" /></label
              ><label>结束日期<input v-model="form.end_date" required type="date" /></label
            ></template>
            <template v-if="method === 'get_fundamentals'"
              ><label
                >报表<select v-model="form.report">
                  <option value="cash_flow">现金流量表</option>
                  <option value="income">利润表</option>
                  <option value="balance">资产负债表</option>
                </select></label
              ><label
                >报告期<input
                  v-model="form.quarter"
                  required
                  pattern="20[0-9]{2}q[1-4]"
                  placeholder="2024q4" /></label
            ></template>
          </div>
          <button class="submit" :disabled="busy || remaining > 0">
            {{ busy ? '查询并保存中…' : remaining ? `等待 ${remaining} 秒` : '查询并保存' }}
          </button>
          <p v-if="error" class="error" role="alert">{{ error }}</p>
        </form>
        <article class="results">
          <div class="result-head">
            <h2>{{ result ? `${resultTitle} · ${rows.length} 条` : '查询结果' }}</h2>
            <button v-if="result" @click="download">导出 JSON</button>
          </div>
          <template v-if="result"
            ><p>获取时间 {{ result.fetched_at }}</p>
            <p v-for="warning in result.warnings" :key="warning" class="error" role="alert">{{ warning }}</p>
            <p class="path">已保存：{{ result.saved_path }}</p>
            <div v-if="rows.length" class="table">
              <table>
                <thead>
                  <tr>
                    <th v-for="column in columns" :key="column">{{ column }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, index) in visible" :key="index">
                    <td v-for="column in columns" :key="column">{{ display(row[column]) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p v-else>查询成功，当前条件下无数据。空结果已保存。</p>
            <div v-if="rows.length > 100">
              <button :disabled="page === 1" @click="page--">上一页</button> {{ page }} /
              {{ Math.ceil(rows.length / 100) }}
              <button :disabled="page * 100 >= rows.length" @click="page++">下一页</button>
            </div></template
          >
          <p v-else class="empty">选择数据类型并填写条件，点击“查询并保存”获取数据。</p>
        </article>
      </section>
    </div>
  </main>
</template>
<style scoped>
.workspace {
  background: #0c1422;
  color: #cad6e7;
  min-height: calc(100vh - 64px);
  padding: 24px;
  font-size: 13px;
}
header,
.result-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
header {
  border-bottom: 1px solid #27364b;
  padding-bottom: 20px;
  margin-bottom: 20px;
}
header small {
  color: #5d8fc2;
  letter-spacing: 2px;
}
h1 {
  font-size: 25px;
  margin: 8px 0;
}
h1 span {
  font-size: 13px;
  color: #8192ab;
  margin-left: 12px;
}
header b {
  color: #55c5b2;
}
.layout {
  display: grid;
  grid-template-columns: 190px minmax(0, 1fr);
  gap: 20px;
}
aside,
form,
.results {
  background: #111e30;
  border: 1px solid #26364d;
  border-radius: 6px;
  padding: 20px;
}
aside button {
  display: block;
  width: 100%;
  text-align: left;
  margin: 8px 0;
}
.active {
  background: #1c4d76;
  color: #80ceff;
  border-color: #367ab3;
}
button,
input,
select {
  background: #18283e;
  color: #dce7f5;
  border: 1px solid #344b65;
  border-radius: 4px;
  padding: 9px;
}
button {
  cursor: pointer;
}
button:disabled {
  opacity: 0.5;
  cursor: default;
}
h2 {
  font-size: 16px;
  margin: 0 0 18px;
}
h2 small {
  font-size: 11px;
  color: #7e93b0;
  margin-left: 12px;
}
.fields {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
}
label {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
input,
select {
  width: 180px;
}
.submit {
  background: #21689a;
  margin-top: 20px;
  min-width: 150px;
}
.results {
  margin-top: 20px;
  min-height: 300px;
  overflow: hidden;
}
.table {
  overflow: auto;
  max-height: 560px;
}
table {
  border-collapse: collapse;
  white-space: nowrap;
  width: 100%;
  font-variant-numeric: tabular-nums;
}
th,
td {
  padding: 10px 14px;
  border-bottom: 1px solid #26364b;
  text-align: left;
}
th {
  position: sticky;
  top: 0;
  background: #1a2c43;
  color: #81b4e5;
}
tbody tr:hover {
  background: #1a2d45;
}
.path {
  overflow-wrap: anywhere;
  color: #75afbc;
}
.empty {
  padding: 65px 10px;
  text-align: center;
  color: #7a8ca6;
}
.error {
  color: #ff9797;
}
aside p {
  line-height: 2;
  color: #8394ad;
  margin-top: 30px;
}
@media (max-width: 750px) {
  .workspace {
    padding: 12px;
  }
  .layout {
    grid-template-columns: 1fr;
  }
  aside button {
    display: inline-block;
    width: auto;
    margin: 4px;
  }
  aside p {
    margin: 10px 0;
  }
  header {
    display: block;
  }
}
</style>
