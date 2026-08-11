/**
 * 前端监控埋点（5.3）：
 * - 错误上报：window.onerror / unhandledrejection / Vue errorHandler
 * - 性能埋点：页面加载、路由切换、K 线加载耗时等（trackTiming）
 * - 上报通道：POST /api/v1/monitor/events 约定接口；后端缺失时 404 静默降级
 *   （事件保留在 localStorage 队列，接口就绪后自动补传；上限裁剪防溢出）
 * - 数据可查：dev 模式 console 输出摘要；localStorage key `stock_invest_monitor`
 */
import { reportEvents, type MonitorEvent } from '@/api/monitor'

const KEY = 'stock_invest_monitor'
const MAX = 100
const FLUSH_DELAY = 5000

function loadQueue(): MonitorEvent[] {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as MonitorEvent[]) : []
  } catch {
    return []
  }
}

function saveQueue(q: MonitorEvent[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(q.slice(-MAX)))
  } catch {
    /* 存储不可用则忽略 */
  }
}

let flushTimer: number | null = null
let flushing = false

/** 入队一条事件并安排定时上报 */
export function track(type: MonitorEvent['type'], name: string, meta?: Record<string, unknown>) {
  const ev: MonitorEvent = { ts: Date.now(), type, name, meta }
  const q = loadQueue()
  q.push(ev)
  saveQueue(q)
  if (import.meta.env.DEV) console.debug(`[monitor] ${type} ${name}`, meta ?? '')
  scheduleFlush()
}

/** 耗时埋点（durationMs 毫秒） */
export function trackTiming(name: string, durationMs: number, meta?: Record<string, unknown>) {
  track('performance', name, { duration_ms: Math.round(durationMs), ...meta })
}

/** 行为埋点（如发送消息、保存策略等） */
export function trackAction(name: string, meta?: Record<string, unknown>) {
  track('action', name, meta)
}

/** 错误上报 */
export function reportError(err: unknown, meta?: Record<string, unknown>) {
  const e = err as Error | undefined
  track('error', 'global', {
    message: e?.message ?? String(err),
    stack: e?.stack,
    ...meta,
  })
}

function scheduleFlush() {
  if (flushTimer != null) return
  flushTimer = window.setTimeout(() => {
    flushTimer = null
    void flush()
  }, FLUSH_DELAY)
}

/** 尝试上报队列（接口缺失/网络失败静默保留，后续重试；登出时清空） */
export async function flush() {
  if (flushing) return
  const q = loadQueue()
  if (!q.length) return
  flushing = true
  try {
    await reportEvents(q)
    localStorage.removeItem(KEY)
  } catch {
    /* 降级：队列保留，由 MAX 裁剪控制体积 */
  } finally {
    flushing = false
  }
}

/** 应用启动时注册全局错误捕获与页面级性能埋点 */
export function initMonitor() {
  window.addEventListener('error', (e) => reportError(e.error ?? e.message, { source: 'error' }))
  window.addEventListener('unhandledrejection', (e) => reportError(e.reason, { source: 'unhandledrejection' }))
  // 页面可见时补传队列
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) void flush()
  })
  // 页面加载总耗时（Navigation Timing）
  window.addEventListener('load', () => {
    const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
    if (nav && nav.loadEventEnd > 0) {
      trackTiming('page_load', nav.loadEventEnd - nav.startTime)
    }
  })
}
