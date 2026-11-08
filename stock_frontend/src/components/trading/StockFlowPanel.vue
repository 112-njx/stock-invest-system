<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { request } from '@/api/http'
const props=defineProps<{code:string;name:string}>()
type FlowRow={date:number;main_net:number|null;jumbo_net:number|null;big_net:number|null;mid_net:number|null;small_net:number|null}
type Payload={coverage:{start:string;end:string}|null;latest:FlowRow|null;totals:Record<string,number|null>;rows:FlowRow[];start:string|null;end:string|null}
const data=ref<Payload>(),start=ref(''),end=ref(''),busy=ref(false),error=ref(''),page=ref(1)
let controller:AbortController|undefined,sequence=0
const fields=[['main_net','主力净流入'],['jumbo_net','超大单净流入'],['big_net','大单净流入'],['mid_net','中单净流入'],['small_net','小单净流入']] as const
const formatDate=(v:string|number)=>String(v).replace(/(\d{4})(\d{2})(\d{2})/,'$1-$2-$3')
function money(v:number|null|undefined){if(v==null)return '暂无数据';return (v>0?'+':'')+(Math.abs(v)>=1e8?(v/1e8).toFixed(2)+'亿':Math.abs(v)>=1e4?(v/1e4).toFixed(2)+'万':v.toLocaleString('zh-CN',{maximumFractionDigits:2}))}
const ordered=computed(()=>[...(data.value?.rows??[])].reverse())
const pages=computed(()=>Math.max(1,Math.ceil(ordered.value.length/50)))
const visible=computed(()=>ordered.value.slice((page.value-1)*50,page.value*50))
const bars=computed(()=>data.value?.rows.slice(-60)??[])
const scale=computed(()=>Math.max(1,...bars.value.map(r=>Math.abs(r.main_net??0))))
const step=computed(()=>900/Math.max(1,bars.value.length))
const fill=(v:number|null)=>v==null?'var(--text-muted)':v>0?'var(--up)':v<0?'var(--down)':'var(--text-secondary)'
async function load(defaultRange=false){
 controller?.abort();const seq=++sequence;controller=new AbortController();busy.value=true;error.value=''
 try{
  if(!defaultRange&&(!start.value||!end.value||start.value>end.value))throw new Error('请选择有效的起止日期')
  const payload=await request<Payload>({url:`/stockdb/stocks/${props.code}/flows`,params:defaultRange?{}:{start:start.value,end:end.value},signal:controller.signal,silent:true,timeout:60000})
  if(seq!==sequence)return
  data.value=payload;start.value=payload.start??'';end.value=payload.end??'';page.value=1
 }catch(e){if(seq===sequence&&!controller?.signal.aborted)error.value=e instanceof Error?e.message:'资金流读取失败'}
 finally{if(seq===sequence)busy.value=false}
}
watch(()=>props.code,()=>{data.value=undefined;start.value='';end.value='';page.value=1;void load(true)},{immediate:true})
onBeforeUnmount(()=>{sequence++;controller?.abort()})
</script>
<template>
<section class="flow-panel" aria-label="个股资金流向">
 <header><strong>{{ name }} {{ code }} · 资金流向</strong><span>资金流日期：{{ data?.latest?formatDate(data.latest.date):'暂无数据' }}</span><button :disabled="busy" @click="load(true)">最近交易日</button></header>
 <p class="coverage">本股本地覆盖：{{ data?.coverage?`${formatDate(data.coverage.start)} ～ ${formatDate(data.coverage.end)}`:'暂无数据' }} · 金额单位：元（万／亿缩写），日期独立于行情</p>
 <p v-if="busy" role="status">正在读取资金流数据…</p><p v-if="error" class="error" role="alert">{{ error }} <button @click="load(!data)">重试</button></p>
 <div v-if="data" class="overview"><div v-for="[field,label] in fields" :key="field"><span>{{ label }}</span><b :style="{color:fill(data.latest?.[field]??null)}">{{ money(data.latest?.[field]) }}</b></div><div v-for="n in [5,10,20]" :key="n"><span>{{ n }}日累计主力净流入</span><b :style="{color:fill(data.totals[String(n)]??null)}">{{ money(data.totals[String(n)]) }}</b></div></div>
 <form class="range" @submit.prevent="load()"><label>开始 <input v-model="start" type="date" aria-label="资金流开始日期" required/></label><label>结束 <input v-model="end" type="date" aria-label="资金流结束日期" required/></label><button :disabled="busy">查询</button><span>单次最多366天；缺失日期不补零</span></form>
 <template v-if="data">
 <div class="chart"><div>主力净流入 · 所选区间最近 {{ bars.length }} 个交易日（悬浮查看）</div>
 <svg v-if="bars.length" viewBox="0 0 1000 235" role="img" aria-label="主力资金净流入柱状图"><line x1="55" x2="955" y1="110" y2="110" stroke="var(--border-strong)"/><text x="0" y="24">{{ money(scale) }}</text><text x="0" y="113">0</text><text x="0" y="204">{{ money(-scale) }}</text>
 <g v-for="(r,i) in bars" :key="r.date"><rect v-if="r.main_net!==null" :x="55+i*step+1" :y="r.main_net>0?110-r.main_net/scale*85:110" :width="Math.max(1,step-2)" :height="Math.max(1,Math.abs(r.main_net)/scale*85)" :fill="fill(r.main_net)"><title>{{ formatDate(r.date) }}：{{ money(r.main_net) }}</title></rect><circle v-else :cx="55+(i+.5)*step" cy="110" r="2" fill="none" stroke="var(--text-muted)"><title>{{ formatDate(r.date) }}：暂无数据</title></circle></g>
 <text x="55" y="228">{{ formatDate(bars[0]!.date) }}</text><text x="955" y="228" text-anchor="end">{{ formatDate(bars[bars.length-1]!.date) }}</text></svg><p v-else>所选日期范围暂无数据</p></div>
 <div class="history-head"><strong>历史明细</strong><span>{{ ordered.length }} 个交易日</span><button :disabled="page<=1" @click="page--">上一页</button><span>{{ page }} / {{ pages }}</span><button :disabled="page>=pages" @click="page++">下一页</button></div>
 <div class="history"><table><thead><tr><th>资金流日期</th><th v-for="[field,label] in fields" :key="field">{{ label }}</th></tr></thead><tbody><tr v-for="r in visible" :key="r.date"><td>{{ formatDate(r.date) }}</td><td v-for="[field] in fields" :key="field" :style="{color:fill(r[field])}">{{ money(r[field]) }}</td></tr></tbody></table><p v-if="!visible.length">暂无数据</p></div>
 </template>
</section>
</template>
<style scoped>
.flow-panel{flex:1;min-height:0;overflow:auto;background:var(--bg-panel);border:1px solid var(--border);padding:12px;color:var(--text);font-size:13px;display:flex;flex-direction:column;gap:10px}header,.range,.history-head{display:flex;align-items:center;flex-wrap:wrap;gap:10px}header span,.coverage,.range span,.history-head span{color:var(--text-secondary)}header button{margin-left:auto}p{margin:0;line-height:1.6}button,input{font:inherit;background:var(--bg-panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:5px 8px}button{cursor:pointer}button:disabled{opacity:.5;cursor:default}.overview{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:8px}.overview>div{border:1px solid var(--border);padding:10px;display:flex;flex-direction:column;gap:6px}.overview span{font-size:12px;color:var(--text-secondary)}.overview b{font-size:16px}.chart{border:1px solid var(--border);padding:8px}.chart svg{width:100%;max-height:260px;display:block}.chart text{font-size:11px;fill:var(--text-secondary)}.history{overflow:auto;min-height:160px;flex:1}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;white-space:nowrap}th,td{text-align:right;padding:8px;border-bottom:1px solid var(--border)}th{position:sticky;top:0;background:var(--bg-panel);color:var(--text-secondary)}th:first-child,td:first-child{text-align:left}.error{color:var(--up)}@media(max-width:800px){.overview{grid-template-columns:repeat(2,minmax(100px,1fr))}}
</style>
