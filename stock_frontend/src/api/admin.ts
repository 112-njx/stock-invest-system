import { request } from './http'

export interface IndicatorSettings { pandas_enabled: boolean; revision: number }

export interface SourcePolicy {
  akshare_enabled: boolean
  auto_update_enabled: boolean
}
export interface Limits {
  interval_seconds: number
  retry_interval_seconds: number
  daily_budget: number
}
export interface Traffic extends Limits {
  day: string
  providers: Array<{
    name: string
    used: number
    health: { state: string; failures: number; last_success_at: string | null }
  }>
}
export interface TaskQueues {
  queues: Record<
    string,
    { ready: number; active: number; delayed: number; reserved: number }
  >
  workers: Record<string, boolean>
}
export interface LocalServices {
  stockdb: { state: string; latest_date: string | null }
  sdk: { state: string; latest_date: string | null }
  date_scope: string
  observed_at: string
}
export interface LocalUpdate {
  status: string
  task_id: string | null
  error: string | null
  progress: number
  message: string
  details?: Record<string, string | number>
  helper_online: boolean
  maintenance: boolean
  can_retry: boolean
  phase: string
  data_version: string | null
}
export interface DisplaySettings {
  synthetic_wick_factor: number
}
export interface ProviderRequest {
  id: string
  task_id: string
  queue: string
  provider: string
  interface: string
  symbol: string | null
  symbol_name?: string
  symbols: Array<{ code: string; name: string }>
  symbol_count: number | null
  period: string | null
  start: string | null
  end: string | null
  phase: string
  attempt: number
  attempts: number
  retry_after: number | null
  started_at: string
  updated_at: string
}
const read = <T>(path: string) => request<T>({ url: `/admin/${path}`, silent: true })
const put = <T>(path: string, data: unknown) =>
  request<T>({ url: `/admin/${path}`, method: 'put', data, silent: true })
export const adminApi = {
  services: () => read<LocalServices>('local-services'),
  indicatorSettings: () => read<IndicatorSettings>('indicator-settings'),
  saveIndicatorSettings: (data: { pandas_enabled: boolean }) => put<IndicatorSettings>('indicator-settings', data),
  policy: () => read<SourcePolicy>('market-source-policy'),
  traffic: () => read<Traffic>('traffic'),
  queues: () => read<TaskQueues>('task-queues'),
  update: () => read<LocalUpdate>('local-market/update'),
  startUpdate: () => request<LocalUpdate>({url: '/admin/local-market/update', method: 'post', silent: true}),
  display: () => read<DisplaySettings>('market-display'),
  requests: () => read<{ requests: ProviderRequest[] }>('provider-requests'),
  savePolicy: (data: SourcePolicy) => put<SourcePolicy>('market-source-policy', data),
  saveLimits: (data: Limits) => put<Traffic>('traffic/limits', data),
  saveDisplay: (data: DisplaySettings) => put<DisplaySettings>('market-display', data),
}
