/**
 * G27 验证脚本专用桩：拦截 `@/api/monitor` 的上报，避免脚本发起真实网络请求。
 * 上报事件收进内存数组，供断言「埋点确实产生」。
 */

export interface MonitorEvent {
  ts: number
  type: 'error' | 'performance' | 'action'
  name: string
  meta?: Record<string, unknown>
}

export const reported: MonitorEvent[] = []

export function reportEvents(events: MonitorEvent[]) {
  reported.push(...events)
  return Promise.resolve()
}
