import { request } from './http'

export interface Parameter {
  name: string
  label: string
  type: string
  required: boolean
  default?: string | number
  min?: number
  max?: number
  placeholder?: string
  options?: Record<string, string>
}
export interface Dataset {
  id: string
  title: string
  group: string
  kind: 'api' | 'table'
  params?: Parameter[]
  fields?: Record<string, string>
  coverage: string
}
export interface Catalog {
  entries: Dataset[]
}
export interface Status {
  retry_after: number
  interval_seconds: number
}
export interface Result extends Status {
  method: string
  parameters: Record<string, unknown>
  warnings?: string[]
  data: unknown
  fetched_at: string
  saved_path: string
}
export const getCatalog = () => request<Catalog>({ url: '/all-data/catalog', silent: true })
export const getStatus = () => request<Status>({ url: '/all-data/status', silent: true })
export const queryData = (data: Record<string, unknown>) =>
  request<Result>({
    method: 'POST',
    url: '/all-data/query',
    timeout: 210000,
    silent: true,
    data,
  })
