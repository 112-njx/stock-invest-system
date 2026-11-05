export const categories = [
  ['sw1', '申万一级'], ['sw2', '申万二级'], ['sw3', '申万三级'], ['concept', '概念'], ['custom', '我的指数'],
] as const
export const algorithms = [
  ['equal', '等权指数'], ['float_mv', '流通市值'], ['amount', '成交额'], ['volume', '成交量'], ['total_mv', '总市值'],
] as const

export type Category = typeof categories[number][0]
export type Weight = typeof algorithms[number][0]
export type Bar = [date: number, open: number, high: number, low: number, close: number,
  volume: number, amount: number, previous: number]
export interface Board { id: string; name: string; count: number; price: number | null; changes: Record<string, number | null> }
export interface Member { code: string; name: string; bar: Bar }
export interface Members {
  members: Member[]
  count: number
  stockCode: string
  stockBars: Bar[]
}
export interface BoardDetail { version: string; members: Member[]; count: number; indices: Record<Weight, Bar[]> }
export interface Workspace {
  version: string
  date: number
  category: Category
  weight: Weight
  boards: Board[]
  charts: Record<string, Bar[]>
  boardId: string
  pinnedBoard?: boolean
  detail: Members
}
export interface Home extends Omit<Workspace, 'category' | 'weight'> {}
export interface Ranking { version: string; date: number; boards: Board[] }

export function percent(value: number) {
  return (value > 0 ? '+' : '') + value.toFixed(2) + '%'
}

export function barReturn(bars: Bar[], days: number) {
  const latest = bars.at(-1)
  const previous = bars.at(-days - 1)?.[4] ?? (days === 1 ? latest?.[7] : 0)
  return latest && previous ? (latest[4] / previous - 1) * 100 : null
}
