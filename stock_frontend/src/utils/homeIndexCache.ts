import type { HomeIndex, Snapshot } from '@/api/market'

const KEY = 'stock_home_indices_v1'
const VERSION = 1

export function readHomeIndexCache(): HomeIndex[] {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) || 'null')
    if (value?.version !== VERSION || !Array.isArray(value.rows)) return []
    return value.rows.filter((row: HomeIndex) =>
      Number.isInteger(row?.id) && typeof row.name === 'string' && row.type === 'index' &&
      (row.snapshot === null || (row.snapshot && row.snapshot.symbol_id === row.id &&
        (row.snapshot.price === null || typeof row.snapshot.price === 'number'))),
    )
  } catch { return [] }
}

export function writeHomeIndexCache(rows: HomeIndex[], snapshots: Record<number, Snapshot>) {
  try {
    localStorage.setItem(KEY, JSON.stringify({
      version: VERSION,
      rows: rows.map((row) => ({ ...row, snapshot: snapshots[row.id] ?? row.snapshot })),
    }))
  } catch { /* 禁用或已满时不影响页面 */ }
}
