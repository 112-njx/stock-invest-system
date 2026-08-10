import { fetchSymbols, fetchWatchlist } from '@/api/market'
import { useMarketStore } from '@/stores/market'

/**
 * 无当前标的时兜底选标的（第一层/第二层共用）：
 * 优先级：关注列表第一项 → 固定大盘指数第一项（上证指数）。
 * 若固定指数未加载则顺带拉取并写入 store（供 G/H 区复用）。
 */
export async function ensureDefaultSymbol() {
  const market = useMarketStore()
  if (market.current) return
  // E/D 区 WatchlistPanel 已加载过则直接复用，避免重复请求
  if (market.watchlist.length) {
    const w = market.watchlist[0]
    market.setCurrent({ id: w.symbol_id, code: w.code, name: w.name, type: w.type })
    return
  }
  try {
    const wl = await fetchWatchlist()
    if (wl.length) {
      market.setWatchlist(wl)
      const w = wl[0]
      market.setCurrent({ id: w.symbol_id, code: w.code, name: w.name, type: w.type })
      return
    }
  } catch {
    /* 继续走指数兜底 */
  }
  if (!market.fixedIndices.length) {
    try {
      market.setFixedIndices(await fetchSymbols({ type: 'index', is_fixed: 1 }))
    } catch {
      /* 静默：页面显示未选择标的 */
    }
  }
  if (market.fixedIndices.length) market.setCurrent(market.fixedIndices[0])
}
