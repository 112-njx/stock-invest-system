import { onMounted, onUnmounted, ref } from 'vue'
import { request } from '@/api/http'

export const syntheticWickFactor = ref(0.5)
let subscribers = 0
let timer: ReturnType<typeof setInterval> | undefined
let pending: Promise<void> | null = null

export function refreshSyntheticWicks(): Promise<void> {
  if (pending) return pending
  pending = request<{ synthetic_wick_factor: number }>({ url: '/market/display-settings', silent: true })
    .then(value => { syntheticWickFactor.value = value.synthetic_wick_factor })
    .catch(() => { /* Retain the last valid display preference during outages. */ })
    .finally(() => { pending = null })
  return pending
}

export function useSyntheticWicks() {
  onMounted(() => {
    subscribers++
    void refreshSyntheticWicks()
    if (!timer) timer = setInterval(() => void refreshSyntheticWicks(), 30000)
  })
  onUnmounted(() => {
    if (--subscribers === 0 && timer) { clearInterval(timer); timer = undefined }
  })
  return syntheticWickFactor
}
