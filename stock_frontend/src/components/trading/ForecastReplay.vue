<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { isAxiosError } from 'axios'
import { getForecastReplay, startForecastReplay, type ForecastReplay, type ReplayOptions } from '@/api/forecast'

const props = defineProps<{ symbol: string }>()
const mode = ref<ReplayOptions['mode']>('reconstructed')
const end = ref('')
const samples = ref(5)
const result = ref<ForecastReplay | null>(null)
const submitting = ref(false)
const error = ref('')
let timer: ReturnType<typeof setTimeout> | undefined
let generation = 0
const busy = computed(() => submitting.value || result.value?.status === 'queued' || result.value?.status === 'running')
const names: Record<string, string> = {
  direction: 'AI · 下一根方向', last_candle: '方向基线 · 沿用上一根', always_up: '方向基线 · 一律预测涨',
  regime: 'AI · 走势类型', previous_regime: '走势基线 · 沿用前五根类型',
}
const labels: Record<string, string> = {
  up: '涨', down: '跌', flat: '平', undetermined: '无法判断',
  trend: '趋势', tight_channel: '窄通道', broad_channel: '宽通道', range: '震荡', breakout: '突破',
}
const caseStatuses: Record<string, string> = {
  evaluated: '已分析', unlabelled: '未来日线不足', missing_archive: '缺少当日快照',
  insufficient: '历史不足', failed: '分析失败',
}
const statusText = { queued: '等待回放', running: '逐日回放中', completed: '回放完成', failed: '回放中断' }
const formatter = new Intl.NumberFormat('zh-CN', { style: 'percent', maximumFractionDigits: 1 })

function ratio(n: number, d: number) {
  return d ? `${formatter.format(n / d)}（${n}/${d}）` : '—'
}

function label(value?: string | null) {
  return value ? labels[value] ?? '—' : '—'
}

function poll() {
  clearTimeout(timer)
  timer = setTimeout(() => void refresh(), 5000)
}

async function refresh() {
  const request = generation
  try {
    const data = await getForecastReplay(props.symbol)
    if (request !== generation) return
    result.value = data
    error.value = ''
  } catch {
    if (request !== generation) return
    error.value = '无法读取回放结果'
  }
  if (busy.value || error.value) poll()
}

async function start() {
  if (busy.value) return
  const request = ++generation
  clearTimeout(timer)
  submitting.value = true
  error.value = ''
  try {
    const data = await startForecastReplay(props.symbol, { end: end.value || null, samples: samples.value, mode: mode.value })
    if (request !== generation) return
    result.value = data
    poll()
  } catch (cause) {
    if (request !== generation) return
    error.value = isAxiosError<{ msg?: string }>(cause) ? cause.response?.data?.msg || '提交回放失败' : '提交回放失败'
  } finally {
    if (request === generation) submitting.value = false
  }
}

watch(() => props.symbol, () => {
  generation++
  clearTimeout(timer)
  result.value = null
  submitting.value = false
  error.value = ''
  void refresh()
}, { immediate: true })
onUnmounted(() => { generation++; clearTimeout(timer) })
</script>

<template>
  <section class="forecast-replay" aria-labelledby="forecast-replay-title">
    <h2 id="forecast-replay-title">历史回放</h2>
    <form @submit.prevent="start">
      <label>数据口径
        <select v-model="mode">
          <option value="reconstructed">重建历史 · 用截止日复权因子</option>
          <option value="archived">当日存档 · 只用已保存的快照</option>
        </select>
      </label>
      <label>回放截止日
        <input v-model="end" type="date" min="1991-01-01" />
      </label>
      <label>回放样本数
        <select v-model.number="samples">
          <option v-for="count in 10" :key="count" :value="count">{{ count }} 根日线</option>
        </select>
      </label>
      <button type="submit" :disabled="busy">开始历史回放</button>
    </form>
    <p>截止日留空时，选择最近已有完整观察窗口的样本。每个样本调用两阶段模型分析，任务在后台执行。</p>
    <p v-if="mode === 'reconstructed'">重建口径只截取当日及此前收盘数据，并按当日因子复权。当前数据源可能包含事后修订。</p>
    <p v-else>当日存档只取本账号在该日收盘后保存的快照。缺少存档的日期计入覆盖率分母。</p>
    <p v-if="error || result?.error" role="alert">{{ error || result?.error }}</p>
    <template v-if="result">
      <p role="status">{{ statusText[result.status] }}
        <template v-if="result.report"> · 已处理 {{ result.report.cases.length }}/{{ result.report.total }}</template>
      </p>
      <p>本报告使用{{ result.options.mode === 'archived' ? '当日存档' : '重建历史' }}，申请 {{ result.options.samples }} 个样本。</p>
      <template v-if="result.report?.cases.length">
        <p>命中率 = 命中 ÷ 有效预测。覆盖率 = 有效预测 ÷ 已有实际结果的样本。这些百分比是历史样本统计。模型未输出概率，规则也没有概率权重。</p>
        <div class="scroll-x" tabindex="0" aria-label="历史回放指标">
          <table>
            <thead><tr><th>方法</th><th>命中率</th><th>有效预测覆盖率</th></tr></thead>
            <tbody>
              <tr v-for="(score, key) in result.report.scores" :key="key">
                <th scope="row">{{ names[key] }}</th><td>{{ ratio(score.hits, score.covered) }}</td>
                <td>{{ ratio(score.covered, score.labelled) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <details>
          <summary>逐日结果</summary>
          <div class="scroll-x" tabindex="0" aria-label="逐日预测与实际结果">
            <table>
              <thead><tr><th>行情截止</th><th>下一根预测 / 实际</th><th>走势预测 / 实际</th><th>走势观察截至</th><th>状态</th></tr></thead>
              <tbody>
                <tr v-for="item in result.report.cases" :key="item.session">
                  <th scope="row">{{ item.session }}</th>
                  <td>{{ label(item.direction) }} / {{ label(item.actual_direction) }}</td>
                  <td>{{ label(item.regime) }} / {{ label(item.actual_regime) }}</td>
                  <td>{{ item.regime_through || '—' }}</td><td>{{ caseStatuses[item.status] }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </details>
        <p>走势观察未来 {{ result.report.horizon }} 根日线。规则先检查突破，再按相对波幅的位移和走势效率区分趋势、通道与震荡（规则 v{{ result.report.rule_version }}）。</p>
      </template>
      <p v-else-if="result.status === 'completed'">截止日前没有可回放的已确认日线。</p>
    </template>
  </section>
</template>

<style scoped>
.forecast-replay { margin-block-end: 16px; padding: 16px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-panel); }
h2 { font-size: 16px; margin-block-end: 12px; }
form { display: flex; flex-wrap: wrap; align-items: end; gap: 8px; }
label { display: grid; gap: 4px; min-width: 0; }
input, select, button { min-height: var(--touch-target); max-width: 100%; border: 1px solid var(--border); border-radius: 4px; padding-inline: 8px; }
button { background: var(--accent); color: white; }
button:disabled { opacity: .6; }
p { margin-block: 8px; color: var(--text-secondary); }
table { width: 100%; border-collapse: collapse; white-space: nowrap; }
th, td { padding: 8px; text-align: start; border-bottom: 1px solid var(--border); }
summary { cursor: pointer; min-height: var(--touch-target); padding-block: 12px; }
</style>
