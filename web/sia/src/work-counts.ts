/**
 * Work counts shared by the drawer and the dashboard (A-01). The request counts come exact from one call
 * (order-svc `GET /requests/counts`, 2026-11-23; was six capped list calls); low stock and approvals still
 * count one page (stop at 100: "100+"). Each source settles on its own: a failed one shows as an error with retry
 * instead of blocking the others. Definitions follow the order state machine (order_svc/domain.py):
 *  - verify: ACCEPTED (signed agreement uploaded; staff verify it when raising purchase orders)
 *  - fulfil: APPROVED, PICKING (Pro Bono) and PURCHASING (paid); each request counted once
 */
import { call, identity, inventory, orders, useSession } from '@cimh/web-app'
import { reactive, ref } from 'vue'

export type CountKey = 'new' | 'quoting' | 'quoted' | 'verify' | 'fulfil' | 'payment' | 'low' | 'approvals'
export type Count = { n: number | null; failed: boolean; exact?: boolean }

const PAGE = 100
const state = reactive<Record<CountKey, Count>>({
  new: { n: null, failed: false },
  quoting: { n: null, failed: false },
  quoted: { n: null, failed: false },
  verify: { n: null, failed: false },
  fulfil: { n: null, failed: false },
  payment: { n: null, failed: false },
  low: { n: null, failed: false },
  approvals: { n: null, failed: false },
})
const updatedAt = ref<Date | null>(null)
const loading = ref(false)

export const REQUEST_STATUS: Partial<Record<CountKey, string>> = {
  new: 'SUBMITTED',
  quoting: 'QUOTING',
  quoted: 'QUOTED',
  verify: 'ACCEPTED',
  fulfil: 'APPROVED,PICKING,PURCHASING',
}

const FROM_API: Partial<Record<CountKey, string>> = {
  new: 'new',
  quoting: 'quoting',
  quoted: 'quoted',
  verify: 'verify',
  fulfil: 'fulfil',
  payment: 'paymentDue',
}
async function requestCounts() {
  const keys = Object.keys(FROM_API) as CountKey[]
  for (const k of keys) state[k].failed = false
  try {
    const res = (await call(() => orders.GET('/requests/counts'))) as Record<string, number>
    for (const k of keys) Object.assign(state[k], { n: res[FROM_API[k]!] ?? 0, exact: true })
  } catch {
    for (const k of keys) state[k].failed = true
  }
}

async function one(key: CountKey, load: () => Promise<number>) {
  state[key].failed = false
  try {
    state[key].n = await load()
  } catch {
    state[key].failed = true
  }
}

export function useWorkCounts() {
  const session = useSession()
  async function refresh(only?: CountKey) {
    loading.value = true
    const jobs: Partial<Record<CountKey, () => Promise<number>>> = {
      low: async () => {
        const r = await call(() => inventory.GET('/stock/low', { params: { query: { limit: PAGE } } }))
        return r.nextCursor ? PAGE + 1 : r.items.length
      },
    }
    if (session.isAdmin)
      jobs.approvals = async () => {
        const r = await call(
          () => identity.GET('/admin/accounts', { params: { query: { status: 'PENDING_APPROVAL', limit: PAGE } } }),
        )
        return r.nextCursor ? PAGE + 1 : r.items.length
      }
    const keys = (only ? [only] : (Object.keys(jobs) as CountKey[])).filter((k) => jobs[k])
    const fromApi = !only || only in FROM_API
    await Promise.allSettled([...keys.map((k) => one(k, jobs[k]!)), ...(fromApi ? [requestCounts()] : [])])
    updatedAt.value = new Date()
    loading.value = false
  }
  return { counts: state, updatedAt, loading, refresh }
}

export const countLabel = (c: Count) =>
  c.failed ? '—' : c.n === null ? '…' : !c.exact && c.n > PAGE ? '100+' : String(c.n)
