/**
 * G16：通知中心状态。
 * - 未读数由 WS notification 消息实时递增，断线/首次进入由接口拉取兜底
 * - 列表按需拉取（打开铃铛面板时）
 * - 活跃公告在应用启动时拉取一次，供顶部 banner 展示
 */
import { defineStore } from 'pinia'
import {
  fetchActiveAnnouncements,
  fetchNotifications,
  fetchUnreadCount,
  markAllNotificationsRead,
  markNotificationRead,
} from '@/api/notifications'
import type { Announcement, NotificationItem } from '@/api/types'
import { wsClient } from '@/utils/wsClient'

const DISMISSED_KEY = 'announcement_dismissed_ids'

export const useNotificationStore = defineStore('notification', {
  state: () => ({
    unread: 0,
    items: [] as NotificationItem[],
    total: 0,
    loading: false,
    /** 通知弹窗开关（供铃铛与头像下拉菜单「通知中心」复用） */
    panelOpen: false,
    /** 活跃公告（banner 数据源） */
    announcements: [] as Announcement[],
    /** 本会话内已关闭的公告 id（localStorage 持久化） */
    dismissedIds: [] as number[],
    /** WS 订阅解绑函数 */
    _unsubscribe: null as null | (() => void),
  }),
  getters: {
    /** 需要展示的公告（排除用户已关闭的） */
    visibleAnnouncements: (state) =>
      state.announcements.filter((a) => !state.dismissedIds.includes(a.id)),
  },
  actions: {
    /** 应用启动时调用：绑定 WS 通知消息 + 拉取未读数与活跃公告 */
    async init() {
      if (this._unsubscribe) return
      this.dismissedIds = readDismissed()
      this._unsubscribe = wsClient.onMessage((msg) => {
        if (msg.type === 'notification') {
          this.unread += 1
        }
      })
      await Promise.all([this.refreshUnread(), this.loadAnnouncements()])
    },

    dispose() {
      this._unsubscribe?.()
      this._unsubscribe = null
    },

    /** 通知弹窗开关（打开时按需拉取列表）；头像下拉「通知中心」复用同一入口 */
    async togglePanel() {
      this.panelOpen = !this.panelOpen
      if (this.panelOpen) await this.load()
    },
    closePanel() {
      this.panelOpen = false
    },

    async refreshUnread() {
      try {
        const data = await fetchUnreadCount()
        this.unread = data.unread
      } catch {
        // 未登录/网络异常静默（铃铛保持 0）
      }
    },

    async load() {
      this.loading = true
      try {
        const data = await fetchNotifications()
        this.items = data.items
        this.total = data.total
        this.unread = data.unread
      } catch {
        // 静默，面板展示空态
      } finally {
        this.loading = false
      }
    },

    async markRead(id: number) {
      const target = this.items.find((i) => i.id === id)
      if (target && !target.is_read) {
        target.is_read = true
        this.unread = Math.max(0, this.unread - 1)
      }
      try {
        await markNotificationRead(id)
      } catch {
        // 失败时下次 load 会纠正
      }
    },

    async markAllRead() {
      // 乐观更新：立即清空未读角标，再与服务端对账
      this.items.forEach((i) => (i.is_read = true))
      this.unread = 0
      try {
        await markAllNotificationsRead()
        await this.refreshUnread()
      } catch {
        // 失败时重新拉取列表，纠正本地状态
        await this.load()
      }
    },

    async loadAnnouncements() {
      try {
        this.announcements = await fetchActiveAnnouncements()
      } catch {
        // 公开接口，失败静默
      }
    },

    dismissAnnouncement(id: number) {
      if (!this.dismissedIds.includes(id)) {
        this.dismissedIds.push(id)
        writeDismissed(this.dismissedIds)
      }
    },

    /** 登出时清空本地通知状态 */
    clear() {
      this.unread = 0
      this.items = []
      this.total = 0
      this.announcements = []
    },
  },
})

function readDismissed(): number[] {
  try {
    const raw = localStorage.getItem(DISMISSED_KEY)
    return raw ? (JSON.parse(raw) as number[]) : []
  } catch {
    return []
  }
}

function writeDismissed(ids: number[]) {
  try {
    localStorage.setItem(DISMISSED_KEY, JSON.stringify(ids))
  } catch {
    // 存储不可用时忽略（仅影响关闭状态持久化）
  }
}
