<script setup lang="ts">
/**
 * L 区 · 快捷功能卡片（4.2）：
 * 两行三列 —— 第一行正中间「创建交易策略」；第二行「诊断符号 / 交易计划 / 机会雷达」。
 * 点击卡片 → 将对应 prompt 模板写入输入框（AIView 处理）。
 */
import type { QuickCardType } from '@/stores/ai'

defineEmits<{ (e: 'select', card: QuickCardType): void }>()

const cards: Array<{ type: QuickCardType; title: string; desc: string; icon: string }> = [
  { type: 'create', title: '创建交易策略', desc: '描述一个入场想法，AI 会补齐规则和风控', icon: '▦' },
  { type: 'diagnose', title: '诊断符号', desc: '趋势、动量、支撑/阻力、流动性和风险', icon: '◎' },
  { type: 'plan', title: '交易计划', desc: '把当前行情整理成可执行的交易检查清单', icon: '▤' },
  { type: 'radar', title: '机会雷达', desc: '密切关注未来 24 小时内可能出现的机会', icon: '◎' },
]
</script>

<template>
  <div class="quick-cards">
    <div class="quick-cards__row quick-cards__row--center">
      <button class="qc-card" @click="$emit('select', 'create')">
        <span class="qc-card__icon">{{ cards[0].icon }}</span>
        <span class="qc-card__title">{{ cards[0].title }}</span>
        <span class="qc-card__desc">{{ cards[0].desc }}</span>
      </button>
    </div>
    <div class="quick-cards__row">
      <button
        v-for="c in cards.slice(1)"
        :key="c.type"
        class="qc-card"
        @click="$emit('select', c.type)"
      >
        <span class="qc-card__icon">{{ c.icon }}</span>
        <span class="qc-card__title">{{ c.title }}</span>
        <span class="qc-card__desc">{{ c.desc }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.quick-cards {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 16px;
}
.quick-cards__row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.quick-cards__row--center {
  grid-template-columns: 1fr 1.4fr 1fr;
}
.quick-cards__row--center .qc-card {
  grid-column: 2;
}
.qc-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 10px 12px;
  text-align: left;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  transition:
    background-color 0.15s,
    border-color 0.15s,
    transform 0.15s;
}
.qc-card:hover {
  background: var(--bg-hover);
  border-color: var(--border-strong);
  transform: translateY(-1px);
}
.qc-card__icon {
  font-size: 15px;
  color: var(--accent);
  line-height: 1;
  margin-bottom: 3px;
}
.qc-card__title {
  font-size: 13px;
  font-weight: 600;
}
.qc-card__desc {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.4;
}
</style>
