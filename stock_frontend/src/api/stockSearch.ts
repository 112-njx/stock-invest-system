import { request } from './http'

export interface SearchStock {
  code: string
  name: string
  type: 'stock'
  market: 'SSE' | 'SZSE' | 'BSE'
  latest_date: string
  ordinal: number
}

export interface StockDirectory {
  version: string
  source: 'stockdb'
  latest_session: string
  total: number
  candidate_count: number
  excluded: Array<{ code: string; reason: string }>
  items: SearchStock[]
  stale: boolean
}

export function fetchStockDirectory() {
  return request<StockDirectory>({ url: '/stocks/search-directory', silent: true, timeout: 60000 })
}
