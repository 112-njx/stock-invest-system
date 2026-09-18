<script setup lang="ts">
/**
 * G35 · 登录页左侧功能卡片（规格书 §2.2 / §2.4）。
 *
 * - `mode: 'image'`（默认）：整图渲染，容器不加背景/边框/内边距（图片自带成品视觉）
 * - `mode: 'data'`（预留）：按结构化字段渲染占位骨架，未来可接真实接口
 * - 鼠标 3D 倾斜由 `useTilt` 提供，作用于本组件根容器
 */
import { useTemplateRef } from 'vue'
import { useTilt } from '@/composables/useTilt'
import type { LoginCardConfig } from '@/config/loginCards'

defineProps<{ card: LoginCardConfig }>()

const rootRef = useTemplateRef<HTMLElement>('root')
const { onEnter, onMove, onLeave } = useTilt(rootRef)

/** data 模式下卡片1 的仪表盘弧段角度（0~100 → -90°~+90° 半圆） */
function gaugeAngle(percent: number): string {
  const clamped = Math.max(0, Math.min(100, percent))
  return `${(-90 + (clamped / 100) * 180).toFixed(1)}deg`
}
</script>

<template>
  <div
    ref="root"
    class="feature-card"
    :class="{ 'feature-card--image': card.mode === 'image' }"
    @mouseenter="onEnter"
    @mousemove="onMove"
    @mouseleave="onLeave"
  >
    <!-- image 模式：三张成品图整图渲染 -->
    <img v-if="card.mode === 'image'" class="feature-card__img" :src="card.imageUrl" :alt="card.alt" />

    <!-- data 模式（预留动态化）：按卡片类型渲染结构化占位 -->
    <template v-else-if="card.kind === 'chance-index'">
      <div class="fc-head">
        <span class="fc-head__title">{{ card.data.title }}</span>
        <span class="fc-head__link">{{ card.data.linkText }} →</span>
      </div>
      <div class="fc-gauge">
        <div class="fc-gauge__arc" :style="{ '--angle': gaugeAngle(card.data.percent) }" />
        <span class="fc-gauge__value">{{ card.data.percent }}%</span>
      </div>
      <div class="fc-gauge__scale"><span>0%</span><span>100%</span></div>
    </template>

    <template v-else-if="card.kind === 'watchlist'">
      <div class="fc-head">
        <span class="fc-head__title">{{ card.data.title }}</span>
        <span class="fc-head__badge">{{ card.data.rows.length }}</span>
      </div>
      <div v-for="row in card.data.rows" :key="row.code" class="fc-row">
        <span class="fc-row__avatar" :style="{ background: row.avatarGradient }">{{ row.avatarText }}</span>
        <div class="fc-row__meta">
          <span class="fc-row__name">{{ row.name }}</span>
          <span class="fc-row__code">{{ row.code }}</span>
        </div>
        <div class="fc-row__quote">
          <span class="fc-row__price">{{ row.price }}</span>
          <span class="fc-row__pct" :class="row.changePct >= 0 ? 'is-up' : 'is-down'">
            {{ row.changePct >= 0 ? '+' : '' }}{{ row.changePct.toFixed(2) }}%
          </span>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="fc-head">
        <span class="fc-head__title">{{ card.data.title }}</span>
      </div>
      <div class="fc-metrics">
        <div class="fc-metric">
          <span class="fc-metric__label">胜率</span>
          <span class="fc-metric__value">{{ card.data.winRate }}</span>
        </div>
        <div class="fc-metric">
          <span class="fc-metric__label">盈亏比</span>
          <span class="fc-metric__value">{{ card.data.profitLossRatio }}</span>
        </div>
        <div class="fc-metric">
          <span class="fc-metric__label">夏普比率</span>
          <span class="fc-metric__value">{{ card.data.sharpe }}</span>
        </div>
      </div>
      <div class="fc-count">{{ card.data.count7 }}</div>
      <div class="fc-sep" />
      <div class="fc-foot">
        <span>年化收益率：<b>{{ card.data.annualReturn }}</b></span>
        <span class="fc-foot__count">{{ card.data.count112 }}</span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.feature-card {
  position: relative;
  flex: 1;
  min-height: 0;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
  padding: 20px;
  overflow: hidden;
  will-change: transform;
  transform-style: preserve-3d;
}
/* image 模式：图片自带成品视觉，容器不再叠加背景/边框/内边距 */
.feature-card--image {
  background: #161d2e;
  border: none;
  padding: 0;
}
.feature-card__img {
  display: block;
  width: 100%;
  height: 100%;
  /* 规格书 §2.2：优先保证关键文字不被裁切（验收要求 page3 底部「年化收益率」完整可见），
     故用 contain + 与图片一致的深蓝灰底色；容器底色见 .feature-card--image */
  object-fit: contain;
  object-position: center;
  border-radius: 16px;
  /* 倾斜时增强景深 */
  transform: translateZ(20px);
}

/* ---- data 模式样式（预留） ---- */
.fc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  color: #e5e7eb;
}
.fc-head__link {
  font-size: 12px;
  color: #9ca3af;
}
.fc-head__badge {
  min-width: 18px;
  padding: 0 6px;
  border-radius: 9px;
  font-size: 11px;
  text-align: center;
  color: #9ca3af;
  background: rgba(255, 255, 255, 0.08);
}
.fc-gauge {
  position: relative;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fc-gauge__arc {
  width: 150px;
  height: 75px;
  border-radius: 150px 150px 0 0;
  background: conic-gradient(
    from -90deg,
    #f97316 0deg,
    #ef4444 var(--angle),
    rgba(255, 255, 255, 0.12) var(--angle),
    rgba(255, 255, 255, 0.12) 180deg
  );
}
.fc-gauge__value {
  position: absolute;
  bottom: 4px;
  font-size: 26px;
  font-weight: 700;
  color: #fff;
  font-variant-numeric: tabular-nums;
}
.fc-gauge__scale {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #9ca3af;
}
.fc-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
}
.fc-row__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
}
.fc-row__meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.fc-row__name {
  font-size: 13px;
  color: #fff;
}
.fc-row__code {
  font-size: 11px;
  color: #9ca3af;
}
.fc-row__quote {
  margin-left: auto;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}
.fc-row__price {
  font-size: 14px;
  color: #fff;
  font-variant-numeric: tabular-nums;
}
.fc-row__pct {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.fc-row__pct.is-up {
  color: var(--up);
}
.fc-row__pct.is-down {
  color: var(--down);
}
.fc-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-top: 14px;
}
.fc-metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.fc-metric__label {
  font-size: 11px;
  color: #9ca3af;
}
.fc-metric__value {
  font-size: 20px;
  font-weight: 600;
  color: #fff;
  font-variant-numeric: tabular-nums;
}
.fc-count {
  margin-top: 10px;
  font-size: 22px;
  font-weight: 600;
  color: #fff;
  font-variant-numeric: tabular-nums;
}
.fc-sep {
  height: 1px;
  margin: 12px 0;
  background: rgba(255, 255, 255, 0.1);
}
.fc-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: #9ca3af;
}
.fc-foot b {
  color: #fff;
}
.fc-foot__count {
  color: #fff;
  font-variant-numeric: tabular-nums;
}
</style>
