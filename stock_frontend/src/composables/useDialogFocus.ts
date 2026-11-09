import { onUnmounted, watch, type Ref } from 'vue'

export function useDialogFocus(dialog: Ref<HTMLElement | undefined>, isOpen: () => boolean) {
  let opener: HTMLElement | null = null

  watch(isOpen, (open) => {
    if (open) opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
  }, { flush: 'sync' })

  watch(isOpen, (open) => {
    if (open) dialog.value?.querySelector<HTMLElement>('[data-dialog-focus]')?.focus()
    else if (opener?.isConnected) opener.focus()
  }, { flush: 'post' })

  function keepFocus(event: KeyboardEvent) {
    const panel = dialog.value
    if (event.key !== 'Tab' || !panel?.contains(document.activeElement)) return
    const controls = Array.from(panel.querySelectorAll<HTMLElement>(
      'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]',
    )).filter(control => control.getClientRects().length > 0)
    const first = controls[0], last = controls[controls.length - 1]
    if (event.shiftKey && document.activeElement === first && last) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last && first) {
      event.preventDefault()
      first.focus()
    }
  }

  document.addEventListener('keydown', keepFocus)
  onUnmounted(() => document.removeEventListener('keydown', keepFocus))
}
