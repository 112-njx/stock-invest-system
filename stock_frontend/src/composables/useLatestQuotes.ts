import { computed, onBeforeUnmount, watch } from 'vue'
import { fetchLatestQuotes } from '@/api/market'
import { useMarketStore } from '@/stores/market'

/** Source latest records: refresh on selection, page visibility and K-line events. */
export function useLatestQuotes() {
  const market = useMarketStore()
  const ids = computed(() => [...new Set([
    ...(market.current ? [market.current.id] : []),
    ...market.watchlist.map(item => item.symbol_id),
    ...market.fixedIndices.map(item => item.id),
  ])])
  let active = false
  async function refresh() {
    if (!active || !ids.value.length) return
    try { market.mergeQuotes(await fetchLatestQuotes(ids.value, true)) } catch { /* Retry on next user action. */ }
  }
  function visible() { if (document.visibilityState === 'visible') void refresh() }
  watch(ids, () => void refresh())
  function start() {
    if (active) return
    active = true
    document.addEventListener('visibilitychange', visible)
    return refresh()
  }
  onBeforeUnmount(() => { active = false; document.removeEventListener('visibilitychange', visible) })
  return { start }
}
