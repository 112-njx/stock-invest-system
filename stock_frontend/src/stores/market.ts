import { defineStore } from 'pinia'
import type { Snapshot, SymbolInfo, WatchlistItem } from '@/api/market'

export type Period = '15m' | '1d' | '1w' | '1mon'

//前端状态管理，当前对话的临时状态，存储在浏览器缓存。
/** 行情状态：当前选中标的 + 快照缓存 + 关注列表（D/E 区共用同一数据源） */
export const useMarketStore = defineStore('market', {
  state: () => ({
    current: null as SymbolInfo | null,
    period: '1d' as Period,
    /** symbol_id -> Snapshot 快照缓存 */
    snapshots: {} as Record<number, Snapshot>,
    /** 关注列表（watchlist API 返回，含记录 id 用于删除） */
    watchlist: [] as WatchlistItem[],
  }),
  actions: {
    setCurrent(symbol: SymbolInfo | null) {
      this.current = symbol
    },
    setPeriod(period: Period) {
      this.period = period
    },
    /** 合并批量快照到缓存 */
    mergeSnapshots(list: Snapshot[]) {
      for (const s of list) this.snapshots[s.symbol_id] = s
    },
    setWatchlist(list: WatchlistItem[]) {
      this.watchlist = list
    },
    /** 本地移除一条关注（接口删除成功后由组件调用） */
    removeWatchlistItem(id: number) {
      this.watchlist = this.watchlist.filter((w) => w.id !== id)
    },
    /** 本地追加一条关注（接口添加成功后由组件调用） */
    addWatchlistItem(item: WatchlistItem) {
      if (!this.watchlist.some((w) => w.symbol_id === item.symbol_id)) {
        this.watchlist.push(item)
      }
    },
  },
})
