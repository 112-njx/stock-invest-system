import { onBeforeUnmount, ref } from 'vue'
import { fetchSnapshot } from '@/api/market'
import { useMarketStore } from '@/stores/market'

//前端业务逻辑，可以理解成后端service
/** 实时行情轮询：7s 拉取快照合并到 marketStore（覆盖当前标的 + 关注列表）。 */
export function useSnapshotPolling(intervalMs = 7000) {
  const market = useMarketStore()
  const running = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  /** 收集需要轮询的 symbol_id：当前标的 + 关注列表（去重） */
  function collectIds(): number[] {
    const ids: number[] = []
    if (market.current) ids.push(market.current.id)
    for (const w of market.watchlist) {
      if (!ids.includes(w.symbol_id)) ids.push(w.symbol_id)
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
    if (running.value) return
    running.value = true
    await tick() // 启动即刷新一次
    timer = setInterval(tick, intervalMs)
  }

  function stop() {
    running.value = false
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  onBeforeUnmount(stop)

  return { running, start, stop }
}
