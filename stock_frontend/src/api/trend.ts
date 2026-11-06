import type { Bar } from './stockdb'

export interface TrendCell {
  wave: number
  change: number
  signals: string
  preClose: number
}
export interface TrendStock {
  code: string
  name: string
  wave: number
  return: number | null
}
export interface TrendColumn extends TrendStock {
  industry: string
  cells: (TrendCell | null)[]
  dif: number
  dea: number
  macd: number
  cross: boolean
  baseDate: number | null
  quoteDate: number
}
export interface TrendOverview {
  version: string
  dates: number[]
  breadth: number[]
  industry: string
  industries: { id: string; name: string; count: number }[]
  stocks: TrendStock[]
  average: number | null
  crossCount: number
}
export interface TrendScreen {
  overview: TrendOverview
  start: number
  columns: Record<string, TrendColumn>
}
export interface TrendHover {
  code: string
  name: string
  date: number
  baseline: number
  bars: Bar[]
  x: number
  y: number
}
