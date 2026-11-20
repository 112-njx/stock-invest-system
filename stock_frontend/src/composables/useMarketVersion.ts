import { readonly, ref, watch, type Ref } from 'vue'

const version = ref<string>()
export const marketVersion = readonly(version)
const indexVersion = ref<string>()
export const headlineIndexVersion = readonly(indexVersion)

/** One lightweight check for all visible market components, including guests. */
export function useMarketVersion(enabled: Ref<boolean>) {
  pollVersion(enabled, '/api/v1/stockdb/market-version', version)
}

export function useHeadlineIndexVersion(enabled: Ref<boolean>) {
  pollVersion(enabled, '/api/v1/market/headline-version', indexVersion)
}

function pollVersion(enabled: Ref<boolean>, url: string, target: Ref<string | undefined>) {
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
        const response = await fetch(url, {
          cache: 'no-store',
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]),
        })
        if (!response.ok) return
        const data = await response.json()
        if (!controller.signal.aborted && typeof data.version === 'string' && data.version) {
          target.value = data.version
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
