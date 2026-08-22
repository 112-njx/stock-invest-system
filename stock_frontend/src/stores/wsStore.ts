/**
 * V0.2 阶段二：WS 订阅管理 Store。
 * - 维护订阅集合（当前标的 + 关注列表 + 固定指数，去重）
 * - 连接建立后发 subscribe，切换标的/增删关注时自动更新
 * - 收到 snapshot 直接更新 marketStore.snapshots
 * - 收到 kline 调用注册的回调（KLineChart.updateLastBar）
 * - 断线时标记 disconnected，由 useSnapshotPolling 降级为 HTTP 轮询
 * 纯状态管理，无 UI 依赖。
 */
import { defineStore } from 'pinia'
import { wsClient, type WsKlineMessage, type WsSnapshotMessage } from '@/utils/wsClient'
import { useMarketStore } from '@/stores/market'
import type { KLineBar, Snapshot } from '@/api/market'

type KlineUpdateHandler = (symbolId: number, period: string, bar: KLineBar) => void

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
        if (msg.type === 'snapshot') {
          this.handleSnapshot(msg as WsSnapshotMessage)
        } else if (msg.type === 'kline') {
          this.handleKline(msg as WsKlineMessage)
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

    /** 处理 snapshot 消息：合并到 marketStore（WS 推送数据只有价格字段，需 merge 到已有快照） */
    handleSnapshot(msg: WsSnapshotMessage) {
      const market = useMarketStore()
      for (const [sidStr, data] of Object.entries(msg.data)) {
        const sid = Number(sidStr)
        const existing = market.snapshots[sid]
        if (existing) {
          // merge：保留 code/name/type/extra，更新价格字段
          const updated: Snapshot = {
            ...existing,
            price: (data.price as number) ?? existing.price,
            change: (data.change as number) ?? existing.change,
            change_pct: (data.change_pct as number) ?? existing.change_pct,
            open: (data.open as number) ?? existing.open,
            high: (data.high as number) ?? existing.high,
            low: (data.low as number) ?? existing.low,
            pre_close: (data.pre_close as number) ?? existing.pre_close,
            volume: (data.volume as number) ?? existing.volume,
            amount: (data.amount as number) ?? existing.amount,
            turnover: (data.turnover as number) ?? existing.turnover,
            amplitude: (data.amplitude as number) ?? existing.amplitude,
            updated_at: (data.updated_at as string) ?? existing.updated_at,
            data_age_seconds: 0,
          }
          market.snapshots[sid] = updated
        }
      }
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
