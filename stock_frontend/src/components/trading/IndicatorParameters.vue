<script setup lang="ts">
import { ref, computed } from 'vue'
import type { IndicatorDefinition, IndicatorValues } from '@/composables/useIndicatorCatalog'
const props = defineProps<{definition:IndicatorDefinition; values:IndicatorValues; saving:boolean}>()
const emit = defineEmits<{save:[values:IndicatorValues]; close:[]}>()
const field = ref(typeof props.values.field === 'string' ? props.values.field : 'close')
const cross = ref(props.values.cross === true)
const fieldLabels:Record<string,string>={close:'收盘价',open:'开盘价',high:'最高价',low:'最低价',volume:'成交量',amount:'成交额'}
const defaults = () => Object.fromEntries(props.definition.parameters.map(p => [p.key, String(p.default)]))
const draft = ref({...defaults(),...Object.fromEntries(Object.entries(props.values).map(([key,value])=>[key,String(value)]))})
const values = computed(() => Object.fromEntries(props.definition.parameters.map(p => [p.key,p.type === 'integer_list' ? (draft.value[p.key] || '').split(',').map(Number) : Number(draft.value[p.key])])) as Record<string,number | number[]>)
const valid = computed(() => props.definition.parameters.every(p => {
  const value = values.value[p.key]
  const entries = Array.isArray(value) ? value : [value]
  return entries.length > 0 && entries.length <= (p.max_items || 1) && new Set(entries).size === entries.length && entries.every(n => typeof n === 'number' && (p.type === 'number' ? Number.isFinite(n) : Number.isInteger(n)) && (p.exclusive_min ? n > p.min : n >= p.min) && n <= p.max)
}) && (props.definition.constraints || []).every(c => c.op !== 'le' || Number(values.value[c.left]) <= Number(values.value[c.right])))
function save() { if(valid.value) emit('save',{...values.value,...(props.definition.input_fields && field.value!=='close' ? {field:field.value} : {}),...(props.definition.cross && cross.value ? {cross:true} : {})}) }
function reset() { draft.value=defaults();field.value='close';cross.value=false }
</script>
<template>
  <form class="indicator-parameters" @submit.prevent="save">
    <b>{{ definition.label }} 参数</b>
    <label v-for="param in definition.parameters" :key="param.key">{{ param.label }} <input v-model="draft[param.key]" :type="param.type === 'integer_list' ? 'text' : 'number'" :min="param.min" :max="param.max" :step="param.type === 'number' ? 'any' : '1'" required :disabled="saving" :aria-label="`${definition.label} ${param.label}`" /></label>
    <p v-if="!valid" role="alert">请输入类型及范围正确的参数；权重不可大于周期。</p>
    <label v-if="definition.input_fields">计算字段 <select v-model="field" :disabled="saving" :aria-label="`${definition.label} 计算字段`"><option v-for="f in definition.input_fields" :key="f" :value="f">{{ fieldLabels[f] || f }}</option></select></label>
    <label v-if="definition.cross"><input v-model="cross" type="checkbox" :disabled="saving" :aria-label="`${definition.label} 金叉死叉标记`" />金叉死叉标记（SDK）</label>
    <button type="button" :disabled="saving" @click="reset">恢复默认参数</button>
    <button :disabled="saving || !valid">保存参数</button>
    <button type="button" :disabled="saving" @click="emit('close')">取消</button>
  </form>
</template>
<style scoped>
.indicator-parameters { padding:12px; border:1px solid var(--border); display:flex; flex-wrap:wrap; gap:8px; }
input { width:70px; background:var(--bg-panel); color:var(--text); border:1px solid var(--border); }
</style>
