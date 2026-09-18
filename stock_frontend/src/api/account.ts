/**
 * G17/G18：数据导出 + 账户删除 API（P1-5 数据复制权 / 删除权）。
 */
import { request } from './http'

/** 导出任务状态 */
export interface ExportTaskInfo {
  task_id: number
  status: 'pending' | 'running' | 'success' | 'failed' | 'expired'
  progress: number
  file_size: number | null
  error: string | null
  created_at: string
  finished_at: string | null
  expires_at: string | null
  download_url: string | null
}

/** G17：创建数据导出任务（异步） */
export function createExport() {
  return request<ExportTaskInfo>({ url: '/users/me/export', method: 'post' })
}

/** G17：查询导出任务状态（成功后含签名下载链接） */
export function fetchExportStatus(taskId: number) {
  return request<ExportTaskInfo>({ url: `/users/me/export/${taskId}`, method: 'get' })
}

/** G18：注销账户（软删除，30 天宽限期内可恢复） */
export function deleteAccount() {
  return request<{ message: string; grace_days: number }>({ url: '/users/me', method: 'delete' })
}

/** G18：宽限期内恢复账户 */
export function restoreAccount(username: string, password: string) {
  return request<{ token: string }>({
    url: '/auth/restore-account',
    method: 'post',
    data: { username, password },
  })
}

/** 后端返回的 download_url 已是含 /api/v1 前缀的完整相对路径，可直接用于 window.open */
export function exportDownloadUrl(downloadUrl: string): string {
  return downloadUrl
}

/* ---------------- G14：用户自填 API Key + token 用量 ---------------- */

/** API Key 配置状态（服务端只回掩码，不回明文） */
export interface ApiKeyStatus {
  has_api_key: boolean
  masked: string | null
}

/** G14：查询自填 API Key 状态 */
export function fetchApiKeyStatus() {
  return request<ApiKeyStatus>({ url: '/users/me/api-key', method: 'get' })
}

/** G14：设置/清除自填 API Key（传空串表示清除，回退服务端默认 Key） */
export function saveApiKey(apiKey: string) {
  return request<ApiKeyStatus>({ url: '/users/me/api-key', method: 'put', data: { api_key: apiKey } })
}

/** G14：累计 token 用量（估算值，非精确计费） */
export interface TokenUsage {
  prompt: number
  completion: number
  total: number
}

/** G14：读取当前用户累计 token 用量（数据源为 /users/me） */
export function fetchTokenUsage() {
  return request<{ llm_tokens_prompt: number; llm_tokens_completion: number; llm_tokens_total: number }>({
    url: '/users/me',
    method: 'get',
  })
}
