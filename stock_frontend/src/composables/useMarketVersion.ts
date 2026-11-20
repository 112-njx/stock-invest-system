import { readonly, ref, watch, type Ref } from 'vue'

const version = ref<string>()
export const marketVersion = readonly(version)

/** One lightweight check for all visible market components, including guests. */
export function useMarketVersion(enabled: Ref<boolean>) {
  watch(enabled, (active, _, onCleanup) => {
    if (!active) return
    let timer: ReturnType<typeof setTimeout> | undefined
    let running = false
    const controller = new AbortController()
    async function check() {
      if (running || document.hidden || controller.signal.aborted) return
      clearTimeout(timer)
      running = true
      try {
        const response = await fetch('/api/v1/stockdb/market-version', {
          cache: 'no-store',
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]),
        })
        if (!response.ok) return
        const data = await response.json()
        if (!controller.signal.aborted && typeof data.version === 'string' && data.version) {
          version.value = data.version
        }
      } catch { /* Retry on the next check. */ }
      finally {
        running = false
        if (!controller.signal.aborted) timer = setTimeout(check, 5000)
      }
    }
    document.addEventListener('visibilitychange', check)
    onCleanup(() => {
      controller.abort()
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', check)
    })
    void check()
  }, { immediate: true })
}
