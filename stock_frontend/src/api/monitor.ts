import { request } from './http'

/** 前端监控事件：error=错误上报 / performance=耗时埋点 / action=行为埋点 */
export interface MonitorEvent {
  ts: number
  type: 'error' | 'performance' | 'action'
  name: string
  meta?: Record<string, unknown>
}

/**
 * 前端监控事件上报（约定接口，5.3）。
 * 后端尚未实现 POST /api/v1/monitor/events 时 404 静默降级，由调用方保留到本地队列，
 * 与 memory/files、agent/runs 的占位模式一致：后端补齐后自动生效。
 */
export function reportEvents(events: MonitorEvent[]) {
  return request<null>({ url: '/monitor/events', method: 'post', data: { events }, silent: true })
}
