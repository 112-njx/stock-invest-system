/**
 * 极简 toast 提示（无 UI 库依赖）：
 * 顶部居中，success/error/info 三态，2.5s 自动消失。
 */

type ToastType = 'success' | 'error' | 'info'

const CONTAINER_ID = 'toast-container'
const BG: Record<ToastType, string> = {
  success: '#16a34a',
  error: '#ef4444',
  info: '#3b82f6',
}

function ensureContainer(): HTMLElement {
  let el = document.getElementById(CONTAINER_ID)
  if (!el) {
    el = document.createElement('div')
    el.id = CONTAINER_ID
    el.style.cssText =
      'position:fixed;top:16px;left:50%;transform:translateX(-50%);z-index:9999;' +
      'display:flex;flex-direction:column;gap:8px;align-items:center;pointer-events:none;'
    document.body.appendChild(el)
  }
  return el
}

function show(message: string, type: ToastType) {
  const el = document.createElement('div')
  el.style.cssText = `background:${BG[type]};color:#fff;padding:8px 16px;border-radius:4px;` +
    'font-size:13px;box-shadow:0 2px 8px rgba(0,0,0,.3);opacity:0;transition:opacity .2s;max-width:80vw;'
  el.textContent = message
  ensureContainer().appendChild(el)
  requestAnimationFrame(() => (el.style.opacity = '1'))
  setTimeout(() => {
    el.style.opacity = '0'
    setTimeout(() => el.remove(), 200)
  }, 2500)
}

export const toast = {
  success: (message: string) => show(message, 'success'),
  error: (message: string) => show(message, 'error'),
  info: (message: string) => show(message, 'info'),
}
