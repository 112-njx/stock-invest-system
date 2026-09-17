/**
 * G16：通知中心 + 系统公告 API。
 */
import { request } from './http'
import type { Announcement, NotificationItem, NotificationList } from './types'

/** 通知列表（未读优先，其次时间倒序） */
export function fetchNotifications(limit = 50, offset = 0) {
  return request<NotificationList>({ url: '/notifications', method: 'get', params: { limit, offset } })
}

/** 未读通知数（铃铛红点/计数） */
export function fetchUnreadCount() {
  return request<{ unread: number }>({ url: '/notifications/unread-count', method: 'get' })
}

/** 单条标记已读 */
export function markNotificationRead(id: number) {
  return request<NotificationItem>({ url: `/notifications/${id}/read`, method: 'patch' })
}

/** 全部标记已读 */
export function markAllNotificationsRead() {
  return request<{ updated: number }>({ url: '/notifications/read-all', method: 'patch' })
}

/** 当前活跃公告（公开，顶部 banner） */
export function fetchActiveAnnouncements() {
  return request<Announcement[]>({ url: '/announcements/active', method: 'get' })
}

/** 全部公告（含历史，I 区「系统公告」入口） */
export function fetchAnnouncementHistory(limit = 50, offset = 0) {
  return request<Announcement[]>({ url: '/announcements', method: 'get', params: { limit, offset } })
}
