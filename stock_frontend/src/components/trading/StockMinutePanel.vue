<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { fetchStockDb } from '@/api/stockdbCache'
import type { Bar } from '@/api/stockdb'
import StockDbChart from '@/components/stockdb/StockDbChart.vue'
const props = defineProps<{code: string}>()
const data = ref<{date:number|null;bars:Bar[];previous:number|null}|null>(null)
const busy=ref(false), failed=ref(false)
let sequence=0
async function load(){
  const id=++sequence
  data.value=null; busy.value=true; failed.value=false
  try {
    const result=await fetchStockDb<{date:number|null;bars:Bar[];previous:number|null}>(`/stocks/${props.code}/minutes/latest`)
    if(id===sequence) data.value=result
  } catch {if(id===sequence) failed.value=true}
  finally {if(id===sequence) busy.value=false}
}
watch(()=>props.code,load,{immediate:true})
onBeforeUnmount(()=>sequence++)
</script>
<template>
  <section class="minute-panel">
    <header><strong>分时行情</strong><small>分时日期 {{ data?.date ?? '—' }}</small></header>
    <p v-if="busy">正在读取分时数据…</p>
    <p v-else-if="failed">分时数据暂不可用 <button @click="load">重试</button></p>
    <StockDbChart v-else-if="data?.bars.length" :bars="data.bars" :baseline="data.previous ?? undefined" minute :label="`${code}最新交易日分时价格与成交量（股）`" />
    <p v-else>暂无分时数据</p>
  </section>
</template>
<style scoped>
.minute-panel{--blueprint-candle-up:var(--quote-up);--blueprint-candle-down:var(--quote-down);--blueprint-up:var(--quote-up);--blueprint-down:var(--quote-down);--blueprint-link:var(--accent);display:flex;flex-direction:column;min-height:220px;min-width:0;background:var(--bg-panel);border:1px solid var(--border);border-radius:6px;overflow:hidden}
header{display:flex;align-items:center;justify-content:space-between;padding:6px 10px;gap:8px;font-size:12px;border-bottom:1px solid var(--border)}small,p{color:var(--text-secondary)}p{margin:auto;font-size:12px}button{color:var(--accent)}.minute-panel :deep(.chart){flex:1;min-height:0;height:auto}
</style>
