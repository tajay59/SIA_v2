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

/**
 * "Try again in 2 minutes." from a Retry-After in seconds: minutes from a minute up (a lock or a rate limit
 * lasts minutes; "120 s" had to be worked out), seconds below one. One wording for toasts and inline messages.
 */
export function tryAgainIn(seconds?: number): string {
  if (!seconds || seconds <= 0) return 'Try again in a moment.'
  if (seconds < 60) {
    const s = Math.ceil(seconds)
    return `Try again in ${s} second${s === 1 ? '' : 's'}.`
  }
  const m = Math.ceil(seconds / 60)
  return `Try again in ${m} minute${m === 1 ? '' : 's'}.`
}

export const useNotify = defineStore('notify', () => {
  const toasts = ref<Toast[]>([])
  /** `detail` replaces "Nothing was saved." where nothing was being saved (e.g. "No code was sent."). */
  const unavailable = ref<null | { retry?: () => void; detail?: string }>(null)

  function toast(text: string, tone: ToastTone = 'info', extra: Partial<Omit<Toast, 'id' | 'text' | 'tone'>> = {}) {
    const t: Toast = { id: ++seq, text, tone, timeout: extra.timeout ?? (tone === 'error' ? 8000 : 4000), ...extra }
    toasts.value = [...toasts.value.slice(-2), t]
    return t.id
  }

  function dismiss(id: number) {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }

  function report(err: unknown, opts: { retry?: () => void; detail?: string } = {}) {
    if (!(err instanceof ApiError)) {
      toast('Something went wrong. Please try again.', 'error')
      return
    }
    if (err.isNetwork) {
      unavailable.value = { retry: opts.retry, detail: opts.detail }
      return
    }
    if (err.status === 409 && err.code === 'VERSION_CONFLICT') {
      toast('This was changed by someone else. The latest version has been loaded.', 'warning')
      opts.retry?.()
      return
    }
    if (err.status === 429) {
      const s = err.retryAfter
      toast(`Too many attempts. ${tryAgainIn(s)}`, 'warning', {
        timeout: Math.max(4000, (s ?? 0) * 1000),
      })
      return
    }
    toast(err.message, 'error')
  }

  return { toasts, unavailable, toast, dismiss, report }
})
