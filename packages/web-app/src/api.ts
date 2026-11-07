/**
 * API access for the web apps (API README §2 and §4, APD §2).
 *
 * `call()` unwraps an openapi-fetch result: data on success, otherwise an `ApiError` built from the RFC 9457
 * Problem. An expired access token is refreshed once, transparently (cookie rotation), and the request is
 * retried. If the refresh fails, `onSessionExpired` listeners run (the app sends the user to Login with
 * `returnTo`).
 */
import { identityClient, type IdentityComponents, type IdentityPaths } from '@cimh/web-api'

type Schemas = IdentityComponents['schemas']
export type Account = Schemas['Account']
export type AccountSummary = Schemas['AccountSummary']
export type AccountStatus = Schemas['AccountStatus']
export type Organisation = Schemas['Organisation']
export type OrganisationInput = Schemas['OrganisationInput']
export type AuditEntry = Schemas['AuditEntry']
export type Role = 'admin' | 'staff' | 'user'
export type { IdentityPaths }

export interface FieldError {
  field: string
  message: string
}

export class ApiError extends Error {
  readonly status: number
  readonly code?: string
  readonly detail?: string
  readonly errors: FieldError[]
  readonly retryAfter?: number

  constructor(status: number, problem: Record<string, unknown> = {}, retryAfter?: number) {
    const detail = typeof problem.detail === 'string' ? problem.detail : undefined
    const title = typeof problem.title === 'string' ? problem.title : undefined
    super(detail ?? title ?? (status === 0 ? 'Network error' : `HTTP ${status}`))
    this.name = 'ApiError'
    this.status = status
    this.code = typeof problem.code === 'string' ? problem.code : undefined
    this.detail = detail
    this.errors = Array.isArray(problem.errors) ? (problem.errors as FieldError[]) : []
    this.retryAfter = retryAfter
  }

  /** Field errors keyed by field name (422), for inline display. */
  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {}
    for (const e of this.errors) if (e.field && !out[e.field]) out[e.field] = e.message
    return out
  }

  get isNetwork(): boolean {
    return this.status === 0 || this.status === 503
  }
}

export const identity = identityClient()

interface FetchResult<T> {
  data?: T
  error?: unknown
  response: Response
}

const expiredListeners = new Set<() => void>()
export function onSessionExpired(fn: () => void): () => void {
  expiredListeners.add(fn)
  return () => expiredListeners.delete(fn)
}

let refreshing: Promise<boolean> | null = null
/** One refresh at a time; concurrent 401s wait for the same rotation (reuse would revoke the family). */
export function refreshSession(): Promise<boolean> {
  refreshing ??= identity
    .POST('/auth/refresh', { body: {} })
    .then((r) => r.response.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null
    })
  return refreshing
}

function toError(res: FetchResult<unknown>): ApiError {
  const retry = Number(res.response.headers.get('Retry-After'))
  const problem = (res.error && typeof res.error === 'object' ? res.error : {}) as Record<string, unknown>
  return new ApiError(res.response.status, problem, Number.isFinite(retry) && retry > 0 ? retry : undefined)
}

const NO_REFRESH_CODES = new Set(['INVALID_CREDENTIALS', 'TOKEN_REUSE', 'MFA_INVALID'])

/**
 * Run a client call and return its data or throw `ApiError`.
 * `refresh: false` for the auth endpoints themselves (login, refresh) and for "am I logged in?" probes.
 */
export async function call<T>(fn: () => Promise<FetchResult<T>>, opts: { refresh?: boolean } = {}): Promise<T> {
  const attempt = async (): Promise<FetchResult<T>> => {
    try {
      return await fn()
    } catch {
      throw new ApiError(0, { title: 'Network error' })
    }
  }
  let res = await attempt()
  if (res.response.status === 401 && opts.refresh !== false) {
    const err = toError(res)
    if (!NO_REFRESH_CODES.has(err.code ?? '')) {
      if (await refreshSession()) {
        res = await attempt()
      } else {
        expiredListeners.forEach((l) => l())
        throw err
      }
    }
  }
  if (!res.response.ok) throw toError(res)
  return res.data as T
}

/** `If-Match` value for an entity with a version (API README §1). */
export const ifMatch = (version: number): string => `"${version}"`
