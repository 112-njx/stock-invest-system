<script setup lang="ts">
import { type AdminConsole } from '@/composables/useAdminConsole'
import AdminNotice from './AdminNotice.vue'
const props = defineProps<{ controller: AdminConsole }>()
const s = props.controller.state
</script>
<template>
  <section class="admin-card">
    <div class="card-title">
      <div>
        <h2>合成指数影线</h2>
        <p>行情页行业指数与指数蓝图共用的显示设置</p>
      </div>
      <span v-if="s.dirty.display" class="badge warning">有未保存修改</span>
    </div>
    <AdminNotice :resource="s.display" />
    <div class="notice">
      仅改变图形及图上的高低值，不改变原始行情、技术指标或策略计算。默认系数为 0.5。
    </div>
    <form @submit.prevent="controller.save('display')">
      <fieldset :disabled="!s.display.data || s.saving.display">
        <label class="factor-label"
          >影线系数<input
            v-model.number="s.displayForm.synthetic_wick_factor"
            aria-label="影线系数"
            type="number"
            min="0"
            max="1"
            step="0.05"
            required
            @input="controller.edit('display')"
        /></label>
        <div class="scale">
          <span>0 · 隐藏影线</span><span>0.5 · 默认</span><span>1 · 原始影线</span>
        </div>
      </fieldset>
      <div class="form-actions">
        <button class="primary" :disabled="!s.display.data || s.saving.display || !s.dirty.display">
          {{ s.saving.display ? '保存中…' : '保存显示设置' }}</button
        ><span class="success" role="status">{{ s.feedback.display }}</span
        ><span class="danger" role="alert">{{ s.saveError.display }}</span>
      </div>
    </form>
  </section>
</template>
