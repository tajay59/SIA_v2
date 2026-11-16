/**
 * Request motion: one request, three places (summary beside the queue, full view beside the narrowed queue,
 * own page). Navigations that move the request between those places run as a View Transition, so the panel
 * named `request-pane` morphs into its new box and the queue (`request-queue`) narrows or widens with it.
 * Stepping from one request to another while open is NOT a view transition (it would freeze the page while
 * the next request loads); RequestView swaps its content in place instead.
 *
 * Skipped when the browser has no View Transitions, when reduced motion is asked for, and on first load.
 */
import { nextTick } from 'vue'
import { type RouteLocationNormalized, type Router, START_LOCATION } from 'vue-router'

// Products move the same way: list (A-05) <-> record beside it (?open=) <-> own page (A-07), named
// `product-list` and `product-pane`. /products/new is not a product place. Admin accounts (A-17: list, ?open=,
// /admin/accounts/:id) and organisations (A-18: list, ?open=) reuse those two names.
const DESK = /^\/(requests|products|admin\/accounts|admin\/organisations)\/?$/
const PAGE = /^\/(requests|products|admin\/accounts)\/(?!new\/?$)([^/]+)\/?$/
const openOf = (r: RouteLocationNormalized) => (typeof r.query.open === 'string' && r.query.open) || null

type Place = { area: string | null; kind: 'desk' | 'beside' | 'page' | null; id: string | null }
/** Which item a route shows in full, and where: 'beside' (list ?open=), 'page' (/<area>/:id), or none. */
function place(r: RouteLocationNormalized): Place {
  const d = DESK.exec(r.path)
  if (d) return openOf(r) ? { area: d[1]!, kind: 'beside', id: openOf(r) } : { area: d[1]!, kind: 'desk', id: null }
  const m = PAGE.exec(r.path)
  return m ? { area: m[1]!, kind: 'page', id: decodeURIComponent(m[2]!) } : { area: null, kind: null, id: null }
}

/** True when the navigation moves a request (or product) between places (open, close, promote, demote). */
export function movesRequest(to: RouteLocationNormalized, from: RouteLocationNormalized): boolean {
  const a = place(from)
  const b = place(to)
  if (!a.kind || !b.kind || a.area !== b.area || a.kind === b.kind) return false
  // desk <-> beside: open / close. beside <-> page: same request changes size. desk -> page: row's own page.
  if (a.kind === 'page' || b.kind === 'page') return a.id === b.id || a.kind === 'desk' || b.kind === 'desk'
  return true
}

// New product: the list's "New product" button (`product-new`) grows into the form page and shrinks back.
const NEW = /^\/products\/new\/?$/
const LIST = /^\/products\/?$/
// WebKit (Safari, every iOS browser) crashes its page process on this transition, even as a plain root
// cross-fade with nothing named (2026-11-15; not the clip, the names, the test's wait or ProductForm's observer).
// Direct loads are fine, so WebKit simply navigates without it. Re-check when WebKit updates.
const webkit = typeof navigator !== 'undefined' && /AppleWebKit/.test(navigator.userAgent) && !/Chrome\/|Chromium\/|Edg\//.test(navigator.userAgent)
export function movesNewProduct(to: RouteLocationNormalized, from: RouteLocationNormalized): boolean {
  if (webkit) return false
  return (NEW.test(to.path) && LIST.test(from.path)) || (NEW.test(from.path) && LIST.test(to.path))
}

const reduced = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

export function installRequestMotion(router: Router): () => void {
  let first = router.currentRoute.value === START_LOCATION
  let pendingAfter: (() => void) | null = null
  const offAfter = router.afterEach(() => {
    first = false
    pendingAfter?.()
    pendingAfter = null
  })
  const offResolve = router.beforeResolve((to, from) => {
    const doc = document as Document & { startViewTransition?: (cb: () => Promise<void>) => { finished: Promise<void> } }
    if (first || !doc.startViewTransition || reduced() || !(movesRequest(to, from) || movesNewProduct(to, from))) return
    // Hold the navigation until the old state is captured; finish the transition once Vue has rendered the new one.
    return new Promise<void>((resolve) => {
      doc.startViewTransition!(async () => {
        const rendered = new Promise<void>((done) => (pendingAfter = done))
        resolve()
        await Promise.race([rendered, new Promise((t) => setTimeout(t, 600))])
        await nextTick()
      })
    })
  })
  return () => {
    offAfter()
    offResolve()
  }
}
