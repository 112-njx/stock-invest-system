import { barReturn, type Member } from '@/api/stockdb'

export const memberSortKeys = ['return', 'price', 'code', 'change', 'amount', 'turnover', 'float_mv'] as const
export type MemberSort = typeof memberSortKeys[number]
export function finite(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}
export function metric(stock: Member | undefined, key: 'volume' | 'amount' | 'turnover' | 'float_mv' | 'total_mv') {
  if (!stock) return null
  if (stock.metrics && key in stock.metrics) return finite(stock.metrics[key])
  return key === 'volume' ? finite(stock.bar[5]) : key === 'amount' ? finite(stock.bar[6]) : null
}
export function memberValue(stock: Member, key: Exclude<MemberSort, 'code'>): number | null {
  if (key === 'price') return finite(stock.bar[4])
  if (key === 'return') return finite(barReturn([stock.bar], 1))
  if (key === 'change') return stock.bar[7] > 0 ? finite(stock.bar[4] - stock.bar[7]) : null
  return metric(stock, key)
}
export function sortMembers(items: Member[], key: MemberSort, ascending: boolean) {
  return [...items].sort((a, b) => {
    if (key === 'code') return (ascending ? 1 : -1) * a.code.localeCompare(b.code)
    const left = memberValue(a, key), right = memberValue(b, key)
    if (left === null || right === null) return left === right ? a.code.localeCompare(b.code) : left === null ? 1 : -1
    return (ascending ? 1 : -1) * (left - right) || a.code.localeCompare(b.code)
  })
}
export function numberText(value: number | null | undefined, digits = 2) {
  return finite(value) === null ? '—' : value!.toFixed(digits)
}
export function compact(value: number | null | undefined) {
  if (finite(value) === null) return '—'
  return Math.abs(value!) >= 1e8 ? (value! / 1e8).toFixed(2) + '亿' : Math.abs(value!) >= 1e4 ? (value! / 1e4).toFixed(2) + '万' : value!.toFixed(0)
}
export function dateText(value: number | null | undefined) {
  return value ? String(value).replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3') : '—'
}
