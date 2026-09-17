import http, { request } from './http'
import type { LoginResult, RefreshResult, SessionInfo, User } from './types'

/** 登录：用户名+密码，返回 access token（refresh token 在 HttpOnly Cookie） */
export function loginApi(username: string, password: string) {
  return request<LoginResult>({ url: '/auth/login', method: 'post', data: { username, password } })
}

/** 注册：注册成功即自动登录（G23：email 必填） */
export function registerApi(username: string, password: string, email: string, nickname?: string) {
  return request<LoginResult>({
    url: '/auth/register',
    method: 'post',
    data: { username, password, email, nickname },
  })
}

/** G23：邮箱验证（邮件链接跳转后调用） */
export function verifyEmailApi(token: string) {
  return request<{ message: string }>({ url: '/auth/verify-email', method: 'get', params: { token } })
}

/** G23：忘记密码（发送重置邮件，防枚举恒返回成功） */
export function forgotPasswordApi(email: string) {
  return request<{ message: string }>({ url: '/auth/forgot-password', method: 'post', data: { email } })
}

/** G23：重置密码（token + 新密码，成功后吊销全部会话） */
export function resetPasswordApi(token: string, newPassword: string) {
  return request<{ message: string }>({
    url: '/auth/reset-password',
    method: 'post',
    data: { token, new_password: newPassword },
  })
}

/** G33：已登录改密（成功后全部会话失效，需重新登录） */
export function changePasswordApi(oldPassword: string, newPassword: string) {
  return request<{ message: string }>({
    url: '/users/me/password',
    method: 'put',
    data: { old_password: oldPassword, new_password: newPassword },
  })
}

/** G33：已登录改邮箱（新邮箱需重新验证） */
export function changeEmailApi(password: string, newEmail: string) {
  return request<{ message: string }>({
    url: '/users/me/email',
    method: 'put',
    data: { password, new_email: newEmail },
  })
}

/** G19：刷新 access token（refresh token 由 Cookie 自动携带） */
export function refreshApi() {
  return request<RefreshResult>({ url: '/auth/refresh', method: 'post' })
}

/** G19：登出（后端吊销 access + refresh + 清 Cookie） */
export function logoutApi() {
  return http.post('/auth/logout')
}

/** G19：活跃设备列表 */
export function fetchSessions() {
  return request<SessionInfo[]>({ url: '/auth/sessions', method: 'get' })
}

/** G19：踢出指定设备 */
export function revokeSession(sessionId: number) {
  return request<null>({ url: `/auth/sessions/${sessionId}`, method: 'delete' })
}

/** 当前用户信息 */
export function fetchMe() {
  return request<User>({ url: '/users/me' })
}

/** 更新当前用户（昵称/头像） */
export function updateMe(patch: Partial<Pick<User, 'nickname' | 'avatar_url'>>) {
  return request<User>({ url: '/users/me', method: 'put', data: patch })
}
