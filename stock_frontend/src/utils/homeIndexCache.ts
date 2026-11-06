import type { HomeIndex, LatestQuote } from '@/api/market'

const KEY = 'stock_home_indices_v3'
const VERSION = 3

/** 后端历史行情可能是无时区的 ISO 字符串；数据库约定它代表 UTC。 */
export function quoteTime(value: string): number {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).getTime()
}

export function readHomeIndexCache(): HomeIndex[] {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) || 'null')
    if (value?.version !== VERSION || !Array.isArray(value.rows)) return []
    return value.rows.filter((row: HomeIndex) =>
      Number.isInteger(row?.id) && typeof row.name === 'string' && row.type === 'index' &&
      (row.quote === null || (row.quote && row.quote.symbol_id === row.id &&
        (row.quote.price === null || typeof row.quote.price === 'number'))),
    )
  } catch { return [] }
}

export function writeHomeIndexCache(rows: HomeIndex[], quotes: Record<number, LatestQuote>) {
  try {
    localStorage.setItem(KEY, JSON.stringify({
      version: VERSION,
      rows: rows.map((row) => ({ ...row, quote: quotes[row.id] ?? row.quote })),
    }))
  } catch { /* 禁用或已满时不影响页面 */ }
}
