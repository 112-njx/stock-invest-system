import { defineStore } from 'pinia'
import { loginApi, registerApi, fetchMe, updateMe } from '@/api/auth'
import type { User } from '@/api/types'

const TOKEN_KEY = 'stock_invest_token'

/** 用户状态：token + 用户信息，登录态由 token 驱动 */
export const useUserStore = defineStore('user', {
  state: () => ({
    // TODO(G19): 改为从响应体/内存读取，不再读 localStorage
    token: localStorage.getItem(TOKEN_KEY) || '',
    user: null as User | null,
  }),
  getters: {
    isLoggedIn: (state) => !!state.token,
    displayName: (state) => state.user?.nickname || state.user?.username || '',
    avatarText: (state) => (state.user?.nickname || state.user?.username || 'U').charAt(0).toUpperCase(),
  },
  actions: {
    async login(username: string, password: string) {
      const data = await loginApi(username, password)
      this.setAuth(data.token, data.user)
    },
    /** 注册成功自动登录（后端注册即签发 JWT） */
    async register(username: string, password: string, nickname?: string) {
      const data = await registerApi(username, password, nickname)
      this.setAuth(data.token, data.user)
    },
    setAuth(token: string, user: User) {
      this.token = token
      this.user = user
      // TODO(G19): 移除 localStorage 存储，token 改由 HttpOnly Cookie 管理
      localStorage.setItem(TOKEN_KEY, token)
    },
    async fetchMe() {
      this.user = await fetchMe()
      return this.user
    },
    async updateProfile(patch: Partial<Pick<User, 'nickname' | 'avatar_url'>>) {
      this.user = await updateMe(patch)
    },
    logout() {
      this.token = ''
      this.user = null
      // TODO(G19): 移除 localStorage 操作，改为调后端 POST /auth/logout + 清 Cookie
      localStorage.removeItem(TOKEN_KEY)
    },
  },
})
