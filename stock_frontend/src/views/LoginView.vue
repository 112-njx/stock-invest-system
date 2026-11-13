<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthForm from '@/components/auth/AuthForm.vue'
import DatasetPreview from '@/components/login/DatasetPreview.vue'
import IndustryPreview from '@/components/login/IndustryPreview.vue'
import ResearchChart from '@/components/login/ResearchChart.vue'
import ResearchStockTable from '@/components/login/ResearchStockTable.vue'
import './login-landing.css'

const route = useRoute()
const router = useRouter()
const page = ref<HTMLElement>()
const signIn = ref<HTMLElement>()
const features = ref<HTMLElement>()
const workflow = ref<HTMLElement>()
const workflowHeading = ref<HTMLElement>()

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

const dataTypes = ['股票日 K', '分时行情', '板块成分', '行业指数', '复权因子', '成交量与成交额']
const marqueePaused = ref(false)

const steps = [
  { title: '先定研究范围', text: '从行业走势找到关注方向，选出几只标的，取同一段历史数据做比较。', mode: 'market' },
  { title: '写下可验证的假设', text: '观察 K 线预测的方向与区间，将入场、退出和仓位写成具体规则。', mode: 'forecast' },
  { title: '回到历史里复盘', text: '运行策略回测，沿收益曲线和逐笔交易找到回撤发生的位置，再调整规则。', mode: 'backtest' },
] as const
const currentStep = ref(0)

function showStep(index: number) {
  currentStep.value = (index + steps.length) % steps.length
  if (window.matchMedia('(max-width: 900px)').matches) return
  const slide = workflow.value?.querySelectorAll<HTMLElement>('.workflow-slide')[currentStep.value]
  slide?.scrollIntoView({ block: 'start' })
}

let disposeMotion: (() => void) | undefined
let disposed = false

onMounted(async () => {
  if (route.hash) jumpTo(page.value?.querySelector<HTMLElement>(
    '#' + CSS.escape(route.hash.slice(1)),
  ) ?? undefined)

  // Let the form and illustrations paint before loading the animation code.
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
  if (disposed) return
  try {
    const [{ gsap }, { ScrollTrigger }] = await Promise.all([
      import('gsap'),
      import('gsap/ScrollTrigger'),
    ])
    if (disposed || !page.value) return
    const scroller = page.value
    gsap.registerPlugin(ScrollTrigger)
    const motion = gsap.matchMedia(scroller)
    disposeMotion = () => motion.revert()

    motion.add('(prefers-reduced-motion: no-preference) and (min-width: 901px) and (min-height: 480px)', () => {
      if (!workflow.value || !workflowHeading.value) return
      ScrollTrigger.create({
        scroller,
        trigger: workflow.value,
        pin: workflowHeading.value,
        pinSpacing: false,
        start: 'top 100px',
        end: () => '+=' + Math.max(0, workflow.value!.offsetHeight - workflowHeading.value!.offsetHeight),
        invalidateOnRefresh: true,
      })
    })
    motion.add('(prefers-reduced-motion: no-preference) and (min-width: 901px)', () => {
      const slides = scroller.querySelectorAll<HTMLElement>('.workflow-slide')
      slides.forEach((slide, index) => {
        const graphic = slide.querySelector('.workflow-graphic')
        if (!graphic) return
        gsap.timeline({
          scrollTrigger: {
            scroller,
            trigger: slide,
            start: 'top bottom',
            end: 'bottom top',
            scrub: 0.6,
          },
        })
          .fromTo(graphic, { scale: 0.8, opacity: 0.3 }, { scale: 1, opacity: 1, duration: 0.35, ease: 'none' })
          .to(graphic, { scale: 1, opacity: 1, duration: 0.3 })
          .to(graphic, { opacity: 0.2, duration: 0.35, ease: 'none' })
        ScrollTrigger.create({
          scroller,
          trigger: slide,
          start: 'top 65%',
          end: 'bottom 65%',
          onEnter: () => { currentStep.value = index },
          onEnterBack: () => { currentStep.value = index },
        })
      })

      // Registration expands the form and moves the sections below it.
      const observer = new ResizeObserver(() => ScrollTrigger.refresh())
      const hero = scroller.querySelector('.landing-hero')
      if (hero) observer.observe(hero)
      return () => observer.disconnect()
    })
  } catch (cause) {
    // Animation loading is optional. The native scroll and form remain usable.
    console.warn('无法加载登录页滚动动效', cause)
  }
})

onBeforeUnmount(() => {
  disposed = true
  disposeMotion?.()
})
</script>

<template>
  <div ref="page" class="login-landing">
    <header class="landing-nav">
      <div class="landing-width nav-inner">
        <RouterLink class="landing-brand" :to="{ name: 'login' }">
          <span class="brand-mark" aria-hidden="true">K</span>量化交易终端
        </RouterLink>
        <nav aria-label="产品导航">
          <a class="nav-section" href="#features" @click.prevent="jumpTo(features)">功能</a>
          <a class="nav-section" href="#workflow" @click.prevent="jumpTo(workflow)">研究示例</a>
          <RouterLink class="nav-market" :to="{ name: 'market-home' }">
            浏览行情 <span aria-hidden="true">↗</span>
          </RouterLink>
        </nav>
      </div>
    </header>

    <section class="landing-width landing-hero" aria-labelledby="landing-title">
      <div class="hero-editorial">
        <p class="hero-category">低频量化研究平台</p>
        <h1 id="landing-title" class="hero-title"><span>把交易想法</span><span>放进历史检验</span></h1>
        <p class="hero-intro">从行情和板块筛选标的，结合 K 线预测提出假设，再用历史回测检验规则。研究所需的股票数据可免费获取。</p>
        <div class="hero-actions">
          <a class="landing-button primary-action" href="#features" @click.prevent="jumpTo(features)">探索功能 <span aria-hidden="true">↓</span></a>
          <RouterLink class="landing-button secondary-action" :to="{ name: 'market-home' }">查看行情 <span aria-hidden="true">↗</span></RouterLink>
        </div>

        <figure class="hero-figure">
          <figcaption><span class="chart-key" />市场研究工作台 <small>图表示例</small></figcaption>
          <div class="hero-plot"><ResearchChart /></div>
          <div class="plot-caption"><span>日 K / 成交量</span><span>历史行情</span></div>
        </figure>
      </div>

      <section id="sign-in" ref="signIn" class="landing-form" tabindex="-1" aria-label="登录或注册">
        <AuthForm :show-qq-login="false" @success="onSuccess" />
      </section>
    </section>

    <div class="data-strip">
      <div class="landing-width strip-inner">
        <span class="strip-title">研究数据</span>
        <div class="marquee-window">
          <div class="marquee-track" :class="{ 'is-paused': marqueePaused }">
            <ul v-for="copy in 2" :key="copy" :aria-hidden="copy === 2 ? true : undefined" class="marquee-list">
              <li v-for="item in dataTypes" :key="item">{{ item }}</li>
            </ul>
          </div>
        </div>
        <button class="marquee-control" type="button" @click="marqueePaused = !marqueePaused">
          {{ marqueePaused ? '继续' : '暂停' }}<span class="visually-hidden">数据滚动</span>
        </button>
      </div>
    </div>

    <section id="features" ref="features" class="landing-width landing-section" tabindex="-1" aria-labelledby="features-title">
      <header class="section-heading">
        <h2 id="features-title">低频研究需要什么？</h2>
        <p>看行情、找方向、验证策略。数据可以带到自己的工作流里。</p>
      </header>
      <div class="feature-grid">
        <article class="feature-card feature-wide forecast-card">
          <div>
            <h3>K 线预测</h3>
            <p>把历史走势和预测区间放在同一张图里，观察方向、波动与不确定性。</p>
          </div>
          <div class="feature-plot"><ResearchChart mode="forecast" /></div>
          <div class="plot-caption"><span>历史日 K</span><span>预测区间示例</span></div>
        </article>

        <article class="feature-card market-card">
          <div>
            <h3>行情与行业观察</h3>
            <p>从大盘云图和指数蓝图看板块分化，沿行业走势找到成分股，再回到个股 K 线。</p>
          </div>
          <IndustryPreview />
          <RouterLink class="feature-link" :to="{ name: 'stockdb' }">查看指数蓝图 <span aria-hidden="true">↗</span></RouterLink>
        </article>

        <article class="feature-card backtest-card">
          <div>
            <h3>策略回测</h3>
            <p>用自然语言写下入场、止损和仓位条件，保存策略，在历史行情中查看收益、回撤与逐笔交易。</p>
          </div>
          <div class="feature-plot"><ResearchChart mode="backtest" /></div>
          <RouterLink class="feature-link" :to="{ name: 'ai' }">进入 AI 策略 <span aria-hidden="true">↗</span></RouterLink>
        </article>

        <article class="feature-card feature-wide data-card">
          <div>
            <h3>免费拉取股票数据</h3>
            <p>项目本地库已有的全部数据均纳入免费获取范围，可用于自己的分析、策略和回测。</p>
          </div>
          <DatasetPreview />
        </article>
      </div>
    </section>

    <section id="workflow" ref="workflow" class="landing-width landing-section workflow" tabindex="-1" aria-labelledby="workflow-title">
      <div ref="workflowHeading" class="workflow-heading">
        <h2 id="workflow-title">一次研究，<br />从哪开始？</h2>
        <p>以一条低频交易规则为例，看看研究过程如何串起来。</p>
        <div class="workflow-controls" aria-label="切换研究示例">
          <button type="button" aria-label="上一步" @click="showStep(currentStep - 1)">←</button>
          <span>{{ currentStep + 1 }} / {{ steps.length }}</span>
          <button type="button" aria-label="下一步" @click="showStep(currentStep + 1)">→</button>
        </div>
      </div>
      <div class="workflow-gallery">
        <article v-for="(step, index) in steps" :key="step.mode" class="workflow-slide" :class="{ 'is-current': index === currentStep }">
          <h3>{{ step.title }}</h3>
          <p>{{ step.text }}</p>
          <div class="workflow-graphic" :class="{ 'workflow-graphic--table': step.mode === 'market' }">
            <ResearchStockTable v-if="step.mode === 'market'" />
            <ResearchChart v-else :mode="step.mode" />
          </div>
        </article>
      </div>
    </section>

    <footer class="landing-width landing-cta">
      <div>
        <h2>从你关注的标的开始。</h2>
        <p>登录后同步自选股，保存你的交易策略。</p>
      </div>
      <a class="landing-button primary-action" href="#sign-in" @click.prevent="jumpTo(signIn)">登录研究工作台 <span aria-hidden="true">↑</span></a>
    </footer>
  </div>
</template>
