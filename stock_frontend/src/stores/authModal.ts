import { defineStore } from 'pinia'

/**
 * G35（方案 B）：登录弹窗的全局开关。
 *
 * 未登录引导散落在多个位置（E/D 区关注列表、支撑压力位设置、AI 页发送、头像区），
 * 统一通过本 store 打开同一个 Modal，避免逐层透传 props/events。
 * 弹窗登录成功后**不跳转页面**，只关闭弹窗并刷新当前页用户态。
 */
export const useAuthModalStore = defineStore('authModal', {
  state: () => ({
    open: false,
    /** 打开时的初始 Tab（未登录引导默认登录，注册引导传 register） */
    tab: 'login' as 'login' | 'register',
  }),
  actions: {
    show(tab: 'login' | 'register' = 'login') {
      this.tab = tab
      this.open = true
    },
    hide() {
      this.open = false
    },
  },
})
