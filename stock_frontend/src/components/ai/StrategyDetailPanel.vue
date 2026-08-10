<script setup lang="ts">
/**
 * N 区 · 交易策略显示区（4.7）：
 * 四部分居中：策略描述 / 回测结果（已保存）/ 代码实现（展示+可编辑保存）/ 回测模块（选标的→发起回测→轮询结果）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useAiStore } from '@/stores/ai'
import {
  createBacktest,
  fetchBacktestResults,
  fetchBacktestTask,
  updateStrategy,
  type BacktestResult,
  type BacktestTask,
} from '@/api/ai'
import type { SymbolInfo } from '@/api/market'
import { toast } from '@/utils/toast'
import SymbolPicker from '@/components/ai/SymbolPicker.vue'

const emit = defineEmits<{ (e: 'back'): void }>()

const ai = useAiStore()
const strategy = computed(() => ai.activeStrategy)

const code = ref('')
watch(strategy, (s) => {
  code.value = s?.code ?? ''
  if (s) void loadResults()
}, { immediate: true })

/* ---------- 回测结果 ---------- */
const results = ref<BacktestResult[]>([])
const resultsLoading = ref(false)

async function loadResults() {
  if (!strategy.value) return
  resultsLoading.value = true
  try {
    results.value = await fetchBacktestResults(strategy.value.id)
  } catch {
    results.value = []
  } finally {
    resultsLoading.value = false
  }
}

/* ---------- 回测模块 ---------- */
const btSymbol = ref<SymbolInfo | null>(null)
const btPeriod = ref('1d')
const btTask = ref<BacktestTask | null>(null)
const btRunning = ref(false)

const PERIODS = [
  { label: '日K', value: '1d' },
  { label: '周K', value: '1w' },
  { label: '月K', value: '1mon' },
  { label: '15分钟', value: '15m' },
]

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
}

async function runBacktest() {
  if (!strategy.value) return
  if (!btSymbol.value) {
    toast.error('请选择回测标的')
    return
  }
  if (btRunning.value) return
  btRunning.value = true
  btTask.value = null
  try {
    const task = await createBacktest({
      strategy_id: strategy.value.id,
      symbol: btSymbol.value.id,
      period: btPeriod.value,
    })
    btTask.value = task
    // 轮询任务状态直至完成
    for (;;) {
      await sleep(2000)
      const t = await fetchBacktestTask(task.id)
      btTask.value = t
      if (t.status === 'success') {
        toast.success('回测完成')
        await loadResults()
        break
      }
      if (t.status === 'failed') {
        toast.error(t.error || '回测失败')
        break
      }
    }
  } catch {
    /* 错误已 toast */
  } finally {
    btRunning.value = false
  }
}

/* ---------- 代码保存 ---------- */
async function saveCode() {
  if (!strategy.value) return
  try {
    const s = await updateStrategy(strategy.value.id, { code: code.value })
    ai.activeStrategy = s
    toast.success('代码已保存')
  } catch {
    /* 错误已 toast */
  }
}

/* ---------- 格式化 ---------- */
function pct(v?: number | null): string {
  return v == null ? '--' : `${(v * 100).toFixed(2)}%`
}
function num(v?: number | null): string {
  return v == null ? '--' : v.toFixed(2)
}

onMounted(() => void loadResults())
</script>

<template>
  <div class="sd">
    <header class="sd__topbar">
      <button class="sd__back" @click="emit('back')">← 返回</button>
      <h2 class="sd__title">{{ strategy?.title || '交易策略' }}</h2>
      <span class="sd__status">{{ strategy?.status === 'active' ? '生效中' : '草稿' }}</span>
    </header>

    <div v-if="!strategy" class="sd__empty">加载中…</div>
    <div v-else class="sd__body">
      <!-- ① 策略描述 -->
      <section class="sd__section">
        <h3 class="sd__h3">交易策略描述</h3>
        <p class="sd__desc">{{ strategy.description || '（无描述）' }}</p>
      </section>

      <!-- ② 回测结果（已保存） -->
      <section class="sd__section">
        <h3 class="sd__h3">回测结果</h3>
        <div v-if="resultsLoading" class="sd__hint">加载中…</div>
        <div v-else-if="!results.length" class="sd__hint">暂未保存回测结果，可在下方发起回测</div>
        <div v-else class="sd__metrics">
          <template v-for="r in results" :key="r.id">
            <div class="metric">
              <span class="metric__label">胜率</span>
              <span class="metric__value">{{ pct(r.win_rate) }}</span>
            </div>
            <div class="metric">
              <span class="metric__label">盈亏比</span>
              <span class="metric__value">{{ num(r.profit_loss_ratio) }}</span>
            </div>
            <div class="metric">
              <span class="metric__label">夏普比率</span>
              <span class="metric__value">{{ num(r.sharpe) }}</span>
            </div>
            <div class="metric">
              <span class="metric__label">累计买入</span>
              <span class="metric__value">{{ r.total_buys ?? '--' }}</span>
            </div>
            <div class="metric">
              <span class="metric__label">累计卖出</span>
              <span class="metric__value">{{ r.total_sells ?? '--' }}</span>
            </div>
            <div class="metric">
              <span class="metric__label">年化收益率</span>
              <span class="metric__value">{{ pct(r.annual_return) }}</span>
            </div>
            <div class="metric">
              <span class="metric__label">最大回撤</span>
              <span class="metric__value">{{ pct(r.max_drawdown) }}</span>
            </div>
          </template>
        </div>
      </section>

      <!-- ③ 代码实现 -->
      <section class="sd__section">
        <h3 class="sd__h3">代码实现</h3>
        <textarea v-model="code" class="sd__code" rows="10" spellcheck="false" />
        <div class="sd__op">
          <button class="sd__btn sd__btn--primary" @click="saveCode">保存代码</button>
        </div>
      </section>

      <!-- ④ 回测模块 -->
      <section class="sd__section">
        <h3 class="sd__h3">回测</h3>
        <div class="sd__bt-row">
          <span class="sd__label">回测标的</span>
          <SymbolPicker v-model="btSymbol" />
        </div>
        <div class="sd__bt-row">
          <span class="sd__label">K线周期</span>
          <select v-model="btPeriod" class="sd__select">
            <option v-for="p in PERIODS" :key="p.value" :value="p.value">{{ p.label }}</option>
          </select>
          <button
            class="sd__btn sd__btn--primary sd__btn--bt"
            :disabled="btRunning"
            @click="runBacktest"
          >
            {{ btRunning ? '回测中…' : '发起回测' }}
          </button>
        </div>
        <div v-if="btTask" class="sd__bt-status">
          任务 #{{ btTask.id }} · {{ btTask.status }}
          <template v-if="btTask.progress != null"> · 进度 {{ btTask.progress }}%</template>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.sd {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.sd__topbar {
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
}
.sd__back {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 4px 10px;
  border-radius: 4px;
  border: 1px solid var(--border-strong);
}
.sd__back:hover {
  background: var(--bg-hover);
  color: var(--text);
}
.sd__title {
  flex: 1;
  font-size: 15px;
  font-weight: 600;
  text-align: center;
}
.sd__status {
  flex: none;
  font-size: 11px;
  color: var(--down);
  background: var(--down-soft);
  border-radius: 3px;
  padding: 2px 8px;
}
.sd__empty {
  padding: 40px;
  text-align: center;
  color: var(--text-muted);
}
.sd__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  align-items: stretch;
  text-align: center;
}
.sd__section {
  text-align: center;
}
.sd__h3 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 10px;
  color: var(--text);
}
.sd__desc {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
  text-align: left;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  white-space: pre-wrap;
  word-break: break-word;
}
.sd__hint {
  font-size: 12px;
  color: var(--text-muted);
  padding: 12px 0;
}
.sd__metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
}
.metric {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  background: var(--bg-panel-2);
  border-radius: 6px;
}
.metric__label {
  font-size: 11px;
  color: var(--text-muted);
}
.metric__value {
  font-size: 16px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.sd__code {
  width: 100%;
  text-align: left;
  resize: vertical;
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  color: var(--text);
  font-family: Consolas, Monaco, 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
  padding: 10px 12px;
  outline: none;
}
.sd__code:focus {
  border-color: var(--accent);
}
.sd__op {
  margin-top: 8px;
  text-align: center;
}
.sd__btn {
  height: 30px;
  padding: 0 16px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--bg-panel-2);
  border: 1px solid var(--border-strong);
  transition: background-color 0.15s;
}
.sd__btn:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text);
}
.sd__btn--primary {
  background: var(--accent);
  border-color: transparent;
  color: #fff;
}
.sd__btn--primary:hover:not(:disabled) {
  filter: brightness(1.1);
  color: #fff;
}
.sd__bt-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.sd__label {
  font-size: 12px;
  color: var(--text-secondary);
}
.sd__select {
  height: 32px;
  padding: 0 8px;
  background: var(--bg-panel-2);
  color: var(--text);
  border: 1px solid var(--border-strong);
  border-radius: 4px;
  font-size: 13px;
  outline: none;
}
.sd__bt-status {
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
