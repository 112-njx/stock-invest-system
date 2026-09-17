/** 后端统一响应包装：成功 code=0，业务失败 code 非 0 */
export interface ApiResponse<T> {
  code: number
  msg: string
  data: T
}

export interface User {
  id: number
  username: string
  email?: string | null
  /** G23：邮箱是否已验证 */
  email_verified?: boolean
  nickname?: string | null
  avatar_url?: string | null
  created_at?: string
}

/** G19：登录/注册响应（access token 在 body，refresh token 在 HttpOnly Cookie） */
export interface LoginResult {
  token: string
  user: User
}

/** G19：刷新响应（仅返回新 access token，refresh 在 Cookie） */
export interface RefreshResult {
  token: string
}

/** G19：会话设备信息 */
export interface SessionInfo {
  id: number
  user_agent?: string | null
  ip_address?: string | null
  created_at: string
  expires_at: string
  is_current: boolean
}
