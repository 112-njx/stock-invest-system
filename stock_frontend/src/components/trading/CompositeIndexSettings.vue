<script setup lang="ts">
import { ref, computed, onBeforeUnmount } from 'vue'
import { searchSymbols, type SymbolInfo } from '@/api/market'
import type { IndicatorValues, IndexMember } from '@/composables/useIndicatorCatalog'
const props=defineProps<{values:IndicatorValues;saving:boolean}>()
const emit=defineEmits<{save:[values:IndicatorValues];close:[]}>()
const members=ref<IndexMember[]>(Array.isArray(props.values.members) ? (props.values.members as IndexMember[]).map(m=>({code:m.code,weight:Number(m.weight ?? 1)})) : [])
const weighting=ref(props.values.weighting==='custom'?'custom':'equal')
const base=ref(Number(props.values.base ?? 1000))
const start=ref(String(props.values.start ?? '2020-01-01'))
const query=ref(''),results=ref<SymbolInfo[]>([]),error=ref(''),searching=ref(false)
let generation=0
onBeforeUnmount(()=>generation++)
async function search() {
  const token=++generation
  if(!query.value.trim()){results.value=[];searching.value=false;return}
  searching.value=true;error.value=''
  try {
    const value=await searchSymbols(query.value.trim(),{type:'stock',limit:20})
    if(token===generation) results.value=value.filter(s=>/^\d{6}$/.test(s.code))
  }catch{if(token===generation)error.value='股票搜索失败，请重试'}
  finally{if(token===generation)searching.value=false}
}
function add(stock:SymbolInfo){if(members.value.length<20&&!members.value.some(m=>m.code===stock.code))members.value.push({code:stock.code,weight:1})}
const sum=computed(()=>members.value.reduce((n,m)=>n+Number(m.weight),0))
const today=new Date().toLocaleDateString('en-CA')
const valid=computed(()=>members.value.length>0&&members.value.length<=20&&new Set(members.value.map(m=>m.code)).size===members.value.length&&members.value.every(m=>/^\d{6}$/.test(m.code)&&Number.isFinite(m.weight)&&m.weight>=0&&m.weight<=1000000)&&(weighting.value==='equal'||sum.value>0)&&Number.isFinite(base.value)&&base.value>0&&base.value<=1e9&&/^\d{4}-\d{2}-\d{2}$/.test(start.value)&&start.value>='1990-01-01'&&start.value<=today)
function reset(){weighting.value='equal';base.value=1000;start.value='2020-01-01';members.value=members.value.map(m=>({...m,weight:1}))}
function save(){if(valid.value)emit('save',{members:members.value.map(m=>({...m})),weighting:weighting.value,base:base.value,start:start.value})}
</script>
<template>
  <form class="composite-settings" aria-label="合成指数设置" @submit.prevent="save">
    <b>ZHISHU 合成指数</b>
    <p>独立股票集合，占一个副图名额；结果由本地 SDK 计算。</p>
    <div><input v-model="query" aria-label="搜索合成指数股票" placeholder="股票名称或代码" :disabled="saving" @input="search" /><button type="button" :disabled="searching||saving" @click="search">搜索</button></div>
    <p v-if="error" role="alert">{{ error }}</p>
    <div class="search-results"><button v-for="stock in results" :key="stock.code" type="button" :disabled="saving||members.length>=20||members.some(m=>m.code===stock.code)" @click="add(stock)">{{ stock.name }} {{ stock.code }} 添加</button></div>
    <label>权重方式 <select v-model="weighting" aria-label="合成指数权重方式" :disabled="saving"><option value="equal">等权</option><option value="custom">自定义固定权重</option></select></label>
    <p>已选 {{ members.length }}/20。自定义权重按比例使用，0 表示不参与；起算后按固定权重合成收益。</p>
    <div v-for="(member,index) in members" :key="member.code" class="member-row"><span>{{ member.code }}</span><input v-model.number="member.weight" type="number" min="0" max="1000000" step="any" :aria-label="`${member.code} 权重`" :disabled="saving||weighting==='equal'" /><span>{{ weighting==='equal' ? (100/members.length).toFixed(2) : (sum>0?100*member.weight/sum:0).toFixed(2) }}%</span><button type="button" :disabled="saving" :aria-label="`移除 ${member.code}`" @click="members.splice(index,1)">移除</button></div>
    <label>指数基点 <input v-model.number="base" type="number" min="0.000001" max="1000000000" step="any" aria-label="指数基点" :disabled="saving" /></label>
    <label>起算日期 <input v-model="start" type="date" min="1990-01-01" :max="today" aria-label="指数起算日期" :disabled="saving" /></label>
    <p>按当前 K 线周期计算。上市日期、停牌和缺少历史时的参与股票数沿用 SDK 结果；不补零、不拼接远程行情。</p>
    <button type="button" :disabled="saving" @click="reset">恢复合成指数默认设置</button>
    <button :disabled="saving||!valid">保存合成指数</button><button type="button" :disabled="saving" @click="emit('close')">取消</button>
  </form>
</template>
<style scoped>
.composite-settings { display:flex; flex-direction:column; gap:8px; border:1px solid var(--border); padding:10px; }
.member-row { display:flex; gap:6px; align-items:center; }.member-row input { width:80px; }
.search-results { max-height:150px; overflow:auto; display:flex; flex-direction:column; }
input,select { background:var(--bg-panel);color:var(--text);border:1px solid var(--border); }
p { font-size:12px;color:var(--text-secondary);margin:0; }
</style>
