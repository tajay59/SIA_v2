/**
 * Test helpers for the browser journeys (TEST_STRATEGY §3 E2E). They talk to the dev stack the way other
 * services would: codes are claimed through identity's internal endpoint with notification-svc's service
 * token (as the real notification-svc does), and the database is only used to find the code reference and
 * to bootstrap the first admin (as migration does in production).
 */
import { execFileSync } from 'node:child_process'
import { createHmac, randomBytes } from 'node:crypto'

export const IDENTITY = process.env.IDENTITY_URL ?? 'http://localhost:18001'
const API = `${IDENTITY}/api/identity/v1`
const MONGO_CONTAINER = process.env.E2E_MONGO_CONTAINER ?? 'sia-dev-mongo-1'
const SERVICE_SECRET = process.env.E2E_SERVICE_SECRET ?? 'dev-notification-secret'

export const run = randomBytes(4).toString('hex')

/**
 * fetch with one retry when a kept-alive connection was closed by the server while idle (uvicorn closes
 * idle connections after 5 s; Node may still reuse them: "other side closed").
 */
export async function req(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init)
  } catch (e) {
    if (e instanceof TypeError && /fetch failed/.test(e.message)) return fetch(url, init)
    throw e
  }
}
export const PASSWORD = `a long e2e password ${run}`

/** Evaluate JS in the dev Mongo (no host port is published) and return the printed JSON. */
export function mongo<T>(js: string): T {
  const out = execFileSync('docker', ['exec', MONGO_CONTAINER, 'mongosh', '--quiet', 'inventory', '--eval', `print(JSON.stringify((() => { ${js} })()))`], {
    encoding: 'utf8',
  })
  return JSON.parse(out.trim().split('\n').pop() ?? 'null') as T
}

let serviceToken: string | null = null
async function token(): Promise<string> {
  if (serviceToken) return serviceToken
  const r = await req(`${API}/internal/service-token`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ service: 'notification', secret: SERVICE_SECRET }),
  })
  if (!r.ok) throw new Error(`service token: ${r.status} ${await r.text()}`)
  serviceToken = ((await r.json()) as { token: string }).token
  return serviceToken
}

/** The code notification-svc would email: newest code of `kind` for the account with `email`. */
export async function claimCode(email: string, kind: 'verify_email' | 'reset_password' = 'verify_email'): Promise<string> {
  for (let i = 0; i < 20; i++) {
    const ref = mongo<string | null>(`
      const a = db.accounts.findOne({ email: ${JSON.stringify(email.toLowerCase())} });
      if (!a) return null;
      const t = db.temp.find({ accountId: a.id, kind: ${JSON.stringify(kind)} }).sort({ _id: -1 }).limit(1).toArray()[0];
      return t ? t.id : null;`)
    if (ref) {
      const r = await req(`${API}/internal/codes/${ref}`, { headers: { Authorization: `Bearer ${await token()}` } })
      if (r.ok) return String(((await r.json()) as { code: string }).code)
    }
    await new Promise((res) => setTimeout(res, 250))
  }
  throw new Error(`no ${kind} code for ${email}`)
}

async function post(path: string, body: unknown): Promise<Response> {
  return req(`${API}${path}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
}

/** An ACTIVE @cimh.edu.bb account, made through the public API (register + verify). */
export async function activeCimhAccount(prefix: string): Promise<string> {
  const email = `${prefix}.${run}@cimh.edu.bb`
  const r = await post('/auth/register', { firstname: 'E2e', lastname: prefix, email, password: PASSWORD, country: 'BB' })
  if (r.status !== 202) throw new Error(`register ${email}: ${r.status} ${await r.text()}`)
  const v = await post('/auth/verify', { email, code: await claimCode(email) })
  if (!v.ok) throw new Error(`verify ${email}: ${v.status}`)
  return email
}

/** First admins come from migration (CLAUDE.md); in dev the role is set directly. */
let adminSeq = 0
export async function adminAccount(): Promise<string> {
  // A new address per call: several specs in one run each need their own admin.
  const email = await activeCimhAccount(`admin${++adminSeq}`)
  mongo(`db.accounts.updateOne({ email: ${JSON.stringify(email)} }, { $set: { role: 'admin' }, $inc: { version: 1 } }); return true`)
  return email
}

/** RFC 6238 TOTP (SHA-1, 30 s, 6 digits) from a base32 key, as an authenticator app computes it. */
export function totp(secret: string, at = Date.now()): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  const clean = secret.replace(/[\s=]/g, '').toUpperCase()
  let bits = ''
  for (const ch of clean) bits += alphabet.indexOf(ch).toString(2).padStart(5, '0')
  const key = Buffer.from(bits.match(/.{8}/g)!.map((b) => parseInt(b, 2)))
  const counter = Buffer.alloc(8)
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 1000 / 30)))
  const h = createHmac('sha1', key).update(counter).digest()
  const o = h[h.length - 1]! & 15
  return String((h.readUInt32BE(o) & 0x7fffffff) % 1_000_000).padStart(6, '0')
}

/** Identity refuses a TOTP step twice (replay protection): wait for the next 30 s window. */
export async function nextTotpWindow(): Promise<void> {
  const left = 30_000 - (Date.now() % 30_000)
  await new Promise((r) => setTimeout(r, left + 500))
}

/** An admin with MFA already on (set up through the API, as the admin would in A-20). Returns the TOTP key. */
export async function adminWithMfa(): Promise<{ email: string; key: string }> {
  const email = await adminAccount()
  const login = await post('/auth/login', { email, password: PASSWORD, client: 'mobile' })
  if (!login.ok) throw new Error(`admin login: ${login.status}`)
  const auth = { Authorization: `Bearer ${((await login.json()) as { accessToken: string }).accessToken}`, 'content-type': 'application/json' }
  const setup = await req(`${API}/auth/mfa/setup`, { method: 'POST', headers: auth })
  const uri = ((await setup.json()) as { otpauthUri: string }).otpauthUri
  const key = new URL(uri).searchParams.get('secret')!
  const confirm = await req(`${API}/auth/mfa/confirm`, { method: 'POST', headers: auth, body: JSON.stringify({ totp: totp(key) }) })
  if (confirm.status !== 204) throw new Error(`mfa confirm: ${confirm.status} ${await confirm.text()}`)
  return { email, key }
}

/** An ACTIVE staff account (dev: the role is set directly, as for the first admin). */
let staffSeq = 0
export async function staffAccount(prefix = 'staff'): Promise<string> {
  const email = await activeCimhAccount(`${prefix}${++staffSeq}`)
  mongo(`db.accounts.updateOne({ email: ${JSON.stringify(email)} }, { $set: { role: 'staff' }, $inc: { version: 1 } }); return true`)
  return email
}

export const CATALOG = process.env.CATALOG_URL ?? 'http://localhost:18002'

/** A Bearer token for an account (mobile-style login), for setting up data through the APIs. */
export async function bearer(email: string): Promise<string> {
  const r = await req(`${API}/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email, password: PASSWORD, client: 'mobile' }),
  })
  if (!r.ok) throw new Error(`login ${email}: ${r.status} ${await r.text()}`)
  return ((await r.json()) as { accessToken: string }).accessToken
}

/** A product created through catalog-svc by a staff member; returns its id. */
export async function apiProduct(staffEmail: string, name: string, threshold = 0): Promise<string> {
  const r = await req(`${CATALOG}/api/catalog/v1/products`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${await bearer(staffEmail)}` },
    body: JSON.stringify({ name, type: 'EQUIP', department: 'Hydrology', sellable: false, probono: false, threshold }),
  })
  if (r.status !== 201) throw new Error(`product: ${r.status} ${await r.text()}`)
  return ((await r.json()) as { id: string }).id
}
