<script setup lang="ts">
import { ref, computed } from 'vue'
import { validateMa, defaultChartSettings, type MaLine } from '@/composables/useDetailChartSettings'
const props = defineProps<{ lines: MaLine[]; saving: boolean; error: string }>()
const emit = defineEmits<{ save: [lines: MaLine[]]; close: [] }>()
const draft = ref(props.lines.map(line => ({ ...line })))
const valid = computed(() => validateMa(draft.value))
function add() {
  const period = [5,10,20,30,60,120,250,1,2,3,4,6].find(n => !draft.value.some(l => l.period === n))!
  draft.value.push({ period, visible: true })
}
</script>
<template>
  <Teleport to="body">
    <div class="modal-mask" @click.self="!saving && emit('close')">
      <form class="ma-settings" role="dialog" aria-label="MA设置" aria-modal="true" @submit.prevent="valid && emit('save', draft)">
        <header><b>MA 设置</b><button type="button" :disabled="saving" aria-label="关闭MA设置" @click="emit('close')">×</button></header>
        <p>按当前周期的K线根数计算，所有股票及周期共用。</p>
        <fieldset :disabled="saving">
          <div v-for="(line, index) in draft" :key="index" class="ma-row">
            <label><input v-model="line.visible" type="checkbox" /> 显示</label>
            <label>周期 <input v-model.number="line.period" :aria-label="`第${index + 1}条MA周期`" type="number" min="1" max="10000" step="1" required /></label>
            <button type="button" :disabled="draft.length <= 1" @click="draft.splice(index, 1)">删除</button>
          </div>
          <button type="button" :disabled="draft.length >= 6" @click="add">添加 MA（{{ draft.length }}/6）</button>
          <button type="button" @click="draft = defaultChartSettings().ma.lines">恢复默认</button>
        </fieldset>
        <p v-if="!valid" role="alert">请输入1～6个不重复的整数周期（1～10000）。</p>
        <p v-if="error" role="alert">{{ error }}</p>
        <footer><button type="button" :disabled="saving" @click="emit('close')">取消</button><button :disabled="!valid || saving">{{ saving ? '保存中…' : '保存' }}</button></footer>
      </form>
    </div>
  </Teleport>
</template>
<style scoped>
.modal-mask { position: fixed; inset: 0; background: #0008; display:flex; align-items:center; justify-content:center; z-index:1000; }
.ma-settings { padding:20px; background:var(--bg-panel); color:var(--text); border:1px solid var(--border); border-radius:8px; max-width:95vw; width:440px; }
header, footer, .ma-row { display:flex; align-items:center; justify-content:space-between; gap:10px; margin:10px 0; }
fieldset { border:0; padding:0; }
p { font-size:12px; color:var(--text-secondary); }
button { padding:5px 9px; cursor:pointer; border:1px solid var(--border); border-radius:4px; background:var(--bg-panel); color:var(--text); }
button:disabled { opacity:.45; cursor:default; }
input[type=number] { width:90px; padding:4px; color:var(--text); background:var(--bg-panel); border:1px solid var(--border); }
</style>
