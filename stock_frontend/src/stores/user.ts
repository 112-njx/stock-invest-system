import { defineStore } from 'pinia'
import { loginApi, registerApi, fetchMe, updateMe, logoutApi } from '@/api/auth'
import type { User } from '@/api/types'

/**
 * 用户状态（G19）：
 * - token 存 Pinia 内存（页面刷新后丢失，由 refresh Cookie 自动恢复）
 * - refresh token 在 HttpOnly Cookie（前端不可见）
 * - 登出时调后端 POST /auth/logout 吊销会话
 */
export const useUserStore = defineStore('user', {
  state: () => ({
    token: '', // G19：纯内存，不读 localStorage
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
    /** 注册成功自动登录（后端注册即签发双 token；G23：email 必填） */
    async register(username: string, password: string, email: string, nickname?: string) {
      const data = await registerApi(username, password, email, nickname)
      this.setAuth(data.token, data.user)
    },
    setAuth(token: string, user: User) {
      this.token = token // G19：仅内存，不写 localStorage
      this.user = user
    },
    async fetchMe() {
      this.user = await fetchMe()
      return this.user
    },
    async updateProfile(patch: Partial<Pick<User, 'nickname' | 'avatar_url'>>) {
      this.user = await updateMe(patch)
    },
    /** G19：调后端登出 + 清本地状态 */
    async logout() {
      try {
        await logoutApi() // POST /auth/logout（吊销 access + refresh + 清 Cookie）
      } catch {
        // 网络错误也清本地状态
      }
      this.clearAuth()
    },
    /** 仅清本地状态（refresh 失败 / 401 降级时调用） */
    clearAuth() {
      this.token = ''
      this.user = null
    },
  },
})
