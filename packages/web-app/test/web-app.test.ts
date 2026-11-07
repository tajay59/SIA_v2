import { beforeEach, describe, expect, it, vi } from 'vitest'

const refreshPost = vi.fn()
vi.mock('@cimh/web-api', () => ({
  identityClient: () => ({ POST: refreshPost }),
}))

const { ApiError, call, ifMatch, onSessionExpired } = await import('../src/api')
const { safeReturnTo } = await import('../src/guards')
const { passwordStrength, register, rule, email, code, isCimhEmail } = await import('../src/validation')

const res = (status: number, body?: unknown, headers: Record<string, string> = {}) => ({
  data: status < 400 ? body : undefined,
  error: status >= 400 ? body : undefined,
  response: new Response(null, { status, headers }),
})

describe('call()', () => {
  beforeEach(() => refreshPost.mockReset())

  it('returns data on success', async () => {
    await expect(call(async () => res(200, { ok: 1 }))).resolves.toEqual({ ok: 1 })
  })

  it('turns a Problem into ApiError with field errors and Retry-After', async () => {
    const err = await call(async () =>
      res(422, { title: 'Validation failed', code: 'VALIDATION_FAILED', errors: [{ field: 'email', message: 'bad' }] }),
    ).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as InstanceType<typeof ApiError>).fieldErrors()).toEqual({ email: 'bad' })
    const limited = (await call(async () => res(429, { title: 'Slow down' }, { 'Retry-After': '30' })).catch((e: unknown) => e)) as InstanceType<
      typeof ApiError
    >
    expect(limited.retryAfter).toBe(30)
  })

  it('maps a network failure to status 0 (shown as the unavailable banner)', async () => {
    const err = (await call(async () => {
      throw new TypeError('fetch failed')
    }).catch((e: unknown) => e)) as InstanceType<typeof ApiError>
    expect(err.status).toBe(0)
    expect(err.isNetwork).toBe(true)
  })

  it('refreshes once on 401 and retries the request', async () => {
    refreshPost.mockResolvedValue({ response: new Response(null, { status: 200 }) })
    const fn = vi.fn().mockResolvedValueOnce(res(401, { code: 'TOKEN_EXPIRED' })).mockResolvedValueOnce(res(200, { me: 1 }))
    await expect(call(fn)).resolves.toEqual({ me: 1 })
    expect(fn).toHaveBeenCalledTimes(2)
    expect(refreshPost).toHaveBeenCalledTimes(1)
  })

  it('concurrent 401s share one refresh (a second rotation would look like token reuse)', async () => {
    refreshPost.mockImplementation(() => new Promise((r) => setTimeout(() => r({ response: new Response(null, { status: 200 }) }), 10)))
    const mk = () => vi.fn().mockResolvedValueOnce(res(401, {})).mockResolvedValueOnce(res(200, 'ok'))
    await Promise.all([call(mk()), call(mk()), call(mk())])
    expect(refreshPost).toHaveBeenCalledTimes(1)
  })

  it('reports an expired session when the refresh fails', async () => {
    refreshPost.mockResolvedValue({ response: new Response(null, { status: 401 }) })
    const seen = vi.fn()
    const off = onSessionExpired(seen)
    await expect(call(async () => res(401, {}))).rejects.toBeInstanceOf(ApiError)
    expect(seen).toHaveBeenCalledOnce()
    off()
  })

  it('never refreshes for wrong credentials or when told not to', async () => {
    await expect(call(async () => res(401, { code: 'INVALID_CREDENTIALS' }))).rejects.toBeInstanceOf(ApiError)
    await expect(call(async () => res(401, {}), { refresh: false })).rejects.toBeInstanceOf(ApiError)
    expect(refreshPost).not.toHaveBeenCalled()
  })

  it('formats If-Match as a quoted version', () => {
    expect(ifMatch(7)).toBe('"7"')
  })
})

describe('safeReturnTo (no open redirects)', () => {
  it.each([
    ['/requests?tab=mine', '/requests?tab=mine'],
    ['//evil.example', '/'],
    ['https://evil.example', '/'],
    ['/\\evil.example', '/'],
    [undefined, '/'],
    [['/a', '/b'], '/a'],
  ])('%s -> %s', (input, want) => expect(safeReturnTo(input, '/')).toBe(want))
})

describe('validation', () => {
  it('requires an organisation except for @cimh.edu.bb', () => {
    const base = { firstname: 'A', lastname: 'B', password: 'x'.repeat(12), department: '', country: 'BB', phone: '', terms: true as const }
    expect(register.safeParse({ ...base, email: 'a@example.org', organisationText: '' }).success).toBe(false)
    expect(register.safeParse({ ...base, email: 'a@example.org', organisationText: 'BMS' }).success).toBe(true)
    expect(register.safeParse({ ...base, email: 'A@CIMH.edu.bb', organisationText: '' }).success).toBe(true)
    expect(isCimhEmail(' x@cimh.edu.bb ')).toBe(true)
  })

  it('builds Vuetify rules from schemas', () => {
    expect(rule(email)('a@b.co')).toBe(true)
    expect(rule(email)('nope')).toBe('Enter a valid email address')
    expect(rule(code)('12345')).toBe('Enter the 6-digit code')
  })

  it('rates passwords; short ones never look strong', () => {
    expect(passwordStrength('').score).toBe(0)
    expect(passwordStrength('Aa1!Aa1!Aa').score).toBeLessThanOrEqual(1)
    expect(passwordStrength('correct horse battery staple').label).toBe('Good')
    expect(passwordStrength('Correct horse battery staple 9').label).toBe('Strong')
  })
})
