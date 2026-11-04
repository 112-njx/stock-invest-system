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
export interface Board { id: string; name: string; count: number; bars: Bar[] }
export interface Member { code: string; name: string; bar: Bar }
export interface BoardDetail { members: Member[]; count: number; indices: Record<Weight, Bar[]> }

export async function stockDbRequest<T>(path: string, signal: AbortSignal, codes?: string[]): Promise<T> {
  const response = await fetch('/api/v1/stockdb' + path, {
    signal,
    ...(codes ? {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ codes }),
    } : {}),
  })
  const body = await response.json()
  if (!response.ok) throw new Error(body.msg || body.detail || '读取本地 stockdb 失败')
  return body
}

export function percent(value: number) {
  return (value > 0 ? '+' : '') + value.toFixed(2) + '%'
}

export function barReturn(bars: Bar[], days: number) {
  const latest = bars.at(-1)
  const previous = bars.at(-days - 1)?.[4] ?? (days === 1 ? latest?.[7] : 0)
  return latest && previous ? (latest[4] / previous - 1) * 100 : null
}
