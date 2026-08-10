<script setup lang="ts">
/**
 * B 区 · 技术指标面板：渲染后端计算的 成交量/成交额/MACD/KDJ（随周期切换刷新）。
 * 左上角设置键 → 弹窗输入支撑/压力位 → POST → 通知父级刷新 K 线横线。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  addSupportResistance,
  fetchIndicators,
  fetchSupportResistance,
  removeSupportResistance,
  type IndicatorRow,
  type SupportResistanceItem,
} from '@/api/market'
import { useMarketStore } from '@/stores/market'
import { useThemeStore } from '@/stores/theme'
import { formatAmount, formatPrice } from '@/utils/color'
import { toast } from '@/utils/toast'
import Sparkline from './Sparkline.vue'
import BaseButton from '@/components/base/BaseButton.vue'

const emit = defineEmits<{ (e: 'sr-changed'): void }>()

const market = useMarketStore()
const theme = useThemeStore()

const current = computed(() => market.current)
const rows = ref<IndicatorRow[]>([])
const loading = ref(false)

const UP_COLOR = computed(() => (theme.mode === 'dark' ? '#ef4444' : '#dc2626'))
const DOWN_COLOR = computed(() => (theme.mode === 'dark' ? '#22c55e' : '#059669'))
const ACCENT = computed(() => (theme.mode === 'dark' ? '#3b82f6' : '#2563eb'))

const RECENT = 24

async function load() {
  if (!current.value) return
  loading.value = true
  try {
    rows.value = await fetchIndicators({
      symbol: current.value.id,
      period: market.period,
      names: 'macd,kdj,volume,amount',
      limit: 200,
    })
  } catch {
    rows.value = []
  } finally {
    loading.value = false
  }
}

const recent = computed(() => rows.value.slice(-RECENT))
const last = computed(() => rows.value[rows.value.length - 1] ?? null)

const volumeSeries = computed(() => ({
  values: recent.value.map((r) => r.volume),
  colors: recent.value.map((r) => (r.close >= r.open ? UP_COLOR.value : DOWN_COLOR.value)),
}))

const amountSeries = computed(() => recent.value.map((r) => r.amount))

const macdHist = computed(() => ({
  values: recent.value.map((r) => r.macd_hist ?? 0),
  colors: recent.value.map((r) => ((r.macd_hist ?? 0) >= 0 ? UP_COLOR.value : DOWN_COLOR.value)),
}))

const kdjSeries = computed(() => ({
  k: recent.value.map((r) => r.kdj_k ?? 0),
  d: recent.value.map((r) => r.kdj_d ?? 0),
  j: recent.value.map((r) => r.kdj_j ?? 0),
}))

watch([current, () => market.period], () => {
  if (current.value) load()
})
onMounted(() => {
  if (current.value) load()
})
onBeforeUnmount(() => {
  closeDialog()
})

/* ---------- 支撑/压力位设置弹窗 ---------- */
const dialogOpen = ref(false)
const srType = ref<'support' | 'pressure'>('support')
const srPrice = ref('')
const srNote = ref('')
const srList = ref<SupportResistanceItem[]>([])
const submitting = ref(false)

async function openDialog() {
  if (!current.value) return
  srList.value = []
  dialogOpen.value = true
  try {
    srList.value = await fetchSupportResistance(current.value.id)
  } catch {
    /* 静默 */
  }
}

function closeDialog() {
  dialogOpen.value = false
  srPrice.value = ''
  srNote.value = ''
  submitting.value = false
}

async function onAddSr() {
  if (!current.value) return
  const price = Number(srPrice.value)
  if (!Number.isFinite(price) || price <= 0) {
    toast.error('请输入有效价位')
    return
  }
  submitting.value = true
  try {
    const item = await addSupportResistance({
      symbol: current.value.id,
      type: srType.value,
      price,
      note: srNote.value.trim() || undefined,
    })
    srList.value.push(item)
    srPrice.value = ''
    srNote.value = ''
    emit('sr-changed')
    toast.success('已添加' + (srType.value === 'support' ? '支撑位' : '压力位'))
  } catch {
    /* 错误已 toast */
  } finally {
    submitting.value = false
  }
}

async function onDeleteSr(item: SupportResistanceItem) {
  try {
    await removeSupportResistance(item.id)
    srList.value = srList.value.filter((s) => s.id !== item.id)
    emit('sr-changed')
  } catch {
    /* 错误已 toast */
  }
}
</script>

<template>
  <div class="indicator-panel">
    <header class="indicator-panel__header">
      <button class="gear-btn" title="支撑/压力位设置" @click="openDialog">
        <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor">
          <path
            d="M8 0 9.4 2.1l2.5-.5 1 2.3 2.3 1-.5 2.5L16.7 8l-2 1.6.5 2.5-2.3 1-1 2.3-2.5-.5L8 16l-1.4-2.1-2.5.5-1-2.3-2.3-1 .5-2.5L-.7 8l2-1.6-.5-2.5 2.3-1 1-2.3 2.5.5L8 0zm0 5.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z"
          />
        </svg>
      </button>
      <span class="indicator-panel__title">技术指标</span>
    </header>

    <div v-if="!current" class="indicator-panel__empty">未选择标的</div>
    <div v-else-if="loading && !rows.length" class="indicator-panel__empty">指标计算中…</div>
    <div v-else-if="!rows.length" class="indicator-panel__empty">暂无指标数据</div>
    <div v-else class="indicator-panel__grid">
      <!-- 成交量 -->
      <div class="ind-card">
        <div class="ind-card__title">成交量</div>
        <div class="ind-card__spark">
          <Sparkline :values="volumeSeries.values" :color="volumeSeries.colors" type="bar" />
        </div>
        <div class="ind-card__latest">{{ formatAmount(last?.volume) }}</div>
      </div>

      <!-- 成交额 -->
      <div class="ind-card">
        <div class="ind-card__title">成交额</div>
        <div class="ind-card__spark">
          <Sparkline :values="amountSeries" :color="ACCENT" type="bar" />
        </div>
        <div class="ind-card__latest">{{ formatAmount(last?.amount) }}</div>
      </div>

      <!-- MACD -->
      <div class="ind-card">
        <div class="ind-card__title">MACD</div>
        <div class="ind-card__spark">
          <Sparkline :values="macdHist.values" :color="macdHist.colors" type="bar" />
        </div>
        <div class="ind-card__latest ind-card__latest--multi">
          <span class="t-secondary">DIF</span> {{ formatPrice(last?.macd_dif, 3) }}
          <span class="t-secondary">DEA</span> {{ formatPrice(last?.macd_dea, 3) }}
          <span class="t-secondary">HIST</span>
          <span :class="(last?.macd_hist ?? 0) >= 0 ? 't-up' : 't-down'">
            {{ formatPrice(last?.macd_hist, 3) }}
          </span>
        </div>
      </div>

      <!-- KDJ -->
      <div class="ind-card">
        <div class="ind-card__title">KDJ</div>
        <div class="ind-card__spark kdj">
          <Sparkline :values="kdjSeries.k" color="#eab308" />
          <Sparkline :values="kdjSeries.d" color="#3b82f6" />
          <Sparkline :values="kdjSeries.j" color="#a855f7" />
        </div>
        <div class="ind-card__latest ind-card__latest--multi">
          <span class="kdj-k">K</span> {{ formatPrice(last?.kdj_k, 2) }}
          <span class="kdj-d">D</span> {{ formatPrice(last?.kdj_d, 2) }}
          <span class="kdj-j">J</span> {{ formatPrice(last?.kdj_j, 2) }}
        </div>
      </div>
    </div>

    <!-- 支撑/压力位设置弹窗 -->
    <Teleport to="body">
      <div v-if="dialogOpen" class="modal-mask" @click.self="closeDialog">
        <div class="modal">
          <header class="modal__header">
            <span>支撑/压力位设置</span>
            <button class="modal__close" @click="closeDialog">×</button>
          </header>

          <div class="modal__body">
            <div class="modal__symbol">
              {{ current?.name }} <span class="t-muted">{{ current?.code }}</span>
            </div>

            <div class="sr-type">
              <button
                class="sr-type__btn"
                :class="{ active: srType === 'support' }"
                @click="srType = 'support'"
              >
                支撑位
              </button>
              <button
                class="sr-type__btn"
                :class="{ active: srType === 'pressure' }"
                @click="srType = 'pressure'"
              >
                压力位
              </button>
            </div>

            <label class="sr-field">
              <span class="sr-field__label">价位</span>
              <input
                v-model="srPrice"
                class="sr-input"
                type="number"
                step="0.01"
                placeholder="请输入股价支撑/压力位"
              />
            </label>
            <label class="sr-field">
              <span class="sr-field__label">备注</span>
              <input
                v-model="srNote"
                class="sr-input"
                type="text"
                maxlength="50"
                placeholder="可选，如：强支撑 / 前高"
              />
            </label>

            <BaseButton size="sm" block :loading="submitting" @click="onAddSr">添加</BaseButton>

            <div v-if="srList.length" class="sr-list">
              <div class="sr-list__title">已设置</div>
              <div v-for="sr in srList" :key="sr.id" class="sr-item">
                <span
                  class="sr-item__type"
                  :class="sr.type === 'support' ? 'sr-item__type--support' : 'sr-item__type--pressure'"
                >
                  {{ sr.type === 'support' ? '支撑' : '压力' }}
                </span>
                <span class="sr-item__price">{{ formatPrice(sr.price) }}</span>
                <span class="sr-item__note">{{ sr.note || '—' }}</span>
                <button class="sr-item__del" @click="onDeleteSr(sr)">删除</button>
              </div>
            </div>
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
  position: relative;
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
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  color: var(--text-secondary);
  border-radius: 3px;
  transition:
    background-color 0.15s,
    color 0.15s;
}
.gear-btn:hover {
  background: var(--bg-hover);
  color: var(--text);
}
.indicator-panel__title {
  font-size: 13px;
  color: var(--text-secondary);
}
.indicator-panel__empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--text-muted);
}
.indicator-panel__grid {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  background: var(--border);
  border-top: 1px solid var(--border);
}
.ind-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 10px;
  background: var(--bg-panel);
  min-width: 0;
}
.ind-card__title {
  font-size: 12px;
  color: var(--text-secondary);
}
.ind-card__spark {
  height: 32px;
  display: flex;
  align-items: flex-end;
  gap: 0;
}
.ind-card__spark.kdj {
  align-items: flex-end;
  position: relative;
}
.ind-card__spark.kdj :deep(.sparkline) {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  opacity: 0.9;
}
.ind-card__latest {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text);
}
.ind-card__latest--multi {
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.kdj-k {
  color: #eab308;
}
.kdj-d {
  color: #3b82f6;
}
.kdj-j {
  color: #a855f7;
}

/* 弹窗 */
.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
}
.modal {
  width: 360px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  box-shadow: var(--shadow);
  overflow: hidden;
}
.modal__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  font-size: 14px;
  font-weight: 600;
}
.modal__close {
  font-size: 18px;
  color: var(--text-secondary);
  line-height: 1;
  padding: 0 4px;
}
.modal__close:hover {
  color: var(--text);
}
.modal__body {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
}
.modal__symbol {
  font-size: 14px;
  font-weight: 600;
}
.sr-type {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}
.sr-type__btn {
  padding: 6px 0;
  font-size: 13px;
  border-radius: 4px;
  border: 1px solid var(--border-strong);
  color: var(--text-secondary);
  transition:
    background-color 0.15s,
    color 0.15s,
    border-color 0.15s;
}
.sr-type__btn.active {
  border-color: var(--accent);
  color: var(--text);
  background: var(--accent-soft);
}
.sr-type__btn:nth-child(1).active {
  color: var(--down);
  border-color: var(--down);
}
.sr-type__btn:nth-child(2).active {
  color: var(--up);
  border-color: var(--up);
}
.sr-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.sr-field__label {
  font-size: 12px;
  color: var(--text-secondary);
}
.sr-input {
  height: 32px;
  padding: 0 10px;
  background: var(--bg-panel-2);
  border: 1px solid var(--border-strong);
  border-radius: 4px;
  color: var(--text);
  font-size: 13px;
  outline: none;
}
.sr-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}
.sr-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  border-top: 1px dashed var(--border);
  padding-top: 10px;
}
.sr-list__title {
  font-size: 12px;
  color: var(--text-muted);
}
.sr-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.sr-item__type {
  flex: none;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
}
.sr-item__type--support {
  color: var(--down);
  background: var(--down-soft);
}
.sr-item__type--pressure {
  color: var(--up);
  background: var(--up-soft);
}
.sr-item__price {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
.sr-item__note {
  flex: 1;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sr-item__del {
  font-size: 12px;
  color: var(--text-muted);
  padding: 2px 6px;
  border-radius: 3px;
}
.sr-item__del:hover {
  color: var(--up);
  background: var(--up-soft);
}
</style>
