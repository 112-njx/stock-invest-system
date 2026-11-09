<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthForm from '@/components/auth/AuthForm.vue'

const route = useRoute()
const router = useRouter()
const signIn = ref<HTMLElement>()
const features = ref<HTMLElement>()
const roadmap = ref<HTMLElement>()

function onSuccess() {
  const redirect = route.query.redirect
  const destination = typeof redirect === 'string' && redirect.startsWith('/') && !redirect.startsWith('//')
    ? redirect
    : { name: 'market-home' }
  router.push(destination)
}

function jumpTo(section?: HTMLElement) {
  section?.focus({ preventScroll: true })
  section?.scrollIntoView({ block: 'start' })
}

// Fixed illustrative prices keep the preview independent of network requests.
const closes = [31, 36, 33, 41, 45, 39, 43, 49, 55, 50, 46, 53, 57, 61, 55, 57, 65, 71, 69, 75, 68, 74, 79, 77, 84, 89]
const candles = closes.map((close, index) => ({
  x: 21 + index * 17,
  open: closes[index - 1] ?? 27,
  close,
}))
const y = (price: number) => 165 - price * 1.45

const capabilities = [
  { number: '01', title: '行情与个股研究', description: '查看股票日 K、分时行情和常用技术指标。把关注的标的放进自选，持续跟踪价格变化。', tags: ['日 K / 分时', '技术指标', '自选股'], to: { name: 'market-home' } },
  { number: '02', title: '行业与板块观察', description: '从大盘云图观察市场分布，用指数蓝图对比行业走势、成分股行情和阶段表现。', tags: ['大盘云图', '指数蓝图', '阶段表现'], to: '/stockdb' },
  { number: '03', title: 'AI 策略与回测', description: '用自然语言描述入场、止损和仓位条件，生成并保存策略，通过历史回测查看收益、回撤和交易记录。', tags: ['策略生成', '历史回测', '交易记录'], to: '/ai' },
]
</script>

<template>
  <div class="login-page">
    <div class="login-wrap">
      <header class="login-header">
        <RouterLink class="brand" to="/">
          <span class="brand-mark" aria-hidden="true">K</span>
          <span>量化交易终端</span>
        </RouterLink>
        <nav class="login-nav" aria-label="产品导航">
          <a href="#features" @click.prevent="jumpTo(features)">功能概览</a>
          <a href="#roadmap" @click.prevent="jumpTo(roadmap)">产品路线</a>
          <RouterLink class="browse-link" :to="{ name: 'market-home' }">浏览行情 <span aria-hidden="true">↗</span></RouterLink>
        </nav>
      </header>

      <div class="hero">
        <section class="hero-copy" aria-labelledby="hero-title">
          <p class="eyebrow"><span class="status-dot" /> 为低频量化研究而建</p>
          <h1 id="hero-title">看懂行情，<br /><span>验证你的策略。</span></h1>
          <p class="hero-description">把行情观察、行业分析和策略回测放进同一个工作台。从发现机会，到用历史数据检验交易想法。</p>
          <a class="explore-link" href="#features" @click.prevent="jumpTo(features)">探索产品 <span aria-hidden="true">↓</span></a>

          <figure class="preview" aria-label="行情图表示意">
            <figcaption class="preview-header">
              <div><span class="preview-dot" aria-hidden="true" /><strong>市场研究工作台</strong></div>
              <span class="preview-label">示意数据</span>
            </figcaption>
            <svg class="preview-chart" viewBox="0 0 480 174" aria-hidden="true">
              <defs>
                <linearGradient id="login-chart-area" x2="0" y2="1">
                  <stop stop-color="#60a5fa" stop-opacity=".2" />
                  <stop offset="1" stop-color="#60a5fa" stop-opacity="0" />
                </linearGradient>
              </defs>
              <path d="M0 28H480 M0 65H480 M0 102H480 M0 139H480 M80 0V174 M160 0V174 M240 0V174 M320 0V174 M400 0V174" stroke="currentColor" opacity=".14" />
              <path d="M12 142 Q103 129 156 104 T285 77 T464 35 V174 H12Z" fill="url(#login-chart-area)" />
              <g v-for="(bar, index) in candles" :key="bar.x" :fill="bar.close >= bar.open ? 'var(--up)' : 'var(--down)'">
                <rect :x="bar.x - 4" :y="158 - index % 5 * 2" width="8" :height="7 + index % 5 * 2" opacity=".25" />
                <rect :x="bar.x - .5" :y="y(Math.max(bar.open, bar.close) + 4)" width="1" :height="Math.abs(bar.close - bar.open) * 1.45 + 11.6" />
                <rect :x="bar.x - 4" :y="y(Math.max(bar.open, bar.close))" width="8" :height="Math.abs(bar.close - bar.open) * 1.45" rx="1" />
              </g>
              <path class="trend-line" d="M21 130 Q65 122 105 109 T190 99 T275 78 T360 62 T446 48" fill="none" stroke="var(--preview-blue)" stroke-width="2" />
            </svg>
            <div class="preview-footer"><span>日 K · 成交量</span><span>行情可视化预览</span></div>
          </figure>
        </section>

        <section id="sign-in" ref="signIn" class="login-card" tabindex="-1" aria-label="登录或注册">
          <p class="card-kicker">账户中心</p>
          <AuthForm :show-qq-login="false" @success="onSuccess" />
        </section>
      </div>

      <section id="features" ref="features" class="product-section" tabindex="-1" aria-labelledby="features-title">
        <p class="eyebrow"><span class="status-dot" /> 现已可用</p>
        <h2 id="features-title">从市场观察到策略验证</h2>
        <p class="section-description">先了解市场和标的，再把交易想法写成可回测的规则。</p>
        <div class="capability-grid">
          <article v-for="feature in capabilities" :key="feature.number" class="capability">
            <span class="feature-number">{{ feature.number }} /</span>
            <h3>{{ feature.title }}</h3>
            <p>{{ feature.description }}</p>
            <ul class="tags" aria-label="功能">
              <li v-for="tag in feature.tags" :key="tag">{{ tag }}</li>
            </ul>
            <RouterLink :to="feature.to">查看{{ feature.title }} <span aria-hidden="true">↗</span></RouterLink>
          </article>
        </div>
      </section>

      <section id="roadmap" ref="roadmap" class="product-section roadmap" tabindex="-1" aria-labelledby="roadmap-title">
        <p class="eyebrow"><span class="roadmap-dot" /> 规划中 · 尚未开放</p>
        <h2 id="roadmap-title">下一步，开放更多研究能力</h2>
        <div class="roadmap-grid">
          <article>
            <h3>K 线预测</h3>
            <p>计划将历史行情与模型预测接入研究流程，展示预测区间，并通过历史数据检验模型表现。</p>
          </article>
          <article>
            <h3>免费股票数据拉取</h3>
            <p>计划逐步开放当前本地库已有的全部数据，提供免费的股票数据拉取能力，便于自行研究和回测。</p>
          </article>
        </div>
      </section>

      <div class="login-bottom">
        <p>让每个交易想法都有据可查。</p>
        <a class="browse-link" href="#sign-in" @click.prevent="jumpTo(signIn)">返回登录 <span aria-hidden="true">↑</span></a>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  --preview-blue: #77b7ff;
  --landing-glow: rgba(47, 115, 245, .16);
  flex: 1;
  min-height: 0;
  overflow: auto;
  scroll-behavior: smooth;
  color: var(--text);
  background: radial-gradient(ellipse at 22% 0, var(--landing-glow), transparent 56%) var(--bg);
}
:global([data-theme='light']) .login-page { --preview-blue: #2563eb; --landing-glow: rgba(47, 115, 245, .09); }
.login-wrap { width: min(1240px, 100% - clamp(32px, 8vw, 112px)); margin-inline: auto; }
.login-header, .login-nav, .brand, .preview-header, .preview-header div, .preview-footer, .login-bottom {
  display: flex;
  align-items: center;
}
.login-header { justify-content: space-between; gap: 16px; min-height: 74px; border-bottom: 1px solid var(--border); }
.brand { gap: 10px; color: var(--text); font-size: 15px; font-weight: 750; text-decoration: none; white-space: nowrap; }
.brand-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  color: #fff;
  background: #2563eb;
  border-radius: 9px;
  font-size: 19px;
  box-shadow: 0 3px 16px rgba(37, 99, 235, .26);
}
.login-nav { gap: clamp(14px, 2vw, 30px); }
.login-nav a, .explore-link, .browse-link, .capability > a { color: var(--text-secondary); text-decoration: none; font-weight: 600; }
.login-nav a:hover, .explore-link:hover, .capability > a:hover { color: var(--preview-blue); }
.browse-link { display: inline-flex; align-items: center; gap: 8px; padding: 8px 13px; border: 1px solid var(--border-strong); border-radius: 8px; white-space: nowrap; }
.browse-link:hover { background: var(--bg-hover); color: var(--text); }
.hero { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(320px, .9fr); gap: clamp(32px, 7vw, 100px); align-items: center; padding: clamp(35px, 6vh, 78px) 0; }
.eyebrow { display: flex; align-items: center; gap: 8px; color: var(--preview-blue); font-size: 12px; font-weight: 700; letter-spacing: .14em; }
.status-dot, .roadmap-dot, .preview-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; flex: none; }
.status-dot { box-shadow: 0 0 13px currentColor; }
.hero h1 { margin-top: 12px; font-size: clamp(38px, 5vw, 76px); line-height: 1.12; letter-spacing: -.045em; font-weight: 800; }
.hero h1 span { color: var(--preview-blue); }
.hero-description { max-width: 34em; margin-top: 14px; color: var(--text-secondary); font-size: clamp(14px, 1.25vw, 17px); line-height: 1.8; }
.explore-link { display: inline-flex; align-items: center; gap: 10px; margin-top: 14px; color: var(--preview-blue); }
.explore-link span { transition: transform .2s ease; }
.explore-link:hover span { transform: translateY(4px); }
.preview { margin-top: 24px; background: var(--bg-panel); border: 1px solid var(--border-strong); border-radius: 14px; box-shadow: 0 16px 50px rgba(3, 10, 24, .17); overflow: hidden; }
.preview-header, .preview-footer { justify-content: space-between; gap: 8px; padding: 10px 16px; }
.preview-header { border-bottom: 1px solid var(--border); }
.preview-header div { gap: 8px; }
.preview-dot { color: var(--preview-blue); }
.preview-label, .preview-footer { color: var(--text-secondary); font-size: 11px; }
.preview-label { padding: 2px 8px; background: var(--bg-hover); border-radius: 5px; }
.preview-chart { display: block; width: 100%; height: clamp(130px, 22vh, 210px); color: var(--text-secondary); }
.preview-footer { border-top: 1px solid var(--border); }
.trend-line { stroke-dasharray: 550; animation: draw-line 1.35s ease-out both; }
@keyframes draw-line { from { stroke-dashoffset: 550; } to { stroke-dashoffset: 0; } }
.login-card {
  min-width: 0;
  padding: clamp(24px, 3.4vw, 44px);
  border: 1px solid var(--border-strong);
  border-radius: 19px;
  background: var(--bg-panel);
  box-shadow: 0 24px 70px rgba(3, 10, 24, .22);
}
.card-kicker { color: var(--preview-blue); font-size: 12px; font-weight: 700; letter-spacing: .15em; margin-bottom: 10px; }
.login-card :deep(.base-input__field) { height: 42px; border-radius: 8px; }
.login-card :deep(.base-input__field::placeholder) { color: var(--text-secondary); }
.login-card :deep(.submit) { border-radius: 8px; }
.product-section { padding: clamp(40px, 6vw, 76px) 0; border-top: 1px solid var(--border); }
.product-section h2 { margin-top: 9px; font-size: clamp(26px, 3vw, 42px); line-height: 1.24; letter-spacing: -.025em; }
.section-description { color: var(--text-secondary); margin-top: 10px; }
.capability-grid, .roadmap-grid { display: grid; gap: 14px; margin-top: 25px; }
.capability-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.capability, .roadmap-grid article { padding: clamp(19px, 2.3vw, 29px); border: 1px solid var(--border-strong); border-radius: 13px; background: var(--bg-panel); }
.capability { display: flex; flex-direction: column; transition: border-color .2s, transform .2s; }
.capability:focus-within, .capability:hover { border-color: var(--accent); transform: translateY(-3px); }
.feature-number { color: var(--preview-blue); font: 600 13px ui-monospace, monospace; margin-bottom: 15px; }
.capability h3, .roadmap h3 { font-size: 18px; }
.capability p, .roadmap-grid p { color: var(--text-secondary); line-height: 1.8; margin-top: 9px; }
.tags { display: flex; flex-wrap: wrap; gap: 6px; margin-block: 17px; list-style: none; }
.tags li { padding: 3px 8px; font-size: 11px; color: var(--preview-blue); background: var(--accent-soft); border-radius: 5px; }
.capability > a { margin-top: auto; align-self: flex-start; color: var(--preview-blue); font-size: 13px; }
.roadmap .eyebrow { color: var(--text-secondary); }
.roadmap-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.roadmap-grid article { border-style: dashed; }
.login-bottom { justify-content: space-between; gap: 10px; padding: 20px 0 34px; border-top: 1px solid var(--border); color: var(--text-secondary); }
.login-page :is(a, section):focus-visible { outline: 2px solid var(--accent); outline-offset: 4px; }
.login-card, .product-section { scroll-margin-block-start: 16px; }
@media (max-width: 850px) {
  .hero { grid-template-columns: minmax(0, 1fr); gap: 24px; }
  .preview { display: none; }
  .login-card { width: min(100%, 480px); }
  .capability-grid { grid-template-columns: 1fr; }
}
@media (max-width: 510px) {
  .login-header { min-height: 62px; }
  .login-nav > a:not(.browse-link) { display: none; }
  .roadmap-grid { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) {
  .login-page { scroll-behavior: auto; }
  .trend-line { animation: none; }
  .explore-link span, .capability { transition: none; }
}
</style>
