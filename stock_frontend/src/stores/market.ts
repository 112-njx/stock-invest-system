import { defineStore } from 'pinia'
import type { Snapshot, SymbolInfo } from '@/api/market'

export type Period = '15m' | '1d' | '1w' | '1mon'

/** 行情状态：当前选中标的 + 快照缓存（E/D 区共用数据源） */
export const useMarketStore = defineStore('market', {
  state: () => ({
    current: null as SymbolInfo | null,
    period: '1d' as Period,
    /** symbol_id -> Snapshot 快照缓存 */
    snapshots: {} as Record<number, Snapshot>,
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
  },
})
