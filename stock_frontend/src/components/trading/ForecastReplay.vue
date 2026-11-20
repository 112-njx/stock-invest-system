<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { isAxiosError } from 'axios'
import { getForecastReplay, startForecastReplay, type ForecastReplay, type ReplayOptions } from '@/api/forecast'

const props = defineProps<{ symbol: string }>()
defineEmits<{ locate: [session: string] }>()
const mode = ref<ReplayOptions['mode']>('reconstructed')
const end = ref('')
const samples = ref(5)
const result = ref<ForecastReplay | null>(null)
const submitting = ref(false)
const error = ref('')
let timer: ReturnType<typeof setTimeout> | undefined
let generation = 0
const active = computed(() => result.value?.status === 'queued' || result.value?.status === 'running')
const busy = computed(() => submitting.value || active.value)
type UncertainSubmission = { priorId: number | null; message: string; retryUntil: number }
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

function poll(submission?: UncertainSubmission) {
  clearTimeout(timer)
  timer = setTimeout(() => void refresh(submission), 5000)
}

async function refresh(submission?: UncertainSubmission) {
  const request = generation
  try {
    const data = await getForecastReplay(props.symbol)
    if (request !== generation) return
    result.value = data
    error.value = submission && !active.value && (!data || data.id === submission.priorId) ? submission.message : ''
  } catch {
    if (request !== generation) return
    error.value = submission?.message || '无法读取回放结果'
    poll(submission)
    return
  }
  if (active.value) poll()
  else if (submission && error.value && Date.now() < submission.retryUntil) poll(submission)
}

async function start() {
  if (busy.value) return
  const request = ++generation
  const priorId = result.value?.id ?? null
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
    const response = isAxiosError<{ msg?: string }>(cause) ? cause.response : undefined
    const message = response?.data?.msg || '提交回放失败'
    const retryUntil = !response || response.status >= 500 ? Date.now() + 15000 : 0
    await refresh({ priorId, message, retryUntil })
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
    <header class="replay-head">
      <h3 id="forecast-replay-title">历史回放</h3>
      <span>{{ symbol }} · 日线</span>
    </header>
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
      <p class="replay-status" role="status">{{ statusText[result.status] }}
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
        <template v-if="result.report.matched_scores">
          <h3>同样本基线对照</h3>
          <p>每行只比较 AI 和该基线都给出明确预测、且已有实际结果的样本。</p>
          <div class="scroll-x" tabindex="0" aria-label="同样本基线对照">
            <table>
              <thead><tr><th>基线</th><th>共同样本</th><th>AI 命中率</th><th>基线命中率</th></tr></thead>
              <tbody>
                <tr v-for="(score, key) in result.report.matched_scores" :key="key">
                  <th scope="row">{{ names[key] }}</th><td>{{ score.count }}</td>
                  <td>{{ ratio(score.ai_hits, score.count) }}</td>
                  <td>{{ ratio(score.baseline_hits, score.count) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
        <details>
          <summary>逐日结果</summary>
          <div class="scroll-x" tabindex="0" aria-label="逐日预测与实际结果">
            <table>
              <thead><tr><th>行情截止</th><th>下一根预测 / 实际</th><th>走势预测 / 实际</th><th>走势观察截至</th><th>状态</th></tr></thead>
              <tbody>
                <tr v-for="item in result.report.cases" :key="item.session">
                  <th scope="row"><button type="button" class="replay-date" @click="$emit('locate', item.session)">{{ item.session }}</button></th>
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
.forecast-replay { min-width: 0; padding: 10px; }
.replay-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap; margin-block-end: 8px; }
.replay-head h3 { font-size: 14px; }
.replay-head span { color: var(--text-secondary); font-size: 12px; }
h3:not(#forecast-replay-title) { font-size: 14px; margin-block-start: 12px; }
form { display: flex; flex-wrap: wrap; align-items: end; gap: 8px; padding: 8px; border-radius: 4px; background: var(--bg-panel-2); }
label { display: grid; gap: 4px; min-width: 0; max-width: 100%; color: var(--text-secondary); }
input, select, button { min-height: var(--touch-target); min-width: 0; max-width: 100%; border: 1px solid var(--border); border-radius: 4px; padding-inline: 8px; }
input, select { background: var(--bg-panel); color: var(--text); }
button { background: var(--accent-soft); color: var(--accent); }
.replay-date { border: 0; background: transparent; }
button:not(:disabled):hover { filter: brightness(1.08); }
button:disabled { opacity: .6; }
p { margin-block: 8px; color: var(--text-secondary); }
.replay-status { margin-block-start: 12px; color: var(--accent); font-weight: 700; }
table { width: 100%; border-collapse: collapse; white-space: nowrap; font-variant-numeric: tabular-nums; }
th, td { padding: 8px; text-align: start; border-bottom: 1px solid var(--border); }
thead { color: var(--text-secondary); }
tbody tr:hover { background: var(--bg-hover); }
summary { cursor: pointer; min-height: var(--touch-target); padding-block: 12px; }
@media (max-width: 480px) {
  form { display: grid; grid-template-columns: minmax(0, 1fr); }
}
</style>
