<script setup lang="ts">
/**
 * A-03 request (staff), Graphite Console. Shown inside the desk (A-02, next to a compact queue) and on its
 * own page (/requests/:id: deep links, email links, phones). Layout follows its own width (container query):
 *   wide   = request on the left, sticky "Next step" panel on the right;
 *   narrow = "Next step" first, then the request (actions never sit at the bottom of a long page).
 * Next step: the actions allowed now (`allowedActions`, the server stays the authority); Cancel is isolated
 * below a seam. Dialogs: verify the signed agreement, then record purchase orders (product names, not line
 * ids); record shipment (local date); mark delivered; reasons for reject / cancel.
 */
import ShipDialog from './ShipDialog.vue'
import {
  act,
  ApiError,
  CARRIERS,
  type Carrier,
  fileUrl,
  getRequest,
  type OrderRequest,
  QuoteTable,
  ReasonDialog,
  RequestFiles,
  RequestTimeline,
  requestTitle,
  ShortRef,
  StatusChip,
  useNotify,
} from '@cimh/web-app'
import { formatDate, formatMoney } from '@cimh/web-ui'
import { mdiArrowRight, mdiClose } from '@mdi/js'
import ICopy from '~icons/material-symbols/content-copy-rounded'
import INote from '~icons/material-symbols/chat-rounded'
import IDone from '~icons/material-symbols/check-circle-rounded'
import IPending from '~icons/material-symbols/radio-button-unchecked'
import INotNeeded from '~icons/material-symbols/do-not-disturb-on-outline-rounded'
import { computed, reactive, ref, watch } from 'vue'
import { BTN, expiresSoon, fmtDate, TONE_ICON, waited, why } from '../request-queue'
import { shortUnit } from '../history'

const props = withDefaults(
  defineProps<{ id: string; embedded?: boolean; /** Where the next request sits relative to the last (queue order). */ direction?: 'next' | 'prev' | 'none' }>(),
  { embedded: false, direction: 'none' },
)
const emit = defineEmits<{ changed: [r: OrderRequest]; close: [] }>()
const notify = useNotify()

const r = ref<OrderRequest | null>(null)
const missing = ref(false)
const failed = ref(false)
const busy = ref<string | null>(null)

async function load() {
  failed.value = false
  missing.value = false
  try {
    const got = await getRequest(props.id)
    if (got.id === props.id) r.value = got
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) missing.value = true
    else failed.value = true
  }
}
// Stepping to another request keeps the previous one on screen (dimmed, inert) until the next arrives, then
// swaps in place: no skeleton flash between requests. The skeleton shows only on the first load.
const stale = computed(() => !!r.value && r.value.id !== props.id)
const swapName = computed(() => `rv-swap-${props.direction}`)
const root = ref<HTMLElement | null>(null)
watch(
  () => props.id,
  () => void load(),
  { immediate: true },
)
watch(
  () => r.value?.id,
  (now, before) => {
    if (!now || !before || now === before) return
    // A new request starts at its top (the embedded view scrolls itself; the own page scrolls the window).
    if (props.embedded) root.value?.scrollTo({ top: 0 })
    else if (root.value && root.value.getBoundingClientRect().top < 0) window.scrollTo({ top: 0 })
  },
  { flush: 'post' },
)
const can = (a: string) => r.value?.allowedActions?.includes(a as never) ?? false

async function run(key: string, path: Parameters<typeof act>[1], body: unknown, done: string): Promise<boolean> {
  if (!r.value) return false
  busy.value = key
  try {
    r.value = await act(r.value, path, body)
    notify.toast(done, 'success')
    emit('changed', r.value)
    return true
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) await load()
    notify.report(e)
    return false
  } finally {
    busy.value = null
  }
}

async function copyId() {
  try {
    await navigator.clipboard.writeText(props.id)
    notify.toast('Request id copied', 'success')
  } catch {
    /* clipboard blocked: the id stays selectable */
  }
}

// ---- reasons
type ReasonKind = 'reject-agreement' | 'reject' | 'cancel'
const reasonFor = ref<ReasonKind | null>(null)
const REASON_TEXT: Record<ReasonKind, { title: string; confirm: string; dismiss: string; text: string; done: string }> = {
  'reject-agreement': { title: 'Reject the signed agreement?', confirm: 'Reject signature', dismiss: 'Back', done: 'Signature rejected; the customer is asked to upload again',
    text: 'Reserved stock is released. The customer is emailed to upload a correctly signed copy.' },
  reject: { title: 'Reject this Pro Bono request?', confirm: 'Reject request', dismiss: 'Keep request', done: 'Request rejected', text: 'The customer is told why.' },
  cancel: { title: 'Cancel this request?', confirm: 'Cancel request', dismiss: 'Keep request', done: 'Request cancelled', text: 'Any reserved stock is released. The customer is told why.' },
}  // prettier-ignore
async function submitReason(reason: string) {
  const kind = reasonFor.value!
  if (await run(kind, `/requests/{requestId}/${kind}`, { reason }, REASON_TEXT[kind].done)) reasonFor.value = null
}

// ---- lines, names and progress
const lineName = (lineId: string) => r.value?.lines.find((l) => l.lineId === lineId)?.product.name ?? lineId
const lineQty = (lineId: string) => r.value?.lines.find((l) => l.lineId === lineId)?.qty ?? 0
/** Lines CIMH picks: every Pro Bono line; on paid requests only lines quoted from CIMH stock. */
const pickLines = computed(() =>
  (r.value?.lines ?? []).filter((l) => r.value!.type === 'PROBONO' || l.source === 'CIMH'),
)
const PICK_STAGES = ['ACCEPTED', 'PURCHASING', 'APPROVED', 'PICKING', 'SHIPPED', 'DELIVERED'] // stock is held from QUOTED
type Step = { label: string; state: 'done' | 'pending' | 'none'; detail: string }
const steps = computed<Step[]>(() => {
  const x = r.value
  if (!x) return []
  const picked = x.lines.reduce((n, l) => n + (l.picked?.length ?? 0), 0)
  const need = pickLines.value.reduce((n, l) => n + l.qty, 0)
  const pickStarted = PICK_STAGES.includes(x.status)
  const pick: Step =
    pickStarted && need === 0
      ? { label: 'Picked', state: 'none', detail: 'Not needed: supplier items ship direct' }
      : {
          label: 'Picked',
          state: pickStarted && picked >= need && need > 0 ? 'done' : 'pending',
          detail: pickStarted ? `${picked} of ${need} units` : 'After acceptance',
        }
  const carrier = x.shipping ? CARRIERS.find((c) => c.value === x.shipping!.carrier)?.title : ''
  return [
    pick,
    x.shipping
      ? { label: 'Shipped', state: 'done', detail: [carrier, x.shipping.tracking, x.shipping.note, x.shipping.date ? formatDate(x.shipping.date) : null].filter(Boolean).join(' · ') }
      : { label: 'Shipped', state: 'pending', detail: 'Not shipped' },
    // Pro Bono requests are free: they get a Pro Bono note, never an invoice.
    ...(x.type === 'PROBONO'
      ? []
      : [
          x.invoice
            ? { label: 'Invoiced', state: 'done' as const, detail: x.invoice.number ?? 'Invoiced' }
            : { label: 'Invoiced', state: 'pending' as const, detail: 'No invoice yet' },
        ]),
  ]
})
const STEP_ICON = { done: IDone, pending: IPending, none: INotNeeded } as const
// Columns that carry nothing at this stage stay hidden.
const showStock = computed(() => r.value?.lines.some((l) => l.cimhAvailable !== null && l.cimhAvailable !== undefined) ?? false)
const showSource = computed(() => r.value?.lines.some((l) => !!l.source) ?? false)
const showReservation = computed(() => r.value?.lines.some((l) => !!l.reservation?.status) ?? false)
const showPicked = computed(() => r.value ? PICK_STAGES.includes(r.value.status) && pickLines.value.length > 0 : false)
const reservationLabel = (s?: string) =>
  ({ NONE: 'Reserving…', RESERVED: 'Reserved', FAILED: 'Not enough stock', RELEASED: 'Released' })[s ?? ''] ?? ''
const money = (v?: string | null) => (v && r.value ? formatMoney(v, r.value.currency ?? 'BBD') : '')
const signed = computed(() => r.value?.agreement?.signedFileId ?? null)
type PurchaseOrder = { supplier: string; poNumber: string; lineIds?: string[] }
const purchaseOrders = computed(() => (r.value?.purchaseOrders ?? []) as unknown as PurchaseOrder[])

// ---- verify the signed agreement, then purchase orders
const poOpen = ref(false)
const po = reactive({ verified: false, rows: [] as { supplier: string; poNumber: string; lineIds: string[] }[] })
function openPo() {
  const x = r.value
  if (!x) return
  const supplierLines = new Set(x.lines.filter((l) => l.source === 'SUPPLIER').map((l) => l.lineId))
  const latest = Math.max(0, ...(x.quotes ?? []).map((q) => q.version))
  const bySupplier = new Map<string, string[]>()
  const taken = new Set<string>() // a line belongs to one supplier only
  for (const q of x.quotes ?? []) {
    if (q.version !== latest) continue
    for (const l of q.lines) {
      if (!supplierLines.has(l.lineId) || taken.has(l.lineId)) continue
      taken.add(l.lineId)
      const name = q.supplier ?? ''
      bySupplier.set(name, [...(bySupplier.get(name) ?? []), l.lineId])
    }
  }
  po.verified = false
  po.rows = [...bySupplier].map(([supplier, lineIds]) => ({ supplier, poNumber: '', lineIds }))
  poOpen.value = true
}
const poValid = computed(() => po.verified && po.rows.every((x) => x.supplier.trim() && x.poNumber.trim() && x.lineIds.length))
async function submitPo() {
  const body = { agreementVerified: po.verified, purchaseOrders: po.rows.map((x) => ({ ...x, supplier: x.supplier.trim(), poNumber: x.poNumber.trim() })) }
  if (await run('po', '/requests/{requestId}/purchase-orders', body, 'Signature verified; purchasing')) poOpen.value = false
}

// ---- ship / deliver (dates in local time: Barbados is UTC-4, so toISOString would give tomorrow after 20:00)
const localToday = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const shipOpen = ref(false)
const openShip = () => (shipOpen.value = true)
async function submitShip(body: Record<string, unknown>) {
  if (await run('ship', '/requests/{requestId}/ship', body, 'Shipment recorded')) shipOpen.value = false
}
const deliverOpen = ref(false)
const invoiceNumber = ref('')
async function submitDeliver() {
  const body = invoiceNumber.value.trim() ? { invoiceNumber: invoiceNumber.value.trim() } : {}
  if (await run('deliver', '/requests/{requestId}/deliver', body, 'Marked delivered')) deliverOpen.value = false
}
</script>

<template>
  <article ref="root" class="rv" :class="{ embedded }" :aria-label="`Request ${id}`">
    <div v-if="missing" class="state">
      <p class="t-body-lg">No request with this id.</p>
      <v-btn to="/requests" variant="outlined" class="m3">Back to requests</v-btn>
    </div>
    <div v-else-if="failed" class="state">
      <p class="t-body-lg">Couldn't load this request.</p>
      <v-btn variant="outlined" class="m3" :prepend-icon="BTN.retry" @click="load">Retry</v-btn>
    </div>
    <div v-else-if="!r" class="skel">
      <div class="console-skel sk-head" />
      <div class="console-skel sk-body" />
    </div>

    <template v-else>
      <Transition :name="swapName" mode="out-in">
      <div :key="r.id" class="rv-body" :class="{ stale }" :inert="stale || undefined" :aria-busy="stale">
      <header class="rv-head">
        <div class="rv-title">
          <p class="who">
            {{ requestTitle(r.lines[0]?.product.name, r.lines.length, r.type) }}
            <span v-if="r.type === 'PROBONO'" class="probono-badge">Pro Bono</span>
          </p>
          <p class="id-line">
            <span class="customer">{{ [r.organisationName, r.customerName].filter(Boolean).join(' · ') }}</span>
            <span aria-hidden="true">·</span>
            <span class="console-mono"><ShortRef :id="r.id" /></span>
            <v-btn variant="text" size="x-small" :icon="ICopy" aria-label="Copy request id" @click="copyId" />
          </p>
        </div>
        <div class="rv-meta">
          <StatusChip :status="r.status" />
          <span class="t-caption muted">{{ (r.waitingDays ?? 0) === 0 ? 'In this status since today' : `In this status for ${waited(r)}` }}</span>
          <span v-if="r.quoteExpiresAt" class="t-caption" :class="expiresSoon(r) ? 'expiring' : 'muted'">
            Quote expires <span class="console-mono">{{ fmtDate(r.quoteExpiresAt) }}</span>
          </span>
          <template v-if="embedded">
            <router-link :to="`/requests/${r.id}`" class="own-page">Own page <v-icon :icon="mdiArrowRight" size="14" /></router-link>
            <v-btn variant="text" size="small" :icon="mdiClose" aria-label="Close request, back to the list" @click="emit('close')" />
          </template>
        </div>
      </header>

      <div class="rv-grid">
        <!-- Next step: first on narrow widths, sticky on the right when wide. -->
        <aside class="next-col" aria-label="Next step">
          <section class="next" :class="why(r).tone">
            <h2 class="console-title">Next step</h2>
            <p class="next-text"><v-icon :icon="TONE_ICON[why(r).tone]" size="18" />{{ why(r).text }}</p>
            <div class="next-actions">
              <p v-if="!r.allowedActions?.length" class="t-caption muted">Nothing for staff to do on this request now.</p>
              <v-btn
                v-if="can('start-quoting')"
                class="m3"
                color="primary"
                :prepend-icon="BTN.quote"
                :loading="busy === 'start'"
                :disabled="!!busy"
                @click="run('start', '/requests/{requestId}/start-quoting', undefined, 'Quoting started; stock checked')"
              >Start quoting</v-btn>
              <!-- While QUOTED the customer acts next: revising is a secondary move, not the main button. -->
              <v-btn
                v-if="can('quote-draft')"
                :to="`/requests/${r.id}/quote`"
                class="m3"
                :color="r.status === 'QUOTED' ? undefined : 'primary'"
                :variant="r.status === 'QUOTED' ? 'outlined' : 'flat'"
                :prepend-icon="BTN.draft"
              >
                {{ r.status === 'QUOTED' ? 'Revise quote' : 'Build quote' }}
              </v-btn>
              <template v-if="can('purchase-orders')">
                <v-btn class="m3" color="primary" :prepend-icon="BTN.verify" :disabled="!!busy" @click="openPo">Verify and purchase</v-btn>
                <v-btn v-if="signed" :href="fileUrl(signed)" target="_blank" variant="outlined" class="m3" :prepend-icon="BTN.signed">Signed agreement</v-btn>
              </template>
              <v-btn
                v-if="can('approve')"
                class="m3"
                color="primary"
                :prepend-icon="BTN.approve"
                :loading="busy === 'approve'"
                :disabled="!!busy"
                @click="run('approve', '/requests/{requestId}/approve', undefined, 'Approved; stock is being reserved')"
              >Approve</v-btn>
              <v-btn v-if="can('pick')" :to="{ path: '/pick', query: { op: 'order', request: r.id } }" class="m3" color="primary" :prepend-icon="BTN.pick">Pick</v-btn>
              <v-btn v-if="can('ship')" class="m3" color="primary" :prepend-icon="BTN.ship" :disabled="!!busy" @click="openShip">Record shipment</v-btn>
              <v-btn v-if="can('deliver')" class="m3" color="primary" :prepend-icon="BTN.deliver" :disabled="!!busy" @click="deliverOpen = true">Mark delivered</v-btn>
              <v-btn v-if="can('reject-agreement')" variant="outlined" class="m3" :disabled="!!busy" @click="reasonFor = 'reject-agreement'">Reject signature</v-btn>
            </div>
            <div v-if="can('reject') || can('cancel')" class="danger-zone">
              <v-btn v-if="can('reject')" variant="outlined" class="m3 m3-danger" :prepend-icon="BTN.reject" :disabled="!!busy" @click="reasonFor = 'reject'">Reject request</v-btn>
              <v-btn v-if="can('cancel')" variant="outlined" class="m3 m3-danger" :prepend-icon="BTN.reject" :disabled="!!busy" @click="reasonFor = 'cancel'">Cancel request</v-btn>
            </div>
          </section>
        </aside>

        <div class="main-col">
          <p v-if="r.notes" class="note"><v-icon :icon="INote" size="16" /><span><strong>Customer note</strong> {{ r.notes }}</span></p>

          <section class="panel">
            <header class="console-head"><h2 class="console-title">Request</h2></header>
            <div class="facts-grid">
              <dl class="facts">
                <div><dt>Customer</dt><dd>{{ r.customerName }}</dd></div>
                <div><dt>Organisation</dt><dd>{{ r.organisationName ?? '—' }}</dd></div>
                <div><dt>Type</dt><dd>{{ r.type === 'PROBONO' ? 'Pro Bono' : 'Paid' }}<template v-if="r.currency"> · <span class="console-mono">{{ r.currency }}</span></template></dd></div>
                <div><dt>Submitted</dt><dd class="console-mono">{{ formatDate(r.submittedAt) }}</dd></div>
              </dl>
              <div v-if="r.shipTo" class="ship-to">
                <p class="dt">Ship to</p>
                <p>{{ r.shipTo.firstname }} {{ r.shipTo.lastname }}</p>
                <p>{{ r.shipTo.organisation }}</p>
                <p>{{ r.shipTo.line1 }}{{ r.shipTo.line2 ? `, ${r.shipTo.line2}` : '' }}</p>
                <p>{{ [r.shipTo.city, r.shipTo.parish, r.shipTo.zip].filter(Boolean).join(' ') }} · {{ r.shipTo.country }}</p>
                <p class="muted">{{ r.shipTo.email }}{{ r.shipTo.tel ? ` · ${r.shipTo.tel}` : '' }}</p>
              </div>
            </div>
            <ol class="steps" aria-label="Fulfilment">
              <li v-for="s in steps" :key="s.label" :class="s.state">
                <v-icon :icon="STEP_ICON[s.state]" size="16" />
                <span class="step-label">{{ s.label }}</span>
                <span class="step-detail">{{ s.detail }}</span>
              </li>
            </ol>
          </section>

          <section class="panel">
            <header class="console-head">
              <h2 class="console-title">Items</h2>
              <span class="t-caption muted console-mono">{{ r.lines.length }}</span>
            </header>
            <div class="table-wrap">
              <table class="items">
                <thead>
                  <tr>
                    <th>Item</th>
                    <th class="num">Qty</th>
                    <th v-if="showStock">CIMH stock</th>
                    <th v-if="showSource">From</th>
                    <th v-if="showReservation">Reservation</th>
                    <th v-if="showPicked" class="num">Picked</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="l in r.lines" :key="l.lineId">
                    <td>
                      <router-link :to="`/products/${l.productId}`" class="item-link">{{ l.product.name }}</router-link>
                      <span v-if="l.product.probono" class="probono-badge sm">Pro Bono</span>
                    </td>
                    <td class="num console-mono" data-label="Qty"><span>{{ l.qty }}</span></td>
                    <td v-if="showStock" data-label="CIMH stock"><span>{{ l.cimhAvailable === null || l.cimhAvailable === undefined ? '—' : l.cimhAvailable ? 'Full quantity' : 'Not enough' }}</span></td>
                    <td v-if="showSource" data-label="From"><span>{{ l.source === 'CIMH' ? 'CIMH stock' : l.source === 'SUPPLIER' ? `${l.supplier ?? 'Supplier'} (ships direct)` : '—' }}</span></td>
                    <td v-if="showReservation" data-label="Reservation">
                      <span :class="{ failed: l.reservation?.status === 'FAILED' }">{{ reservationLabel(l.reservation?.status) || '—' }}</span>
                      <span v-if="l.reservation?.units?.length" class="units console-mono" :title="l.reservation.units.join(', ')">{{ l.reservation.units.map(shortUnit).join(', ') }}</span>
                    </td>
                    <td v-if="showPicked" class="num console-mono" data-label="Picked"><span>{{ l.picked?.length ?? 0 }}</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section v-if="r.quotes?.length || r.cimhQuote" class="panel">
            <header class="console-head"><h2 class="console-title">Quote</h2></header>
            <div class="pad">
              <QuoteTable :request="r" staff />
              <ul v-if="r.agreement?.rejections?.length" class="rejections">
                <li v-for="(rej, i) in r.agreement.rejections" :key="i" class="muted">
                  Signature rejected <span class="console-mono">{{ formatDate(rej.at!) }}</span>: {{ rej.reason }}
                </li>
              </ul>
            </div>
          </section>

          <section v-if="purchaseOrders.length" class="panel">
            <header class="console-head"><h2 class="console-title">Purchase orders</h2></header>
            <ul class="pos">
              <li v-for="(p, i) in purchaseOrders" :key="i">
                <span class="po-sup">{{ p.supplier }}</span>
                <span class="console-mono">{{ p.poNumber }}</span>
                <span class="muted">{{ (p.lineIds ?? []).map((id) => `${lineQty(id)}× ${lineName(id)}`).join(', ') }}</span>
              </li>
            </ul>
          </section>

          <section class="panel">
            <header class="console-head"><h2 class="console-title">Files</h2></header>
            <div class="pad"><RequestFiles :files="r.files ?? []" bare /></div>
          </section>
          <section class="panel">
            <header class="console-head"><h2 class="console-title">Timeline</h2></header>
            <div class="pad"><RequestTimeline :request="r" history /></div>
          </section>
        </div>
      </div>
      </div>
      </Transition>

      <ReasonDialog
        :model-value="reasonFor !== null"
        v-bind="reasonFor ? REASON_TEXT[reasonFor] : { title: '', confirm: '' }"
        danger
        :busy="!!busy"
        @update:model-value="(v: boolean) => !v && (reasonFor = null)"
        @submit="submitReason"
      />

      <v-dialog v-model="poOpen" max-width="640" scrollable>
        <v-card title="Verify the agreement, then record purchase orders">
          <v-card-text class="dlg">
            <section class="dlg-step">
              <h3 class="console-title">1 · Check the signature</h3>
              <v-btn v-if="signed" :href="fileUrl(signed)" target="_blank" variant="outlined" class="m3" :prepend-icon="BTN.signed">Open the signed agreement</v-btn>
              <p v-else class="t-caption muted">No signed agreement is attached.</p>
              <v-checkbox v-model="po.verified" label="The signed agreement is complete and signed by an authorised person" hide-details />
            </section>
            <section class="dlg-step" :class="{ off: !po.verified }">
              <h3 class="console-title">2 · Purchase orders</h3>
              <p v-if="!po.rows.length" class="t-body muted">Every item comes from CIMH stock: no purchase order is needed.</p>
              <div v-for="(row, i) in po.rows" :key="i" class="po-row">
                <v-text-field v-model="row.supplier" label="Supplier" :placeholder="row.supplier ? undefined : 'Supplier name'" hide-details density="compact" :disabled="!po.verified" />
                <v-text-field v-model="row.poNumber" label="PO number" hide-details density="compact" :disabled="!po.verified" />
                <p class="po-lines">{{ row.lineIds.map((id) => `${lineQty(id)}× ${lineName(id)}`).join(' · ') }}</p>
              </div>
            </section>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="poOpen = false">Back</v-btn>
            <v-btn color="primary" variant="flat" class="m3" :disabled="!poValid" :loading="busy === 'po'" @click="submitPo">Start purchasing</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <ShipDialog v-model="shipOpen" :request-id="r.id" :customer="r.organisationName || r.customerName || null" :busy="busy === 'ship'" @submit="submitShip" />

      <v-dialog v-model="deliverOpen" max-width="480">
        <v-card title="Mark delivered">
          <v-card-text>
            <v-text-field v-model="invoiceNumber" label="Invoice number (optional)" />
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="deliverOpen = false">Back</v-btn>
            <v-btn color="primary" variant="flat" class="m3" :loading="busy === 'deliver'" @click="submitDeliver">Mark delivered</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </template>
  </article>
</template>

<style scoped>
.rv {
  container-type: inline-size;
  display: flex;
  flex-direction: column;
  min-width: 0;
  animation: console-swap-in 200ms var(--ease-out) both;
}
/* Swap between requests: the old one dims (after a beat, so fast loads never flicker), leaves quickly, and
   the next arrives from the side of the queue it came from (below for the next row, above for the previous). */
.rv-body {
  display: flex;
  flex-direction: column;
  min-width: 0;
  transition: opacity 160ms ease-out;
}
.rv-body.stale {
  opacity: 0.55;
  transition-delay: 150ms;
  cursor: progress;
}
.rv-swap-next-leave-active,
.rv-swap-prev-leave-active,
.rv-swap-none-leave-active {
  transition:
    opacity 90ms ease-in,
    transform 90ms ease-in;
}
.rv-swap-next-enter-active,
.rv-swap-prev-enter-active,
.rv-swap-none-enter-active {
  transition:
    opacity 200ms ease-out,
    transform 260ms var(--ease-out);
}
.rv-swap-next-leave-to,
.rv-swap-prev-leave-to,
.rv-swap-none-leave-to,
.rv-swap-next-enter-from,
.rv-swap-prev-enter-from,
.rv-swap-none-enter-from {
  opacity: 0;
}
.rv-swap-next-leave-to {
  transform: translateY(-6px);
}
.rv-swap-next-enter-from {
  transform: translateY(12px);
}
.rv-swap-prev-leave-to {
  transform: translateY(6px);
}
.rv-swap-prev-enter-from {
  transform: translateY(-12px);
}
.rv-swap-none-enter-from {
  transform: translateX(8px);
}
.rv p {
  margin: 0;
}
.state {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--sp-3);
  padding: var(--sp-8) var(--sp-4);
}
.skel {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding: var(--sp-4);
}
.sk-head {
  height: 56px;
  border-radius: 4px;
}
.sk-body {
  height: 320px;
  border-radius: 4px;
}

/* Header: who + id on the left; status, waiting, expiry (and close when embedded) on the right. */
.rv-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--sp-2) var(--sp-4);
  padding: var(--sp-3) var(--sp-4);
  /* Open request = a graphite bar (theme ink at 7% over the surface): neutral, but clearly not the summary panel. */
  border-bottom: 1px solid color-mix(in srgb, rgb(var(--v-theme-on-surface)) 16%, rgb(var(--v-theme-surface)));
  background: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 7%, rgb(var(--v-theme-surface)));
}
.who {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-2);
  font-size: 20px;
  line-height: 26px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.id-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px var(--sp-2);
  font-size: 13px;
  color: rgb(var(--v-theme-secondary));
}
.id-line .customer {
  min-width: 0;
  overflow-wrap: anywhere;
}
.rv-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-3);
}
.expiring {
  color: rgb(var(--v-theme-error));
  font-weight: 600;
}
.own-page {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
}
.own-page:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

/* Body: one column (Next step first) until the view itself is wide enough for two. */
.rv-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-areas: 'next' 'main';
  gap: var(--sp-4);
  padding: var(--sp-4);
}
@container (min-width: 880px) {
  .rv-grid {
    grid-template-columns: minmax(0, 1fr) 300px;
    grid-template-areas: 'main next';
    align-items: start;
  }
  .next-col {
    position: sticky;
    top: var(--sp-4);
  }
}
.next-col {
  grid-area: next;
}
.main-col {
  grid-area: main;
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
  min-width: 0;
}
.next {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4) var(--sp-4);
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface-variant));
}
.next-text {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: 16px;
  line-height: 22px;
  font-weight: 600;
}
.next-text .v-icon {
  color: rgb(var(--v-theme-primary));
}
.next.wait .next-text .v-icon,
.next.closed .next-text .v-icon {
  color: rgb(var(--v-theme-secondary));
}
.next.urgent .next-text,
.next.urgent .next-text .v-icon {
  color: rgb(var(--v-theme-warning));
}
.next.expiring .next-text,
.next.expiring .next-text .v-icon {
  color: rgb(var(--v-theme-error));
}
.next-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
  margin-top: var(--sp-1);
}
.danger-zone {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
  margin-top: var(--sp-3);
  padding-top: var(--sp-3);
  border-top: 1px solid rgb(var(--v-theme-seam));
}

.note {
  display: flex;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4);
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
  font-size: 14px;
  line-height: 20px;
  max-width: 80ch;
}
.note .v-icon {
  flex: none;
  margin-top: 2px;
  color: rgb(var(--v-theme-primary));
}
.note strong {
  margin-right: var(--sp-1);
}
.panel {
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
  min-width: 0;
}
.pad {
  padding: var(--sp-3) var(--sp-4);
}
.facts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--sp-4);
  padding: var(--sp-3) var(--sp-4);
}
.facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sp-3);
  margin: 0;
}
.facts dt,
.ship-to .dt {
  font-size: 12px;
  line-height: 16px;
  color: rgb(var(--v-theme-secondary));
}
.facts dd {
  margin: 2px 0 0;
  font-size: 14px;
  line-height: 20px;
}
.ship-to {
  font-size: 14px;
  line-height: 20px;
}
.ship-to .dt {
  margin-bottom: 2px;
}
.steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.steps li {
  display: grid;
  grid-template-columns: auto 1fr;
  column-gap: var(--sp-2);
  align-items: center;
  padding: var(--sp-2) var(--sp-4);
  font-size: 13px;
  line-height: 18px;
}
.steps li + li {
  border-left: 1px solid rgb(var(--v-theme-seam));
}
.steps .v-icon {
  grid-row: span 2;
  color: rgb(var(--v-theme-secondary));
}
.steps li.done .v-icon {
  color: rgb(var(--v-theme-success));
}
.step-label {
  font-weight: 600;
}
.step-detail {
  color: rgb(var(--v-theme-secondary));
  overflow-wrap: anywhere;
}
@container (max-width: 520px) {
  .steps {
    grid-template-columns: 1fr;
  }
  .steps li + li {
    border-left: 0;
    border-top: 1px solid rgb(var(--v-theme-seam));
  }
  .facts {
    grid-template-columns: 1fr 1fr;
  }
}

.table-wrap {
  overflow-x: auto;
  container-type: inline-size;
}
/* Narrow panels (phones): one block per line, each value with its label, instead of a table cut at the edge. */
@container (max-width: 519px) {
  .items thead {
    display: none;
  }
  .items tr {
    display: block;
    padding: var(--sp-2) 0;
    border-bottom: 1px solid rgb(var(--v-theme-seam));
  }
  .items tr:last-child {
    border-bottom: 0;
  }
  .items td {
    display: flex;
    justify-content: space-between;
    gap: var(--sp-3);
    padding: 2px var(--sp-4);
    border-bottom: 0;
    text-align: left;
  }
  .items td > span {
    min-width: 0;
    text-align: right;
    overflow-wrap: anywhere;
  }
  .items td[data-label="Reservation"] {
    flex-wrap: wrap;
  }
  .items td[data-label="Reservation"] > .units {
    flex-basis: 100%;
    text-align: left;
  }
  .items td[data-label]::before {
    content: attr(data-label);
    color: rgb(var(--v-theme-secondary));
    font-family: Inter, sans-serif;
  }
}
.items {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
  line-height: 20px;
}
.items th {
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgb(var(--v-theme-secondary));
  padding: var(--sp-2) var(--sp-4);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
  white-space: nowrap;
}
.items td {
  padding: var(--sp-2) var(--sp-4);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
  vertical-align: top;
}
.items tr:last-child td {
  border-bottom: 0;
}
.items .num {
  text-align: right;
}
.item-link {
  color: inherit;
  font-weight: 500;
  text-decoration: none;
}
.item-link:hover {
  color: rgb(var(--v-theme-primary));
  text-decoration: underline;
  text-underline-offset: 3px;
}
.probono-badge.sm {
  margin-left: var(--sp-2);
}
.failed {
  color: rgb(var(--v-theme-error));
  font-weight: 600;
}
.units {
  display: block;
  font-size: 12px;
  color: rgb(var(--v-theme-secondary));
}
.agreement {
  margin-top: var(--sp-3) !important;
}
.rejections {
  margin: var(--sp-2) 0 0;
  padding-left: var(--sp-4);
  font-size: 13px;
}
.pos {
  list-style: none;
  margin: 0;
  padding: 0;
}
.pos li {
  display: grid;
  grid-template-columns: minmax(120px, 1fr) minmax(100px, auto) minmax(0, 2fr);
  gap: var(--sp-3);
  padding: var(--sp-2) var(--sp-4);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
  font-size: 14px;
}
.pos li:last-child {
  border-bottom: 0;
}
.po-sup {
  font-weight: 500;
}

.dlg {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.dlg-step {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--sp-2);
}
.dlg-step.off {
  opacity: 0.6;
}
.po-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-2);
  width: 100%;
}
.po-lines {
  grid-column: 1 / -1;
  font-size: 13px;
  color: rgb(var(--v-theme-secondary));
}
.two {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-3);
}
.mono-input :deep(input) {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}
@media (max-width: 599.98px) {
  .po-row,
  .two {
    grid-template-columns: 1fr;
  }
  .pos li {
    grid-template-columns: 1fr auto;
  }
  .pos li .muted {
    grid-column: 1 / -1;
  }
}
@media (prefers-reduced-motion: reduce) {
  .rv {
    animation-name: console-fade-in;
  }
  [class*='rv-swap-'][class*='-from'],
  [class*='rv-swap-'][class*='-to'] {
    transform: none;
  }
}
</style>
