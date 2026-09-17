import axios, { type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios'
import type { ApiResponse } from './types'
import { toast } from '@/utils/toast'
import { useUserStore } from '@/stores/user'
import router from '@/router'

declare module 'axios' {
  interface AxiosRequestConfig {
    /** 静默模式：业务错误不 toast（轮询等高频请求使用，避免错误刷屏） */
    silent?: boolean
    /** 内部标记：跳过 401 自动刷新（refresh 接口自身使用，防递归） */
    _skipRefresh?: boolean
  }
}

/** G19：刷新锁，防止多个并发请求同时触发 refresh */
let isRefreshing = false
let refreshSubscribers: Array<(token: string) => void> = []

function subscribeTokenRefresh(callback: (token: string) => void) {
  refreshSubscribers.push(callback)
}

function onTokenRefreshed(newToken: string) {
  refreshSubscribers.forEach((cb) => cb(newToken))
  refreshSubscribers = []
}

function onRefreshFailed() {
  refreshSubscribers = []
}

/**
 * axios 实例：
 * - baseURL `/api/v1`（开发代理到后端 8000，生产由 Nginx 反代）
 * - withCredentials=true：跨域请求自动携带 Cookie（refresh token Cookie）
 * - 请求拦截注入 Bearer token（从 Pinia 内存读取）
 * - 响应拦截：401 时自动 refresh → 重放原请求；refresh 失败则登出跳登录页
 */
const http = axios.create({
  baseURL: '/api/v1',
  timeout: 20000,
  withCredentials: true,
})

http.interceptors.request.use((config) => {
  const user = useUserStore()
  if (user.token) config.headers.Authorization = `Bearer ${user.token}`
  return config
})

http.interceptors.response.use(
  (response) => {
    const body = response.data as ApiResponse<unknown>
    if (body && typeof body === 'object' && 'code' in body && body.code !== 0) {
      if (!response.config.silent) toast.error(body.msg || '请求失败')
      return Promise.reject(new Error(body.msg || '请求失败'))
    }
    return response
  },
  async (error) => {
    const status = error.response?.status as number | undefined
    const body = error.response?.data
    const msg = (body && typeof body === 'object' && body.msg) || error.message || '网络错误'
    const originalConfig = error.config as (InternalAxiosRequestConfig & { _skipRefresh?: boolean }) | undefined

    // G19：401 自动 refresh 重试（仅一次，防递归）
    if (status === 401 && originalConfig && !originalConfig._skipRefresh) {
      if (isRefreshing) {
        // 已有 refresh 在进行中，排队等待
        return new Promise((resolve) => {
          subscribeTokenRefresh((newToken: string) => {
            originalConfig.headers.Authorization = `Bearer ${newToken}`
            originalConfig._skipRefresh = true
            resolve(http(originalConfig))
          })
        })
      }

      isRefreshing = true
      try {
        const { refreshApi } = await import('@/api/auth')
        const result = await refreshApi()
        const newToken = result.token

        // 更新 Pinia store 中的 token（不写 localStorage）
        const user = useUserStore()
        user.token = newToken

        isRefreshing = false
        onTokenRefreshed(newToken)

        // 重放原请求
        originalConfig.headers.Authorization = `Bearer ${newToken}`
        originalConfig._skipRefresh = true
        return http(originalConfig)
      } catch {
        isRefreshing = false
        onRefreshFailed()

        // refresh 失败 → 登出跳登录页
        const user = useUserStore()
        user.clearAuth()
        if (router.currentRoute.value.name !== 'login') {
          router.push({ name: 'login', query: { redirect: router.currentRoute.value.fullPath } })
        }
        return Promise.reject(error)
      }
    }

    // 非 401 或已重试过的 401
    if (status === 401) {
      const user = useUserStore()
      if (user.token) {
        user.clearAuth()
        if (router.currentRoute.value.name !== 'login') {
          router.push({ name: 'login', query: { redirect: router.currentRoute.value.fullPath } })
        }
      }
    }
    if (!originalConfig?.silent) toast.error(msg)
    return Promise.reject(error)
  },
)

/** 发起请求并直接返回后端 data 字段（silent 用于轮询等高频场景） */
export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  const res = await http.request<ApiResponse<T>>(config)
  return res.data.data
}

export default http
