<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { getCatalog, getStatus, queryData, type Dataset, type Result } from '@/api/allData'
const datasets = ref<Dataset[]>([])
const selected = ref('get_last_tick')
const groups = computed(() => [...new Set(datasets.value.map((item) => item.group))])
const group = ref('实时逐笔')
const search = ref('')
const choices = computed(() =>
  datasets.value.filter(
    (item) =>
      item.group === group.value &&
      `${item.title} ${item.id}`.toLowerCase().includes(search.value.toLowerCase())
  )
)
const active = computed(() => choices.value.find((item) => item.id === selected.value))
watch(
  choices,
  (options) => {
    if (!options.some((item) => item.id === selected.value)) selected.value = options[0]?.id || ''
  },
  { flush: 'sync' }
)
const form = reactive<Record<string, string | number>>({})
interface Filter {
  field: string
  op: string
  value: string
  type: string
}
const filters = ref<Filter[]>([])
const fields = ref<string[]>([])
const customFields = ref('')
const orderField = ref(''),
  direction = ref('desc'),
  limit = ref(100)
const busy = ref(false),
  loading = ref(false),
  error = ref(''),
  catalogError = ref('')
const remaining = ref(0),
  interval = ref(40),
  page = ref(1),
  raw = ref(false)
const result = ref<Result | null>(null),
  resultTitle = ref('')
let cooldownUntil = 0
let timer: ReturnType<typeof setInterval> | undefined
function updateRemaining() {
  remaining.value = Math.max(0, Math.ceil((cooldownUntil - Date.now()) / 1000))
}
function setCooldown(seconds: number) {
  cooldownUntil = Date.now() + seconds * 1000
  updateRemaining()
}
async function status() {
  try {
    const data = await getStatus()
    setCooldown(data.retry_after)
    interval.value = data.interval_seconds
  } catch {
    error.value = '无法读取在线服务状态，可稍后手动重试'
  }
}
async function loadCatalog() {
  loading.value = true
  catalogError.value = ''
  try {
    datasets.value = (await getCatalog()).entries
    resetForm()
  } catch {
    catalogError.value = '本地接口目录读取失败，请检查查询桥后重试'
  } finally {
    loading.value = false
  }
}
function resetForm() {
  Object.keys(form).forEach((key) => delete form[key])
  for (const param of active.value?.params || []) form[param.name] = param.default ?? ''
  filters.value = []
  fields.value = []
  customFields.value = ''
  orderField.value = ''
  limit.value = 100
}
watch(selected, resetForm)
function chooseGroup(value: string) {
  group.value = value
  search.value = ''
  selected.value = datasets.value.find((item) => item.group === value)?.id || ''
}
function onVisibilityChange() {
  if (document.visibilityState === 'visible') {
    updateRemaining()
    void status()
  }
}
onMounted(() => {
  void loadCatalog()
  void status()
  timer = setInterval(updateRemaining, 1000)
  document.addEventListener('visibilitychange', onVisibilityChange)
})
onUnmounted(() => {
  clearInterval(timer)
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
function filterValue(filter: Filter) {
  const convert = (value: string) => {
    if (filter.type === 'number') {
      if (!value.trim() || !Number.isFinite(Number(value))) throw new Error('筛选值必须为有效数值')
      return Number(value)
    }
    if (filter.type === 'boolean') {
      if (!['true', 'false'].includes(value.trim())) throw new Error('布尔筛选值应为 true 或 false')
      return value.trim() === 'true'
    }
    return value.trim()
  }
  return filter.op === 'in' ? filter.value.split(',').map(convert) : convert(filter.value)
}
async function run() {
  if (busy.value || remaining.value > 0 || !active.value) return
  busy.value = true
  error.value = ''
  const target = active.value
  try {
    const payload: Record<string, unknown> = { method: target.id }
    if (target.kind === 'table') {
      Object.assign(payload, {
        filters: filters.value.map((item) => ({
          field: item.field,
          op: item.op,
          value: filterValue(item),
        })),
        fields: [
          ...new Set([
            ...fields.value,
            ...customFields.value
              .split(',')
              .map((value) => value.trim())
              .filter(Boolean),
          ]),
        ],
        limit: limit.value,
        order_field: orderField.value,
        order_direction: direction.value,
      })
    } else {
      for (const param of target.params || []) {
        const value = form[param.name]
        if (value === '' || value === undefined) continue
        payload[param.name] =
          param.type === 'datetime-local'
            ? String(value).replace('T', ' ') + (String(value).length === 16 ? ':00' : '')
            : param.type === 'number'
              ? Number(value)
              : value
      }
    }
    const data = await queryData(payload)
    result.value = data
    resultTitle.value = target.title
    page.value = 1
    raw.value = false
    setCooldown(data.retry_after)
    interval.value = data.interval_seconds
  } catch (e: unknown) {
    error.value =
      (e as { response?: { data?: { msg?: string } } }).response?.data?.msg ||
      (e instanceof Error ? e.message : '查询失败，系统不会自动重试')
    await status()
  } finally {
    busy.value = false
  }
}
const rows = computed<Record<string, unknown>[]>(() => {
  const data = result.value?.data
  if (data == null) return []
  const list = Array.isArray(data) ? data : [data]
  return list.map((item) =>
    item && typeof item === 'object' ? (item as Record<string, unknown>) : { value: item }
  )
})
const columns = computed(() => [...new Set(rows.value.flatMap((row) => Object.keys(row)))])
const visible = computed(() => rows.value.slice((page.value - 1) * 100, page.value * 100))
function display(value: unknown) {
  return value == null ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value)
}
function fieldLabel(name: string) {
  return datasets.value.find((item) => item.id === result.value?.method)?.fields?.[name] || name
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
    <p v-if="catalogError" class="error" role="alert">
      {{ catalogError }} <button @click="loadCatalog">重试读取目录</button>
    </p>
    <p v-if="loading">正在读取本地接口目录…</p>
    <div class="layout">
      <aside aria-label="数据目录" tabindex="0">
        <h3>数据目录 · {{ datasets.length }}</h3>
        <button
          v-for="name in groups"
          :key="name"
          :data-group="name"
          :class="{ active: group === name }"
          :disabled="busy"
          @click="chooseGroup(name)"
        >
          {{ name }} <small>{{ datasets.filter((item) => item.group === name).length }}</small>
        </button>
        <p>
          共享请求间隔 {{ interval }} 秒<br />手动查询 · 成功后本地保存<br />不可用接口仍保留查询入口
        </p>
      </aside>
      <section>
        <form @submit.prevent="run">
          <div class="dataset-picker">
            <label
              >搜索当前分类<input
                v-model="search"
                @keydown.enter.prevent
                placeholder="数据名称或接口名"
                :disabled="busy" /></label
            ><label
              >数据项目<select v-model="selected" :disabled="busy || !choices.length">
                <option v-for="item in choices" :key="item.id" :value="item.id">
                  {{ item.title }}
                </option>
              </select></label
            >
          </div>
          <p v-if="!choices.length && !loading && !catalogError" class="hint">
            当前分类没有匹配项目，请修改搜索条件。
          </p>
          <template v-if="active"
            ><h2>
              {{ active.title }} <small>{{ active.id }}</small>
            </h2>
            <p class="hint">{{ active.coverage }}</p>
            <fieldset :disabled="busy">
              <div v-if="active.kind === 'api'" class="fields">
                <label v-for="param in active.params" :key="`${active.id}:${param.name}`"
                  >{{ param.label }}<span v-if="param.required" class="required">必填</span>
                  <select
                    v-if="param.type === 'select'"
                    v-model="form[param.name]"
                    :required="param.required"
                  >
                    <option v-for="(label, value) in param.options" :key="value" :value="value">
                      {{ label }}
                    </option>
                  </select>
                  <input
                    v-else
                    v-model="form[param.name]"
                    :data-param="param.name"
                    :type="param.type"
                    :required="param.required"
                    :min="param.min"
                    :max="param.max"
                    :placeholder="param.placeholder"
                  />
                </label>
              </div>
              <template v-else>
                <p class="hint">
                  文档字段提示并非完整表结构；筛选、排序可填写其他字段名。仅支持单个字段标识符，实际字段由上游校验。
                </p>
                <p class="hint">
                  筛选条件同时满足；未设置筛选时查询表内前
                  {{ limit }} 条。列表值用英文逗号分隔，代码请使用文本类型以保留前导零。
                </p>
                <p v-if="!Object.keys(active.fields || {}).length" class="hint">
                  文档未提供此表的字段清单，可填写字段名查询；字段不支持时显示接口错误。
                </p>
                <datalist id="table-fields">
                  <option v-for="(description, name) in active.fields" :key="name" :value="name">
                    {{ description }}
                  </option>
                </datalist>
                <div v-for="(filter, index) in filters" :key="index" class="filter-row">
                  <label
                    >字段<input
                      v-model="filter.field"
                      list="table-fields"
                      required
                      placeholder="字段名称"
                  /></label>
                  <label
                    >运算<select v-model="filter.op">
                      <option
                        v-for="op in ['==', '!=', '>', '>=', '<', '<=', 'in', 'like']"
                        :key="op"
                      >
                        {{ op }}
                      </option>
                    </select></label
                  >
                  <label
                    >值类型<select v-model="filter.type">
                      <option value="text">文本 / 日期</option>
                      <option value="number">数值</option>
                      <option value="boolean">布尔值</option>
                    </select></label
                  >
                  <label
                    >值<input v-model="filter.value" required placeholder="文本、日期或列表值"
                  /></label>
                  <button type="button" @click="filters.splice(index, 1)">移除</button>
                </div>
                <button
                  type="button"
                  :disabled="filters.length >= 10"
                  @click="filters.push({ field: '', op: '==', value: '', type: 'text' })"
                >
                  添加筛选条件
                </button>
                <div class="fields table-options">
                  <label
                    >返回条数（单次最多5000）<input
                      v-model.number="limit"
                      type="number"
                      required
                      min="1"
                      max="5000"
                  /></label>
                  <label
                    >排序字段（可选）<input
                      v-model="orderField"
                      list="table-fields"
                      placeholder="留空使用上游默认顺序"
                  /></label>
                  <label
                    >排序方向<select v-model="direction">
                      <option value="desc">降序</option>
                      <option value="asc">升序</option>
                    </select></label
                  >
                  <label v-if="Object.keys(active.fields || {}).length"
                    >返回字段（可选，多选；留空返回全部）<select v-model="fields" multiple size="4">
                      <option
                        v-for="(description, name) in active.fields"
                        :key="name"
                        :value="name"
                      >
                        {{ name }} · {{ description }}
                      </option>
                    </select></label
                  >
                  <label
                    >补充返回字段（可选）<input
                      v-model="customFields"
                      class="custom-fields"
                      placeholder="例如 id,code，英文逗号分隔"
                  /></label>
                </div>
              </template>
            </fieldset>
          </template>
          <button class="submit" :disabled="busy || remaining > 0 || !active || loading">
            {{ busy ? '查询并保存中…' : remaining ? `等待 ${remaining} 秒` : '查询并保存' }}
          </button>
          <p v-if="error" class="error" role="alert">{{ error }}</p>
        </form>
        <article class="results">
          <div class="result-head">
            <h2>{{ result ? `${resultTitle} · ${rows.length} 条` : '查询结果' }}</h2>
            <div v-if="result">
              <button @click="raw = !raw">{{ raw ? '表格视图' : '原始结果' }}</button>
              <button @click="download">导出 JSON</button>
            </div>
          </div>
          <template v-if="result"
            ><p>获取时间 {{ result.fetched_at }}</p>
            <p class="request-summary">查询条件：{{ JSON.stringify(result.parameters) }}</p>
            <p v-for="warning in result.warnings" :key="warning" class="error" role="alert">
              {{ warning }}
            </p>
            <p class="path">已保存：{{ result.saved_path }}</p>
            <pre v-if="raw">{{ JSON.stringify(result.data, null, 2) }}</pre>
            <template v-else
              ><div v-if="rows.length" class="table">
                <table>
                  <thead>
                    <tr>
                      <th v-for="column in columns" :key="column" :title="fieldLabel(column)">
                        {{ column }}
                      </th>
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
          </template>
          <p v-else class="empty">选择数据项目并填写条件，点击“查询并保存”获取数据。</p>
        </article>
      </section>
    </div>
  </main>
</template>
<style scoped>
fieldset {
  border: 0;
  padding: 0;
  margin: 0;
  min-width: 0;
}
.dataset-picker {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 24px;
}
.dataset-picker select {
  width: min(500px, 70vw);
}
.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: end;
  margin: 12px 0;
}
.filter-row input {
  width: 160px;
}
.filter-row select {
  width: 120px;
}
.table-options {
  margin-top: 20px;
}
.hint {
  color: #8394ad;
  line-height: 1.7;
}
.required {
  font-size: 10px;
  color: #75afbc;
}
.request-summary {
  overflow-wrap: anywhere;
  color: #8394ad;
}
pre {
  max-height: 560px;
  overflow: auto;
  white-space: pre-wrap;
}
aside {
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}
.layout > section {
  min-height: 0;
  min-width: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}
aside small {
  float: right;
  opacity: 0.6;
}

.workspace {
  background: #0c1422;
  color: #cad6e7;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
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
  flex-shrink: 0;
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
  flex: 1;
  min-height: 0;
  grid-template-columns: 190px minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
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
    grid-template-rows: minmax(100px, 30%) minmax(0, 1fr);
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
