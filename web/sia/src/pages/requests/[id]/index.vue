<script setup lang="ts">
/**
 * A-03 request (staff), in the legacy SIA OrdersInternal structure: the "paper" with Ship to, Request # and
 * date, then the fulfilment sections (Shipping, Picked, Invoiced) and the items table. v2 adds the lines'
 * CIMH availability, choice and reservation; the quote; files; the full timeline; and an action panel whose
 * buttons come from `allowedActions`. Dialogs: purchase orders (with the signature check), ship, deliver,
 * and reasons for reject / cancel.
 */
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
  StatusChip,
  useNotify,
} from '@cimh/web-app'
import { formatDate, formatMoney } from '@cimh/web-ui'
import { mdiArrowLeft, mdiFileSign } from '@mdi/js'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

definePage({ meta: { guard: 'staff', title: 'Request' } })
const route = useRoute('/requests/[id]/')
const router = useRouter()
const notify = useNotify()
const r = ref<OrderRequest | null>(null)
const missing = ref(false)
const busy = ref(false)

async function load() {
  try {
    r.value = await getRequest(route.params.id)
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) missing.value = true
    else notify.report(e)
  }
}
watch(() => route.params.id, () => void load(), { immediate: true })
const can = (a: string) => r.value?.allowedActions?.includes(a as never) ?? false

async function run(path: Parameters<typeof act>[1], body: unknown, done: string): Promise<boolean> {
  if (!r.value) return false
  busy.value = true
  try {
    r.value = await act(r.value, path, body)
    notify.toast(done, 'success')
    return true
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) await load()
    notify.report(e)
    return false
  } finally {
    busy.value = false
  }
}

// ---- reasons
type ReasonKind = 'reject-agreement' | 'reject' | 'cancel'
const reasonFor = ref<ReasonKind | null>(null)
const REASON_TEXT: Record<ReasonKind, { title: string; confirm: string; text: string; done: string }> = {
  'reject-agreement': { title: 'Reject the signed agreement?', confirm: 'Reject signature', done: 'Signature rejected; the customer is asked to upload again',
    text: 'Reserved stock is released. The customer is emailed to upload a correctly signed copy.' },
  reject: { title: 'Reject this Pro Bono request?', confirm: 'Reject request', done: 'Request rejected', text: 'The customer is told why.' },
  cancel: { title: 'Cancel this request?', confirm: 'Cancel request', done: 'Request cancelled', text: 'Any reserved stock is released.' },
}  // prettier-ignore
async function submitReason(reason: string) {
  const kind = reasonFor.value!
  if (await run(`/requests/{requestId}/${kind}`, { reason }, REASON_TEXT[kind].done)) reasonFor.value = null
}

// ---- purchase orders (+ signature verification)
const poOpen = ref(false)
const supplierLines = computed(() => r.value?.lines.filter((l) => l.choice === 'SUPPLIER') ?? [])
const po = reactive({ verified: false, rows: [] as { supplier: string; poNumber: string; lineIds: string[] }[] })
function openPo() {
  const bySupplier = new Map<string, string[]>()
  for (const q of r.value?.quotes ?? []) {
    if (q.version !== Math.max(...(r.value?.quotes ?? []).map((x) => x.version))) continue
    for (const l of q.lines)
      if (supplierLines.value.some((s) => s.lineId === l.lineId))
        bySupplier.set(q.supplier ?? '', [...(bySupplier.get(q.supplier ?? '') ?? []), l.lineId])
  }
  po.verified = false
  po.rows = [...bySupplier].map(([supplier, lineIds]) => ({ supplier, poNumber: '', lineIds }))
  poOpen.value = true
}
const poValid = computed(() => po.verified && po.rows.every((x) => x.supplier.trim() && x.poNumber.trim() && x.lineIds.length))
async function submitPo() {
  const body = { agreementVerified: po.verified, purchaseOrders: po.rows.map((x) => ({ ...x, supplier: x.supplier.trim(), poNumber: x.poNumber.trim() })) }
  if (await run('/requests/{requestId}/purchase-orders', body, 'Signature verified; purchasing')) poOpen.value = false
}

// ---- ship / deliver
const shipOpen = ref(false)
const ship = reactive({ carrier: 'DHL' as Carrier, tracking: '', note: '', cost: '', date: new Date().toISOString().slice(0, 10), notifyCustomer: true })
const shipValid = computed(() => (ship.carrier === 'HAND' || ship.tracking.trim()) && (!ship.cost || /^\d{1,12}\.\d{2}$/.test(ship.cost)))
async function submitShip() {
  const body = { carrier: ship.carrier, date: ship.date, notifyCustomer: ship.notifyCustomer,
    tracking: ship.tracking.trim() || null, note: ship.note.trim() || null, cost: ship.cost || null }  // prettier-ignore
  if (await run('/requests/{requestId}/ship', body, 'Shipment recorded')) shipOpen.value = false
}
const deliverOpen = ref(false)
const invoiceNumber = ref('')
async function submitDeliver() {
  const body = invoiceNumber.value.trim() ? { invoiceNumber: invoiceNumber.value.trim() } : {}
  if (await run('/requests/{requestId}/deliver', body, 'Marked delivered')) deliverOpen.value = false
}

const signed = computed(() => r.value?.agreement?.signedFileId ?? null)
const reservationLabel = (s?: string) => ({ NONE: 'Reserving…', RESERVED: 'Reserved', FAILED: 'Not enough stock', RELEASED: 'Released' })[s ?? ''] ?? ''
const money = (v?: string | null) => (v && r.value ? formatMoney(v, r.value.currency ?? 'BBD') : '')
</script>

<template>
  <div class="page stack-md">
    <v-btn to="/requests" variant="text" :prepend-icon="mdiArrowLeft" class="back">Requests</v-btn>
    <p v-if="missing" class="t-body">No request with this id.</p>
    <v-skeleton-loader v-else-if="!r" type="heading, table" />
    <div v-else class="layout">
      <div class="main stack-md">
        <v-card border flat class="paper">
          <div class="paper-head">
            <div>
              <p class="t-label muted">Ship to</p>
              <template v-if="r.shipTo">
                <p class="t-label">{{ r.shipTo.firstname.toUpperCase() }} {{ r.shipTo.lastname.toUpperCase() }}</p>
                <p class="t-body">{{ r.shipTo.organisation }}</p>
                <p class="t-body">{{ r.shipTo.line1 }}{{ r.shipTo.line2 ? `, ${r.shipTo.line2}` : '' }}</p>
                <p class="t-body">{{ [r.shipTo.city, r.shipTo.parish, r.shipTo.zip].filter(Boolean).join(' ') }}</p>
                <p class="t-body">{{ r.shipTo.country }} · {{ r.shipTo.email }}{{ r.shipTo.tel ? ` · ${r.shipTo.tel}` : '' }}</p>
              </template>
            </div>
            <div class="meta">
              <p><span class="muted">Request #</span> <span class="t-mono">{{ r.id }}</span></p>
              <p><span class="muted">Date</span> {{ formatDate(r.submittedAt) }}</p>
              <p><span class="muted">Customer</span> {{ r.customerName }}</p>
              <p><span class="muted">Organisation</span> {{ r.organisationName ?? '—' }}</p>
              <p><span class="muted">Type</span> {{ r.type === 'PROBONO' ? 'Pro Bono' : `Paid · ${r.currency}` }}</p>
              <StatusChip :status="r.status" />
            </div>
          </div>

          <div class="sections">
            <div :class="['sec', r.shipping ? 'done' : '']">
              <p class="t-label">Shipping</p>
              <p v-if="r.shipping" class="t-body">
                {{ CARRIERS.find((c) => c.value === r!.shipping!.carrier)?.title }} {{ r.shipping.tracking ?? '' }}
                <span v-if="r.shipping.date" class="muted">· {{ formatDate(r.shipping.date) }}</span>
              </p>
              <p v-else class="t-caption muted">Not shipped</p>
            </div>
            <div :class="['sec', r.lines.every((l) => (l.picked?.length ?? 0) >= l.qty || (r!.type === 'PAID' && l.choice !== 'CIMH')) ? 'done' : '']">
              <p class="t-label">Picked</p>
              <p class="t-body tnum">{{ r.lines.reduce((n, l) => n + (l.picked?.length ?? 0), 0) }} units</p>
            </div>
            <div :class="['sec', r.invoice ? 'done' : '']">
              <p class="t-label">Invoiced</p>
              <p class="t-body">{{ r.invoice?.number ?? '—' }}</p>
            </div>
          </div>

          <v-table density="comfortable">
            <thead>
              <tr><th>Item</th><th class="num">Qty</th><th>CIMH stock</th><th>Choice</th><th>Reservation</th><th class="num">Picked</th></tr>
            </thead>
            <tbody>
              <tr v-for="l in r.lines" :key="l.lineId">
                <td>
                  <router-link :to="`/products/${l.productId}`" class="t-label">{{ l.product.name }}</router-link>
                  <span v-if="l.product.probono" class="t-caption muted"> · Pro Bono</span>
                </td>
                <td class="num tnum">{{ l.qty }}</td>
                <td>{{ l.cimhAvailable === null || l.cimhAvailable === undefined ? '' : l.cimhAvailable ? 'Full quantity' : 'Not enough' }}</td>
                <td>{{ l.choice === 'CIMH' ? 'CIMH stock' : l.choice === 'SUPPLIER' ? 'Supplier' : '' }}</td>
                <td>
                  <span :class="{ 'text-error': l.reservation?.status === 'FAILED' }">{{ reservationLabel(l.reservation?.status) }}</span>
                  <span v-if="l.reservation?.units?.length" class="t-caption muted d-block t-mono">{{ l.reservation.units.join(', ') }}</span>
                </td>
                <td class="num tnum">{{ l.picked?.length ?? 0 }}</td>
              </tr>
            </tbody>
          </v-table>
          <p v-if="r.notes" class="t-body notes"><strong>Customer notes:</strong> {{ r.notes }}</p>
        </v-card>

        <section v-if="r.quotes?.length">
          <h2 class="t-h3">Quote</h2>
          <QuoteTable :request="r" staff />
          <p v-if="r.agreement" class="t-body">
            Agreement total <strong class="tnum">{{ money(r.agreement.total) }}</strong>
            <template v-for="(rej, i) in r.agreement.rejections ?? []" :key="i"><br /><span class="muted">Signature rejected {{ formatDate(rej.at!) }}: {{ rej.reason }}</span></template>
          </p>
        </section>

        <section v-if="r.purchaseOrders?.length">
          <h2 class="t-h3">Purchase orders</h2>
          <v-table density="compact">
            <tbody>
              <tr v-for="(p, i) in r.purchaseOrders as any[]" :key="i">
                <td>{{ p.supplier }}</td><td class="t-mono">{{ p.poNumber }}</td><td>{{ (p.lineIds ?? []).join(', ') }}</td>
              </tr>
            </tbody>
          </v-table>
        </section>

        <RequestFiles :files="r.files ?? []" />
        <section>
          <h2 class="t-h3">Timeline</h2>
          <RequestTimeline :request="r" history />
        </section>
      </div>

      <aside class="side">
        <v-card border flat class="actions">
          <v-card-title class="t-h3">Actions</v-card-title>
          <v-card-text class="stack-sm">
            <p v-if="!r.allowedActions?.length" class="t-body muted">Nothing to do for this request now.</p>
            <v-btn v-if="can('start-quoting')" color="primary" block :loading="busy" @click="run('/requests/{requestId}/start-quoting', undefined, 'Quoting started; stock checked')">Start quoting</v-btn>
            <v-btn v-if="can('quote-draft')" :to="`/requests/${r.id}/quote`" color="primary" block>{{ r.status === 'QUOTED' ? 'Revise quote' : 'Build quote' }}</v-btn>
            <template v-if="can('purchase-orders')">
              <v-btn v-if="signed" :href="fileUrl(signed)" target="_blank" variant="outlined" block :prepend-icon="mdiFileSign">View signed agreement</v-btn>
              <v-btn color="primary" block @click="openPo">Verify and purchase</v-btn>
            </template>
            <v-btn v-if="can('reject-agreement')" variant="outlined" block @click="reasonFor = 'reject-agreement'">Reject signature</v-btn>
            <v-btn v-if="can('approve')" color="primary" block :loading="busy" @click="run('/requests/{requestId}/approve', undefined, 'Approved; stock is being reserved')">Approve</v-btn>
            <v-btn v-if="can('reject')" variant="outlined" block @click="reasonFor = 'reject'">Reject</v-btn>
            <v-btn v-if="can('pick')" :to="{ path: '/pick', query: { op: 'order', request: r.id } }" color="primary" block>Pick</v-btn>
            <v-btn v-if="can('ship')" color="primary" block @click="shipOpen = true">Record shipment</v-btn>
            <v-btn v-if="can('deliver')" color="primary" block @click="deliverOpen = true">Mark delivered</v-btn>
            <v-btn v-if="can('cancel')" variant="text" color="error" block @click="reasonFor = 'cancel'">Cancel request</v-btn>
          </v-card-text>
        </v-card>
      </aside>
    </div>

    <ReasonDialog
      :model-value="reasonFor !== null"
      v-bind="reasonFor ? REASON_TEXT[reasonFor] : { title: '', confirm: '' }"
      danger
      :busy="busy"
      @update:model-value="(v: boolean) => !v && (reasonFor = null)"
      @submit="submitReason"
    />

    <v-dialog v-model="poOpen" max-width="640">
      <v-card title="Verify the agreement and record purchase orders">
        <v-card-text class="stack-sm">
          <v-btn v-if="signed" :href="fileUrl(signed)" target="_blank" variant="outlined" :prepend-icon="mdiFileSign">Open the signed agreement</v-btn>
          <div v-for="(row, i) in po.rows" :key="i" class="po-row">
            <v-text-field v-model="row.supplier" label="Supplier" hide-details />
            <v-text-field v-model="row.poNumber" label="PO number" hide-details />
            <p class="t-caption muted">Lines {{ row.lineIds.join(', ') }}</p>
          </div>
          <p v-if="!po.rows.length" class="t-body muted">Every item comes from CIMH stock: no purchase order is needed.</p>
          <v-checkbox v-model="po.verified" label="The signed agreement is complete and signed by an authorised person" hide-details />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="poOpen = false">Back</v-btn>
          <v-btn color="primary" variant="flat" :disabled="!poValid" :loading="busy" @click="submitPo">Start purchasing</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="shipOpen" max-width="560">
      <v-card title="Record shipment">
        <v-card-text class="stack-sm">
          <v-radio-group v-model="ship.carrier" inline label="Carrier" hide-details>
            <v-radio v-for="c in CARRIERS" :key="c.value" :label="c.title" :value="c.value" />
          </v-radio-group>
          <v-text-field v-if="ship.carrier !== 'HAND'" v-model="ship.tracking" label="Tracking number" />
          <v-text-field v-model="ship.note" :label="ship.carrier === 'HAND' ? 'Delivered by / collected by' : 'Note (optional)'" />
          <div class="two">
            <v-text-field v-model="ship.date" type="date" label="Date" />
            <v-text-field v-model="ship.cost" label="Shipping cost (optional)" placeholder="0.00" :rules="[(v: string) => !v || /^\d{1,12}\.\d{2}$/.test(v) || 'Use 2 decimals, e.g. 45.00']" />
          </div>
          <v-checkbox v-model="ship.notifyCustomer" label="Email the customer" hide-details />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="shipOpen = false">Back</v-btn>
          <v-btn color="primary" variant="flat" :disabled="!shipValid" :loading="busy" @click="submitShip">Record shipment</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="deliverOpen" max-width="480">
      <v-card title="Mark delivered">
        <v-card-text>
          <v-text-field v-model="invoiceNumber" label="Invoice number (optional)" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deliverOpen = false">Back</v-btn>
          <v-btn color="primary" variant="flat" :loading="busy" @click="submitDeliver">Mark delivered</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: var(--sp-6);
  align-items: start;
}
.side {
  position: sticky;
  top: 88px;
}
@media (max-width: 1100px) {
  .layout {
    grid-template-columns: minmax(0, 1fr);
  }
  /* One column: a sticky Actions card would sit under the scrolling request and stop taps reaching it. */
  .side {
    position: static;
  }
}
@media (max-width: 599.98px) {
  .sections {
    grid-template-columns: minmax(0, 1fr);
  }
}
.paper {
  padding: var(--sp-4);
}
.paper-head {
  display: flex;
  justify-content: space-between;
  gap: var(--sp-6);
  flex-wrap: wrap;
}
.meta p {
  margin-bottom: var(--sp-1);
}
.sections {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--sp-3);
  margin: var(--sp-4) 0;
}
.sec {
  border-left: 4px solid rgb(var(--v-theme-warning));
  padding: var(--sp-2) var(--sp-3);
  background: rgba(var(--v-theme-on-surface), 0.03);
  border-radius: 4px;
}
.sec.done {
  border-left-color: rgb(var(--v-theme-success));
}
.num {
  text-align: right;
}
.notes {
  margin-top: var(--sp-3);
}
.po-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-2);
}
.po-row p {
  grid-column: 1 / -1;
}
.two {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-3);
}
</style>
