/** 红涨绿跌语义色工具 */
export type Trend = 'up' | 'down' | 'flat'

export function trendOf(value?: number | null): Trend {
  if (value == null || Number.isNaN(value) || value === 0) return 'flat'
  return value > 0 ? 'up' : 'down'
}

/** 返回语义色 CSS 类名（t-up / t-down / t-flat） */
export function trendClass(value?: number | null): string {
  return `t-${trendOf(value)}`
}

/** 带符号百分比，如 +0.71% / -1.20% */
export function formatPct(value?: number | null, digits = 2): string {
  if (value == null || Number.isNaN(value)) return '--'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(digits)}%`
}

/** 价格格式化 */
export function formatPrice(value?: number | null, digits = 2): string {
  if (value == null || Number.isNaN(value)) return '--'
  return value.toFixed(digits)
}

/** 成交量/成交额缩写：亿/万 */
export function formatAmount(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '--'
  const abs = Math.abs(value)
  if (abs >= 1e8) return `${(value / 1e8).toFixed(2)}亿`
  if (abs >= 1e4) return `${(value / 1e4).toFixed(2)}万`
  return String(Math.round(value))
}
