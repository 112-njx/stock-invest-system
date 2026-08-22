import { onBeforeUnmount, ref, watch } from 'vue'
import { fetchSnapshot } from '@/api/market'
import { useMarketStore } from '@/stores/market'
import { useWsStore } from '@/stores/wsStore'

//前端业务逻辑，可以理解成后端service
/** 实时行情轮询：拉取快照合并到 marketStore（覆盖当前标的 + 关注列表）。
 *  V0.2：WS 连接时自动停止轮询，断线时降级为轮询。 */
export function useSnapshotPolling(intervalMs = 7000) {
  const market = useMarketStore()
  const ws = useWsStore()
  const running = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null
  let pollingEnabled = false // start() 被调用后置 true，stop() 后置 false

  /** 收集需要轮询的 symbol_id：当前标的 + 关注列表 + 固定指数（G/H 区，去重） */
  function collectIds(): number[] {
    const ids: number[] = []
    if (market.current) ids.push(market.current.id)
    for (const w of market.watchlist) {
      if (!ids.includes(w.symbol_id)) ids.push(w.symbol_id)
    }
    for (const i of market.fixedIndices) {
      if (!ids.includes(i.id)) ids.push(i.id)
    }
    return ids
  }

  async function tick() {
    const ids = collectIds()
    if (!ids.length) return
    try {
      const list = await fetchSnapshot(ids, true) // silent：轮询失败不 toast 刷屏
      market.mergeSnapshots(list)
    } catch {
      /* 错误已由拦截器静默处理，下次轮询自动恢复 */
    }
  }

  async function start() {
    pollingEnabled = true
    if (running.value) return
    // V0.2：WS 已连接时不启动轮询（由 WS 实时推送），等断线后自动恢复
    if (ws.connected) return
    running.value = true
    await tick() // 启动即刷新一次
    timer = setInterval(tick, intervalMs)
  }

  function stop() {
    pollingEnabled = false
    running.value = false
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  // V0.2：WS 连接状态变化时自动启停轮询
  watch(() => ws.connected, (connected) => {
    if (connected) {
      // WS 连上：停止轮询
      running.value = false
      if (timer) { clearInterval(timer); timer = null }
    } else if (pollingEnabled && !running.value) {
      // WS 断线且轮询已启用：自动恢复轮询
      running.value = true
      tick()
      timer = setInterval(tick, intervalMs)
    }
  })

  onBeforeUnmount(stop)

  return { running, start, stop }
}
