/**
 * V0.2 阶段二：WebSocket 实时行情单例客户端。
 * - 连接 ws(s)://{host}/api/v1/ws/market?token={jwt}
 * - 自动重连：指数退避 1s/2s/4s/8s，最大 30s
 * - 心跳：收到 {"type":"ping"} 自动回 {"type":"pong"}；30s 无消息主动断开重连
 * - 消息分发：按 type 路由（snapshot/kline/error），支持回调注册
 * - 断线补拉：重连成功后发 {"action":"sync","since":"<最后收到消息的ISO时间>"}
 * - BroadcastChannel：同浏览器只保持一个 WS 连接，其他标签页通过 BroadcastChannel 接收消息
 * 纯基础设施，无 UI 依赖。
 */
import { useUserStore } from '@/stores/user'

export type WsMessageType = 'snapshot' | 'kline' | 'ping' | 'pong' | 'error'

export interface WsSnapshotMessage {
  type: 'snapshot'
  data: Record<string, Record<string, unknown>>
}

export interface WsKlineMessage {
  type: 'kline'
  symbol_id: number
  period: string
  bar: Record<string, unknown>
}

export type WsMessage = WsSnapshotMessage | WsKlineMessage | { type: 'ping' } | { type: 'pong' } | { type: 'error'; message: string }

type MessageHandler = (msg: WsMessage) => void
type StatusHandler = (connected: boolean) => void

const RECONNECT_BASE = 1000
const RECONNECT_MAX = 30000
const HEARTBEAT_TIMEOUT = 30000
const CHANNEL_NAME = 'stock-market-ws'

function buildWsUrl(): string {
  const user = useUserStore()
  const token = user.token
  if (import.meta.env.DEV) {
    return `ws://127.0.0.1:8000/api/v1/ws/market?token=${encodeURIComponent(token)}`
  }
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${location.host}/api/v1/ws/market?token=${encodeURIComponent(token)}`
}

class WsClient {
  private ws: WebSocket | null = null
  private reconnectAttempts = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private heartbeatTimer: ReturnType<typeof setTimeout> | null = null
  private lastMessageTime = ''
  private handlers = new Set<MessageHandler>()
  private statusHandlers = new Set<StatusHandler>()
  private connected = false
  private channel: BroadcastChannel | null = null
  private isLeader = false
  private manualClose = false

  constructor() {
    if (typeof BroadcastChannel !== 'undefined') {
      this.channel = new BroadcastChannel(CHANNEL_NAME)
      this.channel.onmessage = (e) => this.onChannelMessage(e.data)
      // 竞选 leader：第一个标签页成为 leader，负责真实 WS 连接
      this.tryBecomeLeader()
    } else {
      this.isLeader = true
    }
  }

  private tryBecomeLeader() {
    // 简单 leader 选举：设置 localStorage 标记，其他标签页检测到已有 leader 则不连接
    const leaderKey = 'stock_ws_leader'
    const existing = localStorage.getItem(leaderKey)
    if (!existing) {
      this.isLeader = true
      localStorage.setItem(leaderKey, String(Date.now()))
      window.addEventListener('beforeunload', () => {
        if (this.isLeader) localStorage.removeItem(leaderKey)
      })
    } else {
      this.isLeader = false
      // 定期检查 leader 是否还活着（每 5s）
      setInterval(() => {
        const leader = localStorage.getItem(leaderKey)
        if (!leader) {
          this.isLeader = true
          localStorage.setItem(leaderKey, String(Date.now()))
          this.connect()
        }
      }, 5000)
    }
  }

  private onChannelMessage(data: { type: string; payload?: unknown }) {
    if (data.type === 'ws_message' && data.payload) {
      this.dispatch(data.payload as WsMessage)
    } else if (data.type === 'ws_status') {
      this.connected = !!data.payload
      this.statusHandlers.forEach((h) => h(this.connected))
    }
  }

  connect() {
    if (!this.isLeader) return
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return
    this.manualClose = false
    this.clearReconnectTimer()

    try {
      this.ws = new WebSocket(buildWsUrl())
    } catch {
      this.scheduleReconnect()
      return
    }

    this.ws.onopen = () => {
      this.connected = true
      this.reconnectAttempts = 0
      this.statusHandlers.forEach((h) => h(true))
      this.broadcastStatus(true)
      this.resetHeartbeat()
      // 断线补拉
      if (this.lastMessageTime) {
        this.send({ action: 'sync', since: this.lastMessageTime })
      }
    }

    this.ws.onmessage = (event) => {
      this.resetHeartbeat()
      try {
        const msg = JSON.parse(event.data) as WsMessage
        if (msg.type === 'ping') {
          this.send({ type: 'pong' })
          return
        }
        if (msg.type === 'snapshot' || msg.type === 'kline') {
          // 记录最后消息时间用于断线补拉
          const now = new Date().toISOString()
          this.lastMessageTime = now
        }
        this.dispatch(msg)
        this.broadcastMessage(msg)
      } catch { /* ignore parse errors */ }
    }

    this.ws.onerror = () => {
      // 错误由 onclose 处理重连
    }

    this.ws.onclose = () => {
      this.connected = false
      this.clearHeartbeat()
      this.statusHandlers.forEach((h) => h(false))
      this.broadcastStatus(false)
      if (!this.manualClose) this.scheduleReconnect()
    }
  }

  disconnect() {
    this.manualClose = true
    this.clearReconnectTimer()
    this.clearHeartbeat()
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.connected = false
  }

  send(data: Record<string, unknown>) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    }
  }

  subscribe(symbolIds: number[]) {
    if (symbolIds.length) this.send({ action: 'subscribe', symbol_ids: symbolIds })
  }

  unsubscribe(symbolIds: number[]) {
    if (symbolIds.length) this.send({ action: 'unsubscribe', symbol_ids: symbolIds })
  }

  onMessage(handler: MessageHandler): () => void {
    this.handlers.add(handler)
    return () => this.handlers.delete(handler)
  }

  onStatus(handler: StatusHandler): () => void {
    this.statusHandlers.add(handler)
    return () => this.statusHandlers.delete(handler)
  }

  isConnected(): boolean {
    return this.connected
  }

  private dispatch(msg: WsMessage) {
    this.handlers.forEach((h) => h(msg))
  }

  private broadcastMessage(msg: WsMessage) {
    if (this.channel) this.channel.postMessage({ type: 'ws_message', payload: msg })
  }

  private broadcastStatus(connected: boolean) {
    if (this.channel) this.channel.postMessage({ type: 'ws_status', payload: connected })
  }

  private scheduleReconnect() {
    this.clearReconnectTimer()
    const delay = Math.min(RECONNECT_BASE * Math.pow(2, this.reconnectAttempts), RECONNECT_MAX)
    this.reconnectAttempts++
    this.reconnectTimer = setTimeout(() => this.connect(), delay)
  }

  private clearReconnectTimer() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  private resetHeartbeat() {
    this.clearHeartbeat()
    this.heartbeatTimer = setTimeout(() => {
      // 30s 无消息，主动断开触发重连
      if (this.ws) this.ws.close()
    }, HEARTBEAT_TIMEOUT)
  }

  private clearHeartbeat() {
    if (this.heartbeatTimer) {
      clearTimeout(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }
}

export const wsClient = new WsClient()
