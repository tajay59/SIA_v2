/**
 * Sign-in pages: the picture beside the form (AuthCard) and the motion between those pages.
 *
 * Picture: the owner generates one per app (prompts in assets/auth/SOURCE.md) and drops them in
 * `assets/auth/` as `shop.webp` / `sia.webp` (still, 3:4 portrait) and optionally `shop.mp4` / `sia.mp4`
 * (silent loop, poster = the still). Until a still exists the legacy enclosure photo stands in.
 */
import { nextTick, ref } from 'vue'
import { type Router, START_LOCATION } from 'vue-router'
import fallback from './assets/legacy/met-enclosure.webp'

const files = import.meta.glob('./assets/auth/*.{webp,jpg,png,mp4,webm}', { eager: true, query: '?url', import: 'default' }) as Record<string, string>
const find = (app: string, exts: string[]) => exts.map((e) => files[`./assets/auth/${app}.${e}`]).find(Boolean) ?? null

export type AuthMedia = { still: string; video: string | null; generated: boolean; caption: string }
export function authMedia(app: 'shop' | 'sia'): AuthMedia {
  const still = find(app, ['webp', 'jpg', 'png'])
  // The caption says only what is true of the picture: the stand-in is a real photo; a generated one is illustrative.
  return {
    still: still ?? fallback,
    video: still ? find(app, ['mp4', 'webm']) : null,
    generated: !!still,
    caption: still ? 'Illustrative image' : 'Meteorological enclosure',
  }
}

/**
 * How the AuthCard that is mounting arrived: 'load' (direct load or from an app page: picture settles, column
 * rises), 'vt' (between sign-in pages with a View Transition: no entrance, the transition is the motion),
 * 'plain' (between sign-in pages without one, e.g. WebKit: only the column lifts in, the picture stays).
 */
let arrival: 'load' | 'vt' | 'plain' = 'load'
export function takeArrival(): 'load' | 'vt' | 'plain' {
  const a = arrival
  arrival = 'load'
  return a
}

const reduced = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
// WebKit's page process crashed on View Transitions between SIA routes (web/sia/src/request-motion.ts); not risked.
const webkit = typeof navigator !== 'undefined' && /AppleWebKit/.test(navigator.userAgent) && !/Chrome\/|Chromium\/|Edg\//.test(navigator.userAgent)

/**
 * Between sign-in pages (every `layout: 'bare'` route): one View Transition. The picture stays still, the form
 * column's words lift out and settle in (`auth-words`), the form morphs to its new height (`auth-form`).
 * Skipped on first load, reduced motion, browsers without View Transitions, and WebKit.
 */
// SHOP pages in the order of its navigation: moving right slides forward, left slides back; deeper = forward.
const SHOP_ORDER = ['/', '/catalogue', '/pro-bono', '/search', '/requests', '/cart', '/account']
function shopRank(path: string): [number, number] {
  const depth = path.split('/').filter(Boolean).length
  const top = '/' + (path.split('/')[1] ?? '')
  const i = SHOP_ORDER.indexOf(top === '/' ? '/' : top)
  return [i < 0 ? SHOP_ORDER.length : i, depth]
}
function shopDirection(to: string, from: string): 'fwd' | 'back' {
  const [a, ad] = shopRank(from)
  const [b, bd] = shopRank(to)
  if (a === b) return bd >= ad ? 'fwd' : 'back'
  return b > a ? 'fwd' : 'back'
}

/** Direction of the last SHOP page change, for App.vue's page transition. */
export const shopDir = ref<'fwd' | 'back'>('fwd')

export function installAuthMotion(router: Router, app?: 'shop' | 'sia'): void {
  let first = router.currentRoute.value === START_LOCATION
  let pendingAfter: (() => void) | null = null
  router.afterEach(() => {
    first = false
    pendingAfter?.()
    pendingAfter = null
  })
  router.beforeResolve((to, from) => {
    const doc = document as Document & { startViewTransition?: (cb: () => Promise<void>) => unknown }
    if (first || to.path === from.path) return
    // SHOP app pages (catalogue, Pro Bono, requests, cart, ...): no View Transition (a whole-page snapshot
    // stretched to the new page's height and held while the page loaded read as jerky). App.vue animates the
    // page itself with a Vue <Transition>; here only the direction of travel is recorded for it.
    if (app === 'shop' && to.meta.layout !== 'bare' && from.meta.layout !== 'bare') {
      shopDir.value = shopDirection(to.path, from.path)
      return
    }
    if (to.meta.layout !== 'bare' || from.meta.layout !== 'bare') return
    if (webkit || !doc.startViewTransition || reduced()) {
      arrival = 'plain'
      return
    }
    arrival = 'vt'
    return new Promise<void>((resolve) => {
      doc.startViewTransition!(async () => {
        const rendered = new Promise<void>((done) => (pendingAfter = done))
        resolve()
        await Promise.race([rendered, new Promise((t) => setTimeout(t, 600))])
        await nextTick()
      })
    })
  })
}
