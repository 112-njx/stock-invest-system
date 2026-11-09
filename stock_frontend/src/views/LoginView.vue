<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthForm from '@/components/auth/AuthForm.vue'
import ResearchChart from '@/components/login/ResearchChart.vue'
import { useLegalModalStore } from '@/stores/legalModal'
import terminalImage from '@/assets/login/landing-terminal.webp'
import terminalMobile from '@/assets/login/landing-mobile.webp'
import heatmapImage from '@/assets/login/landing-heatmap.webp'
import './login-landing.css'

interface Coverage {
  stock_count: number | null
  stock_date: string | null
  stock_stale: boolean
  board_count: number
  board_date: number
  sample_start: number | null
}

const route = useRoute()
const router = useRouter()
const legal = useLegalModalStore()
const page = ref<HTMLElement>()
const dataSection = ref<HTMLElement>()
const features = ref<HTMLElement>()
const workflow = ref<HTMLElement>()
const drawer = ref<HTMLElement>()
const closeButton = ref<HTMLButtonElement>()
const authForm = ref<InstanceType<typeof AuthForm>>()
const drawerOpen = ref(false)
const coverage = ref<Coverage>()
let trigger: HTMLElement | null = null
let disposeMotion: (() => void) | undefined
let coverageTimer: ReturnType<typeof setTimeout> | undefined
const coverageRequest = new AbortController()

function onSuccess() {
  const redirect = route.query.redirect
  const destination = typeof redirect === 'string' && redirect.startsWith('/') && !redirect.startsWith('//')
    ? redirect
    : { name: 'market-home' }
  void router.push(destination)
}

function jumpTo(section?: HTMLElement) {
  section?.focus({ preventScroll: true })
  section?.scrollIntoView({ block: 'start' })
}

async function openLogin(event?: MouseEvent) {
  trigger = event?.currentTarget instanceof HTMLElement ? event.currentTarget : null
  drawerOpen.value = true
  await nextTick()
  closeButton.value?.focus({ preventScroll: true })
}

async function closeLogin() {
  if (legal.open || authForm.value?.restoreOpen) return
  drawerOpen.value = false
  await nextTick()
  const returnTarget = trigger ?? page.value?.querySelector<HTMLElement>('.nav-login')
  returnTarget?.focus({ preventScroll: true })
}

function onDrawerKey(event: KeyboardEvent) {
  if (legal.open || authForm.value?.restoreOpen) return
  if (event.key === 'Escape') {
    event.stopPropagation()
    void closeLogin()
  }
  if (event.key !== 'Tab' || !drawer.value) return
  const controls = [...drawer.value.querySelectorAll<HTMLElement>(
    'button:not(:disabled), input:not(:disabled), a[href], [tabindex="0"]',
  )].filter((control) => control.getClientRects().length > 0)
  const first = controls[0]
  const last = controls.at(-1)
  if (event.shiftKey && document.activeElement === first && last) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last && first) {
    event.preventDefault()
    first.focus()
  }
}

function formatDate(value?: string | number | null) {
  return value == null ? '待核验' : String(value).replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3')
}

const metrics = computed(() => {
  const snapshot = coverage.value
  return [
    {
      label: '股票覆盖',
      value: snapshot?.stock_count?.toLocaleString('zh-CN') ?? '—',
      detail: snapshot?.stock_date
        ? (snapshot.stock_stale ? '缓存快照 ' : '目录快照 ') + formatDate(snapshot.stock_date)
        : '按有效日 K 校验',
    },
    {
      label: '板块目录',
      value: snapshot?.board_count.toLocaleString('zh-CN') ?? '—',
      detail: '申万一至三级及概念',
    },
    {
      label: '日线跨度示例',
      value: snapshot?.sample_start ? String(snapshot.sample_start).slice(0, 4) + ' 年起' : '—',
      detail: '平安银行 000001',
    },
    {
      label: '最新交易日',
      value: snapshot ? formatDate(snapshot.board_date) : '—',
      detail: '本地行情快照',
    },
  ]
})

async function loadCoverage(attempt = 0) {
  try {
    const response = await fetch('/api/v1/stockdb/coverage', { signal: coverageRequest.signal })
    if (response.ok && !coverageRequest.signal.aborted) coverage.value = await response.json() as Coverage
  } catch {
    // The rest of the landing page remains usable when local market data is unavailable.
  }
  if ((coverage.value?.stock_count == null || coverage.value.stock_stale) && attempt < 3 && !coverageRequest.signal.aborted) {
    coverageTimer = setTimeout(() => void loadCoverage(attempt + 1), 2200)
  }
}

const datasets = [
  { title: '日线', columns: ['字段', '示例'], rows: [['交易日期', '2026-11-06'], ['标的代码', '000001'], ['收盘价', '11.81']] },
  { title: '板块', columns: ['字段', '示例'], rows: [['行业分类', '申万一级'], ['板块名称', '银行'], ['成分股', '平安银行']] },
  { title: '复权', columns: ['字段', '格式'], rows: [['标的代码', '六位股票代码'], ['生效日期', 'YYYY-MM-DD'], ['复权因子', '数值']] },
]
const selectedDataset = shallowRef(datasets[0]!)

const steps = [
  { title: '筛选标的', text: '从板块分化找到方向，挑出候选股票，拉取同一期间的日线做比较。' },
  { title: '设定规则', text: '结合预测区间提出假设，写下入场、退出和仓位条件。' },
  { title: '检查结果', text: '在历史行情中跑策略，用回撤和逐笔交易找出规则的薄弱环节。' },
]

onMounted(async () => {
  void loadCoverage()
  if (route.hash === '#sign-in' || route.query.redirect) {
    void openLogin()
  } else if (route.hash) {
    jumpTo(page.value?.querySelector<HTMLElement>('#' + CSS.escape(route.hash.slice(1))) ?? undefined)
  }

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  try {
    const [{ gsap }, { ScrollTrigger }] = await Promise.all([import('gsap'), import('gsap/ScrollTrigger')])
    if (!page.value || coverageRequest.signal.aborted) return
    const scroller = page.value
    gsap.registerPlugin(ScrollTrigger)
    const motion = gsap.matchMedia(scroller)
    disposeMotion = () => motion.revert()
    motion.add('(prefers-reduced-motion: no-preference)', () => {
      scroller.querySelectorAll<HTMLElement>('.feature-media').forEach((panel) => {
        gsap.fromTo(panel, { scale: 0.96, opacity: 0.72 }, {
          scale: 1,
          opacity: 1,
          ease: 'none',
          scrollTrigger: { scroller, trigger: panel, start: 'top bottom', end: 'center 75%', scrub: 0.35 },
        })
      })
      gsap.from('.workflow-step', {
        y: 12,
        opacity: 0.72,
        stagger: 0.1,
        duration: 0.45,
        scrollTrigger: { scroller, trigger: workflow.value, start: 'top 85%', once: true },
      })
    })
  } catch {
    // Native scrolling also works without the optional motion bundle.
  }
})

onBeforeUnmount(() => {
  coverageRequest.abort()
  clearTimeout(coverageTimer)
  disposeMotion?.()
})
</script>

<template>
  <div ref="page" class="login-landing">
    <div :inert="drawerOpen">
      <header class="landing-nav">
        <div class="landing-width nav-inner">
          <RouterLink class="landing-brand" :to="{ name: 'login' }">
            <span class="brand-mark" aria-hidden="true">K</span>量化交易终端
          </RouterLink>
          <nav aria-label="产品导航">
            <a class="nav-section" href="#features" @click.prevent="jumpTo(features)">功能</a>
            <RouterLink class="nav-market" :to="{ name: 'market-home' }">浏览行情</RouterLink>
            <button type="button" class="landing-button primary-action nav-login" @click="openLogin">登录</button>
          </nav>
        </div>
      </header>

      <section class="landing-width landing-hero" aria-labelledby="landing-title">
        <h1 id="landing-title" class="hero-title">低频量化研究工作台</h1>
        <p class="hero-intro">看行情、做预测、跑回测，免费获取研究所需的股票数据。</p>
        <div class="hero-actions">
          <RouterLink class="landing-button primary-action" :to="{ name: 'market-home' }">浏览行情 <span aria-hidden="true">↗</span></RouterLink>
          <a class="landing-button secondary-action" href="#data" @click.prevent="jumpTo(dataSection)">查看数据覆盖 <span aria-hidden="true">↓</span></a>
        </div>

        <figure class="hero-figure">
          <figcaption><span>指数研究终端</span><small>界面实拍 · 2026-11-06</small></figcaption>
          <picture>
            <source media="(max-width: 620px)" :srcset="terminalMobile" width="625" height="321" />
            <img :src="terminalImage" width="1280" height="478" fetchpriority="high"
              alt="指数研究终端，展示行业列表、银行指数 K 线、成分股和个股走势" />
          </picture>
        </figure>
      </section>

      <section id="data" ref="dataSection" class="landing-width coverage-section" tabindex="-1" aria-labelledby="coverage-title">
        <div class="section-heading">
          <h2 id="coverage-title">免费获取本地库数据</h2>
          <p>可用于独立研究与回测。各标的历史起始日期以实际覆盖为准。</p>
        </div>
        <dl class="coverage-grid">
          <div v-for="metric in metrics" :key="metric.label">
            <dt>{{ metric.label }}</dt>
            <dd>{{ metric.value }}</dd>
            <dd class="metric-detail">{{ metric.detail }}</dd>
          </div>
        </dl>
      </section>

      <section id="features" ref="features" class="landing-width landing-section" tabindex="-1" aria-labelledby="features-title">
        <header class="section-heading">
          <h2 id="features-title">从市场观察到策略验证</h2>
        </header>
        <div class="feature-grid">
          <article class="feature-card feature-wide market-card">
            <h3>行情与行业观察</h3>
            <p>用大盘云图看涨跌分布，再到指数蓝图比较板块走势和成分股。</p>
            <div class="feature-media"><img :src="heatmapImage" loading="lazy" decoding="async" width="1248" height="570" alt="大盘云图实拍，红色表示上涨，绿色表示下跌" /></div>
            <RouterLink class="feature-link" :to="{ name: 'heatmap' }">查看大盘云图 <span aria-hidden="true">↗</span></RouterLink>
          </article>

          <article class="feature-card forecast-card">
            <h3>K 线预测</h3>
            <p>在历史走势旁查看预测区间，把不确定性纳入研究假设。</p>
            <div class="feature-media"><ResearchChart mode="forecast" /></div>
            <div class="plot-caption"><span>历史日 K</span><span>预测区间示例</span></div>
          </article>

          <article class="feature-card backtest-card">
            <h3>策略回测</h3>
            <p>将入场、止损与仓位写成规则，通过收益、回撤与交易记录检验。</p>
            <div class="backtest-preview" aria-label="回测报告示例">
              <div class="report-head"><strong>回测报告</strong><small>示例</small></div>
              <dl class="report-metrics">
                <div><dt>累计收益</dt><dd class="report-up">+8.42%</dd></div>
                <div><dt>最大回撤</dt><dd class="report-down">−4.16%</dd></div>
                <div><dt>交易次数</dt><dd>12</dd></div>
              </dl>
              <div class="feature-media"><ResearchChart mode="backtest" /></div>
              <div class="report-trade"><span>逐笔交易</span><span>开仓 · 平仓 · 持有周期</span></div>
            </div>
            <RouterLink class="feature-link" :to="{ name: 'ai' }">进入 AI 策略 <span aria-hidden="true">↗</span></RouterLink>
          </article>

          <article class="feature-card feature-wide data-card">
            <h3>股票数据字段</h3>
            <p>日线、板块成分与复权因子可带入自己的分析流程。</p>
            <div class="dataset-preview">
              <div class="dataset-options" aria-label="选择数据字段示例">
                <button v-for="dataset in datasets" :key="dataset.title" type="button"
                  :aria-pressed="selectedDataset === dataset" @click="selectedDataset = dataset">
                  {{ dataset.title }}
                </button>
              </div>
              <table aria-label="数据字段示例">
                <thead><tr><th v-for="column in selectedDataset.columns" :key="column" scope="col">{{ column }}</th></tr></thead>
                <tbody><tr v-for="[field, value] in selectedDataset.rows" :key="field"><th scope="row">{{ field }}</th><td>{{ value }}</td></tr></tbody>
              </table>
            </div>
          </article>
        </div>
      </section>

      <section ref="workflow" id="workflow" class="landing-width workflow" aria-labelledby="workflow-title">
        <h2 id="workflow-title">一次低频研究怎么做</h2>
        <ol class="workflow-steps">
          <li v-for="step in steps" :key="step.title" class="workflow-step">
            <h3>{{ step.title }}</h3><p>{{ step.text }}</p>
          </li>
        </ol>
      </section>

      <footer class="landing-width landing-cta">
        <div><h2>从你关注的标的开始</h2><p>登录后同步自选股，保存你的交易策略。</p></div>
        <button type="button" class="landing-button primary-action" @click="openLogin">登录工作台 <span aria-hidden="true">↗</span></button>
      </footer>
    </div>

    <Teleport to="body">
      <Transition name="landing-drawer">
        <div v-if="drawerOpen" class="landing-drawer-mask" @click.self="closeLogin">
          <section ref="drawer" class="landing-drawer-panel" role="dialog" aria-modal="true" aria-label="登录或注册"
            @keydown="onDrawerKey">
            <div class="drawer-heading">
              <strong>量化交易终端</strong>
              <button ref="closeButton" type="button" aria-label="关闭登录" @click="closeLogin">×</button>
            </div>
            <AuthForm ref="authForm" :show-qq-login="false" @success="onSuccess" />
          </section>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
