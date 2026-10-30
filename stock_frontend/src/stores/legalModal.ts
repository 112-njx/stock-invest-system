import { defineStore } from 'pinia'

/**
 * 法律文档轻量弹窗的全局开关。
 *
 * 这两份文档不再配置独立路由页面，底部版权条、注册协议、设置面板等入口
 * 统一通过本 store 打开同一个 Modal：暗色遮罩盖住当前页，ESC / 点遮罩 / × 关闭，
 * 关闭后停留在触发弹窗的页面（不发生路由跳转）。
 *
 */
export type LegalDocKey = 'terms' | 'privacy' | 'disclaimer'

export const useLegalModalStore = defineStore('legalModal', {
  state: () => ({
    /** 当前展示的文档；null 表示弹窗关闭 */
    doc: null as LegalDocKey | null,
  }),
  getters: {
    open: (state) => state.doc !== null,
  },
  actions: {
    show(doc: LegalDocKey) {
      this.doc = doc
    },
    hide() {
      this.doc = null
    },
  },
})
