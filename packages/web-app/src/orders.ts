/**
 * Orders API access and helpers for SHOP and SIA (orders.openapi.yaml; APD S-07…S-12, A-01…A-04).
 *
 * State changes send `If-Match` with the request version; the server answers 409 for a stale version or an
 * action that isn't allowed now. Screens show buttons from `allowedActions`, so they never offer an
 * action the server would refuse.
 */
import { BASE, documentsClient, type OrdersComponents, ordersClient } from '@cimh/web-api'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { call, ifMatch } from './api'
import { newScanKey } from './inventory'

type S = OrdersComponents['schemas']
export type Cart = S['Cart']
export type CartLine = Cart['lines'][number]
export type RequestSummary = S['RequestSummary']
export type OrderRequest = S['Request']
export type RequestLine = S['Line']
export type RequestStatus = S['RequestStatus']
export type LineChoice = S['LineChoice']
export type Carrier = S['Carrier']
export type FileRef = S['FileRef']

export type Currency = S['Currency']
export type RequestAction = NonNullable<OrderRequest['allowedActions']>[number]

export const orders = ordersClient()
const documents = documentsClient()

export const CARRIERS: { value: Carrier; title: string }[] = [
  { value: 'FEDEX', title: 'FedEx' },
  { value: 'DHL', title: 'DHL' },
  { value: 'HAND', title: 'Hand delivery' },
]

export const FILE_KIND_LABELS: Record<FileRef['kind'], string> = {
  supplier_quote: 'Supplier quote',
  cimh_quote: 'CIMH quote',
  agreement: 'Agreement',
  signed_agreement: 'Signed agreement',
  invoice: 'Invoice',
  commercial_invoice: 'Commercial invoice',
  probono_invoice: 'Pro Bono invoice',
  upload: 'File',
}

/** What the customer has to do now, if anything (list badge on S-10). */
export function customerActionNeeded(r: Pick<RequestSummary, 'status'>): string | null {
  if (r.status === 'QUOTED') return 'Quote ready'
  if (r.status === 'AWAITING_AGREEMENT') return 'Agreement to sign'
  return null
}

/** Steps of the status timeline, in order, for a request type (the current step is highlighted). */
export function statusSteps(type: OrderRequest['type']): RequestStatus[] {
  return type === 'PROBONO'
    ? ['SUBMITTED', 'APPROVED', 'PICKING', 'SHIPPED', 'DELIVERED']
    : ['SUBMITTED', 'QUOTING', 'QUOTED', 'AWAITING_AGREEMENT', 'ACCEPTED', 'PURCHASING', 'SHIPPED', 'DELIVERED']
}

export const isClosed = (s: RequestStatus) => s === 'CANCELLED' || s === 'REJECTED' || s === 'DECLINED'

export async function getRequest(id: string): Promise<OrderRequest> {
  return (await call(() => orders.GET('/requests/{requestId}', { params: { path: { requestId: id } } }))) as OrderRequest
}

type ActionPath =
  | '/requests/{requestId}/agreement'
  | '/requests/{requestId}/accept'
  | '/requests/{requestId}/decline'
  | '/requests/{requestId}/cancel'
  | '/requests/{requestId}/start-quoting'
  | '/requests/{requestId}/send-quote'
  | '/requests/{requestId}/reject-agreement'
  | '/requests/{requestId}/purchase-orders'
  | '/requests/{requestId}/approve'
  | '/requests/{requestId}/reject'
  | '/requests/{requestId}/ship'
  | '/requests/{requestId}/deliver'

/** POST one state-changing action with the request's version. Returns the updated request. */
export async function act(r: Pick<OrderRequest, 'id' | 'version'>, path: ActionPath, body?: unknown): Promise<OrderRequest> {
  const params = { path: { requestId: r.id }, header: { 'If-Match': ifMatch(r.version) } }
  // Bodies differ per action; the server validates them strictly.
  return (await call(() => orders.POST(path as any, { params, body } as any))) as OrderRequest
}

export async function saveQuoteDraft(r: Pick<OrderRequest, 'id' | 'version'>, body: unknown): Promise<OrderRequest> {
  const params = { path: { requestId: r.id }, header: { 'If-Match': ifMatch(r.version) } }
  return (await call(() => orders.PUT('/requests/{requestId}/quote-draft', { params, body } as any))) as OrderRequest
}

/** Pick one scanned unit for a line (staff). One Idempotency-Key per physical scan. */
export async function pickForRequest(requestId: string, lineId: string, unit: string, key = newScanKey()): Promise<OrderRequest> {
  const params = { path: { requestId }, header: { 'Idempotency-Key': key } }
  return (await call(() =>
    orders.POST('/requests/{requestId}/picks', { params, body: { lineId, unit } } as any),
  )) as OrderRequest
}

/** Upload a file to a request (document-svc). Customers may upload only `signed_agreement`. */
export async function uploadRequestFile(requestId: string, kind: 'signed_agreement' | 'supplier_quote' | 'upload', file: File) {
  const form = new FormData()
  form.append('file', file)
  form.append('requestId', requestId)
  form.append('kind', kind)
  return (await call(() =>
    documents.POST('/files', { body: form as any, bodySerializer: (b: unknown) => b as FormData } as any),
  )) as { id: string; name: string }
}

export const fileUrl = (id: string) => `${BASE.documents}/files/${encodeURIComponent(id)}`

/** Lines priced from CIMH stock vs supplier, side by side (latest quote version only). */
export function quoteRows(r: OrderRequest) {
  const qv = Math.max(0, ...(r.quotes ?? []).map((q) => q.version))
  const supplier = new Map<string, { unitPrice: string; total: string; supplier?: string }>()
  for (const q of r.quotes ?? []) {
    if (q.version !== qv) continue
    for (const l of q.lines) supplier.set(l.lineId, { unitPrice: l.unitPrice, total: l.total, supplier: q.supplier })
  }
  const cimh = new Map<string, { unitPrice: string; total: string }>()
  if (r.cimhQuote && r.cimhQuote.version === qv) for (const l of r.cimhQuote.lines) cimh.set(l.lineId, l)
  return {
    version: qv,
    rows: r.lines.map((line) => ({ line, supplier: supplier.get(line.lineId) ?? null, cimh: cimh.get(line.lineId) ?? null })),
  }
}

export function addCents(...amounts: (string | null | undefined)[]): string {
  const cents = amounts.reduce((sum, a) => sum + (a ? Math.round(Number(a) * 100) : 0), 0)
  return (cents / 100).toFixed(2)
}

/** The customer's cart, shared by the product page (add), the top bar (badge) and the cart page. */
export const useCart = defineStore('cart', () => {
  const cart = ref<Cart | null>(null)
  const count = computed(() => cart.value?.lines.reduce((n, l) => n + l.qty, 0) ?? 0)

  async function load(): Promise<Cart> {
    cart.value = (await call(() => orders.GET('/cart'))) as Cart
    return cart.value
  }
  async function setQty(productId: string, qty: number): Promise<Cart> {
    cart.value = (await call(() =>
      orders.PUT('/cart/lines/{productId}', { params: { path: { productId } }, body: { qty } }),
    )) as Cart
    return cart.value
  }
  async function add(productId: string, qty: number): Promise<Cart> {
    const have = (cart.value ?? (await load())).lines.find((l) => l.productId === productId)?.qty ?? 0
    return setQty(productId, have + qty)
  }
  async function remove(productId: string): Promise<Cart> {
    cart.value = (await call(() =>
      orders.DELETE('/cart/lines/{productId}', { params: { path: { productId } } }),
    )) as Cart
    return cart.value
  }
  async function submit(body: {
    currency?: Currency
    shipTo: S['ShippingAddress']
    billTo?: S['ShippingAddress']
    notes?: string | null
  }): Promise<OrderRequest[]> {
    const params = { header: { 'Idempotency-Key': newScanKey() } }
    const out = (await call(() => orders.POST('/requests', { params, body } as any))) as { requests: OrderRequest[] }
    cart.value = cart.value ? { ...cart.value, lines: [], hasPaidLines: false, hasProbonoLines: false } : null
    return out.requests
  }
  function reset() {
    cart.value = null
  }
  return { cart, count, load, setQty, add, remove, submit, reset }
})
