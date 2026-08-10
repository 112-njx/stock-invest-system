import { request } from './http'

export type SymbolType = 'stock' | 'etf' | 'index'
export type Period = '15m' | '1d' | '1w' | '1mon'

export interface SymbolInfo {
  id: number
  code: string
  name: string
  type: SymbolType
  market?: string
  industry?: string
  etf_linked?: string
  is_fixed_index?: boolean
  sort_order?: number
}

export interface KLineBar {
  ts: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount: number
}

export interface Snapshot {
  symbol_id: number
  code: string
  name: string
  type: SymbolType
  price: number | null
  change: number | null
  change_pct: number | null
  open: number | null
  high: number | null
  low: number | null
  pre_close: number | null
  volume: number | null
  amount: number | null
  turnover: number | null
  amplitude: number | null
  updated_at?: string | null
  /** 特殊字段：个股 market_cap/pe、ETF nav/premium、指数 pe */
  extra: Record<string, unknown>
}

export interface WatchlistItem {
  id: number
  symbol_id: number
  code: string
  name: string
  type: SymbolType
  price: number | null
  change: number | null
  change_pct: number | null
  updated_at?: string | null
  created_at?: string | null
}

/** 技术指标行：K 线基础字段 + 请求的指标列（macd_dif/dea/hist、kdj_k/d/j；成交量成交额为基础字段） */
export interface IndicatorRow extends KLineBar {
  macd_dif?: number | null
  macd_dea?: number | null
  macd_hist?: number | null
  kdj_k?: number | null
  kdj_d?: number | null
  kdj_j?: number | null
}

export interface SupportResistanceItem {
  id: number
  symbol_id: number
  type: 'support' | 'pressure'
  price: number
  note?: string | null
  created_at: string
}

/** 标的列表（type/search/is_fixed 过滤，G/H 区与下拉框数据源） */
export function fetchSymbols(params?: { type?: SymbolType; search?: string; is_fixed?: 0 | 1 }) {
  return request<SymbolInfo[]>({ url: '/symbols', params })
}

/** 标的搜索联想（6 位代码/名称，已入库优先） */
export function searchSymbols(q: string) {
  return request<SymbolInfo[]>({ url: '/symbols/search', params: { q } })
}

/** 多周期 K 线（15m/1d/1w/1mon，时间 UTC） */
export function fetchKLine(params: {
  symbol: string | number
  period: Period
  start?: string
  end?: string
  limit?: number
}) {
  return request<KLineBar[]>({ url: '/kline', params })
}

/** 批量实时快照（symbols 为 symbol_id 或代码逗号分隔；silent 供轮询使用，失败不 toast） */
export function fetchSnapshot(symbols: Array<string | number>, silent = false) {
  return request<Snapshot[]>({ url: '/snapshot', params: { symbols: symbols.join(',') }, silent })
}

/** 关注列表（合并实时快照） */
export function fetchWatchlist() {
  return request<WatchlistItem[]>({ url: '/watchlist' })
}

/** 添加关注（symbol 为代码或 symbol_id） */
export function addWatchlist(symbol: string | number) {
  return request<WatchlistItem>({ url: '/watchlist', method: 'post', data: { symbol } })
}

/** 删除关注（按 watchlist 记录 id） */
export function removeWatchlist(watchlistId: number) {
  return request<null>({ url: `/watchlist/${watchlistId}`, method: 'delete' })
}

/** 技术指标（服务端计算 MACD/KDJ/成交量/成交额，前端只渲染） */
export function fetchIndicators(params: {
  symbol: string | number
  period: Period
  names?: string
  limit?: number
}) {
  return request<IndicatorRow[]>({ url: '/indicators', params })
}

/** 支撑/压力位列表（可按标的过滤） */
export function fetchSupportResistance(symbolId?: number) {
  return request<SupportResistanceItem[]>({
    url: '/support-resistance',
    params: symbolId ? { symbol_id: symbolId } : undefined,
    silent: true,
  })
}

/** 添加支撑/压力位（symbol 为代码或 symbol_id，type=support|pressure） */
export function addSupportResistance(payload: {
  symbol: string | number
  type: 'support' | 'pressure'
  price: number
  note?: string
}) {
  return request<SupportResistanceItem>({ url: '/support-resistance', method: 'post', data: payload })
}

/** 删除支撑/压力位（按记录 id） */
export function removeSupportResistance(srId: number) {
  return request<null>({ url: `/support-resistance/${srId}`, method: 'delete' })
}
