<script setup lang="ts">
/**
 * A-04 quote builder (staff; QUOTING, or revising a QUOTED request), Graphite Console.
 *   Suppliers: name + their quote files (document-svc `supplier_quote`). Each supplier has a local key, so
 *   renaming one keeps its prices; two suppliers may not share a name.
 *   Lines: offer from CIMH stock (only lines fully in stock; the server prices them from the catalogue cost,
 *   converted with the exchange rate for USD) and/or one supplier with a unit price.
 *   Summary: CIMH price (estimate from the catalogue cost), supplier totals, the admin fee (once), and the
 *   range the customer's agreement total can fall in, before anything is sent.
 * The draft saves itself (PUT quote-draft, If-Match) shortly after each change; a failed save never stops
 * later saves; a version conflict re-reads the version and saves the same draft again (local edits win).
 * Leaving the page saves a pending change first. "Send quote" saves, then sends; the customer is emailed.
 */
import {
  act,
  ApiError,
  call,
  catalog,
  fileUrl,
  getRequest,
  type OrderRequest,
  saveQuoteDraft,
  uploadRequestFile,
  useNotify,
  shortRef,
} from '@cimh/web-app'
import { formatMoney } from '@cimh/web-ui'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { BTN } from '../../../request-queue'

definePage({ meta: { guard: 'staff', title: 'Quote builder', ownHeading: true } })
const route = useRoute('/requests/[id]/quote')
const router = useRouter()
const notify = useNotify()
const r = ref<OrderRequest | null>(null)
const loadFailed = ref(false)

interface Supplier { key: number; name: string; fileIds: string[]; uploading: boolean }
interface LineState { cimh: boolean; supplier: number | null; unitPrice: string }
type Draft = { supplierQuotes: { supplier: string; fileIds: string[]; lines: { lineId: string; unitPrice: string }[] }[]; cimh?: { lineIds: string[]; exchangeRate?: string | null } | null }

const suppliers = ref<Supplier[]>([])
const lines = reactive<Record<string, LineState>>({})
const exchangeRate = ref('')
const fileNames = reactive<Record<string, string>>({})
let nextKey = 1
let ready = false

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
  for (const f of x.files ?? []) fileNames[f.id] = f.name
  const draft = (x as unknown as { quoteDraft?: Draft }).quoteDraft
  const latest = Math.max(0, ...(x.quotes ?? []).map((q) => q.version))
  // Start from the draft, else from the last sent quote (revising), else empty.
  const sq: Draft['supplierQuotes'] = draft?.supplierQuotes ??
    (x.quotes ?? []).filter((q) => q.version === latest).map((q) => ({ supplier: q.supplier ?? '', fileIds: q.fileIds ?? [],
      lines: q.lines.map((l) => ({ lineId: l.lineId, unitPrice: l.unitPrice })) }))  // prettier-ignore
  const cimhIds = draft?.cimh?.lineIds ?? x.cimhQuote?.lines.map((l) => l.lineId) ?? []
  suppliers.value = sq.map((s) => ({ key: nextKey++, name: s.supplier, fileIds: [...s.fileIds], uploading: false }))
  for (const l of x.lines) {
    const i = sq.findIndex((s) => s.lines.some((y) => y.lineId === l.lineId))
    lines[l.lineId] = {
      cimh: cimhIds.includes(l.lineId) && !!l.cimhAvailable,
      supplier: i >= 0 ? suppliers.value[i]!.key : null,
      unitPrice: i >= 0 ? (sq[i]!.lines.find((y) => y.lineId === l.lineId)?.unitPrice ?? '') : '',
    }
  }
  exchangeRate.value = draft?.cimh?.exchangeRate ?? x.cimhQuote?.exchangeRate ?? ''
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

// ---- draft body: only valid, unique suppliers and valid prices travel; the rest stays on screen
function draftBody(): Draft {
  return {
    supplierQuotes: suppliers.value
      .filter((s) => s.name.trim() && !dupName(s))
      .map((s) => ({
        supplier: s.name.trim(),
        fileIds: s.fileIds,
        lines: Object.entries(lines)
          .filter(([, v]) => v.supplier === s.key && MONEY.test(v.unitPrice))
          .map(([lineId, v]) => ({ lineId, unitPrice: v.unitPrice })),
      })),
    cimh: {
      lineIds: Object.entries(lines).filter(([, v]) => v.cimh).map(([k]) => k),
      exchangeRate: rateOk.value ? exchangeRate.value : null,
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
  [suppliers, lines, exchangeRate],
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
  if (saveState.value === 'saved') return `Draft saved ${t}${unsavedPrices.value ? ` · ${unsavedPrices.value} price${unsavedPrices.value > 1 ? 's' : ''} to fix` : ''}`
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
  suppliers.value.push({ key: nextKey++, name: '', fileIds: [], uploading: false })
  void nextTick(() => (document.querySelector('.sup:last-of-type input') as HTMLInputElement | null)?.focus())
}
const usedBy = (s: Supplier) => Object.values(lines).filter((v) => v.supplier === s.key).length
const removing = ref<Supplier | null>(null)
function askRemove(s: Supplier) {
  if (usedBy(s)) removing.value = s
  else removeSupplier(s)
}
function removeSupplier(s: Supplier) {
  suppliers.value = suppliers.value.filter((x) => x !== s)
  for (const v of Object.values(lines)) if (v.supplier === s.key) v.supplier = null
  removing.value = null
}
function useForUnassigned(s: Supplier) {
  for (const l of r.value?.lines ?? []) if (lines[l.lineId]!.supplier === null) lines[l.lineId]!.supplier = s.key
}
const unassigned = computed(() => Object.values(lines).filter((v) => v.supplier === null).length)
async function attach(s: Supplier, files: File | File[] | null) {
  const list = files ? (Array.isArray(files) ? files : [files]) : []
  if (!r.value || !list.length) return
  s.uploading = true
  try {
    for (const f of list) {
      const ref = await uploadRequestFile(r.value.id, 'supplier_quote', f)
      fileNames[ref.id] = ref.name || f.name
      s.fileIds.push(ref.id)
    }
  } catch (e) {
    notify.report(e)
  } finally {
    s.uploading = false
  }
}
const supplierItems = computed(() => [
  { title: 'None', value: null as number | null },
  ...suppliers.value.filter((s) => s.name.trim()).map((s) => ({ title: s.name.trim(), value: s.key as number | null })),
])

// ---- keyboard: Enter in a price moves down the column; the missing list jumps to the row
function nextPrice(lineId: string) {
  const ids = r.value?.lines.map((l) => l.lineId) ?? []
  const next = ids[ids.indexOf(lineId) + 1]
  if (next) (document.getElementById(`price-${next}`) as HTMLInputElement | null)?.focus()
}
function jumpTo(lineId: string) {
  const row = document.getElementById(`row-${lineId}`)
  row?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  const target = lines[lineId]?.supplier !== null ? `price-${lineId}` : `sup-${lineId}`
  ;(document.getElementById(target) as HTMLInputElement | null)?.focus({ preventScroll: true })
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
const supTotal = (lineId: string) => {
  const v = lines[lineId]
  return v && v.supplier !== null && MONEY.test(v.unitPrice) ? cents(v.unitPrice) * qtyOf(lineId) : null
}
const noCost = computed(() => r.value?.lines.filter((l) => lines[l.lineId]?.cimh && !costBBD[l.productId] && l.productId in costBBD) ?? [])
const totals = computed(() => {
  const x = r.value
  if (!x) return null
  let sup = 0
  let cimh = 0
  let lo = 0
  let hi = 0
  let complete = true
  for (const l of x.lines) {
    const opts: number[] = []
    const s = supTotal(l.lineId)
    if (s !== null) {
      sup += s
      opts.push(s)
    }
    if (lines[l.lineId]?.cimh) {
      const c = cimhTotal(l.lineId)
      if (c === null) complete = false
      else {
        cimh += c
        opts.push(c)
      }
    }
    if (!opts.length) complete = false
    else {
      lo += Math.min(...opts)
      hi += Math.max(...opts)
    }
  }
  const fee = feeKnown.value ? convert(feeCents.value) : null
  return { sup, cimh, fee, lo: fee === null ? null : lo + fee, hi: fee === null ? null : hi + fee, complete }
})

// ---- send
const sending = ref(false)
const canSend = computed(() => !missing.value.length && !needsRate.value && !dupes.value && !unsavedPrices.value)
const confirmSend = ref(false)
const nextVersion = computed(() => Math.max(0, ...(r.value?.quotes ?? []).map((q) => q.version)) + 1)
const pricedLines = computed(() => (r.value?.lines.length ?? 0) - missing.value.length)
async function send() {
  if (!r.value || sending.value) return
  sending.value = true
  try {
    await save()
    r.value = await act(r.value, '/requests/{requestId}/send-quote', undefined)
    notify.toast(`Quote version ${Math.max(...(r.value.quotes ?? []).map((q) => q.version))} sent to the customer`, 'success')
    confirmSend.value = false
    await router.push(`/requests/${r.value.id}`)
  } catch (e) {
    confirmSend.value = false // the reason shows on the page (toast, marked prices)
    if (e instanceof ApiError) notify.report(e)
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <div class="qb">
    <nav class="crumbs" aria-label="Breadcrumb">
      <v-btn :to="`/requests/${route.params.id}`" variant="text" class="m3" :prepend-icon="BTN.back">Request</v-btn>
    </nav>

    <div v-if="loadFailed" class="state">
      <p class="t-body-lg">Couldn't load this request.</p>
      <v-btn variant="outlined" class="m3" :prepend-icon="BTN.retry" @click="load">Retry</v-btn>
    </div>
    <div v-else-if="!r" class="console-skel sk" />

    <template v-else>
      <header class="qb-head">
        <div>
          <h1 class="qb-title">{{ r.status === 'QUOTED' ? 'Revise quote' : 'Build quote' }}</h1>
          <p class="qb-sub">
            {{ r.organisationName || r.customerName }} · <span class="console-mono" :title="r.id">{{ shortRef(r.id) }}</span> · prices in
            <strong class="console-mono">{{ r.currency }}</strong>
          </p>
        </div>
        <p class="save" :class="saveState" role="status">
          <span>{{ statusText }}</span>
          <button v-if="saveState === 'error'" type="button" class="console-retry" @click="save().catch(() => undefined)">Retry</button>
        </p>
      </header>

      <div class="qb-grid">
        <div class="qb-main">
          <section class="panel">
            <header class="console-head">
              <h2 class="console-title">Suppliers</h2>
              <span class="t-caption muted">Quote files are kept with the request</span>
            </header>
            <div class="sups">
              <p v-if="!suppliers.length" class="t-body muted">No supplier yet. Add one to price lines that CIMH stock can't cover.</p>
              <div v-for="s in suppliers" :key="s.key" class="sup">
                <v-text-field
                  v-model="s.name"
                  label="Supplier name"
                  density="compact"
                  hide-details="auto"
                  :error-messages="dupName(s) ? 'Another supplier has this name' : undefined"
                  class="sup-name"
                />
                <v-file-input
                  label="Quote file (PDF or image)"
                  :prepend-icon="BTN.attach"
                  accept=".pdf,.jpg,.jpeg,.png"
                  multiple
                  hide-details
                  density="compact"
                  :loading="s.uploading"
                  :model-value="[]"
                  class="sup-file"
                  @update:model-value="(f: File | File[] | null) => attach(s, f)"
                />
                <div class="sup-actions">
                  <v-btn
                    v-if="s.name.trim() && unassigned"
                    variant="text"
                    class="m3"
                    size="small"
                    @click="useForUnassigned(s)"
                  >Use for {{ unassigned }} unassigned line{{ unassigned > 1 ? 's' : '' }}</v-btn>
                  <v-btn variant="text" size="small" :icon="BTN.remove" :aria-label="`Remove ${s.name || 'supplier'}`" @click="askRemove(s)" />
                </div>
                <div v-if="s.fileIds.length" class="files">
                  <v-chip
                    v-for="f in s.fileIds"
                    :key="f"
                    :href="fileUrl(f)"
                    target="_blank"
                    size="small"
                    label
                    closable
                    :close-label="`Remove ${fileNames[f] ?? 'file'} from this quote`"
                    @click:close.prevent="s.fileIds = s.fileIds.filter((x) => x !== f)"
                  >{{ fileNames[f] ?? 'Quote file' }}</v-chip>
                </div>
              </div>
              <v-btn variant="outlined" class="m3 add" :prepend-icon="BTN.add" @click="addSupplier">Add supplier</v-btn>
            </div>
          </section>

          <section class="panel">
            <header class="console-head">
              <h2 class="console-title">Prices</h2>
              <span class="t-caption muted">Enter moves to the next price</span>
            </header>
            <div class="lines" role="table" :aria-label="`Prices in ${r.currency}`">
              <div class="lrow lhead" role="row">
                <span role="columnheader">Item</span>
                <span role="columnheader" class="num">Qty</span>
                <span role="columnheader">CIMH stock</span>
                <span role="columnheader">Supplier</span>
                <span role="columnheader">Unit price</span>
                <span role="columnheader" class="num">Line total</span>
              </div>
              <div
                v-for="l in r.lines"
                :id="`row-${l.lineId}`"
                :key="l.lineId"
                class="lrow"
                :class="{ todo: !lineReady(l.lineId) }"
                role="row"
              >
                <span role="cell" class="item">
                  <span class="item-name">{{ l.product.name }}</span>
                  <span v-if="!lineReady(l.lineId)" class="todo-word">No price yet</span>
                </span>
                <span role="cell" class="num console-mono qty"><span class="cell-label">Qty </span>{{ l.qty }}</span>
                <span role="cell" class="cimh">
                  <template v-if="l.cimhAvailable">
                    <v-checkbox v-model="lines[l.lineId]!.cimh" label="Offer" hide-details density="compact" />
                    <span class="cimh-price console-mono" :title="usd ? 'Catalogue cost converted at the exchange rate (estimate)' : 'Catalogue cost (estimate)'">
                      {{ costBBD[l.productId] === undefined ? '…' : costBBD[l.productId] === null ? 'No cost' : fmt(cimhUnit(l.lineId)) }}
                    </span>
                  </template>
                  <span v-else class="t-caption muted">Not fully in stock</span>
                </span>
                <span role="cell">
                  <v-select
                    :id="`sup-${l.lineId}`"
                    v-model="lines[l.lineId]!.supplier"
                    :items="supplierItems"
                    density="compact"
                    hide-details
                    :aria-label="`Supplier for ${l.product.name}`"
                  />
                </span>
                <span role="cell">
                  <v-text-field
                    :id="`price-${l.lineId}`"
                    v-model="lines[l.lineId]!.unitPrice"
                    density="compact"
                    placeholder="0.00"
                    inputmode="decimal"
                    class="price"
                    :disabled="lines[l.lineId]!.supplier === null"
                    :error-messages="priceError(lines[l.lineId]!) || undefined"
                    hide-details="auto"
                    :aria-label="`Unit price for ${l.product.name}`"
                    @keydown.enter.prevent="nextPrice(l.lineId)"
                  />
                </span>
                <span role="cell" class="num console-mono total">{{ supTotal(l.lineId) === null ? '' : fmt(supTotal(l.lineId)) }}</span>
              </div>
            </div>
          </section>
        </div>

        <aside class="qb-side" aria-label="Quote summary">
          <section class="panel summary">
            <header class="console-head"><h2 class="console-title">What the customer sees</h2></header>
            <div class="sum-body">
              <v-text-field
                v-if="usd"
                v-model="exchangeRate"
                label="Exchange rate (BBD per 1 USD)"
                density="compact"
                inputmode="decimal"
                class="rate"
                hide-details="auto"
                :error-messages="rateError || undefined"
                hint="CIMH-stock prices and the admin fee are in BBD"
                persistent-hint
              />
              <dl class="sum">
                <div><dt>Supplier prices</dt><dd class="console-mono">{{ fmt(totals?.sup ?? 0) }}</dd></div>
                <div><dt>CIMH stock <span class="muted">(estimate)</span></dt><dd class="console-mono">{{ anyCimh ? fmt(totals?.cimh ?? null) : '—' }}</dd></div>
                <div>
                  <dt>Admin fee, once</dt>
                  <!-- 0.00 read like a mistake: say no fee is set (admins set it under Settings › Fees). -->
                  <dd v-if="!feeKnown" class="console-mono">Unknown</dd>
                  <dd v-else-if="feeCents === 0" class="muted">None set</dd>
                  <dd v-else class="console-mono">{{ fmt(totals?.fee ?? null) }}</dd>
                </div>
                <!-- A range in this narrow panel wrapped over two lines: lowest and highest get a row each. -->
                <template v-if="totals?.complete && totals.lo !== null && totals.lo !== totals.hi">
                  <div class="grand"><dt>Agreement total, lowest</dt><dd class="console-mono">{{ fmt(totals.lo) }}</dd></div>
                  <div class="grand"><dt>Agreement total, highest</dt><dd class="console-mono">{{ fmt(totals.hi) }}</dd></div>
                </template>
                <div v-else class="grand">
                  <dt>Agreement total</dt>
                  <dd class="console-mono">
                    <template v-if="!totals?.complete || totals.lo === null">—</template>
                    <template v-else>{{ fmt(totals.lo) }}</template>
                  </dd>
                </div>
              </dl>
              <p class="t-caption muted">
                The customer picks CIMH stock or the supplier on each offered line; the range runs from the lowest to the
                highest choices. The server sets the final CIMH prices from the catalogue when the quote is sent. Valid 30 days.
              </p>
              <p v-if="noCost.length" class="warn">
                <v-icon :icon="BTN.reject" size="16" />No catalogue cost for {{ noCost.map((l) => l.product.name).join(', ') }}: sending will be refused.
              </p>

              <div v-if="missing.length" class="missing">
                <p class="missing-title">{{ missing.length }} line{{ missing.length > 1 ? 's' : '' }} without a price</p>
                <ul>
                  <li v-for="l in missing" :key="l.lineId">
                    <button type="button" class="console-retry" @click="jumpTo(l.lineId)">{{ l.product.name }}</button>
                  </li>
                </ul>
              </div>
              <p v-if="dupes" class="warn"><v-icon :icon="BTN.reject" size="16" />Two suppliers share a name.</p>
              <p v-if="unsavedPrices" class="warn"><v-icon :icon="BTN.reject" size="16" />Fix the price{{ unsavedPrices > 1 ? 's' : '' }} marked in red.</p>

              <v-btn color="primary" class="m3 send" :prepend-icon="BTN.verify" :disabled="!canSend" @click="confirmSend = true">
                {{ r.status === 'QUOTED' ? 'Send revised quote…' : 'Send quote…' }}
              </v-btn>
              <p class="t-caption muted">You check it once more before the customer is emailed{{ r.status === 'QUOTED' ? ' the new version' : '' }}.</p>
            </div>
          </section>
        </aside>
      </div>

      <v-dialog v-model="confirmSend" max-width="520" :persistent="sending">
        <v-card>
          <v-card-title class="t-h3">{{ r.status === 'QUOTED' ? 'Email the revised quote?' : 'Email this quote?' }}</v-card-title>
          <v-card-subtitle><span class="console-mono" :title="r.id">{{ shortRef(r.id) }}</span></v-card-subtitle>
          <v-divider />
          <v-card-text class="stack">
            <dl class="sum check">
              <div><dt>To</dt><dd>{{ r.customerName }}<template v-if="r.organisationName">, {{ r.organisationName }}</template></dd></div>
              <div><dt>Quote version</dt><dd class="console-mono">{{ nextVersion }}</dd></div>
              <div><dt>Lines priced</dt><dd class="console-mono">{{ pricedLines }} of {{ r.lines.length }}</dd></div>
              <div><dt>Supplier prices</dt><dd class="console-mono">{{ fmt(totals?.sup ?? 0) }}</dd></div>
              <div v-if="anyCimh"><dt>CIMH stock <span class="muted">(estimate)</span></dt><dd class="console-mono">{{ fmt(totals?.cimh ?? null) }}</dd></div>
              <div class="grand">
                <dt>Agreement total <span class="muted">(estimate)</span></dt>
                <dd class="console-mono">
                  <template v-if="!totals?.complete || totals.lo === null">—</template>
                  <template v-else-if="totals.lo === totals.hi">{{ fmt(totals.lo) }}</template>
                  <template v-else>{{ fmt(totals.lo) }} – {{ fmt(totals.hi) }}</template>
                </dd>
              </div>
            </dl>
            <p v-if="noCost.length" class="warn">
              <v-icon :icon="BTN.reject" size="16" />No catalogue cost for {{ noCost.map((l) => l.product.name).join(', ') }}: sending will be refused.
            </p>
            <p class="t-body muted">
              The email goes out at once and can't be recalled. The quote is valid 30 days; to change it afterwards you send a revised version.
            </p>
          </v-card-text>
          <v-card-actions class="row-end">
            <v-btn class="m3" variant="text" :disabled="sending" @click="confirmSend = false">Keep editing</v-btn>
            <v-btn class="m3" color="primary" variant="flat" :prepend-icon="BTN.verify" :loading="sending" @click="send">Email the customer</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <v-dialog :model-value="!!removing" max-width="440" @update:model-value="(v: boolean) => !v && (removing = null)">
        <v-card :title="`Remove ${removing?.name || 'this supplier'}?`">
          <v-card-text>
            Their prices on {{ removing ? usedBy(removing) : 0 }} line{{ removing && usedBy(removing) > 1 ? 's' : '' }} are cleared.
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
  max-width: 1500px;
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
  height: 420px;
  border-radius: 4px;
}
.qb-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--sp-2) var(--sp-4);
}
.qb-title {
  margin: 0;
  font-size: 22px;
  line-height: 28px;
  font-weight: 600;
  letter-spacing: -0.01em;
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
.qb-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: var(--sp-4);
  align-items: start;
}
.qb-main {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
  min-width: 0;
}
.qb-side {
  position: sticky;
  top: var(--sp-4);
}
.panel {
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
  min-width: 0;
}

.sups {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4) var(--sp-4);
}
.sup {
  display: grid;
  grid-template-columns: minmax(200px, 1fr) minmax(220px, 1fr) auto;
  gap: var(--sp-3);
  align-items: center;
  padding-bottom: var(--sp-3);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.sup-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-1);
}
.files {
  grid-column: 1 / -1;
  display: flex;
  gap: var(--sp-1);
  flex-wrap: wrap;
}
.add {
  align-self: flex-start;
}

/* Price lines: a grid table; rows without a price carry the words "No price yet" (amber), not colour alone. */
.lines {
  display: flex;
  flex-direction: column;
  /* The line layout follows the panel, not the window: at 1440 px with the drawer and the summary the panel is
     ~795 px, narrower than the six columns need (~840 px), and the line total was cut off. */
  container: qlines / inline-size;
}
.lrow {
  display: grid;
  grid-template-columns: minmax(160px, 1.4fr) 48px minmax(150px, 1fr) minmax(160px, 1fr) minmax(130px, 0.8fr) minmax(100px, 0.7fr);
  gap: var(--sp-3);
  align-items: center;
  padding: var(--sp-2) var(--sp-4);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
  font-size: 14px;
  line-height: 20px;
  transition: background-color 160ms ease-out;
}
.lrow:last-child {
  border-bottom: 0;
}
.lhead {
  font-size: 11px;
  line-height: 16px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgb(var(--v-theme-secondary));
}
.lrow:target,
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
.cimh {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.cimh-price {
  font-size: 13px;
  color: rgb(var(--v-theme-secondary));
  white-space: nowrap;
}
.price :deep(input),
.rate :deep(input) {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.total {
  white-space: nowrap;
}

.sum-body {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4) var(--sp-4);
}
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
.warn {
  display: flex;
  gap: var(--sp-2);
  align-items: flex-start;
  font-size: 13px;
  color: rgb(var(--v-theme-error));
}
.warn .v-icon {
  flex: none;
  margin-top: 1px;
}
.missing {
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
}
.missing-title {
  font-size: 13px;
  font-weight: 600;
  color: rgb(var(--v-theme-warning));
}
.missing ul {
  margin: var(--sp-1) 0 0;
  padding-left: var(--sp-4);
  font-size: 13px;
}
.send {
  align-self: stretch;
}

@media (max-width: 1099.98px) {
  .qb-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .qb-side {
    position: static;
  }
}
/* Mid-width panel: two rows per line (item, qty, CIMH stock / supplier, price, line total), labels in the cells. */
@container qlines (max-width: 899.98px) {
  .lhead {
    display: none;
  }
  .lrow {
    grid-template-columns: minmax(0, 1.3fr) 56px minmax(0, 1fr) minmax(0, 0.9fr);
    grid-template-areas: 'item qty cimh cimh' 'sup sup price total';
    row-gap: var(--sp-2);
    padding: var(--sp-3) var(--sp-4);
  }
  .lrow > :nth-child(1) { grid-area: item; }
  .lrow > :nth-child(2) { grid-area: qty; }
  .lrow > :nth-child(3) { grid-area: cimh; }
  .lrow > :nth-child(4) { grid-area: sup; }
  .lrow > :nth-child(5) { grid-area: price; }
  .lrow > :nth-child(6) { grid-area: total; align-self: center; }
  .cell-label {
    display: inline;
    color: rgb(var(--v-theme-secondary));
  }
}
/* Narrow: each line becomes a small card (item + qty, then CIMH, supplier, price, total). */
@container qlines (max-width: 599.98px) {
  .lhead {
    display: none;
  }
  .lrow {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    grid-template-areas: 'item qty' 'cimh cimh' 'sup sup' 'price total';
    row-gap: var(--sp-2);
    padding: var(--sp-3) var(--sp-4);
  }
  .lrow > :nth-child(1) { grid-area: item; }
  .lrow > :nth-child(2) { grid-area: qty; }
  .lrow > :nth-child(3) { grid-area: cimh; }
  .lrow > :nth-child(4) { grid-area: sup; }
  .lrow > :nth-child(5) { grid-area: price; }
  .lrow > :nth-child(6) { grid-area: total; align-self: center; }
  .cell-label {
    display: inline;
    color: rgb(var(--v-theme-secondary));
  }
}
/* The supplier list sits outside the lines panel: it still follows the window. */
@media (max-width: 759.98px) {
  .sup {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .sup-file {
    grid-column: 1 / -1;
    grid-row: 2;
  }
}
@media (max-width: 599.98px) {
  .qb {
    padding: var(--sp-3) var(--sp-3) var(--sp-4);
  }
}
@media (prefers-reduced-motion: reduce) {
  .lrow {
    transition: none;
  }
}
</style>
