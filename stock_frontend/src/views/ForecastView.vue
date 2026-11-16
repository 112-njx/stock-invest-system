<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { isAxiosError } from 'axios'
import { fetchKLine, type KLineBar } from '@/api/market'
import { getForecastHistory, retryForecast, setForecastTracking, startForecast, type ForecastRun } from '@/api/forecast'
import nightGrid from '@/assets/forecast-night-grid.jpg'
import StockSearch from '@/components/layout/StockSearch.vue'
import ForecastCandlePreview from '@/components/trading/ForecastCandlePreview.vue'
import ForecastEvidence from '@/components/trading/ForecastEvidence.vue'
import ForecastMethod from '@/components/trading/ForecastMethod.vue'
import ForecastReplay from '@/components/trading/ForecastReplay.vue'
import { useAuthModalStore } from '@/stores/authModal'
import { useUserStore } from '@/stores/user'

const symbol = ref('')
const page = ref<HTMLElement>()
const bars = ref<KLineBar[]>([])
const state = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const dateFormat = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'medium', timeZone: 'Asia/Shanghai',
})
const priceFormat = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
const changeFormat = new Intl.NumberFormat('zh-CN', { style: 'percent', maximumFractionDigits: 2, signDisplay: 'exceptZero' })
const latestBar = computed(() => bars.value[0])
const closeChange = computed(() => {
  const [latest, previous] = bars.value
  return latest && previous?.close ? (latest.close - previous.close) / previous.close : null
})
const workflow = ['收盘日线', '行情诊断', '走势推演', '逐日回放', '基线对照']
const marqueePaused = ref(false)
let requestId = 0
let historyId = 0
let selection = 0
let timer: ReturnType<typeof setInterval>
let lastPoll = 0
let disposed = false
let disposeMotion: (() => void) | undefined
const user = useUserStore()
const authModal = useAuthModalStore()
const runs = ref<ForecastRun[]>([])
const selected = ref<number | null>(null)
const tracking = ref(false)
const action = ref<'run' | 'retry' | 'track' | null>(null)
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
  void setupMotion().catch(cause => console.warn('无法加载预测走势动效', cause))
})
onUnmounted(() => {
  disposed = true
  disposeMotion?.()
  clearInterval(timer)
  selection++
  historyId++
  requestId++
})

function goTo(id: string) {
  const target = page.value?.querySelector<HTMLElement>(`#${id}`)
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  target?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
  target?.focus({ preventScroll: true })
}

async function setupMotion() {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  const [{ gsap }, { ScrollTrigger }] = await Promise.all([import('gsap'), import('gsap/ScrollTrigger')])
  const scroller = page.value
  if (disposed || !scroller) return
  gsap.registerPlugin(ScrollTrigger)
  const motion = gsap.matchMedia(scroller)
  disposeMotion = () => motion.revert()

  motion.add('(prefers-reduced-motion: no-preference)', () => {
    const hero = scroller.querySelector('.forecast-hero')
    const photo = scroller.querySelector('.forecast-hero-photo')
    if (hero && photo) {
      gsap.timeline({ scrollTrigger: { scroller, trigger: hero, start: 'top top', end: 'bottom top', scrub: 0.6 } })
        .fromTo(photo, { scale: 0.8, opacity: 0.9 }, { scale: 1, opacity: 1, duration: 0.45, ease: 'none' })
        .to(photo, { opacity: 0.2, duration: 0.55, ease: 'none' })
    }
    const deck = scroller.querySelector('.method-deck')
    if (deck) {
      gsap.fromTo(deck.querySelectorAll('[data-forecast-stack]'),
        { y: (index: number) => 72 + index * 30, opacity: 0.35 },
        { y: 0, opacity: 1, stagger: 0.15, ease: 'none',
          scrollTrigger: { scroller, trigger: deck, start: 'top 95%', end: 'center 56%', scrub: 0.5 } },
      )
    }
    const observer = new ResizeObserver(() => ScrollTrigger.refresh())
    const workspace = scroller.querySelector('.forecast-workspace')
    if (workspace) observer.observe(workspace)
    return () => observer.disconnect()
  })
}

async function runAction(kind: 'run' | 'retry' | 'track', runId?: number) {
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
      const result = runId === undefined ? await startForecast(symbol.value) : await retryForecast(runId)
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
      void refreshRuns()
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
  <section ref="page" class="forecast-page" aria-labelledby="forecast-title">
    <nav class="forecast-nav" aria-label="预测走势页内导航">
      <div class="forecast-shell forecast-nav-inner">
        <a class="forecast-brand" href="#forecast-title" @click.prevent="goTo('forecast-title')">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" aria-hidden="true">
            <path d="M4 17l5-5 4 3 7-9M15 6h5v5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <span>走势研究</span>
        </a>
        <div class="forecast-nav-links">
          <a href="#forecast-workspace" @click.prevent="goTo('forecast-workspace')">工作台</a>
          <a href="#forecast-replay" @click.prevent="goTo('forecast-replay')">历史回放</a>
          <a href="#forecast-method" @click.prevent="goTo('forecast-method')">方法</a>
        </div>
      </div>
    </nav>

    <header class="forecast-hero">
      <!-- Photo by Vladimir Kudinov · https://unsplash.com/photos/KBX9XHk266s -->
      <img :src="nightGrid" class="forecast-hero-photo" alt="" fetchpriority="high" width="1920" height="1080" />
      <div class="forecast-shell forecast-hero-content">
        <h1 id="forecast-title" tabindex="-1"><span>预测走势</span><span>用历史检验判断</span></h1>
        <p>从已收盘的 A 股日线推演下一根方向和后续走势，再把预测放回历史中逐日检验。</p>
        <div class="forecast-hero-actions">
          <a class="forecast-cta" href="#forecast-workspace" @click.prevent="goTo('forecast-workspace')">选择股票 <span aria-hidden="true">↗</span></a>
          <a class="forecast-cta forecast-cta-secondary" href="#forecast-replay" @click.prevent="goTo('forecast-replay')">历史回放 <span aria-hidden="true">↓</span></a>
        </div>
      </div>
    </header>

    <div class="forecast-marquee">
      <div class="forecast-marquee-window" aria-hidden="true">
        <div class="forecast-marquee-track" :class="{ 'is-paused': marqueePaused }">
          <div v-for="copy in 2" :key="copy" class="forecast-marquee-group">
            <span v-for="item in workflow" :key="item">{{ item }}</span>
          </div>
        </div>
      </div>
      <button type="button" class="forecast-marquee-toggle" aria-label="暂停流程滚动"
        :aria-pressed="marqueePaused" @click="marqueePaused = !marqueePaused">
        <span aria-hidden="true">{{ marqueePaused ? '▷' : 'Ⅱ' }}</span>
      </button>
    </div>

    <div class="forecast-shell">
    <section id="forecast-workspace" tabindex="-1" class="forecast-workspace" aria-labelledby="forecast-workspace-title">
      <div class="forecast-workspace-head">
        <div>
          <h2 id="forecast-workspace-title">研究工作台</h2>
          <p>选定标的后，查看行情、运行分析或回放历史。</p>
        </div>
        <div class="forecast-picker"><StockSearch browse @select="loadHistory" /></div>
      </div>

      <div class="forecast-grid">
      <section class="forecast-panel forecast-market" aria-labelledby="forecast-history-title" :aria-busy="state === 'loading'">
        <div class="forecast-panel-head">
          <h3 id="forecast-history-title">{{ symbol ? `${symbol} · 最近日 K 线` : '最近日 K 线' }}</h3>
          <span>A 股 · 日线</span>
        </div>
        <p v-if="state === 'loading'" role="status" class="forecast-empty">正在读取历史行情…</p>
        <template v-else-if="state === 'error'">
          <p role="status">暂时无法读取历史行情。</p>
          <button type="button" class="forecast-retry" @click="loadHistory(symbol)">重试</button>
        </template>
        <template v-else-if="latestBar">
          <div class="forecast-quote">
            <div>
              <p>最近收盘</p>
              <strong>{{ priceFormat.format(latestBar.close) }}</strong>
              <span v-if="closeChange !== null" :class="{ 'quote-up': closeChange > 0, 'quote-down': closeChange < 0 }">
                {{ changeFormat.format(closeChange) }} 较上一根
              </span>
            </div>
            <time :datetime="latestBar.ts">{{ dateFormat.format(new Date(latestBar.ts)) }}</time>
          </div>
          <ForecastCandlePreview :bars="bars" />
          <details class="forecast-price-details">
            <summary>日线明细</summary>
            <div class="scroll-x" role="region" aria-label="最近的日 K 线数据" tabindex="0">
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
          </details>
        </template>
        <div v-else class="forecast-empty forecast-empty-chart">
          <span>{{ symbol ? '该股票暂无可用的日 K 线。' : '选择股票后显示实际行情' }}</span>
        </div>
      </section>

    <section class="forecast-panel forecast-analysis" aria-labelledby="forecast-analysis-title">
      <div class="forecast-panel-head">
        <h3 id="forecast-analysis-title">{{ symbol ? `${symbol} · 走势分析` : '走势分析' }}</h3>
        <span>两阶段分析</span>
      </div>
      <div v-if="!symbol" class="forecast-analysis-empty">
        <p><strong>行情诊断</strong>查看当前趋势和引用的日线证据。</p>
        <p><strong>走势推演</strong>分别查看下一根方向和下一阶段类型。</p>
      </div>
      <template v-else>
      <p v-if="!user.token">登录后可运行分析、查看历史记录和开启自动跟踪。</p>
      <div class="forecast-actions">
        <button type="button" class="forecast-run" :disabled="Boolean(action) || hasActiveRun" @click="runAction('run')">
          {{ action === 'run' ? '正在提交…' : '分析走势' }}
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
        <div class="forecast-run-state">
          <p role="status" class="forecast-status">{{ statuses[chosen.status] }}</p>
          <p>行情截至 {{ chosen.snapshot.latest_session || '暂无已确认日线' }} · {{ chosen.snapshot.bar_count }} 根日线</p>
        </div>
        <p v-if="chosen.error" role="alert">{{ chosen.error }}</p>
        <button v-if="chosen.status === 'failed'" type="button" class="forecast-retry"
          :disabled="Boolean(action) || hasActiveRun" @click="runAction('retry', chosen.id)">
          {{ action === 'retry' ? '正在提交…' : '重试此记录' }}
        </button>
        <section v-if="chosen.diagnosis" class="forecast-diagnosis">
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
            <p v-if="chosen.regime_horizon">观察窗口为未来 {{ chosen.regime_horizon }} 根有成交日 K 线。</p>
            <p v-else-if="chosen.models.prediction">旧版预测，观察窗口未固定。</p>
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
      <p v-else-if="user.token && !historyLoading" class="forecast-analysis-hint">运行分析后，诊断、预测与证据会显示在这里。</p>
      </template>
    </section>

      <div id="forecast-replay" tabindex="-1" class="forecast-replay-slot">
        <ForecastReplay v-if="symbol && user.token && user.user" :key="user.user.id" :symbol="symbol" />
        <section v-else class="forecast-panel forecast-replay-placeholder" aria-labelledby="forecast-replay-placeholder-title">
          <div>
            <h3 id="forecast-replay-placeholder-title">历史回放</h3>
            <p>按时间顺序重跑预测，核对实际结果、简单基线、命中率与覆盖率。</p>
          </div>
          <button v-if="!symbol" type="button" class="forecast-retry" @click="goTo('forecast-workspace')">前往选股</button>
          <button v-else type="button" class="forecast-run" @click="authModal.show()">登录后回放</button>
        </section>
      </div>
      </div>
    </section>

    <ForecastMethod />

    <footer class="forecast-footer">
      <div>
        <h2>从一只股票开始</h2>
        <p>选定标的，查看日线，或提交一组历史样本。</p>
      </div>
      <a class="forecast-cta" href="#forecast-workspace" @click.prevent="goTo('forecast-workspace')">打开研究工作台 <span aria-hidden="true">↗</span></a>
    </footer>
    </div>
  </section>
</template>

<style scoped src="./forecast-workspace.css"></style>
