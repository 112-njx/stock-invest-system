import { ref, watch, onScopeDispose } from 'vue'
import { request } from '@/api/http'
export interface IndicatorParameter { key: string; label: string; type: 'integer' | 'integer_list' | 'number'; default: number | number[]; min: number; max: number; max_items?: number; exclusive_min?: boolean }
export interface IndicatorSeries { field: string; label: string; color: string; kind: 'line' | 'histogram'; direction: 'sign' | 'candle' }
export interface IndexMember { code: string; weight: number }
export type IndicatorValues = Record<string, number | number[] | string | boolean | IndexMember[]>
export interface IndicatorDefinition { key: string; label: string; placement: 'main' | 'panel'; parameters: IndicatorParameter[]; series: IndicatorSeries[]; reference_lines: number[]; format?: 'volume'; precision?: number; engines: string[]; input_fields?: string[]; cross?: boolean; constraints?: {left:string;op:'le';right:string}[] }
export function useIndicatorCatalog(enabled: () => boolean) {
  const definitions = ref<IndicatorDefinition[]>([])
  const error = ref('')
  let generation = 0
  async function load() {
    const token = ++generation
    if (!enabled()) return
    try {
      const data = await request<{version: number; indicators: IndicatorDefinition[]}>({url:'/indicators/catalog', silent:true})
      if (token !== generation) return
      if (!Array.isArray(data.indicators)) throw Error('Invalid catalog')
      definitions.value = data.indicators
      error.value = ''
    } catch { if (token === generation) error.value = '指标目录加载失败，请重试' }
  }
  watch(enabled, load, {immediate:true})
  onScopeDispose(() => { generation++ })
  return { definitions, error, load }
}
