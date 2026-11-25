import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const get = vi.fn()
const post = vi.fn()
let cookie: string | undefined
vi.mock('@cimh/web-api', () => ({
  identityClient: () => ({ GET: get, POST: post }),
  readCookie: () => cookie,
}))

const { useSession } = await import('../src/session')

const res = (status: number, body?: unknown) => ({
  data: status < 400 ? body : undefined,
  error: status >= 400 ? body : undefined,
  response: new Response(null, { status }),
})

describe('session load (am I signed in?)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    get.mockReset()
    post.mockReset()
    cookie = undefined
  })

  it('asks nothing when no session cookie exists (a visitor sees no 401s)', async () => {
    const s = useSession()
    await s.load()
    expect(s.loaded).toBe(true)
    expect(s.isLoggedIn).toBe(false)
    expect(get).not.toHaveBeenCalled()
    expect(post).not.toHaveBeenCalled()
  })

  it('loads the account when a session cookie exists', async () => {
    cookie = 'csrf'
    get.mockResolvedValue(res(200, { id: 'ACC1', role: 'user', firstname: 'Cass', lastname: 'Tomer' }))
    const s = useSession()
    await s.load()
    expect(s.isLoggedIn).toBe(true)
    expect(post).not.toHaveBeenCalled()
  })

  it('refreshes once when the access token has expired, then asks again', async () => {
    cookie = 'csrf'
    get.mockResolvedValueOnce(res(401, { code: 'TOKEN_EXPIRED' })).mockResolvedValueOnce(res(200, { id: 'ACC1', role: 'user' }))
    post.mockResolvedValue({ response: new Response(null, { status: 200 }) })
    const s = useSession()
    await s.load()
    expect(post).toHaveBeenCalledTimes(1)
    expect(s.isLoggedIn).toBe(true)
  })

  it('ends signed out when the refresh fails', async () => {
    cookie = 'csrf'
    get.mockResolvedValue(res(401, {}))
    post.mockResolvedValue({ response: new Response(null, { status: 401 }) })
    const s = useSession()
    await s.load()
    expect(s.isLoggedIn).toBe(false)
    expect(s.loaded).toBe(true)
  })
})
