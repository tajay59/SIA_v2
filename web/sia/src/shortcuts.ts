/**
 * SIA keyboard shortcuts (Design Brief §accessibility): `/` focuses the page's search, `s` the scan box,
 * `g` then `r` opens Requests. Ignored while typing in a field, with Ctrl/Alt/Meta held, or when a dialog
 * is open (dialogs keep their own keys, Esc closes them).
 */
export interface ShortcutActions {
  focusSearch: () => void
  focusScan: () => void
  go: (path: string) => void
}

const GO: Record<string, string> = { r: '/requests' }
const SEQUENCE_MS = 1500

function typing(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el || typeof el.closest !== 'function') return false
  return !!el.closest('input, textarea, select, [contenteditable=""], [contenteditable="true"], [role="textbox"]')
}

export function shortcutHandler(actions: ShortcutActions, doc: Pick<Document, 'querySelector'> = document) {
  let gAt = 0
  return (e: KeyboardEvent) => {
    if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || typing(e.target)) return
    if (doc.querySelector('[role="dialog"]')) return
    const key = e.key
    if (gAt && Date.now() - gAt < SEQUENCE_MS && GO[key]) {
      gAt = 0
      e.preventDefault()
      actions.go(GO[key])
      return
    }
    gAt = 0
    if (key === 'g') gAt = Date.now()
    else if (key === '/') {
      e.preventDefault()
      actions.focusSearch()
    } else if (key === 's') {
      e.preventDefault()
      actions.focusScan()
    }
  }
}

/** The page's own search field (marked `data-page-search`), else null. */
export function pageSearch(doc: Pick<Document, 'querySelector'> = document): HTMLInputElement | null {
  return doc.querySelector<HTMLInputElement>('[data-page-search] input')
}
