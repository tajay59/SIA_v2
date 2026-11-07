/**
 * Route guards (APD §1 "Guards", §2 global behaviour). Pages declare `definePage({ meta: { guard } })`.
 *   public · auth (any ACTIVE account) · customer (role user, not @cimh.edu.bb) · staff · admin
 * SIA defaults to `staff`, SHOP to `public`.
 */
import type { Router } from 'vue-router'
import { onSessionExpired } from './api'
import { useNotify } from './notify'
import { useSession } from './session'

export type Guard = 'public' | 'auth' | 'customer' | 'staff' | 'admin'

declare module 'vue-router' {
  interface RouteMeta {
    guard?: Guard
    /** Page title for the tab and the app bar. */
    title?: string
    /** `bare` = centred card without app navigation (login, sign-up…). */
    layout?: 'default' | 'bare'
  }
}

/** Only same-app absolute paths are accepted as `returnTo` (no open redirects). */
export function safeReturnTo(value: unknown, fallback: string): string {
  const v = Array.isArray(value) ? value[0] : value
  return typeof v === 'string' && v.startsWith('/') && !v.startsWith('//') && !v.includes('\\') ? v : fallback
}

export interface GuardOptions {
  app: 'shop' | 'sia'
  appName: string
  /** Where customers (SHOP) or staff (SIA) land after login. */
  home: string
  loginPath?: string
  /** SIA: admins without MFA are sent here first. */
  mfaPath?: string
  /** SIA: shown to logged-in non-staff ("This app is for CIMH staff"). */
  staffOnlyPath?: string
}

export function installGuards(router: Router, opts: GuardOptions): void {
  const login = opts.loginPath ?? '/login'
  const defaultGuard: Guard = opts.app === 'sia' ? 'staff' : 'public'

  router.beforeEach(async (to) => {
    const session = useSession()
    try {
      await session.load()
    } catch (e) {
      useNotify().report(e, { retry: () => void router.replace(to.fullPath) })
    }
    const guard = to.meta.guard ?? defaultGuard
    if (guard === 'public') return true
    if (!session.isLoggedIn) return { path: login, query: { returnTo: to.fullPath } }

    if (opts.app === 'sia') {
      if (!session.isStaff) return to.path === opts.staffOnlyPath ? true : { path: opts.staffOnlyPath ?? login }
      if (opts.mfaPath && session.needsMfaSetup && to.path !== opts.mfaPath) return { path: opts.mfaPath }
    }
    if (guard === 'customer' && !session.isCustomer) return { path: opts.home }
    if (guard === 'staff' && !session.isStaff) return { path: opts.home }
    if (guard === 'admin' && !session.isAdmin) return { path: opts.home }
    return true
  })

  router.afterEach((to) => {
    const title = to.meta.title
    if (typeof document !== 'undefined') document.title = title ? `${title} · ${opts.appName}` : opts.appName
  })

  onSessionExpired(() => {
    const current = router.currentRoute.value
    if ((current.meta.guard ?? defaultGuard) !== 'public') {
      useNotify().toast('Your session has ended. Please log in again.', 'info')
      void router.push({ path: login, query: { returnTo: current.fullPath } })
    }
  })
}
