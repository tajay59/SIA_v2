/**
 * Previous / next product from inside the record (owner 2026-11-25): the products list (A-05) remembers the order
 * it shows for this browser tab, so the record beside it and the product's own page can step through the same
 * list. Browser storage can be unavailable; then there is simply no previous/next.
 */
import { ref } from 'vue'

const KEY = 'sia.products.order'
const MAX = 500

function read(): string[] {
  try {
    const v: unknown = JSON.parse(sessionStorage.getItem(KEY) ?? '[]')
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}

/** The list's product ids, in the order shown. */
export const productOrder = ref<string[]>(read())

export function rememberProductOrder(ids: string[]): void {
  productOrder.value = ids.slice(0, MAX)
  try {
    sessionStorage.setItem(KEY, JSON.stringify(productOrder.value))
  } catch {
    // private mode / blocked storage: previous/next still works while the list is open
  }
}

export interface Neighbours {
  prev: string | null
  next: string | null
  /** 0-based place in the list, and the list's length. */
  index: number
  total: number
}

/** The products before and after `id` in the remembered list, or null when `id` is not in it. */
export function neighbours(id: string, ids: string[] = productOrder.value): Neighbours | null {
  const i = ids.indexOf(id)
  if (i < 0) return null
  return { prev: ids[i - 1] ?? null, next: ids[i + 1] ?? null, index: i, total: ids.length }
}

/** Alt+↑ / Alt+↓ outside a field and with no dialog open: which way to step, or null. */
export function stepKey(e: KeyboardEvent, doc: Pick<Document, 'querySelector'> = document): -1 | 1 | null {
  if (!e.altKey || e.ctrlKey || e.metaKey || e.shiftKey || e.defaultPrevented) return null
  if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return null
  const el = e.target as HTMLElement | null
  if (el && typeof el.closest === 'function' && el.closest('input, textarea, select, [contenteditable="true"], [role="textbox"]')) return null
  if (doc.querySelector('[role="dialog"]')) return null
  return e.key === 'ArrowUp' ? -1 : 1
}
