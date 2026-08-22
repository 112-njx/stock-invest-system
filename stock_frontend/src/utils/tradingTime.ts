/**
 * A 股交易时段判断（与后端 sync_service.is_market_open 逻辑一致）：
 * 工作日（周一~周五）9:30-11:30 / 13:00-15:00（UTC+8）。
 * 纯工具函数，无 UI 依赖。
 */

/** 判断给定时间（默认当前）是否处于 A 股交易时段 */
export function isMarketOpen(now: Date = new Date()): boolean {
  const utc8 = new Date(now.getTime() + (now.getTimezoneOffset() + 480) * 60000)
  const day = utc8.getUTCDay()
  if (day === 0 || day === 6) return false
  const hm = utc8.getUTCHours() * 100 + utc8.getUTCMinutes()
  return (930 <= hm && hm <= 1130) || (1300 <= hm && hm <= 1500)
}

export type FreshnessLevel = 'live' | 'stale' | 'closed' | 'unknown'

export interface FreshnessInfo {
  level: FreshnessLevel
  /** 展示文案，如 "14:35:22更新" / "收盘 15:00更新" / "数据延迟" / "--" */
  label: string
}

/**
 * 根据快照更新时间与 data_age_seconds 计算新鲜度展示信息。
 * - 交易时段：age<300s 绿色"HH:MM:SS更新"；>=300s 黄色"数据延迟"
 * - 非交易时段：灰色"收盘 HH:MM更新"
 * - 无 updated_at：unknown，展示 "--"
 */
export function getFreshness(
  updatedAt?: string | null,
  dataAgeSeconds?: number | null,
  now: Date = new Date(),
): FreshnessInfo {
  if (!updatedAt) return { level: 'unknown', label: '--' }
  const timeStr = formatTime(updatedAt)
  const open = isMarketOpen(now)
  const age = dataAgeSeconds ?? Math.max(0, (now.getTime() - new Date(updatedAt).getTime()) / 1000)
  if (open) {
    if (age < 300) return { level: 'live', label: `${timeStr}更新` }
    return { level: 'stale', label: '数据延迟' }
  }
  return { level: 'closed', label: `收盘 ${timeStr.slice(0, 5)}更新` }
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '--'
  const utc8 = new Date(d.getTime() + (d.getTimezoneOffset() + 480) * 60000)
  const hh = String(utc8.getUTCHours()).padStart(2, '0')
  const mm = String(utc8.getUTCMinutes()).padStart(2, '0')
  const ss = String(utc8.getUTCSeconds()).padStart(2, '0')
  return `${hh}:${mm}:${ss}`
}
