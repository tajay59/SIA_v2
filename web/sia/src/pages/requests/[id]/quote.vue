<script setup lang="ts">
/**
 * A-04 quote builder (staff; QUOTING, or revising a QUOTED request), Graphite Console, "supplier tabs with viewer".
 *   "View and sign" (owner, 2026-11-17): staff fix where every line comes from; the customer only signs or cancels.
 *   One tab per supplier, plus CIMH stock. A supplier tab shows its quote files as large tiles and the selected file
 *   open on the left (QuoteDocument: pdf.js / img), and every request line on the right: typing a price gives the
 *   line to this supplier (taking it from CIMH stock or another supplier), a line held elsewhere says so and can be
 *   moved here. Every quote is in BBD; a supplier may quote in USD with its own BBD-per-USD rate. Each supplier and
 *   CIMH stock carry their estimated shipping to the customer.
 *   CIMH stock tab: lines fully in stock start there (the server prices them from the catalogue cost).
 *   Footer: supplier prices, CIMH estimate, shipping, admin fee (once), the total the customer signs, what is
 *   missing, Send quote (confirm dialog; the customer is emailed the quote and its agreement).
 * Each supplier has a local key, so renaming one keeps its prices; two suppliers may not share a name.
 * The draft saves itself (PUT quote-draft, If-Match) shortly after each change; a failed save never stops later
 * saves; a version conflict re-reads the version and saves the same draft again (local edits win). Leaving the
 * page saves a pending change first.
 */
import {
  act,
  agreementPreviewUrl,
  ApiError,
  call,
  catalog,
  getRequest,
  type OrderRequest,
  saveQuoteDraft,
  uploadRequestFile,
  useNotify,
  ShortRef,
} from '@cimh/web-app'
import { formatMoney } from '@cimh/web-ui'
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import IPdf from '~icons/material-symbols/picture-as-pdf-rounded'
import IImage from '~icons/material-symbols/image-rounded'
import IUpload from '~icons/material-symbols/upload-file-rounded'
import IClose from '~icons/material-symbols/close-rounded'
import IStock from '~icons/material-symbols/shelves-rounded'
import IWarn from '~icons/material-symbols/error-rounded'
import ICheck from '~icons/material-symbols/check-rounded'
import IPreview from '~icons/material-symbols/contract-rounded'
import ITodo from '~icons/material-symbols/radio-button-unchecked'
import QuoteDocument from '../../../components/quote/QuoteDocument.vue'
import { BTN } from '../../../request-queue'

definePage({ meta: { guard: 'staff', title: 'Quote builder', ownHeading: true } })
const ICON = {
  pdf: markRaw(IPdf), image: markRaw(IImage), upload: markRaw(IUpload), close: markRaw(IClose), stock: markRaw(IStock),
  warn: markRaw(IWarn), check: markRaw(ICheck), preview: markRaw(IPreview), todo: markRaw(ITodo),
} // prettier-ignore
const CURRENCIES = ['BBD', 'USD'] as const
const { xs } = useDisplay()
const route = useRoute('/requests/[id]/quote')
const router = useRouter()
const notify = useNotify()
const r = ref<OrderRequest | null>(null)
const loadFailed = ref(false)

/** `ship`: estimated shipping straight to the customer, in the supplier's currency. */
interface Supplier { key: number; name: string; fileIds: string[]; uploading: boolean; currency: 'BBD' | 'USD'; rate: string; ship: string }
/** A line comes from one place: CIMH stock (`cimh`) or one supplier, never both. */
interface LineState { cimh: boolean; supplier: number | null; unitPrice: string }
type Draft = {
  supplierQuotes: { supplier: string; currency?: 'BBD' | 'USD'; exchangeRate?: string | null; shippingEstimate?: string | null; fileIds: string[]; lines: { lineId: string; unitPrice: string }[] }[]
  cimh?: { lineIds: string[]; exchangeRate?: string | null; shippingEstimate?: string | null } | null
}

const suppliers = ref<Supplier[]>([])
const lines = reactive<Record<string, LineState>>({})
const exchangeRate = ref('')
const cimhShip = ref('') // estimated shipping of the CIMH stock lines, BBD
const fileMeta = reactive<Record<string, { name: string; mime: string }>>({})
let nextKey = 1
let ready = false

// ---- tabs: a supplier key, or 'cimh'
const tab = ref<number | 'cimh'>('cimh')
const openFile = reactive<Record<number, string>>({})
const current = computed(() => (typeof tab.value === 'number' ? suppliers.value.find((s) => s.key === tab.value) ?? null : null))
const anyCimhAvailable = computed(() => r.value?.lines.some((l) => l.cimhAvailable) ?? false)
/** Arrow keys, Home and End move between tabs (WAI-ARIA tabs pattern, automatic activation). */
function onTabKey(e: KeyboardEvent) {
  const order: (number | 'cimh')[] = [...suppliers.value.map((s) => s.key), ...(anyCimhAvailable.value || anyCimh.value ? ['cimh' as const] : [])]
  const i = order.indexOf(tab.value)
  const to = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: order.length - 1 }[e.key]
  if (to === undefined || !order.length) return
  e.preventDefault()
  tab.value = order[(to + order.length) % order.length]!
  void nextTick(() => document.getElementById(`tab-${tab.value}`)?.focus())
}

// ---- money (cents as integers; USD conversion half-up like the server)
const MONEY = /^\d{1,12}\.\d{2}$/
const RATE = /^\d+(\.\d{1,6})?$/
const cents = (s: string) => {
  const [a, b = '0'] = s.split('.')
  return Number(a) * 100 + Number(b.padEnd(2, '0').slice(0, 2))
}
const fromCents = (c: number) => `${Math.floor(c / 100)}.${String(c % 100).padStart(2, '0')}`
/** BBD cents → request currency cents (USD = BBD / rate, half-up), or null when the rate is missing. */
function convert(bbdCents: number): number | null {
  if (!usd.value) return bbdCents
  if (!rateOk.value) return null
  const [i, f = ''] = exchangeRate.value.split('.')
  const micro = BigInt(i) * 1_000_000n + BigInt(f.padEnd(6, '0'))
  const num = BigInt(bbdCents) * 1_000_000n
  let q = num / micro
  if ((num % micro) * 2n >= micro) q += 1n
  return Number(q)
}
/** Supplier USD cents → BBD cents (unit price × BBD-per-USD rate, half-up like the server), or null without a valid rate. */
function usdToBbd(usdCents: number, rate: string): number | null {
  if (!RATE.test(rate) || Number(rate) <= 0) return null
  const [i, f = ''] = rate.split('.')
  const micro = BigInt(i) * 1_000_000n + BigInt(f.padEnd(6, '0'))
  const num = BigInt(usdCents) * micro
  let q = num / 1_000_000n
  if ((num % 1_000_000n) * 2n >= 1_000_000n) q += 1n
  return Number(q)
}
const cur = computed(() => r.value?.currency ?? 'BBD')
const fmt = (c: number | null) => (c === null ? '—' : formatMoney(fromCents(c), cur.value))
const usd = computed(() => cur.value === 'USD')
const rateOk = computed(() => RATE.test(exchangeRate.value) && Number(exchangeRate.value) > 0)

// ---- reference data: catalogue cost of in-stock lines, the admin fee
const costBBD = reactive<Record<string, string | null>>({})
const adminFeeBBD = ref<string | null>(null)
const feeKnown = ref(false)
async function loadReference(x: OrderRequest) {
  const ids = [...new Set(x.lines.filter((l) => l.cimhAvailable).map((l) => l.productId))]
  await Promise.allSettled(
    ids.map(async (id) => {
      const p = (await call(() => catalog.GET('/products/{productId}', { params: { path: { productId: id } } }))) as { cost?: string | null }
      costBBD[id] = p.cost ?? null
    }),
  )
  try {
    const fees = (await call(() => catalog.GET('/settings/fees' as never))) as { types: { name: string; fee: string }[] }
    adminFeeBBD.value = fees.types.find((t) => t.name === 'admin')?.fee ?? '0.00'
    feeKnown.value = true
  } catch {
    feeKnown.value = false
  }
}

async function load() {
  ready = false
  loadFailed.value = false
  try {
    r.value = await getRequest(route.params.id)
  } catch (e) {
    loadFailed.value = true
    notify.report(e)
    return
  }
  const x = r.value
  if (!x.allowedActions?.includes('quote-draft')) return void router.replace(`/requests/${x.id}`)
  for (const f of x.files ?? []) fileMeta[f.id] = { name: f.name, mime: f.mime }
  const draft = (x as unknown as { quoteDraft?: Draft }).quoteDraft
  const latest = Math.max(0, ...(x.quotes ?? []).map((q) => q.version))
  // Start from the draft, else from the last sent quote (revising), else empty.
  const sq: Draft['supplierQuotes'] = draft?.supplierQuotes ??
    (x.quotes ?? []).filter((q) => q.version === latest).map((q) => ({ supplier: q.supplier ?? '', fileIds: q.fileIds ?? [],
      currency: q.sourceCurrency ?? 'BBD', exchangeRate: q.exchangeRate ?? null,
      shippingEstimate: q.sourceShippingEstimate ?? q.shippingEstimate ?? null,
      lines: q.lines.map((l) => ({ lineId: l.lineId, unitPrice: l.sourceUnitPrice ?? l.unitPrice })) }))  // prettier-ignore
  // Nothing priced yet: every line CIMH holds in full starts in CIMH stock.
  const fresh = !draft && !x.quotes?.length && !x.cimhQuote
  const cimhIds = draft?.cimh?.lineIds ?? x.cimhQuote?.lines.map((l) => l.lineId) ?? []
  suppliers.value = sq.map((s) => ({ key: nextKey++, name: s.supplier, fileIds: [...s.fileIds], uploading: false,
    currency: s.currency ?? 'BBD', rate: s.exchangeRate ?? '', ship: s.shippingEstimate ?? '' }))  // prettier-ignore
  for (const s of suppliers.value) if (s.fileIds[0]) openFile[s.key] = s.fileIds[0]
  for (const l of x.lines) {
    const i = sq.findIndex((s) => s.lines.some((y) => y.lineId === l.lineId))
    // A draft from before 2026-11-17 could hold a line in both places: the supplier price wins.
    lines[l.lineId] = {
      cimh: i < 0 && !!l.cimhAvailable && (fresh || cimhIds.includes(l.lineId)),
      supplier: i >= 0 ? suppliers.value[i]!.key : null,
      unitPrice: i >= 0 ? (sq[i]!.lines.find((y) => y.lineId === l.lineId)?.unitPrice ?? '') : '',
    }
  }
  exchangeRate.value = draft?.cimh?.exchangeRate ?? x.cimhQuote?.exchangeRate ?? ''
  cimhShip.value = draft?.cimh?.shippingEstimate ?? x.cimhQuote?.shippingEstimate ?? ''
  tab.value = suppliers.value[0]?.key ?? 'cimh'
  void loadReference(x)
  await nextTick()
  ready = true
}
watch(() => route.params.id, () => void load(), { immediate: true })

// ---- validation
const nameOf = (key: number | null) => suppliers.value.find((s) => s.key === key)?.name.trim() ?? ''
const dupName = (s: Supplier) =>
  !!s.name.trim() && suppliers.value.some((o) => o !== s && o.name.trim().toLowerCase() === s.name.trim().toLowerCase())
const priceError = (s: LineState) => (s.supplier !== null && s.unitPrice && !MONEY.test(s.unitPrice) ? 'Use 2 decimals, e.g. 120.00' : '')
const lineReady = (id: string) => {
  const v = lines[id]
  return !!v && (v.cimh || (v.supplier !== null && !!nameOf(v.supplier) && MONEY.test(v.unitPrice)))
}
const missing = computed(() => r.value?.lines.filter((l) => !lineReady(l.lineId)) ?? [])
const unsavedPrices = computed(() => Object.values(lines).filter((v) => v.supplier !== null && v.unitPrice && !MONEY.test(v.unitPrice)).length)
const anyCimh = computed(() => Object.values(lines).some((v) => v.cimh))
const feeCents = computed(() => (feeKnown.value && adminFeeBBD.value ? cents(adminFeeBBD.value) : 0))
// The server needs the rate on USD requests when CIMH stock is offered or an admin fee applies.
const needsRate = computed(() => usd.value && (anyCimh.value || !feeKnown.value || feeCents.value > 0) && !rateOk.value)
const rateError = computed(() => {
  if (!usd.value || !exchangeRate.value) return needsRate.value ? 'Required: CIMH stock or the admin fee is priced in BBD' : ''
  if (!RATE.test(exchangeRate.value)) return 'A number, up to 6 decimals, e.g. 2.0'
  if (Number(exchangeRate.value) <= 0) return 'Must be more than 0'
  return ''
})
const dupes = computed(() => suppliers.value.some(dupName))
const unnamed = computed(() => suppliers.value.filter((s) => !s.name.trim() && usedBy(s)).length)
// A supplier quoted in USD (BBD requests only) needs its own BBD-per-USD rate.
const supUsd = (s: Supplier | undefined | null) => !usd.value && s?.currency === 'USD'
const supRateError = (s: Supplier) => {
  if (!supUsd(s)) return ''
  if (!s.rate) return 'Required for a USD quote'
  if (!RATE.test(s.rate)) return 'A number, up to 6 decimals, e.g. 2.0'
  return Number(s.rate) > 0 ? '' : 'Must be more than 0'
}
const ratesMissing = computed(() => suppliers.value.filter((s) => supRateError(s)).length)
// Every place that supplies a line carries its estimated shipping (0.00 is fine; empty is not).
const SHIP_HINT = 'Enter the estimated shipping (0.00 if there is none)'
const shipError = (s: Supplier) => (usedBy(s) && !MONEY.test(s.ship) ? (s.ship ? 'Use 2 decimals, e.g. 45.00' : SHIP_HINT) : '')
const cimhShipError = computed(() => (anyCimh.value && !MONEY.test(cimhShip.value) ? (cimhShip.value ? 'Use 2 decimals, e.g. 45.00' : SHIP_HINT) : ''))
const shipMissing = computed(() => suppliers.value.filter((s) => shipError(s)).length + (cimhShipError.value ? 1 : 0))
const supOf = (key: number | null) => suppliers.value.find((s) => s.key === key)
/** The currency staff type a supplier's prices in: its own on BBD requests, else the request's. */
const typeCur = (s: Supplier) => (supUsd(s) ? 'USD' : cur.value)

// ---- field messages: a wrong value says so at once; a missing one only after Send or Preview was pressed
const tried = ref(false)
const nameMsg = (s: Supplier) =>
  dupName(s) ? 'Another supplier has this name' : tried.value && !s.name.trim() && usedBy(s) ? 'Name the supplier' : ''
function rateMsg(s: Supplier) {
  if (!supUsd(s) || (!s.rate && !tried.value)) return ''
  return s.rate ? supRateError(s) : 'Needed for a USD quote'
}
function shipMsg(s: Supplier) {
  if (s.ship && !MONEY.test(s.ship)) return 'Use 2 decimals, e.g. 45.00'
  return tried.value && !s.ship && usedBy(s) ? 'Needed: 0.00 if none' : ''
}
const cimhShipMsg = computed(() => {
  if (cimhShip.value && !MONEY.test(cimhShip.value)) return 'Use 2 decimals, e.g. 45.00'
  return tried.value && !cimhShip.value && anyCimh.value ? 'Needed: 0.00 if none' : ''
})
const cimhRateMsg = computed(() => (exchangeRate.value || tried.value ? rateError.value : ''))
const supFlag = (s: Supplier) => !!(nameMsg(s) || rateMsg(s) || shipMsg(s))
const todoClass = computed(() => (tried.value ? 'err-line' : 'todo-line'))
const todoIcon = computed(() => (tried.value ? ICON.warn : ICON.todo))

// ---- draft body: only valid, unique suppliers and valid prices travel; the rest stays on screen
function draftBody(): Draft {
  return {
    supplierQuotes: suppliers.value
      .filter((s) => s.name.trim() && !dupName(s))
      .map((s) => ({
        supplier: s.name.trim(),
        ...(usd.value ? {} : { currency: s.currency, exchangeRate: s.currency === 'USD' && !supRateError(s) ? s.rate : null }),
        shippingEstimate: MONEY.test(s.ship) ? s.ship : null,
        fileIds: s.fileIds,
        lines: Object.entries(lines)
          .filter(([, v]) => v.supplier === s.key && MONEY.test(v.unitPrice))
          .map(([lineId, v]) => ({ lineId, unitPrice: v.unitPrice })),
      })),
    cimh: {
      lineIds: Object.entries(lines).filter(([, v]) => v.cimh).map(([k]) => k),
      exchangeRate: rateOk.value ? exchangeRate.value : null,
      shippingEstimate: MONEY.test(cimhShip.value) ? cimhShip.value : null,
    },
  }
}

// ---- autosave
const saveState = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')
const savedAt = ref<Date | null>(null)
let timer: ReturnType<typeof setTimeout> | undefined
let pending = false
let chain: Promise<void> = Promise.resolve()
async function saveOnce() {
  if (!r.value) return
  saveState.value = 'saving'
  const body = draftBody()
  try {
    try {
      r.value = await saveQuoteDraft(r.value, body)
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 409)) throw e
      // Someone (or another tab) changed the request: take the new version, keep this draft.
      const fresh = await getRequest(r.value.id)
      if (!fresh.allowedActions?.includes('quote-draft')) throw e
      r.value = await saveQuoteDraft(fresh, body)
    }
    saveState.value = 'saved'
    savedAt.value = new Date()
  } catch (e) {
    saveState.value = 'error'
    notify.report(e)
    throw e
  }
}
/** Queue a save after any earlier one; an earlier failure never blocks this one. */
function save(): Promise<void> {
  pending = false
  clearTimeout(timer)
  const run = chain.catch(() => undefined).then(saveOnce)
  chain = run
  return run
}
watch(
  [suppliers, lines, exchangeRate, cimhShip],
  () => {
    if (!ready) return
    pending = true
    clearTimeout(timer)
    timer = setTimeout(() => void save().catch(() => undefined), 800)
  },
  { deep: true },
)
const statusText = computed(() => {
  const t = savedAt.value?.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  if (saveState.value === 'saving') return 'Saving…'
  if (saveState.value === 'error') return 'Not saved'
  if (saveState.value === 'saved') return `Draft saved ${t}`
  return ''
})
// Leaving with a change still waiting: save it first; closing the tab: ask.
onBeforeRouteLeave(async () => {
  if (pending) await save().catch(() => undefined)
})
const beforeUnload = (e: BeforeUnloadEvent) => {
  if (pending || saveState.value === 'saving') e.preventDefault()
}
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', beforeUnload)
  clearTimeout(timer)
})

// ---- suppliers
function addSupplier() {
  const s: Supplier = { key: nextKey++, name: '', fileIds: [], uploading: false, currency: 'BBD', rate: '', ship: '' }
  suppliers.value.push(s)
  tab.value = s.key
  void nextTick(() => (document.getElementById(`sup-name-${s.key}`) as HTMLInputElement | null)?.focus())
}
const usedBy = (s: Supplier) => Object.values(lines).filter((v) => v.supplier === s.key).length
const removing = ref<Supplier | null>(null)
function askRemove(s: Supplier) {
  if (usedBy(s)) removing.value = s
  else removeSupplier(s)
}
function removeSupplier(s: Supplier) {
  const i = suppliers.value.indexOf(s)
  suppliers.value = suppliers.value.filter((x) => x !== s)
  for (const v of Object.values(lines)) if (v.supplier === s.key) Object.assign(v, { supplier: null, unitPrice: '' })
  removing.value = null
  tab.value = suppliers.value[Math.max(0, i - 1)]?.key ?? 'cimh'
}

// ---- files: large tiles; the selected one opens in the viewer
const dragging = ref(false)
const isPdf = (id: string) => fileMeta[id]?.mime === 'application/pdf'
async function attach(s: Supplier, files: FileList | File[] | null) {
  const list = files ? Array.from(files) : []
  if (!r.value || !list.length) return
  s.uploading = true
  try {
    for (const f of list) {
      const ref = await uploadRequestFile(r.value.id, 'supplier_quote', f)
      fileMeta[ref.id] = { name: ref.name || f.name, mime: f.type || 'application/pdf' }
      s.fileIds.push(ref.id)
      openFile[s.key] = ref.id
    }
  } catch (e) {
    notify.report(e)
  } finally {
    s.uploading = false
  }
}
function onDrop(s: Supplier, e: DragEvent) {
  dragging.value = false
  void attach(s, e.dataTransfer?.files ?? null)
}
function detach(s: Supplier, id: string) {
  s.fileIds = s.fileIds.filter((x) => x !== id)
  if (openFile[s.key] === id) openFile[s.key] = s.fileIds[0] ?? ''
}

// ---- prices in a supplier tab: typing gives the line to this supplier (out of CIMH stock), clearing it frees it
function priceFor(s: Supplier, lineId: string) {
  const v = lines[lineId]
  return v?.supplier === s.key ? v.unitPrice : ''
}
function setPrice(s: Supplier, lineId: string, value: string) {
  const v = lines[lineId]
  if (!v) return
  const t = value.trim()
  if (t) Object.assign(v, { supplier: s.key, unitPrice: t, cimh: false })
  else if (v.supplier === s.key) Object.assign(v, { supplier: null, unitPrice: '' })
}
function moveHere(s: Supplier, lineId: string) {
  const v = lines[lineId]
  if (!v) return
  Object.assign(v, { supplier: s.key, unitPrice: '', cimh: false })
  void nextTick(() => (document.getElementById(`price-${s.key}-${lineId}`) as HTMLInputElement | null)?.focus())
}
/** CIMH stock tab: taking a line from stock frees it from any supplier price (one place per line). */
function setStock(lineId: string, on: boolean) {
  const v = lines[lineId]
  if (!v) return
  if (on) Object.assign(v, { cimh: true, supplier: null, unitPrice: '' })
  else v.cimh = false
}
const holder = (lineId: string) => {
  const v = lines[lineId]
  return v?.supplier !== null && v?.supplier !== undefined ? supOf(v.supplier) ?? null : null
}
/** A line held by another supplier: its own currency, plus BBD when it quoted in USD. */
function heldPrice(lineId: string) {
  const v = lines[lineId]
  const s = holder(lineId)
  if (!v?.unitPrice || !s) return '—'
  const own = `${typeCur(s)} ${v.unitPrice}`
  const u = supUnit(lineId)
  return supUsd(s) && u !== null ? `${own} (${fmt(u)})` : own
}
const linesOf = (s: Supplier) => r.value?.lines.filter((l) => lines[l.lineId]?.supplier === s.key).length ?? 0

// ---- keyboard: Enter in a price moves down the column; the missing list jumps to the line
function nextPrice(s: Supplier, lineId: string) {
  const ids = r.value?.lines.map((l) => l.lineId) ?? []
  for (const id of ids.slice(ids.indexOf(lineId) + 1)) {
    const el = document.getElementById(`price-${s.key}-${id}`) as HTMLInputElement | null
    if (el) return el.focus()
  }
}
async function jumpTo(lineId: string) {
  const v = lines[lineId]
  tab.value = v?.supplier ?? current.value?.key ?? suppliers.value[0]?.key ?? 'cimh'
  await nextTick()
  const id = typeof tab.value === 'number' ? `price-${tab.value}-${lineId}` : `offer-${lineId}`
  const el = document.getElementById(id) as HTMLInputElement | null
  el?.closest('.lrow')?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  el?.focus({ preventScroll: true })
}

// ---- figures
const qtyOf = (lineId: string) => r.value?.lines.find((l) => l.lineId === lineId)?.qty ?? 0
function cimhUnit(lineId: string): number | null {
  const l = r.value?.lines.find((x) => x.lineId === lineId)
  const c = l ? costBBD[l.productId] : null
  return c ? convert(cents(c)) : null
}
const cimhTotal = (lineId: string) => {
  const u = cimhUnit(lineId)
  return u === null ? null : u * qtyOf(lineId)
}
/** A supplier line's unit price in the request currency (USD supplier prices converted to BBD). */
function supUnit(lineId: string): number | null {
  const v = lines[lineId]
  if (!v || v.supplier === null || !MONEY.test(v.unitPrice)) return null
  const s = supOf(v.supplier)
  return supUsd(s) ? usdToBbd(cents(v.unitPrice), s!.rate) : cents(v.unitPrice)
}
const supTotal = (lineId: string) => {
  const u = supUnit(lineId)
  return u === null ? null : u * qtyOf(lineId)
}
const noCost = computed(() => r.value?.lines.filter((l) => lines[l.lineId]?.cimh && !costBBD[l.productId] && l.productId in costBBD) ?? [])
/** A supplier's estimated shipping in the request currency (its USD figure converted at its rate). */
function supShip(s: Supplier): number | null {
  if (!MONEY.test(s.ship)) return null
  return supUsd(s) ? usdToBbd(cents(s.ship), s.rate) : cents(s.ship)
}
/** What the customer signs for: every line once, estimated shipping per source, the admin fee once. */
const totals = computed(() => {
  const x = r.value
  if (!x) return null
  let sup = 0
  let cimh = 0
  let ship = 0
  let complete = true
  for (const l of x.lines) {
    const v = lines[l.lineId]
    const t = v?.cimh ? cimhTotal(l.lineId) : supTotal(l.lineId)
    if (t === null) complete = false
    else if (v?.cimh) cimh += t
    else sup += t
  }
  for (const s of suppliers.value) {
    if (!usedBy(s)) continue
    const c = supShip(s)
    if (c === null) complete = false
    else ship += c
  }
  if (anyCimh.value) {
    const c = MONEY.test(cimhShip.value) ? convert(cents(cimhShip.value)) : null
    if (c === null) complete = false
    else ship += c
  }
  const fee = feeKnown.value ? convert(feeCents.value) : null
  const total = complete && fee !== null ? sup + cimh + ship + fee : null
  return { sup, cimh, ship, fee, total, complete }
})

// ---- send
const sending = ref(false)
const problems = computed(
  () => missing.value.length + (needsRate.value ? 1 : 0) + (dupes.value ? 1 : 0) + unsavedPrices.value + ratesMissing.value + unnamed.value + shipMissing.value,
)
/** The review dialog: the agreement as the customer will get it (a marked preview) beside what is sent. Opened by
 * Preview agreement or Send quote; both can email it from there. */
const review = ref<'preview' | 'send' | null>(null)
const previewKey = ref(0)
/** A refused preview (the server says why in the document pane) offers no Email: that send would be refused too. */
const previewState = ref<'loading' | 'ready' | 'error'>('loading')
// A quote may be CIMH stock only (no supplier quotes), so every place a version is kept counts.
const nextVersion = computed(() => {
  const x = r.value
  const sent = [...(x?.quotes ?? []).map((q) => q.version), x?.cimhQuote?.version ?? 0, x?.agreement?.quoteVersion ?? 0]
  return Math.max(0, ...sent) + 1
})
const pricedLines = computed(() => (r.value?.lines.length ?? 0) - missing.value.length)
/** Never disabled for missing input: a press marks what is missing and goes to the first gap. */
async function askReview(mode: 'preview' | 'send') {
  if (problems.value) {
    tried.value = true
    return goToProblem()
  }
  // The preview is drawn from the saved draft, so a change still waiting (or a failed save) is saved first; if
  // that fails the review stays closed: the PDF would show an older draft than the screen ("Not saved" + toast).
  try {
    if (pending || saveState.value === 'error') await save()
    else await chain
  } catch {
    return
  }
  previewKey.value++
  previewState.value = 'loading'
  review.value = mode
}
async function goToProblem() {
  if (missing.value[0]) return jumpTo(missing.value[0].lineId)
  const s = suppliers.value.find(supFlag)
  if (s) {
    tab.value = s.key
    await nextTick()
    const field = nameMsg(s) ? 'name' : rateMsg(s) ? 'rate' : 'ship'
    return document.getElementById(`sup-${field}-${s.key}`)?.focus()
  }
  if (cimhRateMsg.value || cimhShipMsg.value) {
    tab.value = 'cimh'
    await nextTick()
    return document.getElementById(cimhRateMsg.value ? 'cimh-rate' : 'cimh-ship')?.focus()
  }
  document.querySelector<HTMLElement>('.qfoot-problems')?.focus()
}
async function send() {
  if (!r.value || sending.value) return
  sending.value = true
  try {
    await save()
    const version = nextVersion.value
    r.value = await act(r.value, '/requests/{requestId}/send-quote', undefined)
    notify.toast(`Quote version ${r.value.agreement?.quoteVersion ?? version} sent to the customer`, 'success')
    review.value = null
    await router.push(`/requests/${r.value.id}`)
  } catch (e) {
    review.value = null // the reason shows on the page (toast, marked prices)
    if (e instanceof ApiError) notify.report(e)
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <div class="qb">
    <!-- The way back sits in the title row once loaded: every pixel of height goes to the quote document. -->
    <nav v-if="!r" class="crumbs" aria-label="Breadcrumb">
      <v-btn :to="`/requests/${route.params.id}`" variant="text" class="m3" :prepend-icon="BTN.back">Request</v-btn>
    </nav>

    <div v-if="loadFailed" class="state">
      <p class="t-body-lg">Couldn't load this request.</p>
      <v-btn variant="outlined" class="m3" :prepend-icon="BTN.retry" @click="load">Retry</v-btn>
    </div>
    <div v-else-if="!r" class="console-skel sk" />

    <template v-else>
      <header class="qb-head">
        <nav class="crumbs" aria-label="Breadcrumb">
          <v-btn :to="`/requests/${route.params.id}`" variant="text" class="m3" :prepend-icon="BTN.back">Request</v-btn>
        </nav>
        <div class="qb-id">
          <h1 class="qb-title">
            {{ r.status === 'QUOTED' ? 'Revise quote' : 'Build quote' }} · {{ r.lines.length }} item{{ r.lines.length > 1 ? 's' : '' }}
            for {{ r.organisationName || r.customerName }}
          </h1>
          <p class="qb-sub">
            <span class="console-mono"><ShortRef :id="r.id" /></span> · the customer sees
            <strong class="console-mono">{{ r.currency }}</strong>
          </p>
        </div>
        <p class="save" :class="saveState" role="status">
          <span>{{ statusText }}</span>
          <button v-if="saveState === 'error'" type="button" class="console-retry" @click="save().catch(() => undefined)">Retry</button>
        </p>
      </header>

      <section class="frame" aria-label="Quote">
        <div class="tabs">
        <div class="tablist" role="tablist" aria-label="Offers" @keydown="onTabKey">
          <button
            v-for="s in suppliers"
            :id="`tab-${s.key}`"
            :key="s.key"
            type="button"
            role="tab"
            class="tab"
            :class="{ on: tab === s.key }"
            :aria-selected="tab === s.key"
            :tabindex="tab === s.key ? 0 : -1"
            aria-controls="offer-panel"
            @click="tab = s.key"
          >
            <span class="tab-name">{{ s.name.trim() || 'New supplier' }}</span>
            <span class="tab-meta console-mono">{{ usd ? cur : s.currency }}<template v-if="supUsd(s) && !supRateError(s)">{{ ' at ' + s.rate }}</template> · {{ linesOf(s) }} of {{ r.lines.length }} priced</span>
            <span v-if="supFlag(s)" class="tab-flag" aria-label="needs attention" />
          </button>
          <button
            v-if="anyCimhAvailable || anyCimh"
            id="tab-cimh"
            type="button"
            role="tab"
            class="tab"
            :class="{ on: tab === 'cimh' }"
            :aria-selected="tab === 'cimh'"
            :tabindex="tab === 'cimh' ? 0 : -1"
            aria-controls="offer-panel"
            @click="tab = 'cimh'"
          >
            <span class="tab-name">CIMH stock</span>
            <span class="tab-meta console-mono">{{ Object.values(lines).filter((v) => v.cimh).length }} of {{ r.lines.length }} from stock</span>
          </button>
        </div>
          <button type="button" class="tab tab-add" aria-label="Add supplier" @click="addSupplier">
            <v-icon :icon="BTN.add" size="18" />Add<span class="add-word"> supplier</span>
          </button>
        </div>

        <!-- Supplier tab: settings strip, then the document beside the lines. -->
        <!-- String key: v-if branches get automatic keys 0, 1, 2, and a numeric supplier key collided with them. -->
        <div v-if="current" id="offer-panel" :key="`sup-${current.key}`" role="tabpanel" :aria-labelledby="`tab-${current.key}`" class="panel-body">
          <!-- The supplier's terms: who, the currency of their quote, its rate, their shipping. A caption over each
               field (labels inside the fields were cut off) and one message line under each, so the row never jumps. -->
          <div class="terms" role="group" :aria-label="`Terms of the quote from ${current.name.trim() || 'this supplier'}`">
            <div class="term term-name">
              <label class="term-label" :for="`sup-name-${current.key}`">Supplier</label>
              <v-text-field
                :id="`sup-name-${current.key}`"
                v-model="current.name"
                placeholder="Name as on their quote"
                hide-details
                :error="!!nameMsg(current)"
                :aria-describedby="`sup-name-msg-${current.key}`"
              />
              <p :id="`sup-name-msg-${current.key}`" class="term-msg" :class="{ bad: nameMsg(current) }">
                <template v-if="nameMsg(current)"><v-icon :icon="ICON.warn" size="14" />{{ nameMsg(current) }}</template>
                <template v-else>The customer sees this name</template>
              </p>
            </div>
            <fieldset v-if="!usd" class="term term-cur">
              <legend class="term-label">Their currency</legend>
              <div class="seg">
                <template v-for="c in CURRENCIES" :key="c">
                  <input :id="`sup-cur-${current.key}-${c}`" v-model="current.currency" type="radio" class="seg-input" :name="`sup-cur-${current.key}`" :value="c" />
                  <label :for="`sup-cur-${current.key}-${c}`" class="seg-btn">
                    <v-icon v-if="current.currency === c" :icon="ICON.check" size="18" />{{ c }}
                  </label>
                </template>
              </div>
              <p class="term-msg">{{ current.currency === 'USD' ? 'Type their USD prices' : 'Prices as on their quote' }}</p>
            </fieldset>
            <div v-if="supUsd(current)" class="term term-rate">
              <label class="term-label" :for="`sup-rate-${current.key}`">Exchange rate</label>
              <v-text-field
                :id="`sup-rate-${current.key}`"
                v-model="current.rate"
                prefix="1 USD ="
                suffix="BBD"
                placeholder="rate"
                persistent-placeholder
                inputmode="decimal"
                class="mono-input"
                hide-details
                :error="!!rateMsg(current)"
                :aria-describedby="`sup-rate-msg-${current.key}`"
              />
              <p :id="`sup-rate-msg-${current.key}`" class="term-msg" :class="{ bad: rateMsg(current) }">
                <template v-if="rateMsg(current)"><v-icon :icon="ICON.warn" size="14" />{{ rateMsg(current) }}</template>
                <template v-else>The customer sees BBD</template>
              </p>
            </div>
            <div class="term term-ship">
              <label class="term-label" :for="`sup-ship-${current.key}`">Estimated shipping</label>
              <v-text-field
                :id="`sup-ship-${current.key}`"
                v-model="current.ship"
                :prefix="typeCur(current)"
                placeholder="amount"
                persistent-placeholder
                inputmode="decimal"
                class="mono-input"
                hide-details
                :error="!!shipMsg(current)"
                :aria-describedby="`sup-ship-msg-${current.key}`"
              />
              <p :id="`sup-ship-msg-${current.key}`" class="term-msg" :class="{ bad: shipMsg(current) }">
                <template v-if="shipMsg(current)"><v-icon :icon="ICON.warn" size="14" />{{ shipMsg(current) }}</template>
                <template v-else>To the customer, 0.00 if none</template>
              </p>
            </div>
            <v-btn
              variant="outlined"
              class="m3 m3-danger sup-remove"
              :aria-label="`Remove ${current.name.trim() || 'this supplier'}`"
              title="Remove supplier"
              @click="askRemove(current)"
            >
              <v-icon :icon="BTN.remove" size="20" /><span class="rm-word">Remove supplier</span>
            </v-btn>
          </div>

          <div class="split">
            <!-- Left: the quote files as large tiles, the selected one open below. -->
            <div class="viewer" :class="{ drag: dragging }" @dragover.prevent="dragging = true" @dragleave.self="dragging = false" @drop.prevent="onDrop(current, $event)">
              <ul v-if="current.fileIds.length" class="tiles" aria-label="Quote files">
                <li v-for="f in current.fileIds" :key="f" class="tile-wrap">
                  <button
                    type="button"
                    class="tile"
                    :class="{ on: openFile[current.key] === f }"
                    :aria-pressed="openFile[current.key] === f"
                    :title="fileMeta[f]?.name"
                    @click="openFile[current.key] = f"
                  >
                    <v-icon :icon="isPdf(f) ? ICON.pdf : ICON.image" size="56" class="tile-icon" />
                    <span class="tile-name">{{ fileMeta[f]?.name ?? 'Quote file' }}</span>
                    <span class="tile-kind">{{ isPdf(f) ? 'PDF' : 'Image' }}</span>
                  </button>
                  <button type="button" class="tile-x" :aria-label="`Remove ${fileMeta[f]?.name ?? 'file'} from this quote`" @click="detach(current, f)">
                    <v-icon :icon="ICON.close" size="16" />
                  </button>
                </li>
                <li class="tile-wrap">
                  <label class="tile tile-add" :class="{ busy: current.uploading }">
                    <input
                      type="file"
                      class="sr-only"
                      accept=".pdf,.jpg,.jpeg,.png,.webp"
                      multiple
                      :disabled="current.uploading"
                      @change="(e) => { attach(current!, (e.target as HTMLInputElement).files); (e.target as HTMLInputElement).value = '' }"
                    />
                    <v-progress-circular v-if="current.uploading" indeterminate size="40" width="3" color="primary" />
                    <v-icon v-else :icon="ICON.upload" size="56" class="tile-icon" />
                    <span class="tile-name">{{ current.uploading ? 'Uploading…' : 'Add quote file' }}</span>
                    <span class="tile-kind">PDF or image</span>
                  </label>
                </li>
              </ul>
              <QuoteDocument
                v-if="openFile[current.key] && fileMeta[openFile[current.key]!]"
                :file-id="openFile[current.key]!"
                :name="fileMeta[openFile[current.key]!]!.name"
                :mime="fileMeta[openFile[current.key]!]!.mime"
                class="viewer-doc"
              />
              <!-- No file yet: the whole pane is the one place to add it. -->
              <label v-else-if="!current.fileIds.length" class="viewer-empty" :class="{ busy: current.uploading }">
                <input
                  type="file"
                  class="sr-only"
                  accept=".pdf,.jpg,.jpeg,.png,.webp"
                  multiple
                  :disabled="current.uploading"
                  @change="(e) => { attach(current!, (e.target as HTMLInputElement).files); (e.target as HTMLInputElement).value = '' }"
                />
                <v-progress-circular v-if="current.uploading" indeterminate size="48" width="3" color="primary" />
                <v-icon v-else :icon="ICON.upload" size="64" class="tile-icon" />
                <span class="t-h3">{{ current.uploading ? 'Uploading…' : `Add ${current.name.trim() || 'the supplier'}'s quote file` }}</span>
                <span class="t-body muted">Pick a PDF or image, or drop it here. It is kept with the request and opens here, beside the prices.</span>
              </label>
            </div>

            <!-- Right: every request line, priced from this supplier or held by another offer. -->
            <div class="lines" role="table" :aria-label="`Prices from ${current.name || 'this supplier'}`">
              <div class="lrow lhead" role="row">
                <span role="columnheader">Item</span>
                <span role="columnheader" class="num">Qty</span>
                <span role="columnheader">Unit price, {{ typeCur(current) }}</span>
                <span role="columnheader" class="num">Line total</span>
              </div>
              <div
                v-for="l in r.lines"
                :key="l.lineId"
                class="lrow"
                :class="{ mine: lines[l.lineId]?.supplier === current.key, todo: !lineReady(l.lineId) }"
                role="row"
              >
                <span role="cell" class="item">
                  <span class="item-name">{{ l.product.name }}</span>
                  <span v-if="!lineReady(l.lineId)" class="todo-word">No price yet</span>
                </span>
                <span role="cell" class="num console-mono qty"><span class="cell-label">Qty </span>{{ l.qty }}</span>
                <span role="cell" class="price-cell">
                  <template v-if="lines[l.lineId]?.cimh">
                    <span class="held">
                      <span><v-icon :icon="ICON.stock" size="14" /> From <strong>CIMH stock</strong></span>
                      <button type="button" class="console-retry held-move" :aria-label="`Price ${l.product.name} from ${current.name.trim() || 'this supplier'} instead`" @click="moveHere(current, l.lineId)">Price it here instead</button>
                    </span>
                  </template>
                  <template v-else-if="holder(l.lineId) && holder(l.lineId) !== current">
                    <span class="held">
                      <span>Priced by <strong>{{ holder(l.lineId)!.name.trim() || 'another supplier' }}</strong>
                        · <span class="console-mono">{{ heldPrice(l.lineId) }}</span></span>
                      <button type="button" class="console-retry held-move" :aria-label="`Price ${l.product.name} from ${current.name.trim() || 'this supplier'} instead`" @click="moveHere(current, l.lineId)">Price it here instead</button>
                    </span>
                  </template>
                  <v-text-field
                    v-else
                    :id="`price-${current.key}-${l.lineId}`"
                    :model-value="priceFor(current, l.lineId)"
                    placeholder="—"
                    inputmode="decimal"
                    class="price mono-input"
                    :prefix="typeCur(current)"
                    :error-messages="lines[l.lineId]?.supplier === current.key ? priceError(lines[l.lineId]!) || undefined : undefined"
                    hide-details="auto"
                    :aria-label="`Unit price for ${l.product.name} in ${typeCur(current)}`"
                    @update:model-value="(v: string) => setPrice(current!, l.lineId, v ?? '')"
                    @keydown.enter.prevent="nextPrice(current, l.lineId)"
                  />
                </span>
                <span role="cell" class="num console-mono total">
                  <template v-if="lines[l.lineId]?.supplier === current.key && supTotal(l.lineId) !== null">{{ fmt(supTotal(l.lineId)) }}</template>
                </span>
              </div>
              <p class="lines-hint t-caption muted">Enter moves to the next price. Leave a line empty if this supplier didn't quote it.</p>
            </div>
          </div>
        </div>

        <!-- CIMH stock tab: lines fully in stock can be offered from the shelves. -->
        <div v-else-if="tab === 'cimh'" id="offer-panel" role="tabpanel" aria-labelledby="tab-cimh" class="panel-body">
          <div class="terms" role="group" aria-label="Terms of the CIMH stock items">
            <p class="terms-note t-body">
              Lines CIMH stock covers in full come from the shelves; the server prices them from the catalogue cost and
              holds the units when the quote is sent. A line comes from CIMH stock or one supplier, not both.
            </p>
            <div v-if="usd" class="term term-rate">
              <label class="term-label" for="cimh-rate">Exchange rate</label>
              <v-text-field
                id="cimh-rate"
                v-model="exchangeRate"
                prefix="1 USD ="
                suffix="BBD"
                placeholder="rate"
                persistent-placeholder
                inputmode="decimal"
                class="mono-input"
                hide-details
                :error="!!cimhRateMsg"
                aria-describedby="cimh-rate-msg"
              />
              <p id="cimh-rate-msg" class="term-msg" :class="{ bad: cimhRateMsg }">
                <template v-if="cimhRateMsg"><v-icon :icon="ICON.warn" size="14" />{{ cimhRateMsg }}</template>
                <template v-else>Stock and the admin fee are in BBD</template>
              </p>
            </div>
            <div class="term term-ship">
              <label class="term-label" for="cimh-ship">Estimated shipping</label>
              <v-text-field
                id="cimh-ship"
                v-model="cimhShip"
                prefix="BBD"
                placeholder="amount"
                persistent-placeholder
                inputmode="decimal"
                class="mono-input"
                hide-details
                :error="!!cimhShipMsg"
                aria-describedby="cimh-ship-msg"
              />
              <p id="cimh-ship-msg" class="term-msg" :class="{ bad: cimhShipMsg }">
                <template v-if="cimhShipMsg"><v-icon :icon="ICON.warn" size="14" />{{ cimhShipMsg }}</template>
                <template v-else>CIMH to the customer, 0.00 if none</template>
              </p>
            </div>
          </div>
          <div class="lines cimh-lines" role="table" aria-label="CIMH stock">
            <div class="lrow lhead" role="row">
              <span role="columnheader">Item</span>
              <span role="columnheader" class="num">Qty</span>
              <span role="columnheader">From stock</span>
              <span role="columnheader" class="num">Estimate</span>
            </div>
            <div v-for="l in r.lines" :key="l.lineId" class="lrow" :class="{ mine: lines[l.lineId]?.cimh }" role="row">
              <span role="cell" class="item">
                <span class="item-name">{{ l.product.name }}</span>
                <span v-if="holder(l.lineId)" class="item-note">Supplier: {{ holder(l.lineId)!.name.trim() || 'unnamed' }}</span>
              </span>
              <span role="cell" class="num console-mono qty"><span class="cell-label">Qty </span>{{ l.qty }}</span>
              <span role="cell">
                <v-checkbox
                  v-if="l.cimhAvailable"
                  :id="`offer-${l.lineId}`"
                  :model-value="lines[l.lineId]!.cimh"
                  label="From stock"
                  hide-details
                  density="compact"
                  @update:model-value="(v: boolean | null) => setStock(l.lineId, !!v)"
                />
                <span v-else class="t-caption muted">Not fully in stock</span>
              </span>
              <span role="cell" class="num console-mono total" :title="usd ? 'Catalogue cost converted at the exchange rate (estimate)' : 'Catalogue cost (estimate)'">
                <template v-if="l.cimhAvailable">
                  {{ costBBD[l.productId] === undefined ? '…' : costBBD[l.productId] === null ? 'No cost' : fmt(cimhTotal(l.lineId)) }}
                </template>
              </span>
            </div>
          </div>
        </div>

        <div v-else id="offer-panel" role="tabpanel" class="panel-body empty-tab">
          <p class="t-body-lg">Add the first supplier to start pricing.</p>
          <p class="t-body muted">Each supplier gets a tab with its quote file beside the request lines.</p>
          <v-btn color="primary" class="m3" :prepend-icon="BTN.add" @click="addSupplier">Add supplier</v-btn>
        </div>

        <!-- What the customer sees, what is missing, Preview and Send. -->
        <footer class="qfoot" aria-label="Quote summary">
          <dl class="figs">
            <div><dt>Supplier prices</dt><dd class="console-mono">{{ fmt(totals?.sup ?? 0) }}</dd></div>
            <div><dt>CIMH stock</dt><dd class="console-mono">{{ anyCimh ? fmt(totals?.cimh ?? null) : '—' }}</dd></div>
            <div><dt>Shipping</dt><dd class="console-mono">{{ fmt(totals?.ship ?? 0) }}</dd></div>
            <div>
              <dt>Admin fee, once</dt>
              <dd v-if="!feeKnown" class="console-mono">Unknown</dd>
              <dd v-else-if="feeCents === 0">None set</dd>
              <dd v-else class="console-mono">{{ fmt(totals?.fee ?? null) }}</dd>
            </div>
            <div class="grand">
              <dt>Total to sign (Estimate)</dt>
              <dd class="console-mono">{{ totals?.total == null ? '—' : fmt(totals.total) }}</dd>
            </div>
          </dl>
          <div class="qfoot-problems" tabindex="-1">
            <template v-if="problems">
              <p v-if="missing.length" :class="tried ? 'warn-line' : 'todo-line'">
                <v-icon :icon="tried ? ICON.warn : ICON.todo" size="16" />
                <span>{{ missing.length }} line{{ missing.length > 1 ? 's' : '' }} without a price:
                  <template v-for="(l, i) in missing.slice(0, 3)" :key="l.lineId">
                    <button type="button" class="console-retry" @click="jumpTo(l.lineId)">{{ l.product.name }}</button><template v-if="i < Math.min(missing.length, 3) - 1">, </template>
                  </template>
                  <template v-if="missing.length > 3"> and {{ missing.length - 3 }} more</template>
                </span>
              </p>
              <p v-if="dupes" class="err-line"><v-icon :icon="ICON.warn" size="16" />Two suppliers share a name.</p>
              <p v-if="unnamed" :class="todoClass"><v-icon :icon="todoIcon" size="16" />A supplier with prices has no name.</p>
              <p v-if="ratesMissing" :class="todoClass"><v-icon :icon="todoIcon" size="16" />Enter the BBD per USD rate for each USD supplier quote.</p>
              <p v-if="needsRate" :class="todoClass"><v-icon :icon="todoIcon" size="16" />Enter the exchange rate (CIMH stock tab).</p>
              <p v-if="shipMissing" :class="todoClass"><v-icon :icon="todoIcon" size="16" />Enter the estimated shipping for each supplier used and for CIMH stock (0.00 if none).</p>
              <p v-if="unsavedPrices" class="err-line"><v-icon :icon="ICON.warn" size="16" />Fix the price{{ unsavedPrices > 1 ? 's' : '' }} marked in red.</p>
            </template>
            <p v-else class="ok-line"><v-icon :icon="BTN.approve" size="16" />Every line priced, shipping estimated. Valid 30 days once sent.</p>
            <p v-if="noCost.length" class="err-line">
              <v-icon :icon="BTN.reject" size="16" />No catalogue cost for {{ noCost.map((l) => l.product.name).join(', ') }}: sending will be refused.
            </p>
          </div>
          <div class="qfoot-actions">
            <v-btn variant="outlined" size="large" class="m3" :prepend-icon="ICON.preview" @click="askReview('preview')">Preview agreement</v-btn>
            <v-btn color="primary" size="large" class="m3 send" :prepend-icon="BTN.verify" @click="askReview('send')">
              {{ r.status === 'QUOTED' ? 'Send revised quote…' : 'Send quote…' }}
            </v-btn>
          </div>
        </footer>
      </section>

      <!-- Review: the agreement exactly as the customer will get it (a marked preview, drawn by document-svc from the
           saved draft) beside what is about to be emailed. Preview agreement and Send quote both open it. -->
      <v-dialog
        :model-value="!!review"
        max-width="1240"
        :fullscreen="xs"
        :persistent="sending"
        scrollable
        @update:model-value="(v: boolean) => !v && (review = null)"
      >
        <v-card class="review">
          <v-card-title class="t-h3">
            {{ review === 'preview' ? 'Agreement preview' : r.status === 'QUOTED' ? 'Email the revised quote?' : 'Email this quote?' }}
          </v-card-title>
          <v-card-subtitle>
            <span class="console-mono"><ShortRef :id="r.id" /></span> · quote version {{ nextVersion }} · not sent yet
          </v-card-subtitle>
          <v-divider />
          <div class="review-body">
            <QuoteDocument
              v-if="review"
              :key="previewKey"
              :src="agreementPreviewUrl(r.id)"
              :name="`Agreement v${nextVersion} · preview`"
              mime="application/pdf"
              what="Agreement preview"
              class="review-doc"
              @state="(v: 'loading' | 'ready' | 'error') => (previewState = v)"
            />
            <aside class="review-side" aria-label="What is emailed">
              <dl class="sum check">
                <div><dt>To</dt><dd>{{ r.customerName }}<template v-if="r.organisationName">, {{ r.organisationName }}</template></dd></div>
                <div><dt>Quote version</dt><dd class="console-mono">{{ nextVersion }}</dd></div>
                <div><dt>Lines priced</dt><dd class="console-mono">{{ pricedLines }} of {{ r.lines.length }}</dd></div>
                <div><dt>Suppliers</dt><dd>{{ suppliers.filter((s) => usedBy(s)).map((s) => s.name.trim()).join(', ') || '—' }}</dd></div>
                <div><dt>Supplier prices</dt><dd class="console-mono">{{ fmt(totals?.sup ?? 0) }}</dd></div>
                <div v-if="anyCimh"><dt>CIMH stock <span class="muted">(estimate)</span></dt><dd class="console-mono">{{ fmt(totals?.cimh ?? null) }}</dd></div>
                <div><dt>Shipping <span class="muted">(estimated)</span></dt><dd class="console-mono">{{ fmt(totals?.ship ?? 0) }}</dd></div>
                <div><dt>Admin fee, once</dt><dd class="console-mono">{{ feeCents === 0 ? 'None' : fmt(totals?.fee ?? null) }}</dd></div>
                <div class="grand">
                  <dt>Total to sign (Estimate)</dt>
                  <dd class="console-mono">{{ totals?.total == null ? '—' : fmt(totals.total) }}</dd>
                </div>
              </dl>
              <p v-if="noCost.length" class="err-line">
                <v-icon :icon="BTN.reject" size="16" />No catalogue cost for {{ noCost.map((l) => l.product.name).join(', ') }}: sending will be refused.
              </p>
              <p class="t-body muted">
                Emailing sends the customer the quote and this agreement to sign, without the preview mark; it can't be
                recalled. CIMH stock lines are held for the request. The quote is valid 30 days; to change it afterwards
                you send a revised version, which replaces the agreement.
              </p>
            </aside>
          </div>
          <v-divider />
          <v-card-actions class="row-end">
            <v-btn class="m3" variant="text" :disabled="sending" @click="review = null">Keep editing</v-btn>
            <v-btn v-if="previewState !== 'error'" class="m3" color="primary" variant="flat" :prepend-icon="BTN.verify" :loading="sending" @click="send">
              Email the customer
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <v-dialog :model-value="!!removing" max-width="440" @update:model-value="(v: boolean) => !v && (removing = null)">
        <v-card :title="`Remove ${removing?.name || 'this supplier'}?`">
          <v-card-text>
            Their prices on {{ removing ? usedBy(removing) : 0 }} line{{ removing && usedBy(removing) > 1 ? 's' : '' }} are cleared. Their files stay with the request.
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="removing = null">Keep supplier</v-btn>
            <v-btn color="error" variant="flat" class="m3" @click="removing && removeSupplier(removing)">Remove</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </template>
  </div>
</template>

<style scoped>
.qb {
  width: 100%;
  max-width: 1600px;
  margin-inline: auto;
  padding: var(--sp-4) var(--sp-6) var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.qb p {
  margin: 0;
}
.crumbs {
  margin-left: -8px;
}
.state {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--sp-3);
  padding: var(--sp-8) 0;
}
.sk {
  height: 520px;
  border-radius: 4px;
}
.qb-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--sp-2) var(--sp-4);
}
.qb-id {
  flex: 1;
  min-width: 0;
}
.qb-title {
  margin: 0;
  font-size: 22px;
  line-height: 28px;
  font-weight: 600;
  letter-spacing: -0.01em;
  text-wrap: balance;
}
.qb-sub {
  font-size: 14px;
  color: rgb(var(--v-theme-secondary));
}
.save {
  display: inline-flex;
  gap: var(--sp-2);
  font-size: 13px;
  color: rgb(var(--v-theme-secondary));
}
.save.error {
  color: rgb(var(--v-theme-error));
  font-weight: 600;
}

/* One bordered frame: tabs, the open offer, the summary footer. */
.frame {
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
  min-width: 0;
}
.tabs {
  display: flex;
  overflow-x: auto;
  scroll-padding-inline: 0 176px;
  scrollbar-width: thin;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.tablist {
  flex: none; /* shrinking let the sticky Add supplier cover the last tab on phones */
  display: flex;
}
.tab {
  position: relative;
  flex: none; /* the strip scrolls; tabs never shrink to "OT…" */
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  min-width: 0;
  max-width: 260px;
  padding: 10px 20px 12px;
  border: 0;
  background: none;
  color: rgb(var(--v-theme-secondary));
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: color 160ms ease-out, background-color 160ms ease-out;
}
.tab::after {
  content: '';
  position: absolute;
  inset: auto 12px 0;
  height: 2px;
  border-radius: 2px 2px 0 0;
  background: rgb(var(--v-theme-primary));
  transform: scaleX(0);
  transition: transform 220ms cubic-bezier(0.2, 0, 0, 1);
}
.tab:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
  color: rgb(var(--v-theme-on-surface));
}
.tab.on {
  color: rgb(var(--v-theme-on-surface));
}
.tab.on::after {
  transform: scaleX(1);
}
.tab-name {
  max-width: 100%;
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tab-meta {
  font-size: 12px;
  color: rgb(var(--v-theme-secondary));
}
.tab-flag {
  position: absolute;
  top: 10px;
  right: 8px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgb(var(--v-theme-error));
}
/* Add supplier stays in reach while the tab strip scrolls (phones); the seam on its left marks the edge. */
.tab-add {
  position: sticky;
  right: 0;
  margin-left: auto;
  background: rgb(var(--v-theme-surface));
  border-left: 1px solid rgb(var(--v-theme-seam));
  flex-direction: row;
  align-items: center;
  gap: var(--sp-2);
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
  white-space: nowrap;
}
.tab-add::after {
  display: none;
}

.panel-body {
  animation: tab-in 200ms cubic-bezier(0.2, 0, 0, 1);
}
@keyframes tab-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
}
/* Terms row: each cell = caption, a 40 px field, one message line. Cells keep their width and wrap as a whole,
   so nothing is cut off; every cell lines up on the same three rows. */
.terms {
  container: terms / inline-size;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: var(--sp-2) var(--sp-4);
  padding: var(--sp-3) var(--sp-4) var(--sp-2);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.term {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}
.term-label {
  padding: 0;
  font-size: 13px;
  line-height: 18px;
  font-weight: 500;
  letter-spacing: 0.1px;
  color: rgb(var(--v-theme-secondary));
}
.term-msg {
  display: flex;
  align-items: center;
  gap: 4px;
  min-height: 16px;
  font-size: 12px;
  line-height: 16px;
  letter-spacing: 0.1px;
  color: rgb(var(--v-theme-secondary));
}
.term-msg.bad {
  color: rgb(var(--v-theme-error));
  font-weight: 500;
}
.term-msg .v-icon {
  flex: none;
}
.term-name {
  flex: 1 1 240px;
  max-width: 380px;
}
.term-rate {
  flex: 0 0 216px;
}
.term-ship {
  flex: 0 0 216px;
}
.terms-note {
  flex: 1 1 420px;
  max-width: 75ch;
  align-self: center;
}
/* An empty field must not read as filled: the placeholder is a word, in muted ink, not a number. */
.term :deep(input::placeholder) {
  font-family: 'Inter Variable', Inter, system-ui, sans-serif;
  color: rgb(var(--v-theme-secondary));
  opacity: 1;
}
.term :deep(.v-field__prefix),
.term :deep(.v-field__suffix) {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 13px;
  color: rgb(var(--v-theme-secondary));
  opacity: 1;
}
/* The remove button sits on the field row, apart from the fields (DESIGN: danger alone). */
.v-btn.m3.sup-remove {
  margin: 22px 0 0 auto;
}
.sup-remove :deep(.v-btn__content) {
  gap: 8px;
}
/* A desk row without room for the word: the icon alone (named by aria-label and title). Phones keep the word. */
@container terms (min-width: 560px) and (max-width: 1099.98px) {
  .v-btn.m3.sup-remove {
    width: 40px;
    min-width: 40px;
    padding: 0 !important; /* the M3 pill padding (console.css) is more specific */
  }
  .rm-word {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }
}

/* Their currency: a Material 3 segmented button (two native radios), as tall as the fields beside it. */
.seg {
  display: inline-flex;
  height: 40px;
  border: 1px solid rgb(var(--v-theme-field-outline));
  border-radius: 999px;
  overflow: hidden;
}
.seg-input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}
.seg-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 84px;
  padding: 0 14px;
  font-size: 14px;
  line-height: 20px;
  font-weight: 500;
  letter-spacing: 0.00625em;
  color: rgb(var(--v-theme-on-surface));
  cursor: pointer;
  user-select: none;
  transition: background-color 160ms ease-out;
}
.seg-btn + .seg-input + .seg-btn {
  border-left: 1px solid rgb(var(--v-theme-field-outline));
}
.seg-btn:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}
.seg-input:checked + .seg-btn {
  background: rgb(var(--v-theme-primary-subtle));
  font-weight: 600;
}
.seg-input:focus-visible + .seg-btn {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.seg-btn .v-icon {
  margin-left: -4px;
  color: rgb(var(--v-theme-primary));
}

/* The document beside the lines: equal halves, the document stays in view while the lines scroll. */
.split {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
}
.viewer {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding: var(--sp-3);
  border-right: 1px solid rgb(var(--v-theme-seam));
  /* Recessed well, a step darker than the page ground, so a white quote page separates in light theme too. */
  background: rgba(var(--v-theme-on-surface), 0.05);
  position: sticky;
  top: 0;
  align-self: start;
  height: min(calc(100vh - 96px), 980px);
  transition: box-shadow 160ms ease-out;
}
.viewer.drag {
  box-shadow: inset 0 0 0 2px rgb(var(--v-theme-primary));
}
.viewer-doc {
  flex: 1;
}
.viewer-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-8) var(--sp-6);
  text-align: center;
  border: 1px dashed rgb(var(--v-theme-field-outline));
  border-radius: 8px;
  background: rgb(var(--v-theme-surface));
  cursor: pointer;
  transition: border-color 160ms ease-out;
}
.viewer-empty:hover {
  border-color: rgb(var(--v-theme-primary));
}
.viewer-empty:focus-within {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.viewer-empty .t-body {
  max-width: 44ch;
}

/* Large square file tiles: the file is the thing staff read from, so it is easy to find and hit. */
.tiles {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  gap: var(--sp-3);
  overflow-x: auto;
  padding-bottom: 2px;
}
.tile-wrap {
  position: relative;
  flex: none;
}
.tile {
  width: 152px;
  height: 152px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: var(--sp-3);
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 8px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  font: inherit;
  text-align: center;
  cursor: pointer;
  transition: border-color 160ms ease-out, background-color 160ms ease-out, transform 120ms ease-out;
}
.tile:hover {
  border-color: rgb(var(--v-theme-primary));
}
.tile:active {
  transform: scale(0.98);
}
.tile.on {
  border: 2px solid rgb(var(--v-theme-primary));
  background: rgb(var(--v-theme-primary-subtle));
}
.tile-icon {
  color: rgb(var(--v-theme-primary));
  margin-bottom: 2px;
}
.tile-name {
  max-width: 100%;
  font-size: 13px;
  font-weight: 600;
  line-height: 18px;
  /* Two lines, broken anywhere: the quote number at the end is what tells two files apart. */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
}
.tile-kind {
  font-size: 12px;
  line-height: 16px;
  color: rgb(var(--v-theme-secondary));
}
.tile-add {
  border-style: dashed;
  border-color: rgb(var(--v-theme-field-outline));
}
.tile-add:focus-within {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.tile-add.busy {
  cursor: progress;
}
.tile-x {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 50%;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-secondary));
  cursor: pointer;
}
.tile-x:hover {
  background: rgba(var(--v-theme-error), 0.12);
  color: rgb(var(--v-theme-error));
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

/* Lines */
.lines {
  display: flex;
  flex-direction: column;
  min-width: 0;
  container: qlines / inline-size;
}
.lrow {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) 44px minmax(160px, 1fr) minmax(96px, 0.7fr);
  gap: var(--sp-3);
  align-items: center;
  min-height: 56px;
  padding: var(--sp-2) var(--sp-4);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
  font-size: 14px;
  line-height: 20px;
  transition: background-color 240ms ease-out;
}
.lhead {
  min-height: 0;
  font-size: 11px;
  line-height: 16px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgb(var(--v-theme-secondary));
}
.lrow.mine {
  background: rgba(var(--v-theme-primary-subtle), 0.7);
}
.lrow:focus-within {
  background: rgb(var(--v-theme-primary-subtle));
}
.item {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.item-name {
  font-weight: 500;
  overflow-wrap: anywhere;
}
.item-note {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: rgb(var(--v-theme-secondary));
}
.todo-word {
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--v-theme-warning));
}
.num {
  text-align: right;
}
.cell-label {
  display: none;
}
.held {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  font-size: 13px;
  color: rgb(var(--v-theme-secondary));
}
.held strong {
  color: rgb(var(--v-theme-on-surface));
}
.held-move {
  text-align: left;
}
.mono-input :deep(input) {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.total {
  white-space: nowrap;
}
.lines-hint {
  padding: var(--sp-3) var(--sp-4);
}
.cimh-lines .lrow {
  grid-template-columns: minmax(0, 1.5fr) 44px minmax(150px, 1fr) minmax(120px, 0.7fr);
}
.empty-tab {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--sp-2);
  padding: var(--sp-8) var(--sp-6);
}
.empty-tab .v-btn {
  margin-top: var(--sp-2);
}

/* Summary footer */
.qfoot {
  position: sticky;
  bottom: 0;
  z-index: 2;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--sp-2) var(--sp-6);
  align-items: center;
  padding: var(--sp-3) var(--sp-4);
  border-top: 1px solid rgb(var(--v-theme-seam));
  background: rgb(var(--v-theme-surface));
  border-radius: 0 0 4px 4px;
}
.figs {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 4px var(--sp-6);
}
.figs > div {
  display: flex;
  flex-direction: column;
}
.figs dt {
  white-space: nowrap;
  font-size: 12px;
  color: rgb(var(--v-theme-secondary));
}
.figs dd {
  margin: 0;
  font-size: 14px;
  white-space: nowrap;
}
.figs .grand dt {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 600;
}
.figs .grand dd {
  font-size: 18px;
  line-height: 24px;
  font-weight: 600;
}
.qfoot-problems {
  grid-column: 1 / -1;
  grid-row: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  outline: none;
}
.warn-line,
.err-line,
.ok-line,
.todo-line {
  display: flex;
  gap: var(--sp-2);
  align-items: flex-start;
}
.warn-line {
  color: rgb(var(--v-theme-warning));
}
.warn-line .console-retry {
  font-size: 13px;
}
.err-line {
  color: rgb(var(--v-theme-error));
}
.ok-line {
  color: rgb(var(--v-theme-success));
  font-weight: 600;
}
.todo-line {
  color: rgb(var(--v-theme-on-surface));
}
.todo-line .v-icon {
  color: rgb(var(--v-theme-secondary));
}
.warn-line .v-icon,
.err-line .v-icon,
.ok-line .v-icon,
.todo-line .v-icon {
  flex: none;
  margin-top: 2px;
}
.qfoot-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--sp-2);
}
.send {
  min-width: 200px;
}

/* Review dialog: the agreement large on the left, what is emailed on the right. */
.review-body {
  flex: 1 1 auto;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  height: min(76vh, 900px);
  min-height: 0;
}
.review-doc {
  border: 0;
  border-right: 1px solid rgb(var(--v-theme-seam));
  border-radius: 0;
}
.review-side {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
  padding: var(--sp-4);
  overflow: auto;
}

/* Dialog figures */
.sum {
  margin: 0;
  display: flex;
  flex-direction: column;
}
.sum > div {
  display: flex;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: 6px 0;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
  font-size: 14px;
}
.sum dt {
  color: rgb(var(--v-theme-secondary));
}
.sum dt .muted {
  color: inherit;
}
.sum dd {
  margin: 0;
  text-align: right;
}
.sum .grand {
  border-bottom: 0;
  padding-top: var(--sp-2);
  font-size: 16px;
  font-weight: 600;
}
.sum .grand dt {
  color: rgb(var(--v-theme-on-surface));
}

/* What is missing sits above the figures and both buttons, which share one row so the document keeps its
   height on a 720 px desk screen. */
@media (max-width: 1439.98px) {
  .qfoot {
    gap: var(--sp-2) var(--sp-4);
  }
  .figs {
    gap: 4px var(--sp-3);
  }
  .figs .grand dd {
    font-size: 16px;
  }
}
@media (max-width: 899.98px) {
  .qfoot {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .figs {
    grid-column: 1 / -1;
    flex-wrap: wrap;
  }
}
/* Narrower: the document sits above the lines (shorter), still beside nothing it would squeeze. */
@media (max-width: 1099.98px) {
  .split {
    grid-template-columns: minmax(0, 1fr);
  }
  .viewer {
    position: static;
    height: auto;
    border-right: 0;
    border-bottom: 1px solid rgb(var(--v-theme-seam));
  }
  .viewer .viewer-doc {
    flex: none;
    height: min(60vh, 560px); /* its own scroll: a price field stays one swipe from the figure */
  }
}
@container qlines (max-width: 479.98px) {
  .lhead {
    display: none;
  }
  .lrow,
  .cimh-lines .lrow {
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas: 'item qty' 'price total';
    row-gap: var(--sp-2);
    padding: var(--sp-3) var(--sp-4);
  }
  .lrow > :nth-child(1) { grid-area: item; }
  .lrow > :nth-child(2) { grid-area: qty; }
  .lrow > :nth-child(3) { grid-area: price; }
  .lrow > :nth-child(4) { grid-area: total; }
  .cell-label {
    display: inline;
    color: rgb(var(--v-theme-secondary));
  }
}
@media (max-width: 599.98px) {
  .qb {
    padding: var(--sp-3) var(--sp-3) var(--sp-4);
  }
  /* A pinned summary would take a third of a phone screen: it closes the page instead. */
  .qfoot {
    position: static;
    grid-template-columns: minmax(0, 1fr);
  }
  .send {
    width: 100%;
  }
  .term-name,
  .term-cur {
    flex: 1 1 100%;
    max-width: none;
  }
  .term-rate,
  .term-ship {
    flex: 1 1 100%;
  }
  .seg {
    width: 100%;
  }
  .seg-btn {
    flex: 1;
  }
  .v-btn.m3.sup-remove {
    margin: 0;
  }
  .qfoot-actions .v-btn {
    flex: 1 1 100%;
  }
  .review-body {
    display: flex;
    flex-direction: column;
    height: auto;
    overflow: auto;
  }
  .review-side {
    order: -1;
    overflow: visible;
  }
  .review-doc {
    height: 70vh;
    border-right: 0;
    border-top: 1px solid rgb(var(--v-theme-seam));
  }
  .tile {
    width: 132px;
    height: auto;
    min-height: 132px; /* grows so both lines of the file name show */
  }
  /* The way back goes above the title again: beside it the title had ~100 px. */
  .qb-head {
    flex-wrap: wrap;
  }
  .qb-head .crumbs {
    flex-basis: 100%;
  }
  .qb-id {
    flex-basis: 100%;
  }
  .add-word {
    display: none;
  }
  .tabs {
    scroll-padding-inline: 0 120px;
  }
  .tab {
    padding: 10px 14px 12px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .panel-body {
    animation: none;
  }
  .tab::after,
  .tile,
  .lrow {
    transition: none;
  }
}
</style>
