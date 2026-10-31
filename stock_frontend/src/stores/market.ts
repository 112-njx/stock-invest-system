import { defineStore } from 'pinia'
import type { Snapshot, SymbolInfo, SyncStatus, WatchlistItem } from '@/api/market'
import { snapshotTime } from '@/utils/homeIndexCache'

export type Period = '15m' | '1d' | '1w' | '1mon'

//前端状态管理，当前对话的临时状态，存储在浏览器缓存。
/** 行情状态：当前选中标的 + 快照缓存 + 关注列表（D/E 区共用同一数据源）+ 固定指数列表（G/H 区） */
export const useMarketStore = defineStore('market', {
  state: () => ({
    current: null as SymbolInfo | null,
    period: '1d' as Period,
    /** symbol_id -> Snapshot 快照缓存 */
    snapshots: {} as Record<number, Snapshot>,
    /** 关注列表（watchlist API 返回，含记录 id 用于删除） */
    watchlist: [] as WatchlistItem[],
    /** 固定指数列表（GET /symbols?type=index&is_fixed=1，G/H 区共用，按 sort_order 前端分组） */
    fixedIndices: [] as SymbolInfo[],
    /** V0.2：固定指数预同步状态 */
    syncStatus: null as SyncStatus | null,
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
      for (const s of list) {
        const existing = this.snapshots[s.symbol_id]
        const incomingTime = s.updated_at ? snapshotTime(s.updated_at) : 0
        const existingTime = existing?.updated_at ? snapshotTime(existing.updated_at) : 0
        if (existing && incomingTime && existingTime) {
          const incomingDay = new Date(incomingTime).toISOString().slice(0, 10)
          const existingDay = new Date(existingTime).toISOString().slice(0, 10)
          if (incomingDay < existingDay) continue
          if (incomingDay === existingDay && existing.source === 'kline' && s.source !== 'kline') continue
          if (incomingDay === existingDay && s.source !== 'kline' && existing.source !== 'kline' && incomingTime < existingTime) continue
        }
        this.snapshots[s.symbol_id] = s
      }
    },
    setWatchlist(list: WatchlistItem[]) {
      this.watchlist = list
    },
    setFixedIndices(list: SymbolInfo[]) {
      this.fixedIndices = list
    },
    /** V0.2：更新固定指数预同步状态 */
    setSyncStatus(status: SyncStatus | null) {
      this.syncStatus = status
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
