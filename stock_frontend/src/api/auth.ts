import { request } from './http'
import type { LoginResult, User } from './types'

/** 登录：用户名+密码，返回 JWT 与用户信息 */
export function loginApi(username: string, password: string) {
  return request<LoginResult>({ url: '/auth/login', method: 'post', data: { username, password } })
}

/** 注册：注册成功即自动登录（签发 JWT） */
export function registerApi(username: string, password: string, nickname?: string) {
  return request<LoginResult>({
    url: '/auth/register',
    method: 'post',
    data: { username, password, nickname },
  })
}

/** 当前用户信息 */
export function fetchMe() {
  return request<User>({ url: '/users/me' })
}

/** 更新当前用户（昵称/头像） */
export function updateMe(patch: Partial<Pick<User, 'nickname' | 'avatar_url'>>) {
  return request<User>({ url: '/users/me', method: 'put', data: patch })
}
