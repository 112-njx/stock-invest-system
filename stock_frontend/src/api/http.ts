import axios, { type AxiosRequestConfig } from 'axios'
import type { ApiResponse } from './types'
import { toast } from '@/utils/toast'
import { useUserStore } from '@/stores/user'
import router from '@/router'

declare module 'axios' {
  interface AxiosRequestConfig {
    /** 静默模式：业务错误不 toast（轮询等高频请求使用，避免错误刷屏） */
    silent?: boolean
  }
}

/**
 * axios 实例：
 * - baseURL `/api/v1`（开发代理到后端 8000，生产由 Nginx 反代）
 * - 请求拦截注入 Bearer token
 * - 响应拦截：业务错误统一 toast，401 登出并跳登录页
 */
const http = axios.create({
  baseURL: '/api/v1',
  timeout: 20000,
})

http.interceptors.request.use((config) => {
  const user = useUserStore()
  if (user.token) config.headers.Authorization = `Bearer ${user.token}`
  return config
})

http.interceptors.response.use(
  (response) => {
    const body = response.data as ApiResponse<unknown>
    // 兼容 HTTP 200 但业务码非 0 的情况
    if (body && typeof body === 'object' && 'code' in body && body.code !== 0) {
      if (!response.config.silent) toast.error(body.msg || '请求失败')
      return Promise.reject(new Error(body.msg || '请求失败'))
    }
    return response
  },
  (error) => {
    const status = error.response?.status as number | undefined
    const body = error.response?.data
    const msg = (body && typeof body === 'object' && body.msg) || error.message || '网络错误'

    if (status === 401) {
      const user = useUserStore()
      if (user.token) {
        user.logout()
        if (router.currentRoute.value.name !== 'login') {
          router.push({ name: 'login', query: { redirect: router.currentRoute.value.fullPath } })
        }
        return Promise.reject(error)
      }
    }
    if (!error.config?.silent) toast.error(msg)
    return Promise.reject(error)
  },
)

/** 发起请求并直接返回后端 data 字段（silent 用于轮询等高频场景） */
export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  const res = await http.request<ApiResponse<T>>(config)
  return res.data.data
}

export default http
