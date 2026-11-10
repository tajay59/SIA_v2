/**
 * The logged-in account (cookies hold the tokens; JS never sees them). Loaded once at start-up via GET /me.
 * Admins without MFA may only use the MFA setup endpoints, /me and logout (API: 403 MFA_REQUIRED), so
 * `needsMfaSetup` sends them to MFA setup first.
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { type Account, ApiError, call, identity, onSessionExpired, refreshSession } from './api'
import { clearDrafts } from './draft'

export type LoginOutcome =
  | { kind: 'ok'; account: Account }
  | { kind: 'mfa' } // admin with MFA: ask for the 6-digit code and log in again
  | { kind: 'blocked'; code: string; message: string }

/** Account-state codes from POST /auth/login (APD §2). Anything else is thrown. */
export const BLOCKING_CODES = new Set([
  'ACCOUNT_PENDING_VERIFICATION',
  'ACCOUNT_PENDING_APPROVAL',
  'ACCOUNT_REJECTED',
  'ACCOUNT_SUSPENDED',
  'ACCOUNT_LOCKED',
])

export const useSession = defineStore('session', () => {
  const account = ref<Account | null>(null)
  const loaded = ref(false)
  let loading: Promise<void> | null = null

  const isLoggedIn = computed(() => account.value !== null)
  const isAdmin = computed(() => account.value?.role === 'admin')
  const isStaff = computed(() => account.value?.role === 'staff' || isAdmin.value)
  const isCimh = computed(() => account.value?.isCimh === true)
  /** Customers: role user and not @cimh.edu.bb (those can browse but never request). */
  const isCustomer = computed(() => account.value?.role === 'user' && !isCimh.value)
  const needsMfaSetup = computed(() => isAdmin.value && account.value?.mfaEnabled !== true)
  const displayName = computed(() =>
    account.value ? `${account.value.firstname} ${account.value.lastname}`.trim() : '',
  )

  function load(force = false): Promise<void> {
    if (loaded.value && !force) return Promise.resolve()
    // A quiet probe: an anonymous visitor is not an "expired session", so no expiry handlers fire here.
    // An expired access token with a valid refresh cookie is refreshed once.
    const me = () => call(() => identity.GET('/me'), { refresh: false })
    loading ??= me()
      .catch(async (e: unknown) => {
        if (e instanceof ApiError && e.status === 401 && (await refreshSession())) return me()
        throw e
      })
      .then((a) => {
        account.value = a
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError && (e.status === 401 || e.status === 403)) account.value = null
        else throw e
      })
      .finally(() => {
        loaded.value = true
        loading = null
      })
    return loading
  }

  async function login(email: string, password: string, totp?: string): Promise<LoginOutcome> {
    try {
      const res = await call(
        () => identity.POST('/auth/login', { body: { email, password, client: 'web', ...(totp ? { totp } : {}) } }),
        { refresh: false },
      )
      account.value = res.account
      loaded.value = true
      return { kind: 'ok', account: res.account }
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        if (e.code === 'MFA_REQUIRED') return { kind: 'mfa' }
        if (e.code && BLOCKING_CODES.has(e.code)) return { kind: 'blocked', code: e.code, message: e.message }
      }
      throw e
    }
  }

  async function logout(): Promise<void> {
    try {
      await call(() => identity.POST('/auth/logout', {}), { refresh: false })
    } catch {
      // Logging out must always succeed locally; the session expires on its own.
    }
    account.value = null
    clearDrafts() // unsaved form copies must not outlive the person's session on a shared PC
  }

  function set(a: Account) {
    account.value = a
  }

  onSessionExpired(() => {
    account.value = null
  })

  return {
    account,
    loaded,
    isLoggedIn,
    isAdmin,
    isStaff,
    isCimh,
    isCustomer,
    needsMfaSetup,
    displayName,
    load,
    login,
    logout,
    set,
  }
})
