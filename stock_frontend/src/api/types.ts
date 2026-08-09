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
  nickname?: string | null
  avatar_url?: string | null
  created_at?: string
}

export interface LoginResult {
  token: string
  user: User
}
