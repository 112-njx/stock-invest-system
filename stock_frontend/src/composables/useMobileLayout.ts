import { onMounted, onUnmounted, ref } from 'vue'

// Match the phone layout breakpoint in responsive.css.
export function useMobileLayout() {
  const query = window.matchMedia('(max-width: 767px), (max-width: 1023px) and (max-height: 500px) and (pointer: coarse)')
  const mobile = ref(query.matches)
  const sync = () => { mobile.value = query.matches }
  onMounted(() => {
    query.addEventListener('change', sync)
    sync()
  })
  onUnmounted(() => query.removeEventListener('change', sync))
  return mobile
}
