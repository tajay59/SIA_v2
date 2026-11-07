/**
 * Toasts and the page-level "service unavailable" banner (APD §2 global behaviour).
 * `report(err)` maps any error to the right surface: 409 → conflict toast, 429 → countdown toast,
 * 503/network → banner with Retry, everything else → error toast with the server's detail.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ApiError } from './api'

export type ToastTone = 'success' | 'info' | 'warning' | 'error'
export interface Toast {
  id: number
  text: string
  tone: ToastTone
  timeout: number
  action?: { label: string; run: () => void }
}

let seq = 0

export const useNotify = defineStore('notify', () => {
  const toasts = ref<Toast[]>([])
  const unavailable = ref<null | { retry?: () => void }>(null)

  function toast(text: string, tone: ToastTone = 'info', extra: Partial<Omit<Toast, 'id' | 'text' | 'tone'>> = {}) {
    const t: Toast = { id: ++seq, text, tone, timeout: extra.timeout ?? (tone === 'error' ? 8000 : 4000), ...extra }
    toasts.value = [...toasts.value.slice(-2), t]
    return t.id
  }

  function dismiss(id: number) {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }

  function report(err: unknown, opts: { retry?: () => void } = {}) {
    if (!(err instanceof ApiError)) {
      toast('Something went wrong. Please try again.', 'error')
      return
    }
    if (err.isNetwork) {
      unavailable.value = { retry: opts.retry }
      return
    }
    if (err.status === 409 && err.code === 'VERSION_CONFLICT') {
      toast('This was changed by someone else. The latest version has been loaded.', 'warning')
      opts.retry?.()
      return
    }
    if (err.status === 429) {
      const s = err.retryAfter
      toast(s ? `Too many attempts. Try again in ${s} s.` : 'Too many attempts. Please wait a moment.', 'warning', {
        timeout: Math.max(4000, (s ?? 0) * 1000),
      })
      return
    }
    toast(err.message, 'error')
  }

  return { toasts, unavailable, toast, dismiss, report }
})
