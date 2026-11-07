import type { IndicatorValues } from '@/composables/useIndicatorCatalog'
import { ref } from 'vue'
import type { fetchIndicators, IndicatorRow } from '@/api/market'

/** Independent results: an unavailable SDK MA must not erase pandas panels. */
export function useChartIndicators(fetch: typeof fetchIndicators) {
  const priceMaRows = ref<IndicatorRow[]>([])
  const indicatorRows = ref<IndicatorRow[]>([])
  const priceMaError = ref('')
  const indicatorError = ref('')
  const panelErrors = ref<Record<string,string>>({})
  const panelRetrying = ref<Record<string, boolean>>({})
  let activeRetry: ((key: string) => Promise<void>) | null = null
  let generation = 0

  function reset() {
    generation++
    activeRetry = null
    panelRetrying.value = {}
    priceMaRows.value = []
    indicatorRows.value = []
    priceMaError.value = indicatorError.value = ''
    panelErrors.value = {}
  }

  async function load(
    params: Omit<Parameters<typeof fetchIndicators>[0], 'names'>,
    panels: boolean,
    isCurrent: () => boolean,
    options?: { periods: number[]; panels: string[]; parameters?: Record<string, {params: IndicatorValues}> },
  ) {
    const request = ++generation
    activeRetry = null
    panelRetrying.value = {}
    const current = () => request === generation && isCurrent()
    const ma = fetch({ ...params, names: 'ma', ...(options ? { params: JSON.stringify({ ma: { periods: options.periods } }) } : {}) }).then(rows => {
      if (!current()) return
      priceMaRows.value = rows
      priceMaError.value = ''
    }).catch(() => {
      if (!current()) return
      priceMaRows.value = []
      priceMaError.value = '主图价格均线获取失败，请检查 SDK 服务'
    })
    const results: Record<string, IndicatorRow[]> = {}
    if (options) { indicatorRows.value = []; panelErrors.value = {}; indicatorError.value = '' }
    const publish = () => {
      const byTime = new Map<string, IndicatorRow>()
      for (const key of options?.panels || []) for (const row of results[key] || []) byTime.set(row.ts, {...byTime.get(row.ts), ...row})
      indicatorRows.value = [...byTime.values()].sort((a,b) => a.ts.localeCompare(b.ts))
    }
    const panelRequests: Record<string, number> = {}
    const loadPanel = async (key: string) => {
      if (!current() || !panels || !options?.panels.includes(key) || panelRetrying.value[key]) return
      const token = (panelRequests[key] || 0) + 1
      panelRequests[key] = token
      const panelCurrent = () => current() && panelRequests[key] === token
      panelRetrying.value[key] = true
      try {
        const rows = await fetch({...params, names:key, params:JSON.stringify({[key]:options.parameters?.[key]?.params || {}})})
        if (!panelCurrent()) return
        results[key] = rows
        delete panelErrors.value[key]
        publish()
      } catch {
        if (!panelCurrent()) return
        panelErrors.value[key] = '获取失败，请重试'
        delete results[key]
        publish()
      } finally {
        if (panelCurrent()) panelRetrying.value[key] = false
      }
    }
    if (panels && options) activeRetry = loadPanel
    const indicators = panels && options ? Promise.all(options.panels.map(loadPanel)) : panels ? fetch({ ...params, names: 'macd,kdj,volume,amount' }).then(rows => {
      if (!current()) return
      indicatorRows.value = rows
      indicatorError.value = ''
    }).catch(() => {
      if (!current()) return
      indicatorRows.value = []
      indicatorError.value = '附图指标获取失败，请检查指标计算设置或服务'
    }) : Promise.resolve()
    if (!panels) {
      indicatorRows.value = []
      indicatorError.value = ''
    }
    // Each branch publishes as soon as it settles; a slow MA never delays panels.
    await Promise.all([ma, indicators])
  }

  async function retryPanel(key: string) { await activeRetry?.(key) }
  return { priceMaRows, indicatorRows, priceMaError, indicatorError, panelErrors, panelRetrying, retryPanel, load, reset }
}
