/**
 * V0.2 阶段二：WS 订阅管理 Store。
 * - 维护订阅集合（当前标的 + 关注列表 + 固定指数，去重）
 * - 连接建立后发 subscribe，切换标的/增删关注时自动更新
 * - K线刷新后读取最新本地行情
 * - 收到 kline 调用 KLineChart 注册的更新回调
 * - 断线时标记 disconnected，重新连接恢复订阅
 * 纯状态管理，无 UI 依赖。
 */
import { defineStore } from 'pinia'
import { wsClient, type WsKlineMessage, type WsKlineRefreshMessage } from '@/utils/wsClient'
import { useMarketStore } from '@/stores/market'
import { fetchLatestQuotes, type KLineBar } from '@/api/market'

type KlineUpdateHandler = (symbolId: number, period: string, bar: KLineBar | null) => void

export const useWsStore = defineStore('ws', {
  state: () => ({
    connected: false,
    /** 当前订阅的 symbol_id 集合 */
    subscribed: new Set<number>(),
    /** kline 更新回调（KLineChart 注册） */
    _klineHandler: null as KlineUpdateHandler | null,
    /** 是否已初始化消息监听 */
    _initialized: false,
  }),
  actions: {
    /** 初始化 WS 连接和消息监听（只调用一次） */
    init() {
      if (this._initialized) return
      this._initialized = true

      wsClient.onStatus((connected) => {
        this.connected = connected
      })

      wsClient.onMessage((msg) => {
        if (msg.type === 'kline') {
          this.handleKline(msg as WsKlineMessage)
        } else if (msg.type === 'kline_refresh') {
          const refresh = msg as WsKlineRefreshMessage
          this._klineHandler?.(refresh.symbol_id, refresh.period, null)
          void fetchLatestQuotes([refresh.symbol_id], true).then(rows => useMarketStore().mergeQuotes(rows)).catch(() => {})
        }
      })

      wsClient.connect()
    },

    /** 注册 K 线更新回调（KLineChart onMounted 时注册） */
    setKlineHandler(handler: KlineUpdateHandler | null) {
      this._klineHandler = handler
    },

    /** 重新计算并同步订阅集合 */
    syncSubscriptions() {
      const market = useMarketStore()
      const ids = new Set<number>()
      if (market.current) ids.add(market.current.id)
      for (const w of market.watchlist) ids.add(w.symbol_id)
      for (const idx of market.fixedIndices) ids.add(idx.id)

      // 计算新增和取消
      const toAdd = [...ids].filter((id) => !this.subscribed.has(id))
      const toRemove = [...this.subscribed].filter((id) => !ids.has(id))

      if (toAdd.length) wsClient.subscribe(toAdd)
      if (toRemove.length) wsClient.unsubscribe(toRemove)

      this.subscribed = ids
    },

    /** 处理 kline 消息：调用 KLineChart 注册的回调 */
    handleKline(msg: WsKlineMessage) {
      if (this._klineHandler) {
        const bar = msg.bar as unknown as KLineBar
        this._klineHandler(msg.symbol_id, msg.period, bar)
      }
    },

    /** 手动断开（登出时调用） */
    disconnect() {
      wsClient.disconnect()
      this.connected = false
      this.subscribed.clear()
      this._initialized = false
    },
  },
})
