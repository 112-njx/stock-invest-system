import { onBeforeUnmount, ref, type Ref } from 'vue'

/**
 * G35 · 以鼠标为重心的 3D 倾斜（规格书 §2.4）。
 *
 * - 鼠标移入卡片后，卡片以鼠标位置为「重心」向该方向倾斜（鼠标偏左上，卡片左上翘起）
 * - 移动过程**实时跟随**（`transition: none`，避免拖尾）；移出时 `0.4s ease` 平滑回正
 * - 用 `requestAnimationFrame` 节流，避免高频 mousemove 卡顿
 *
 * 用法：把 `onEnter/onMove/onLeave` 绑到卡片容器，`el` 传该容器的模板 ref。
 */
export function useTilt(el: Ref<HTMLElement | null>, maxDeg = 6) {
  const tilting = ref(false)
  let raf = 0
  let pending: { x: number; y: number } | null = null

  function apply() {
    raf = 0
    const node = el.value
    if (!node || !pending) return
    const { x, y } = pending
    node.style.transform = `perspective(800px) rotateX(${(-y * maxDeg).toFixed(2)}deg) rotateY(${(x * maxDeg).toFixed(2)}deg)`
  }

  function onEnter() {
    tilting.value = true
    const node = el.value
    if (node) node.style.transition = 'none'
  }

  function onMove(e: MouseEvent) {
    const node = el.value
    if (!node) return
    const rect = node.getBoundingClientRect()
    // jsdom / 未布局场景下尺寸为 0，跳过以免除零
    if (!rect.width || !rect.height) return
    pending = {
      x: (e.clientX - rect.left - rect.width / 2) / (rect.width / 2),
      y: (e.clientY - rect.top - rect.height / 2) / (rect.height / 2),
    }
    if (!raf) raf = requestAnimationFrame(apply)
  }

  function onLeave() {
    tilting.value = false
    pending = null
    if (raf) {
      cancelAnimationFrame(raf)
      raf = 0
    }
    const node = el.value
    if (!node) return
    node.style.transition = 'transform 0.4s ease'
    node.style.transform = 'perspective(800px) rotateX(0deg) rotateY(0deg)'
  }

  onBeforeUnmount(() => {
    if (raf) cancelAnimationFrame(raf)
  })

  return { tilting, onEnter, onMove, onLeave }
}
