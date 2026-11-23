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
export type LineSource = S['LineSource']
export type Carrier = S['Carrier']
export type Shipment = S['Shipment']
export type ShipmentInput = S['ShipmentInput']
export type ShipmentPatch = S['ShipmentPatch']
export type FileRef = S['FileRef']

export type Currency = S['Currency']
export type RequestAction = NonNullable<OrderRequest['allowedActions']>[number]

export const orders = ordersClient()
const documents = documentsClient()

export const CARRIERS: { value: Carrier; title: string }[] = [
  { value: 'FEDEX', title: 'FedEx' },
  { value: 'DHL', title: 'DHL' },
  { value: 'UPS', title: 'UPS' },
  { value: 'HAND', title: 'Hand delivery' },
  { value: 'OTHER', title: 'Other' },
]

/** How a shipment's carrier reads: the name staff typed for OTHER, else the carrier's name. */
export function carrierLabel(s: Pick<Shipment, 'carrier' | 'carrierName'>): string {
  return s.carrierName || CARRIERS.find((c) => c.value === s.carrier)?.title || s.carrier
}

/** One place that still has lines to ship: CIMH stock (or Pro Bono), or one supplier shipping direct. */
export interface OpenSource {
  key: string
  source: LineSource
  supplier: string | null
  label: string
  lines: RequestLine[]
}

/** Lines not yet in a shipment, grouped by where they ship from (CIMH stock first, then each supplier). */
export function openSources(r: Pick<OrderRequest, 'type' | 'lines' | 'shipments'>): OpenSource[] {
  const shipped = new Set((r.shipments ?? []).flatMap((s) => s.lineIds))
  const out = new Map<string, OpenSource>()
  for (const ln of r.lines ?? []) {
    if (shipped.has(ln.lineId)) continue
    const fromSupplier = r.type !== 'PROBONO' && ln.source === 'SUPPLIER'
    const supplier = fromSupplier ? (ln.supplier ?? null) : null
    const key = fromSupplier ? `S:${supplier ?? ''}` : 'CIMH'
    if (!out.has(key)) {
      out.set(key, {
        key,
        source: fromSupplier ? 'SUPPLIER' : 'CIMH',
        supplier,
        label: fromSupplier ? (supplier ?? 'Supplier') : 'CIMH stock',
        lines: [],
      })
    }
    out.get(key)!.lines.push(ln)
  }
  return [...out.values()].sort((a, b) => (a.key === 'CIMH' ? -1 : b.key === 'CIMH' ? 1 : a.label.localeCompare(b.label)))
}

/** Who sends a shipment, in the customer's words. */
export function shipmentSender(s: Pick<Shipment, 'source' | 'supplier'>): string {
  if (s.source === 'SUPPLIER') return s.supplier ? `Sent directly by ${s.supplier}` : 'Sent directly by the supplier'
  if (s.source === 'CIMH') return 'Sent by CIMH'
  return 'Shipment'
}

export const FILE_KIND_LABELS: Record<FileRef['kind'], string> = {
  supplier_quote: 'Supplier quote',
  cimh_quote: 'CIMH quote',
  agreement: 'Agreement',
  signed_agreement: 'Signed agreement',
  invoice: 'Invoice',
  commercial_invoice: 'Commercial invoice',
  probono_invoice: 'Pro Bono invoice',
  payment_proof: 'Proof of payment',
  upload: 'File',
}

/** What the customer has to do now, if anything (list badge on S-10). */
export function customerActionNeeded(r: Pick<RequestSummary, 'status'>): string | null {
  if (r.status === 'QUOTED') return 'Quote to sign'
  return null
}

/** A request named by what was asked for ("Aneroid barometer and 2 more"); the id is only a reference. */
/**
 * Short reference for a record id. v2 ids are `<3 letters><32 hex>` (ORD, QTE, AUD…): "ORD…3f9a2c", the last six
 * characters being the part people read out. Other long ids keep their head and tail; short ones stay whole.
 * Pages show the full id somewhere visible (the record's header), never only in a tooltip.
 */
export function shortRef(id: string | null | undefined): string {
  if (!id) return ''
  const m = /^([A-Z]{3})([0-9a-f]{26,32})$/i.exec(id)
  if (m) return `${m[1]}…${m[2]!.slice(-6)}`
  return id.length > 14 ? `${id.slice(0, 6)}…${id.slice(-4)}` : id
}

export function requestTitle(firstItemName: string | null | undefined, lineCount: number, type: OrderRequest['type'] = 'PAID'): string {
  if (!firstItemName) return type === 'PROBONO' ? 'Pro Bono request' : 'Request'
  if (lineCount <= 1) return firstItemName
  return `${firstItemName} and ${lineCount - 1} more`
}

/** How long a quote is still valid ("12 days left"); `soon` within a week. Null without a date. */
export function expiryNote(iso: string | null | undefined): { days: number; text: string; soon: boolean } | null {
  if (!iso) return null
  const days = Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000)
  const text = days < 0 ? 'expired' : days === 0 ? 'expires today' : days === 1 ? '1 day left' : `${days} days left`
  return { days, text, soon: days <= 7 }
}

/** Steps of the status timeline, in order, for a request type (the current step is highlighted). */
export function statusSteps(type: OrderRequest['type']): RequestStatus[] {
  return type === 'PROBONO'
    ? ['SUBMITTED', 'APPROVED', 'PICKING', 'SHIPPED', 'DELIVERED']
    : ['SUBMITTED', 'QUOTING', 'QUOTED', 'ACCEPTED', 'PURCHASING', 'SHIPPED', 'DELIVERED']
}

export const isClosed = (s: RequestStatus) => s === 'CANCELLED' || s === 'REJECTED' || s === 'DECLINED'

export async function getRequest(id: string): Promise<OrderRequest> {
  return (await call(() => orders.GET('/requests/{requestId}', { params: { path: { requestId: id } } }))) as OrderRequest
}

type ActionPath =
  | '/requests/{requestId}/accept'
  | '/requests/{requestId}/mark-paid'
  | '/requests/{requestId}/decline'
  | '/requests/{requestId}/cancel'
  | '/requests/{requestId}/start-quoting'
  | '/requests/{requestId}/send-quote'
  | '/requests/{requestId}/reject-agreement'
  | '/requests/{requestId}/purchase-orders'
  | '/requests/{requestId}/approve'
  | '/requests/{requestId}/reject'
  | '/requests/{requestId}/shipments'
  | '/requests/{requestId}/deliver'

/** POST one state-changing action with the request's version. Returns the updated request. */
export async function act(r: Pick<OrderRequest, 'id' | 'version'>, path: ActionPath, body?: unknown): Promise<OrderRequest> {
  const params = { path: { requestId: r.id }, header: { 'If-Match': ifMatch(r.version) } }
  // Bodies differ per action; the server validates them strictly.
  return (await call(() => orders.POST(path as any, { params, body } as any))) as OrderRequest
}

/** Correct a recorded shipment (staff). */
export async function editShipment(
  r: Pick<OrderRequest, 'id' | 'version'>,
  shipmentId: string,
  body: ShipmentPatch,
): Promise<OrderRequest> {
  const params = { path: { requestId: r.id, shipmentId }, header: { 'If-Match': ifMatch(r.version) } }
  return (await call(() =>
    orders.PATCH('/requests/{requestId}/shipments/{shipmentId}', { params, body } as any),
  )) as OrderRequest
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

/** Upload a file to a request (document-svc). Customers may upload only `signed_agreement` (QUOTED) and
 * `payment_proof` (a delivered paid request). */
export async function uploadRequestFile(
  requestId: string,
  kind: 'signed_agreement' | 'payment_proof' | 'supplier_quote' | 'upload',
  file: File,
) {
  const form = new FormData()
  form.append('file', file)
  form.append('requestId', requestId)
  form.append('kind', kind)
  return (await call(() =>
    documents.POST('/files', { body: form as any, bodySerializer: (b: unknown) => b as FormData } as any),
  )) as { id: string; name: string }
}

/** A delivered paid request the customer still has to pay (no proof of payment sent yet). */
export const paymentDue = (r: { paymentStatus?: string | null }) => r.paymentStatus === 'DUE'

export const fileUrl = (id: string) => `${BASE.documents}/files/${encodeURIComponent(id)}`
/** The agreement a Send quote would email, drawn from the saved draft and marked as a preview (staff; never stored). */
export const agreementPreviewUrl = (requestId: string) => `${BASE.documents}/requests/${encodeURIComponent(requestId)}/agreement-preview`

/** Staff-built invoice / commercial invoice (SIA invoice builder; document-svc, legacy SIA layout). */
export type InvoiceKind = 'invoice' | 'commercial_invoice'
export interface InvoiceLineInput { lineId?: string | null; description: string; qty: number; unitPrice: string }
export interface InvoiceInput {
  kind: InvoiceKind
  number: string
  /** YYYY-MM-DD */
  date: string
  lines: InvoiceLineInput[]
  fees: string
  discount: string
  shipping: string
  emailCustomer: boolean
  emailStaff: boolean
}
export interface InvoiceDraft {
  kind: InvoiceKind
  number: string | null
  lines: InvoiceLineInput[]
  fees: string
  discount: string
  shipping: string
  /** Bill-to (invoice) or ship-to (commercial invoice), one row per printed line. */
  recipient: string[]
}

const reqPath = (requestId: string) => ({ params: { path: { requestId } } })

/** The lines, fee and shipping the builder starts from: every priced line, or only CIMH-stock lines (commercial). */
export async function getInvoiceDraft(requestId: string, kind: InvoiceKind): Promise<InvoiceDraft> {
  const opts = { params: { path: { requestId }, query: { kind } } }
  return (await call(() => documents.GET('/requests/{requestId}/invoice-draft' as any, opts as any))) as InvoiceDraft
}

/** The PDF as it would be created, marked as a preview (never stored). */
export async function previewInvoice(requestId: string, body: InvoiceInput): Promise<Blob> {
  const opts = { ...reqPath(requestId), body, parseAs: 'blob' }
  return (await call(() => documents.POST('/requests/{requestId}/invoice-preview' as any, opts as any))) as Blob
}

/** Store the invoice on the request; document-svc emails the customer and/or the staff invoice list as ticked. */
export async function createInvoice(requestId: string, body: InvoiceInput): Promise<{ id: string; name: string }> {
  const opts = { ...reqPath(requestId), body }
  return (await call(() => documents.POST('/requests/{requestId}/invoices' as any, opts as any))) as { id: string; name: string }
}

/** The supplier's own USD unit price and the rate, when staff converted a USD supplier quote to BBD. */
export interface PriceSource { unitPrice: string; currency: 'USD' | 'BBD'; rate: string }
export interface PricedLine {
  line: RequestLine
  source: LineSource | null
  /** Supplier name for SUPPLIER lines (customers see it: they hold the supplier's own quote). */
  supplier: string | null
  unitPrice: string | null
  total: string | null
  converted: PriceSource | null
}
export interface PricedQuote {
  version: number
  rows: PricedLine[]
  /** Estimated shipping per source: CIMH stock first, then each supplier. */
  shipping: { source: LineSource; label: string; amount: string }[]
  items: string
  fee: string | null
  /** What the customer signs for (agreement total); the sum of the parts when no agreement is there yet. */
  total: string
}

/**
 * "View and sign" (2026-11-17): the latest quote as the customer signs it. Staff fixed the source of every line,
 * so each line has one price; estimated shipping per source; the admin fee once; the total.
 */
export function pricedQuote(r: OrderRequest): PricedQuote {
  // The latest version staff sent (supplier quotes and the CIMH stock quote carry it).
  const qv = Math.max(0, ...(r.quotes ?? []).map((q) => q.version), r.cimhQuote?.version ?? 0)
  const supplier = new Map<string, { unitPrice: string; total: string; supplier: string | null; converted: PriceSource | null }>()
  const shipping: PricedQuote['shipping'] = []
  for (const q of r.quotes ?? []) {
    if (q.version !== qv || !q.lines.length) continue
    for (const l of q.lines) {
      const converted = q.sourceCurrency && l.sourceUnitPrice && q.exchangeRate
        ? { unitPrice: l.sourceUnitPrice, currency: q.sourceCurrency, rate: q.exchangeRate } : null // prettier-ignore
      supplier.set(l.lineId, { unitPrice: l.unitPrice, total: l.total, supplier: q.supplier ?? null, converted })
    }
    if (q.shippingEstimate != null) shipping.push({ source: 'SUPPLIER', label: q.supplier ?? 'Supplier', amount: q.shippingEstimate })
  }
  const cimh = new Map<string, { unitPrice: string; total: string }>()
  if (r.cimhQuote && r.cimhQuote.version === qv) {
    for (const l of r.cimhQuote.lines) cimh.set(l.lineId, l)
    if (r.cimhQuote.lines.length && r.cimhQuote.shippingEstimate != null)
      shipping.unshift({ source: 'CIMH', label: 'CIMH stock', amount: r.cimhQuote.shippingEstimate })
  }
  const rows: PricedLine[] = r.lines.map((line) => {
    const source: LineSource | null = line.source ?? (cimh.has(line.lineId) ? 'CIMH' : supplier.has(line.lineId) ? 'SUPPLIER' : null)
    if (source === 'CIMH') {
      const p = cimh.get(line.lineId)
      return { line, source, supplier: null, unitPrice: p?.unitPrice ?? null, total: p?.total ?? null, converted: null }
    }
    const p = supplier.get(line.lineId)
    return {
      line,
      source,
      supplier: line.supplier ?? p?.supplier ?? null,
      unitPrice: p?.unitPrice ?? null,
      total: p?.total ?? null,
      converted: p?.converted ?? null,
    }
  })
  const items = addCents(...rows.map((x) => x.total))
  const fee = r.adminFee && Number(r.adminFee) > 0 ? r.adminFee : null
  const signed = r.agreement && r.agreement.quoteVersion === qv ? r.agreement.total : undefined
  return { version: qv, rows, shipping, items, fee, total: signed ?? addCents(items, ...shipping.map((s) => s.amount), fee) }
}

/** The agreement of the current quote version, if staff have sent one (an older version's is void). */
export function currentAgreement(r: OrderRequest) {
  const ag = r.agreement
  return ag && ag.quoteVersion === pricedQuote(r).version ? ag : null
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
