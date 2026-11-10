/**
 * Unsaved form data survives a session expiry (APD §2): while someone types, the form is copied to this
 * tab's sessionStorage; when the page opens again (after logging back in, or a reload) the copy is
 * restored and a toast says so. `clear()` after a successful save or on Cancel. Logout removes every
 * draft (shared PCs). Drafts older than MAX_AGE are ignored. Storage may be blocked: then nothing is kept.
 */
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { useNotify } from './notify'

const PREFIX = 'cimh:draft:'
const MAX_AGE = 4 * 60 * 60 * 1000

interface Stored<T> {
  at: number
  value: T
}

function storage(): Storage | null {
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

export function readDraft<T>(key: string): T | null {
  try {
    const raw = storage()?.getItem(PREFIX + key)
    if (!raw) return null
    const s = JSON.parse(raw) as Stored<T>
    if (Date.now() - s.at > MAX_AGE) {
      storage()?.removeItem(PREFIX + key)
      return null
    }
    return s.value
  } catch {
    return null
  }
}

export function writeDraft<T>(key: string, value: T): void {
  try {
    storage()?.setItem(PREFIX + key, JSON.stringify({ at: Date.now(), value } satisfies Stored<T>))
  } catch {
    /* full or blocked: the draft is simply not kept */
  }
}

export function removeDraft(key: string): void {
  try {
    storage()?.removeItem(PREFIX + key)
  } catch {
    /* ignore */
  }
}

/** Every draft of this tab (logout). */
export function clearDrafts(): void {
  const s = storage()
  if (!s) return
  try {
    for (const k of Object.keys(s)) if (k.startsWith(PREFIX)) s.removeItem(k)
  } catch {
    /* ignore */
  }
}

/**
 * Keep the value returned by `get` as a draft under `key` (a function, so it can follow the record's
 * id/version); `set` puts a restored draft back. Restores once, on mount, after the form's own defaults.
 * `pristine` (optional) is the untouched form: a value equal to it is not a draft (it removes the copy).
 */
export function useDraft<T>(key: () => string | null, get: () => T, set: (v: T) => void, pristine?: () => T) {
  const notify = useNotify()
  let ready = false
  let timer: ReturnType<typeof setTimeout> | undefined

  onMounted(() => {
    const k = key()
    const saved = k ? readDraft<T>(k) : null
    if (saved !== null && !(pristine && JSON.stringify(saved) === JSON.stringify(pristine()))) {
      set(saved)
      notify.toast('Your unsaved changes were restored.', 'info')
    }
    ready = true
  })

  function persist() {
    const k = key()
    if (!k) return
    const v = get()
    if (pristine && JSON.stringify(v) === JSON.stringify(pristine())) removeDraft(k)
    else writeDraft(k, v)
  }
  let pending = false
  watch(
    () => JSON.stringify(get()),
    () => {
      if (!ready) return
      clearTimeout(timer)
      pending = true
      timer = setTimeout(() => {
        pending = false
        persist()
      }, 300)
    },
  )
  // Leaving (e.g. sent to Login because the session ended) must not drop the last keystrokes.
  onBeforeUnmount(() => {
    clearTimeout(timer)
    if (pending) persist()
  })

  return {
    clear() {
      clearTimeout(timer)
      pending = false
      const k = key()
      if (k) removeDraft(k)
    },
  }
}
