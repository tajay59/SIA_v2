/**
 * Work counts shared by the drawer and the dashboard (A-01). One fetch per count, each settles on its own:
 * a failed count shows as an error with retry instead of blocking the others. Counts stop at 100 ("100+",
 * one page). Definitions follow the order state machine (order_svc/domain.py):
 *  - verify: ACCEPTED (signed agreement uploaded; staff verify it when raising purchase orders)
 *  - fulfil: APPROVED, PICKING (Pro Bono) and PURCHASING (paid); each request counted once
 */
import { call, identity, inventory, orders, type RequestSummary, useSession } from '@cimh/web-app'
import { reactive, ref } from 'vue'

export type CountKey = 'new' | 'quoting' | 'quoted' | 'signature' | 'verify' | 'fulfil' | 'low' | 'approvals'
export type Count = { n: number | null; failed: boolean }

const PAGE = 100
const state = reactive<Record<CountKey, Count>>({
  new: { n: null, failed: false },
  quoting: { n: null, failed: false },
  quoted: { n: null, failed: false },
  signature: { n: null, failed: false },
  verify: { n: null, failed: false },
  fulfil: { n: null, failed: false },
  low: { n: null, failed: false },
  approvals: { n: null, failed: false },
})
const updatedAt = ref<Date | null>(null)
const loading = ref(false)

export const REQUEST_STATUS: Partial<Record<CountKey, string>> = {
  new: 'SUBMITTED',
  quoting: 'QUOTING',
  quoted: 'QUOTED',
  signature: 'AWAITING_AGREEMENT',
  verify: 'ACCEPTED',
  fulfil: 'APPROVED,PICKING,PURCHASING',
}

async function requests(status: string): Promise<number> {
  const res = (await call(
    () => orders.GET('/requests', { params: { query: { scope: 'all', status, limit: PAGE } as never } }),
  )) as { items: RequestSummary[]; nextCursor: string | null }
  return res.nextCursor ? PAGE + 1 : res.items.length
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
    for (const [k, s] of Object.entries(REQUEST_STATUS)) jobs[k as CountKey] = () => requests(s!)
    if (session.isAdmin)
      jobs.approvals = async () => {
        const r = await call(
          () => identity.GET('/admin/accounts', { params: { query: { status: 'PENDING_APPROVAL', limit: PAGE } } }),
        )
        return r.nextCursor ? PAGE + 1 : r.items.length
      }
    const keys = only ? [only] : (Object.keys(jobs) as CountKey[])
    await Promise.allSettled(keys.map((k) => one(k, jobs[k]!)))
    updatedAt.value = new Date()
    loading.value = false
  }
  return { counts: state, updatedAt, loading, refresh }
}

export const countLabel = (c: Count) => (c.failed ? '—' : c.n === null ? '…' : c.n > PAGE ? '100+' : String(c.n))
