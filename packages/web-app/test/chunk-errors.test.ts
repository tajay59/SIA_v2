// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest'
import { handleChunkErrors } from '../src/bootstrap'

function fakeWindow() {
  const target = new EventTarget()
  const store = new Map<string, string>()
  const reload = vi.fn()
  const win = {
    addEventListener: target.addEventListener.bind(target),
    sessionStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) },
    location: { reload },
  } as unknown as Window
  const fire = (message: string) => {
    const e = new Event('vite:preloadError', { cancelable: true }) as Event & { payload?: unknown }
    e.payload = new Error(message)
    target.dispatchEvent(e)
    return e
  }
  return { win, reload, fire }
}

describe('lazy chunk errors', () => {
  it('ignores a CSS preload aborted by navigation', () => {
    const { win, reload, fire } = fakeWindow()
    handleChunkErrors(win)
    expect(fire('Unable to preload CSS for /assets/VCheckbox.css').defaultPrevented).toBe(true)
    expect(reload).not.toHaveBeenCalled()
  })

  it('reloads once for a missing JS chunk (new deploy), then lets the error surface', () => {
    const { win, reload, fire } = fakeWindow()
    handleChunkErrors(win)
    expect(fire('Failed to fetch dynamically imported module: /assets/quote-1a2b.js').defaultPrevented).toBe(true)
    expect(reload).toHaveBeenCalledTimes(1)
    expect(fire('Failed to fetch dynamically imported module: /assets/quote-1a2b.js').defaultPrevented).toBe(false)
    expect(reload).toHaveBeenCalledTimes(1)
  })
})
