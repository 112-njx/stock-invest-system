import { ref } from 'vue'
import type { fetchIndicators, IndicatorRow } from '@/api/market'

/** Independent results: an unavailable SDK MA must not erase pandas panels. */
export function useChartIndicators(fetch: typeof fetchIndicators) {
  const priceMaRows = ref<IndicatorRow[]>([])
  const indicatorRows = ref<IndicatorRow[]>([])
  const priceMaError = ref('')
  const indicatorError = ref('')
  let generation = 0

  function reset() {
    generation++
    priceMaRows.value = []
    indicatorRows.value = []
    priceMaError.value = indicatorError.value = ''
  }

  async function load(
    params: Omit<Parameters<typeof fetchIndicators>[0], 'names'>,
    panels: boolean,
    isCurrent: () => boolean,
  ) {
    const request = ++generation
    const current = () => request === generation && isCurrent()
    const ma = fetch({ ...params, names: 'ma' }).then(rows => {
      if (!current()) return
      priceMaRows.value = rows
      priceMaError.value = ''
    }).catch(() => {
      if (!current()) return
      priceMaRows.value = []
      priceMaError.value = '主图价格均线获取失败，请检查 SDK 服务'
    })
    const indicators = panels ? fetch({ ...params, names: 'macd,kdj,volume,amount' }).then(rows => {
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

  return { priceMaRows, indicatorRows, priceMaError, indicatorError, load, reset }
}
