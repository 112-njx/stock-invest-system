<script setup lang="ts">
import { computed, ref } from 'vue'

const steps = [
  { name: '固定行情截点', detail: '模型只读取截止日及此前的日线。使用当日存档时，缺少当天快照的样本会单独标记。' },
  { name: '拆开两个问题', detail: '用下一根日线的开盘与收盘判方向。走势类型单独观察后续五根有成交日线。' },
  { name: '和基线对照', detail: '把模型结果与实际行情、沿用上一根等简单基线并列，分别统计命中率和覆盖率。' },
]
const notes = [
  { name: '有效预测覆盖率', detail: '先看有多少样本得到明确答案。无法判断的样本保留在覆盖率的分母里。' },
  { name: '命中率', detail: '只在已有实际结果且预测明确的样本中统计命中。报告同时展示分子和分母。' },
  { name: '数据口径', detail: '当日存档保留当时看到的数据。重建历史使用截止日因子，原始行情可能包含事后修订。' },
]
const activeStep = ref(0)
const noteIndex = ref(0)
const note = computed(() => notes[noteIndex.value]!)

function moveNote(delta: number) {
  noteIndex.value = (noteIndex.value + delta + notes.length) % notes.length
}
</script>

<template>
  <section id="forecast-method" tabindex="-1" class="forecast-method" aria-labelledby="forecast-method-title">
    <div class="method-head">
      <h2 id="forecast-method-title">回放怎么检验预测</h2>
      <p>从固定输入开始，逐日核对两种预测。</p>
    </div>
    <div class="method-accordion">
      <article v-for="(step, index) in steps" :key="step.name" :class="{ 'method-open': activeStep === index }">
        <h3><button type="button" :aria-expanded="activeStep === index" :aria-controls="`forecast-method-${index}`"
          @click="activeStep = index">{{ step.name }}</button></h3>
        <p v-show="activeStep === index" :id="`forecast-method-${index}`">{{ step.detail }}</p>
      </article>
    </div>
    <div class="method-reading">
      <div class="method-deck" aria-hidden="true">
        <div class="method-sheet sheet-back" data-forecast-stack>
          <svg viewBox="0 0 240 86" fill="none">
            <path d="M0 12H240M0 43H240M0 74H240M40 0V86M80 0V86M120 0V86M160 0V86M200 0V86" />
          </svg>
        </div>
        <div class="method-sheet sheet-middle" data-forecast-stack>
          <svg viewBox="0 0 240 86" fill="none">
            <path d="M0 12H240M0 43H240M0 74H240M40 0V86M80 0V86M120 0V86M160 0V86M200 0V86" />
          </svg>
        </div>
        <div class="method-sheet sheet-front" data-forecast-stack>
          <svg viewBox="0 0 240 86" fill="none">
            <path d="M0 12H240M0 43H240M0 74H240M40 0V86M80 0V86M120 0V86M160 0V86M200 0V86" />
            <path class="sheet-line" d="m4 68 25-12 22 5 25-26 21 12 25-11 18 6 30-26 23 13 41-19" />
          </svg>
        </div>
      </div>
      <div class="method-note">
        <p class="method-caption">读懂回放报告</p>
        <div aria-live="polite" aria-atomic="true">
          <h3>{{ note.name }}</h3>
          <p>{{ note.detail }}</p>
        </div>
        <div class="note-controls">
          <button type="button" aria-label="上一条报告说明" @click="moveNote(-1)">←</button>
          <button type="button" aria-label="下一条报告说明" @click="moveNote(1)">→</button>
          <span>{{ noteIndex + 1 }} / {{ notes.length }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.forecast-method { display: grid; gap: 24px; padding-block: var(--forecast-chapter); border-top: 1px solid var(--forecast-rule); }
.method-head h2 { font-size: clamp(25px, 4vw, 44px); font-weight: 680; line-height: 1.2; }
.method-head p { margin-block-start: 8px; color: var(--text-secondary); }
.method-accordion { display: flex; gap: 8px; min-height: 170px; }
.method-accordion article { display: flex; flex: 0 0 58px; min-width: 0; background: var(--forecast-panel); border: 1px solid var(--forecast-rule); border-radius: 12px; transition: flex .36s ease, border-color .2s; }
.method-accordion article:hover { border-color: var(--forecast-accent); }
.method-accordion .method-open { flex: 1 1 0; }
.method-accordion h3 { display: flex; flex: 0 0 56px; }
.method-accordion button { width: 100%; min-height: var(--touch-target); padding: 12px; writing-mode: vertical-rl; color: var(--text); font-size: 14px; font-weight: 650; letter-spacing: .15em; }
.method-open button { color: var(--forecast-accent); }
.method-accordion p { align-self: center; max-width: 45ch; padding: 16px; color: var(--text-secondary); font-size: clamp(15px, 2vw, 21px); }
.method-reading { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); align-items: center; gap: clamp(16px, 4vw, 48px); min-height: 240px; padding: clamp(16px, 4vw, 42px); border-radius: 16px; border: 1px solid var(--forecast-rule); background: var(--forecast-panel); overflow: hidden; }
.method-deck { position: relative; min-height: 150px; isolation: isolate; }
.method-sheet { position: absolute; inset: 10px 12% 16px; display: grid; align-items: center; padding: 12px; border: 1px solid var(--forecast-rule); border-radius: 12px; background: var(--forecast-inset); }
.sheet-back { translate: -11% 16px; rotate: -9deg; }
.sheet-middle { translate: 9% -13px; rotate: 8deg; }
.sheet-front { border-color: var(--forecast-accent); }
.method-sheet svg { width: 100%; stroke: var(--forecast-rule); stroke-width: 1; }
.sheet-front .sheet-line { stroke: var(--forecast-accent); stroke-width: 2; }
.method-note h3 { margin-block: 4px 8px; font-size: clamp(20px, 3vw, 32px); }
.method-note p { color: var(--text-secondary); }
.method-note .method-caption { color: var(--forecast-accent); font-weight: 650; }
.note-controls { display: flex; align-items: center; gap: 8px; margin-top: 14px; color: var(--text-secondary); }
.note-controls button { width: var(--touch-target); min-height: var(--touch-target); border: 1px solid var(--forecast-rule); border-radius: 50%; color: var(--text); font-size: 19px; }
.note-controls button:hover { background: var(--forecast-inset); border-color: var(--forecast-accent); }
@media (max-width: 600px) {
  .method-accordion { display: grid; min-height: 0; }
  .method-accordion article { display: block; }
  .method-accordion button { writing-mode: horizontal-tb; text-align: start; letter-spacing: 0; }
  .method-accordion p { padding: 0 12px 14px; }
  .method-reading { grid-template-columns: 1fr; }
  .method-deck { min-height: 126px; }
}
@media (prefers-reduced-motion: reduce) {
  .method-accordion article { transition: none; }
}
</style>
