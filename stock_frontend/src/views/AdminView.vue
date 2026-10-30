<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { request } from '@/api/http'

interface Provider { name: string; used: number; health: { state: string; failures: number; last_success_at: string | null } }
interface Traffic { day: string; interval_seconds: number; daily_budget: number; poll_interval_seconds: number; probe_interval_seconds: number; providers: Provider[]; queues: Record<string, number>; sync_status: Record<string, { status: string; message: string } | null> }
const data = ref<Traffic | null>(null)
const interval = ref(2)
const budget = ref(2000)
const error = ref('')
const saving = ref(false)

async function load() {
  try {
    data.value = await request<Traffic>({ url: '/admin/traffic' })
    interval.value = data.value.interval_seconds
    budget.value = data.value.daily_budget
    error.value = ''
  } catch { error.value = '管理指标读取失败' }
}
async function save() {
  saving.value = true
  try {
    await request<Traffic>({ url: '/admin/traffic/limits', method: 'put', data: { interval_seconds: interval.value, daily_budget: budget.value } })
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
        <label>单数据源每日请求预算<input v-model.number="budget" type="number" min="100" max="100000"></label>
        <button :disabled="saving" @click="save">保存</button>
        <p>实时行情任务间隔：{{ data.poll_interval_seconds }} 秒；熔断源探测间隔：{{ data.probe_interval_seconds }} 秒。达到预算后该数据源当日暂停外部调用。</p>
      </section>
      <section><h2>任务队列</h2><div class="grid"><article v-for="(count, name) in data.queues" :key="name"><h3>{{ name }}</h3><strong>{{ count }}</strong></article></div></section>
      <section><h2>数据同步</h2><p v-for="(item, name) in data.sync_status" :key="name">{{ name }}：{{ item?.status || '无记录' }} · {{ item?.message || '' }}</p></section>
    </template>
  </main>
</template>

<style scoped>
.admin{max-width:1100px;margin:0 auto;padding:24px;color:var(--text)}
header{display:flex;align-items:center;justify-content:space-between}h1{font-size:22px}h2{font-size:17px;margin:0 0 12px}
section{background:var(--bg-panel);border:1px solid var(--border);border-radius:8px;padding:20px;margin:16px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}article{padding:14px;background:var(--bg-hover);border-radius:6px}article h3{font-size:14px;margin:0 0 8px}strong{font-size:22px}p{color:var(--text-secondary);font-size:13px}
label{display:block;margin:12px 0;font-size:13px}input{display:block;margin-top:6px;padding:7px;background:var(--bg-hover);color:var(--text);border:1px solid var(--border);border-radius:4px;width:180px}
button{padding:7px 14px;border-radius:5px;background:var(--accent);color:white}.error{color:#e55}
</style>
