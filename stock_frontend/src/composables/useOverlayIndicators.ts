import { ref, shallowRef } from 'vue'
import type { fetchIndicators, IndicatorRow } from '@/api/market'
export function useOverlayIndicators(fetch: typeof fetchIndicators) {
  const rows = shallowRef<Record<string,IndicatorRow[]>>({})
  const errors = ref<Record<string,string>>({})
  const retrying = ref<Record<string,boolean>>({})
  let generation=0
  let activeRetry: ((key:string)=>Promise<void>) | null=null
  function reset() { generation++; activeRetry=null; rows.value={}; errors.value={}; retrying.value={} }
  async function load(params: Omit<Parameters<typeof fetchIndicators>[0],'names'>, keys:string[], options:Record<string,{params:Record<string,number | number[]>}>, isCurrent:()=>boolean) {
    reset()
    const token=generation
    const current=()=>token===generation && isCurrent()
    async function request(key:string) {
      if(!current() || !keys.includes(key) || retrying.value[key]) return
      retrying.value[key]=true
      try {
        const result=await fetch({...params,names:key,params:JSON.stringify({[key]:options[key]?.params || {}})})
        if(!current()) return
        rows.value={...rows.value,[key]:result}
        delete errors.value[key]
      } catch {
        if(!current()) return
        errors.value[key]='获取失败，请重试'
        const next={...rows.value};delete next[key];rows.value=next
      } finally { if(current()) retrying.value[key]=false }
    }
    activeRetry=request
    // Avoid submitting every main overlay to the single native worker at once.
    for(const key of keys) { if(!current()) return; await request(key) }
  }
  async function retry(key:string) { await activeRetry?.(key) }
  return {rows,errors,retrying,load,retry,reset}
}
