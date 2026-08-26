<script setup lang="ts">
/**
 * B 区 · 技术指标面板（重写版 bug3）：
 * - 一行一个指标（非 2x2 网格），根据开启数量均分高度
 * - 默认开启：成交量、MACD；可通过左上角齿轮弹窗切换四个指标显隐
 * - 指标数据后端计算（/api/v1/indicators），前端只渲染
 * - 支撑/压力位设置已移至 A 区 KLineChart header，本组件不再处理
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { fetchIndicators, type IndicatorRow } from '@/api/market'
import { useMarketStore } from '@/stores/market'
import { useThemeStore } from '@/stores/theme'
import { formatAmount, formatPrice } from '@/utils/color'
import Sparkline, { type LineSeries } from './Sparkline.vue'

type IndicatorKey = 'volume' | 'amount' | 'macd' | 'kdj'

interface IndicatorMeta {
  key: IndicatorKey
  label: string
  /** 内联 SVG 图标（viewBox 0 0 16 16） */
  icon: string
}

const INDICATORS: IndicatorMeta[] = [
  {
    key: 'volume',
    label: '成交量',
    icon: '<rect x="1" y="8" width="3" height="7" rx="0.5"/><rect x="6.5" y="4" width="3" height="11" rx="0.5"/><rect x="12" y="1" width="3" height="14" rx="0.5"/>',
  },
  {
    key: 'amount',
    label: '成交额',
    icon: '<circle cx="8" cy="8" r="6.5"/><text x="8" y="11" text-anchor="middle" font-size="8" font-weight="bold" fill="currentColor" stroke="none">¥</text>',
  },
  {
    key: 'macd',
    label: 'MACD',
    icon: '<path d="M1 11 L5 5 L9 9 L15 3" fill="none"/><path d="M1 13 L5 9 L9 11 L15 7" fill="none" opacity="0.5"/>',
  },
  {
    key: 'kdj',
    label: 'KDJ',
    icon: '<path d="M1 10 Q4 4 8 8 T15 6" fill="none"/><path d="M1 12 Q5 7 9 10 T15 9" fill="none" opacity="0.6"/><path d="M1 14 Q6 10 10 12 T15 11" fill="none" opacity="0.35"/>',
  },
]

const market = useMarketStore()
const theme = useThemeStore()

const current = computed(() => market.current)
const rows = ref<IndicatorRow[]>([])
const loading = ref(false)

/** 已开启的指标（默认成交量 + MACD），持久化到 localStorage */
const STORAGE_KEY = 'indicator_visibility'
const enabled = ref<Set<IndicatorKey>>(new Set(['volume', 'macd']))

function loadVisibility() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const arr = JSON.parse(raw) as IndicatorKey[]
      if (Array.isArray(arr) && arr.length) {
        enabled.value = new Set(arr.filter((k) => INDICATORS.some((i) => i.key === k)))
        return
      }
    }
  } catch {
    /* ignore */
  }
  enabled.value = new Set(['volume', 'macd'])
}

function saveVisibility() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...enabled.value]))
  } catch {
    /* ignore */
  }
}

function toggleIndicator(key: IndicatorKey) {
  const next = new Set(enabled.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  enabled.value = next
  saveVisibility()
}

const enabledList = computed(() => INDICATORS.filter((i) => enabled.value.has(i.key)))

const UP_COLOR = computed(() => (theme.mode === 'dark' ? '#ef4444' : '#dc2626'))
const DOWN_COLOR = computed(() => (theme.mode === 'dark' ? '#22c55e' : '#059669'))

/** KDJ K/D/J 序列色 */
const KDJ = computed(() => {
  void theme.mode
  const g = getComputedStyle(document.documentElement)
  const get = (n: string, fb: string) => g.getPropertyValue(n).trim() || fb
  return {
    k: get('--ind-k', '#eab308'),
    d: get('--ind-d', '#3b82f6'),
    j: get('--ind-j', '#a855f7'),
  }
})

/** MACD DIF/DEA 色：DIF 用强调色，DEA 用橙色 */
const MACD_COLORS = computed(() => {
  void theme.mode
  const g = getComputedStyle(document.documentElement)
  return {
    dif: g.getPropertyValue('--ind-dif').trim() || '#3b82f6',
    dea: g.getPropertyValue('--ind-dea').trim() || '#f59e0b',
  }
})

const RECENT = 60

async function load() {
  if (!current.value) return
  loading.value = true
  try {
    rows.value = await fetchIndicators({
      symbol: current.value.id,
      period: market.period,
      names: 'macd,kdj,volume,amount',
    })
  } catch {
    rows.value = []
  } finally {
    loading.value = false
  }
}

const recent = computed(() => rows.value.slice(-RECENT))
const last = computed(() => rows.value[rows.value.length - 1] ?? null)

/* ---------- 各指标数据 ---------- */
const volumeBars = computed(() => ({
  values: recent.value.map((r) => r.volume),
  colors: recent.value.map((r) => (r.close >= r.open ? UP_COLOR.value : DOWN_COLOR.value)),
}))

const amountBars = computed(() => ({
  values: recent.value.map((r) => r.amount),
  colors: recent.value.map((r) => (r.close >= r.open ? UP_COLOR.value : DOWN_COLOR.value)),
}))

/** MACD HIST 柱状 */
const macdHist = computed(() => ({
  values: recent.value.map((r) => r.macd_hist ?? 0),
  colors: recent.value.map((r) => ((r.macd_hist ?? 0) >= 0 ? UP_COLOR.value : DOWN_COLOR.value)),
}))

/** MACD 统一数值范围（DIF/DEA/HIST 共用，保证叠加对齐） */
const macdRange = computed(() => {
  const vals = recent.value.flatMap((r) => [r.macd_dif ?? 0, r.macd_dea ?? 0, r.macd_hist ?? 0])
  const absMax = vals.length ? Math.max(...vals.map((v) => Math.abs(v)), 0.0001) : 1
  return { max: absMax, min: -absMax }
})

/** MACD DIF/DEA 折线（多系列） */
const macdLines = computed<LineSeries[]>(() => [
  { values: recent.value.map((r) => r.macd_dif ?? 0), color: MACD_COLORS.value.dif },
  { values: recent.value.map((r) => r.macd_dea ?? 0), color: MACD_COLORS.value.dea },
])

/** KDJ 三线折线（多系列） */
const kdjLines = computed<LineSeries[]>(() => [
  { values: recent.value.map((r) => r.kdj_k ?? 0), color: KDJ.value.k },
  { values: recent.value.map((r) => r.kdj_d ?? 0), color: KDJ.value.d },
  { values: recent.value.map((r) => r.kdj_j ?? 0), color: KDJ.value.j },
])

watch([current, () => market.period], () => {
  if (current.value) load()
})
onMounted(() => {
  loadVisibility()
  if (current.value) load()
})
onBeforeUnmount(() => {
  closePicker()
})

/* ---------- 指标选择弹窗 ---------- */
const pickerOpen = ref(false)

function openPicker() {
  pickerOpen.value = true
}
function closePicker() {
  pickerOpen.value = false
}
</script>

<template>
  <div class="indicator-panel">
    <header class="indicator-panel__header">
      <button class="gear-btn" title="选择技术指标" @click="openPicker">
        <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor">
          <path
            d="M8 0 9.4 2.1l2.5-.5 1 2.3 2.3 1-.5 2.5L16.7 8l-2 1.6.5 2.5-2.3 1-1 2.3-2.5-.5L8 16l-1.4-2.1-2.5.5-1-2.3-2.3-1 .5-2.5L-.7 8l2-1.6-.5-2.5 2.3-1 1-2.3 2.5.5L8 0zm0 5.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z"
          />
        </svg>
      </button>
      <span class="indicator-panel__title">技术指标</span>
      <span class="indicator-panel__count">{{ enabledList.length }}/{{ INDICATORS.length }}</span>
    </header>

    <div v-if="!current" class="indicator-panel__empty">未选择标的</div>
    <div v-else-if="loading && !rows.length" class="indicator-panel__empty">指标计算中…</div>
    <div v-else-if="!rows.length" class="indicator-panel__empty">暂无指标数据</div>
    <div v-else-if="!enabledList.length" class="indicator-panel__empty">未开启任何指标，点击左上角齿轮选择</div>
    <div v-else class="indicator-panel__rows" :style="{ gridTemplateRows: `repeat(${enabledList.length}, 1fr)` }">
      <!-- 成交量 -->
      <div v-if="enabled.has('volume')" class="ind-row">
        <div class="ind-row__head">
          <span class="ind-row__icon" v-html="INDICATORS[0].icon" />
          <span class="ind-row__label">成交量</span>
          <span class="ind-row__value">{{ formatAmount(last?.volume) }}</span>
        </div>
        <div class="ind-row__chart">
          <Sparkline :values="volumeBars.values" :color="volumeBars.colors" type="bar" :height="48" />
        </div>
      </div>

      <!-- 成交额 -->
      <div v-if="enabled.has('amount')" class="ind-row">
        <div class="ind-row__head">
          <span class="ind-row__icon" v-html="INDICATORS[1].icon" />
          <span class="ind-row__label">成交额</span>
          <span class="ind-row__value">{{ formatAmount(last?.amount) }}</span>
        </div>
        <div class="ind-row__chart">
          <Sparkline :values="amountBars.values" :color="amountBars.colors" type="bar" :height="48" />
        </div>
      </div>

      <!-- MACD -->
      <div v-if="enabled.has('macd')" class="ind-row">
        <div class="ind-row__head">
          <span class="ind-row__icon" v-html="INDICATORS[2].icon" />
          <span class="ind-row__label">MACD</span>
          <span class="ind-row__value ind-row__value--multi">
            <span class="t-secondary">DIF</span> {{ formatPrice(last?.macd_dif, 3) }}
            <span class="t-secondary">DEA</span> {{ formatPrice(last?.macd_dea, 3) }}
            <span class="t-secondary">HIST</span>
            <span :class="(last?.macd_hist ?? 0) >= 0 ? 't-up' : 't-down'">
              {{ formatPrice(last?.macd_hist, 3) }}
            </span>
          </span>
        </div>
        <div class="ind-row__chart ind-row__chart--macd">
          <Sparkline :values="macdHist.values" :color="macdHist.colors" type="bar" :height="48" :max="macdRange.max" :min="macdRange.min" />
          <Sparkline :lines="macdLines" type="line" :height="48" :max="macdRange.max" :min="macdRange.min" class="ind-row__overlay" />
        </div>
      </div>

      <!-- KDJ -->
      <div v-if="enabled.has('kdj')" class="ind-row">
        <div class="ind-row__head">
          <span class="ind-row__icon" v-html="INDICATORS[3].icon" />
          <span class="ind-row__label">KDJ</span>
          <span class="ind-row__value ind-row__value--multi">
            <span class="kdj-k">K</span> {{ formatPrice(last?.kdj_k, 2) }}
            <span class="kdj-d">D</span> {{ formatPrice(last?.kdj_d, 2) }}
            <span class="kdj-j">J</span> {{ formatPrice(last?.kdj_j, 2) }}
          </span>
        </div>
        <div class="ind-row__chart">
          <Sparkline :lines="kdjLines" type="line" :height="48" />
        </div>
      </div>
    </div>

    <!-- 指标选择弹窗 -->
    <Teleport to="body">
      <div v-if="pickerOpen" class="modal-mask" @click.self="closePicker">
        <div class="modal">
          <header class="modal__header">
            <span>选择技术指标</span>
            <button class="modal__close" @click="closePicker">×</button>
          </header>
          <div class="modal__body">
            <div class="picker-grid">
              <button
                v-for="ind in INDICATORS"
                :key="ind.key"
                class="picker-item"
                :class="{ active: enabled.has(ind.key) }"
                @click="toggleIndicator(ind.key)"
              >
                <span class="picker-item__icon" v-html="ind.icon" />
                <span class="picker-item__label">{{ ind.label }}</span>
                <span class="picker-item__check">{{ enabled.has(ind.key) ? '✓' : '' }}</span>
              </button>
            </div>
            <div class="picker-hint">点击切换指标显示，选择自动保存</div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.indicator-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
.indicator-panel__header {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
}
.gear-btn {
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  padding: 2px;
  border-radius: 3px;
  transition:
    color 0.15s,
    background-color 0.15s;
}
.gear-btn:hover {
  color: var(--text);
  background: var(--bg-hover);
}
.indicator-panel__title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}
.indicator-panel__count {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}
.indicator-panel__empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--text-muted);
}

/* 一行一个指标：grid 行数量由开启指标数决定 */
.indicator-panel__rows {
  flex: 1;
  min-height: 0;
  display: grid;
  gap: 0;
}
.ind-row {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 4px 10px 6px;
  border-bottom: 1px solid var(--border);
}
.ind-row:last-child {
  border-bottom: none;
}
.ind-row__head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
  padding-bottom: 2px;
}
.ind-row__icon {
  width: 14px;
  height: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  flex: none;
}
.ind-row__icon :deep(svg) {
  width: 14px;
  height: 14px;
}
.ind-row__label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  flex: none;
}
.ind-row__value {
  margin-left: auto;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--text);
}
.ind-row__value--multi {
  display: inline-flex;
  gap: 8px;
  align-items: center;
}
.ind-row__chart {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  position: relative;
}
.ind-row__chart--macd {
  position: relative;
}
.ind-row__overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.t-secondary {
  color: var(--text-muted);
}
.t-up {
  color: var(--up);
}
.t-down {
  color: var(--down);
}
.kdj-k {
  color: var(--ind-k, #eab308);
  font-weight: 600;
}
.kdj-d {
  color: var(--ind-d, #3b82f6);
  font-weight: 600;
}
.kdj-j {
  color: var(--ind-j, #a855f7);
  font-weight: 600;
}

/* 弹窗 */
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal {
  width: 380px;
  max-width: 90vw;
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  overflow: hidden;
}
.modal__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  font-weight: 600;
}
.modal__close {
  font-size: 18px;
  color: var(--text-muted);
  cursor: pointer;
  line-height: 1;
}
.modal__close:hover {
  color: var(--text);
}
.modal__body {
  padding: 14px;
}
.picker-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}
.picker-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 6px;
  background: var(--bg-panel-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  position: relative;
}
.picker-item:hover {
  border-color: var(--accent);
}
.picker-item.active {
  border-color: var(--accent);
  background: var(--bg-active);
}
.picker-item__icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
}
.picker-item.active .picker-item__icon {
  color: var(--accent);
}
.picker-item__icon :deep(svg) {
  width: 24px;
  height: 24px;
}
.picker-item__label {
  font-size: 12px;
  color: var(--text);
}
.picker-item__check {
  position: absolute;
  top: 4px;
  right: 6px;
  font-size: 12px;
  color: var(--accent);
  font-weight: 700;
}
.picker-hint {
  margin-top: 10px;
  font-size: 11px;
  color: var(--text-muted);
  text-align: center;
}
</style>
