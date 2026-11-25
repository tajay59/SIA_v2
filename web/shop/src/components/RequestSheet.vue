<template>
  <div class="sheet" :class="{ switching, settled, 'own-page': level === 1 }" :style="{ '--dir': dir }" :inert="switching || undefined" :aria-busy="switching || undefined">
    <div v-if="missing" class="missing">
      <p class="t-body">This request doesn't exist or isn't shared with you.</p>
    </div>
    <v-skeleton-loader v-else-if="!request" type="heading, paragraph, table" />
    <div v-else :key="request.id" class="content">
      <header class="head">
        <p class="ref">
          {{ request.type === 'PROBONO' ? 'Pro Bono request' : 'Request' }}
          <ShortRef :id="request.id" fit copy />
          · sent {{ formatDate(request.submittedAt) }}
        </p>
        <div class="title-row">
          <component :is="`h${level}`" ref="heading" tabindex="-1" class="title">{{ title }}</component>
          <span class="title-side">
            <StatusChip :status="request.status" />
            <!-- Beside the list: the whole request on its own page (shareable, room for the papers). -->
            <v-btn v-if="level === 2" :to="`/requests/${request.id}`" variant="outlined" size="small" :append-icon="mdiArrowRight">Open full page</v-btn>
          </span>
        </div>
      </header>

      <!-- The request path: a Vuetify v-timeline across the sheet, one node per stage, the line filled to where it
           stands. Its items render divs, so the list semantics come from roles. -->
      <v-timeline
        v-if="!closed"
        role="list"
        aria-label="Request progress"
        class="path"
        :class="{ 'your-turn': well?.tone === 'turn' || well?.tone === 'warn' || well?.tone === 'due' }"
        :style="{ '--at': Math.max(0, stageAt) }"
        direction="horizontal"
        align="center"
        side="end"
        density="compact"
        line-thickness="3"
        truncate-line="both"
      >
        <v-timeline-item
          v-for="(s, i) in stages"
          :key="s.label"
          role="listitem"
          class="stage"
          :style="{ '--i': i }"
          :class="{ done: i < stageAt || (finished && i === stageAt), current: i === stageAt && !finished }"
          :aria-current="i === stageAt ? 'step' : undefined"
          :dot-color="i < stageAt || finished ? 'primary' : undefined"
          :icon="i < stageAt || finished ? mdiCheck : undefined"
          fill-dot
        >
          <span class="stage-label">{{ s.label }}</span>
        </v-timeline-item>
      </v-timeline>

      <section v-if="well" class="well" :class="well.tone" aria-label="Where it stands">
        <div class="well-text">
          <p class="well-title">{{ well.title }}</p>
          <p class="well-body">{{ well.text }}</p>
          <p v-if="expiry && request.quoteExpiresAt" class="well-expiry" :class="{ soon: expiry.soon }">
            <v-icon v-if="expiry.soon" :icon="mdiClockAlertOutline" size="16" />
            Quote valid until {{ formatDate(request.quoteExpiresAt) }} ({{ expiry.text }})
          </p>
          <!-- The person who comes back (often another day, often someone else) with the signed copy goes straight to sending it; View and sign opens on checking the quote. -->
          <p v-if="handoff && !resend" class="well-return">
            Already signed?
            <router-link :to="`/requests/${request.id}/agreement?task=send`" class="well-link">
              Send the signed copy<v-icon :icon="mdiArrowRight" size="16" />
            </router-link>
          </p>
        </div>
        
        <div v-if="can('accept') && currentAgreement(request)" class="well-acts">
          <v-btn
            :to="`/requests/${request.id}/agreement${resend ? '?task=send' : ''}`"
            color="primary"
            variant="flat"
            size="large"
            class="well-act"
            :class="{ 'well-cta': !ctaSeen }"
            @click="ctaPressed"
          >
            {{ resend ? 'Send it again' : 'View and sign' }}
          </v-btn>
          <v-btn v-if="can('decline')" variant="text" class="well-act" @click="dialog = 'decline'">Cancel request</v-btn>
        </div>
        <div v-else-if="payable && request.paymentStatus !== 'PAID'" class="well-acts">
          <v-btn
            :color="request.paymentStatus === 'DUE' ? 'error' : undefined"
            :variant="request.paymentStatus === 'DUE' ? 'flat' : 'outlined'"
            :size="request.paymentStatus === 'DUE' ? 'large' : undefined"
            class="well-act"
            @click="payOpen = true"
          >
            {{ request.paymentStatus === 'DUE' ? 'Send proof of payment' : 'Send another proof' }}
          </v-btn>
        </div>
      </section>
      <PaymentProofDialog v-if="payable" v-model="payOpen" :request="request" @sent="onProofSent" />
      
      <p v-if="!mine" class="t-body muted readonly">Requested by {{ request.customerName }} (same organisation). You can view it; only they can act on it.</p>

      <!-- The papers after signing: page 1 of each as a small sheet; a tile opens it full size. -->
      <section v-if="papers.length" class="section" aria-labelledby="sec-papers">
        <div class="papers-head">
          <component :is="secTag" id="sec-papers" class="sec-title papers-title">Papers</component>
          <span class="papers-hint" aria-hidden="true">Opens full size</span>
        </div>
        <ul class="tiles">
          <li v-for="p in papers" :key="p.key">
            <DocumentReader v-if="p.id" :file-id="p.id" :mime="p.mime" :name="p.label">
              <template #default="{ props: a }">
                <button type="button" class="tile" v-bind="a" :aria-label="`Read ${p.label} full size (${p.kind})`">
                  <DocumentThumb :file-id="p.id" :mime="p.mime" />
                  <span class="tile-name">{{ p.label }}</span>
                  <span class="tile-kind">{{ p.kind }}</span>
                </button>
              </template>
            </DocumentReader>
            <div v-else class="tile wait">
              <span class="tile-empty">Not yet</span>
              <span class="tile-name">{{ p.label }}</span>
              <span class="tile-kind">{{ p.kind }}</span>
            </div>
          </li>
        </ul>
      </section>

      <template v-for="part in order" :key="part">
        <!-- The total is said once: in the quote's own total row (its name follows the state). -->
        <details v-if="part === 'quote' && showQuote && quoteRecord" class="section quote-record">
          <summary class="sec-title record-sum">
            <span>Quote</span>
            <span class="record-total">{{ quoteRecord }}</span>
            <v-icon :icon="mdiChevronDown" size="20" class="history-chev" aria-hidden="true" />
          </summary>
          <QuoteTable :request="request" />
        </details>
        <section v-else-if="part === 'quote' && showQuote" class="section" aria-labelledby="sec-quote">
          <component :is="secTag" id="sec-quote" class="sec-title">Quote</component>
          <QuoteTable :request="request" />
        </section>

        <section v-else-if="part === 'items'" class="section" aria-labelledby="sec-items">
          <component :is="secTag" id="sec-items" class="sec-title">{{ paidLines.length && probonoLines.length ? 'Items' : 'Items requested' }}</component>
          <template v-for="group in [{ key: 'paid', lines: paidLines }, { key: 'probono', lines: probonoLines }]" :key="group.key">
            <template v-if="group.lines.length">
              <p v-if="paidLines.length && probonoLines.length" class="group-label">
                <template v-if="group.key === 'probono'"><span class="probono-badge">Free</span> Pro Bono</template>
                <template v-else>To be quoted</template>
              </p>
              <ul class="items">
                <li v-for="l in group.lines" :key="l.lineId">
                  <span class="thumb">
                    <img v-if="l.product.image" :src="l.product.image" alt="" loading="lazy" />
                    <v-icon v-else :icon="mdiPackageVariantClosed" size="22" class="no-photo" />
                  </span>
                  <span class="item-main">
                    <router-link :to="`/catalogue/${l.productId}`" class="item-name">{{ l.product.name }}</router-link>
                    <span class="muted">{{ [l.product.make, l.product.modelname].filter(Boolean).join(' · ') }}</span>
                  </span>
                  <span class="item-end">
                    <span class="tnum">× {{ l.qty }}</span>
                    <span v-if="l.product.probono && !(paidLines.length && probonoLines.length)" class="probono-badge">Free</span>
                    <span v-if="sourceOf(l)" class="muted small">{{ sourceOf(l) }}</span>
                  </span>
                </li>
              </ul>
            </template>
          </template>
        </section>
      </template>

      <section class="section" aria-labelledby="sec-delivery">
        <component :is="secTag" id="sec-delivery" class="sec-title">Delivery</component>
        <dl class="facts">
          <div v-if="request.shipTo">
            <dt>Deliver to</dt>
            <dd>
              {{ request.shipTo.firstname }} {{ request.shipTo.lastname }}<br />
              <template v-if="request.shipTo.organisation">{{ request.shipTo.organisation }}<br /></template>
              {{ request.shipTo.line1 }}<template v-if="request.shipTo.line2">, {{ request.shipTo.line2 }}</template><br />
              {{ [request.shipTo.city, request.shipTo.parish, request.shipTo.zip].filter(Boolean).join(' ') }}<br />
              {{ countryName(request.shipTo.country) }}
            </dd>
          </div>
          <!-- Every quote is BBD now; only a legacy USD request says so. -->
          <div v-if="request.currency && request.currency !== 'BBD'">
            <dt>Quote currency</dt>
            <dd>{{ request.currency }}</dd>
          </div>
        </dl>
        <!-- One row per parcel (CIMH stock, each supplier shipping direct), then what has not left yet. -->
        <ul v-if="request.shipments?.length || (shipStarted && toShip.length)" class="parcels" aria-label="Shipments">
          <li v-for="s in request.shipments" :key="s.id" class="parcel">
            <v-icon :icon="mdiPackageVariantClosed" size="20" class="parcel-icon" aria-hidden="true" />
            <div class="parcel-body">
              <p class="parcel-head"><strong>{{ shipmentSender(s) }}</strong></p>
              <p class="parcel-meta">
                {{ carrierLabel(s) }}<template v-if="s.date"> · {{ formatDate(s.date) }}</template><template v-if="s.note"> · {{ s.note }}</template>
                <template v-if="s.tracking">
                  ·
                  <a v-if="s.trackingUrl" :href="s.trackingUrl" target="_blank" rel="noopener" class="track" :aria-label="`Track ${s.tracking} with ${carrierLabel(s)} (opens a new tab)`">Track {{ s.tracking }}<v-icon :icon="mdiOpenInNew" size="14" aria-hidden="true" /></a>
                  <span v-else>Tracking {{ s.tracking }}</span>
                </template>
              </p>
              <p class="parcel-items">{{ s.lineIds.map(lineLabel).join(', ') }}</p>
            </div>
          </li>
          <li v-if="shipStarted && toShip.length" class="parcel waiting">
            <v-icon :icon="mdiClockAlertOutline" size="20" class="parcel-icon" aria-hidden="true" />
            <div class="parcel-body">
              <p class="parcel-head"><strong>Not shipped yet</strong></p>
              <p class="parcel-items">{{ toShip.join(', ') }}</p>
            </div>
          </li>
        </ul>
      </section>

      <!-- Dated changes, folded: the path above already shows where it stands. -->
      <details v-if="changes.length" class="section history">
        <summary class="sec-title history-sum">
          <span>History</span>
          <span class="history-n">{{ changes.length }} {{ changes.length === 1 ? 'change' : 'changes' }}</span>
          <v-icon :icon="mdiChevronDown" size="20" class="history-chev" aria-hidden="true" />
        </summary>
        <!-- Newest first, as a Vuetify v-timeline: the latest change on a filled node, earlier ones hollow. -->
        <v-timeline role="list" aria-label="History" class="changes" side="end" density="compact" align="start" truncate-line="both" line-thickness="2">
          <v-timeline-item
            v-for="(h, i) in changes"
            :key="i"
            role="listitem"
            class="change"
            :class="{ latest: i === 0 }"
            :dot-color="i === 0 ? 'primary' : undefined"
            fill-dot
          >
            <span class="ch-what">{{ changeText(h) }}<template v-if="h.reason"><span class="ch-why">: {{ h.reason }}</span></template></span>
            <span class="ch-when tnum">{{ formatDateTime(h.at) }}</span>
          </v-timeline-item>
        </v-timeline>
      </details>

      <!-- While a quote waits, Cancel request sits beside View and sign in the well; otherwise it is here. -->
      <div v-if="can('cancel') || (can('decline') && !currentAgreement(request))" class="actions">
        <v-btn variant="outlined" color="error" @click="dialog = can('decline') ? 'decline' : 'cancel'">Cancel request</v-btn>
      </div>

      <ReasonDialog
        :model-value="dialog !== null"
        title="Cancel this request?"
        :text="dialog === 'decline' ? 'The quote lapses and nothing will be ordered. You can send a new request later.' : 'Nothing will be ordered for this request.'"
        confirm="Cancel request"
        danger
        :busy="busy"
        @update:model-value="(v: boolean) => !v && (dialog = null)"
        @submit="(reason: string) => run(dialog!, reason)"
      />
    </div>
  </div>
</template>

<script lang="ts">
/** The request the last sheet showed (any level), so the list ↔ own page change can tell it is the same one. */
let lastShown = ''
</script>

<script setup lang="ts">
/**
 * One request as the customer sees it (S-11), shared by the docket on /requests (beside the list) and the
 * request's own page. Reading order: reference + title, the request path (one rule, a node per stage, filled
 * to where it stands), the "whose move" well (the customer's turn in the primary tone with its action; CIMH's
 * turn neutral; amber only when a quote expires within a week), then Quote (first while it waits for the
 * customer), Status, Items, Delivery and the actions the server allows. "View and sign" (2026-11-17):
 * while QUOTED the customer's move is View and sign, or Cancel request (the server's `decline`).
 * Same-organisation users see it read-only (the server sends no actions for them).
 * No Files section and no document preview (owner, 2026-11-18): the quote files and the agreement are read on
 * View and sign (S-12).
 * One of each (critique fix, 2026-11-18): one progress model (the path; dated changes fold into History at the end,
 * in the same words), the total once, and while the requester's quote waits the page is a hand-off: the well says
 * what the agreement is and leads to View and sign, which holds the priced quote (S-11 shows no prices then).
 */
import {
  act,
  ApiError,
  carrierLabel,
  countryName,
  currentAgreement,
  DocumentThumb,
  expiryNote,
  FILE_KIND_LABELS,
  getRequest,
  isClosed,
  openSources,
  type OrderRequest,
  pricedQuote,
  QuoteTable,
  ReasonDialog,
  requestTitle,
  shipmentSender,
  shopDir,
  ShortRef,
  StatusChip,
  useNotify,
  useSession,
} from '@cimh/web-app'
import { formatDate, formatDateTime, formatMoney, statusLabel } from '@cimh/web-ui'
import { mdiArrowRight, mdiCheck, mdiChevronDown, mdiClockAlertOutline, mdiOpenInNew, mdiPackageVariantClosed } from '@mdi/js'
import { computed, nextTick, ref, watch } from 'vue'
import DocumentReader from './DocumentReader.vue'
import PaymentProofDialog from './PaymentProofDialog.vue'

const props = withDefaults(defineProps<{ id: string; level?: 1 | 2; setTitle?: boolean; dir?: 1 | -1 }>(), { level: 1, setTitle: false, dir: 1 })
const emit = defineEmits<{ changed: [OrderRequest] }>()

// ---- Delivery: one row per shipment, and the items that have not left yet
const lineLabel = (lineId: string) => {
  const ln = request.value?.lines.find((l) => l.lineId === lineId)
  return ln ? `${ln.product.name} × ${ln.qty}` : lineId
}
const shipStarted = computed(() => ['PURCHASING', 'PICKING', 'SHIPPED'].includes(request.value?.status ?? '') && !!request.value?.shipments?.length)
const toShip = computed(() =>
  request.value ? openSources(request.value).flatMap((s) => s.lines.map((l) => lineLabel(l.lineId))) : [],
)
const session = useSession()
const notify = useNotify()
const request = ref<OrderRequest | null>(null)
const missing = ref(false)
const heading = ref<HTMLElement | null>(null)

const title = computed(() => {
  const r = request.value
  return r ? requestTitle(r.lines[0]?.product.name, r.lines.length, r.type) : ''
})

async function load(focus = false) {
  missing.value = false
  try {
    const r = await getRequest(props.id)
    if (r.id !== props.id) return
    request.value = r
    if (props.setTitle) document.title = `${title.value} · CIMH Stores`
    if (focus) {
      await nextTick()
      heading.value?.focus({ preventScroll: true })
    }
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) missing.value = true
    else notify.report(e, { retry: () => void load() })
  }
}
watch(
  () => props.id,
  (id, old) => {
    // Keep the previous request on screen (dimmed) while the next loads: no skeleton flash between rows.
    if (!request.value || request.value.id !== id) void load(!!old)
  },
  { immediate: true },
)
const switching = computed(() => !!request.value && request.value.id !== props.id)
// Orders list ↔ this request's own page (shopDir 'quiet') showing the request that was just on screen: the page
// cross-fades, so the path fill and the well don't replay. Another request opened afterwards plays as usual.
const settledId = ref(shopDir.value === 'quiet' && props.id === lastShown ? props.id : '')
watch(
  () => props.id,
  (id) => {
    lastShown = id
    if (id !== settledId.value) settledId.value = ''
  },
  { immediate: true },
)
const settled = computed(() => !!settledId.value && request.value?.id === settledId.value)

const can = (a: string) => request.value?.allowedActions?.includes(a as never) ?? false
const mine = computed(() => request.value?.customer === session.account?.id)
const showQuote = computed(() => !!(request.value?.quotes?.length || request.value?.cimhQuote) && request.value?.type === 'PAID')
const quoteLive = computed(() => request.value?.status === 'QUOTED')
const expiry = computed(() => (quoteLive.value ? expiryNote(request.value?.quoteExpiresAt) : null))
/** The requester's quote waits and View and sign is open to them: the priced quote is read there, not here. */
const handoff = computed(() => quoteLive.value && can('accept') && !!request.value && !!currentAgreement(request.value))
/** Staff turned the signed copy down (ACCEPTED → QUOTED): the move is to send a new copy, not to start again. */
const resend = computed(() => {
  const last = request.value?.history?.at(-1)
  return handoff.value && last?.from === 'ACCEPTED' && last.to === 'QUOTED'
})
/** Section headings sit one level under the title (h2 on the page, h3 beside the list). */
const secTag = computed(() => `h${props.level + 1}`)

/**
 * View and sign calls for attention (owner, 2026-11-18): a soft halo and a pulse until the customer first presses it
 * for this quote version (a revised quote calls again). Remembered in this browser; a private window forgets.
 */
const ctaKey = computed(() => (request.value ? `cimh.cta.${request.value.id}.v${pricedQuote(request.value).version}` : ''))
const ctaSeen = ref(true)
watch(
  ctaKey,
  (k) => {
    try {
      ctaSeen.value = !k || localStorage.getItem(k) === '1'
    } catch {
      ctaSeen.value = false
    }
  },
  { immediate: true },
)
function ctaPressed() {
  ctaSeen.value = true
  try {
    localStorage.setItem(ctaKey.value, '1')
  } catch {
    /* private window: it calls again next visit */
  }
}

/** The request path the customer reads: fewer, plainer stages than the status list (stages group statuses). */
const STAGES = {
  PAID: [
    { label: 'Sent', statuses: ['SUBMITTED'] },
    { label: 'Quote', statuses: ['QUOTING', 'QUOTED'] },
    { label: 'Signed', statuses: ['ACCEPTED'] },
    { label: 'Ordered', statuses: ['PURCHASING'] },
    { label: 'Shipped', statuses: ['SHIPPED'] },
    { label: 'Delivered', statuses: ['DELIVERED'] },
  ],
  PROBONO: [
    { label: 'Sent', statuses: ['SUBMITTED'] },
    { label: 'Approved', statuses: ['APPROVED'] },
    { label: 'Picking', statuses: ['PICKING'] },
    { label: 'Shipped', statuses: ['SHIPPED'] },
    { label: 'Delivered', statuses: ['DELIVERED'] },
  ],
} as const
const stages = computed(() => (request.value ? STAGES[request.value.type === 'PROBONO' ? 'PROBONO' : 'PAID'] : []))
const stageAt = computed(() => {
  const s = request.value?.status
  return stages.value.findIndex((st) => (st.statuses as readonly string[]).includes(s ?? ''))
})
const closed = computed(() => !!request.value && isClosed(request.value.status))
const finished = computed(() => request.value?.status === 'DELIVERED')

/** Where the request stands and who acts next. */
type Tone = 'turn' | 'warn' | 'due' | 'cimh' | 'done' | 'stop'

const well = computed<{ tone: Tone; title: string; text: string } | null>(() => {
  const r = request.value
  if (!r) return null
  const who = mine.value ? 'you' : r.customerName
  const turn: Tone = expiry.value?.soon ? 'warn' : 'turn'

  switch (r.status) {
    case 'SUBMITTED':
      return r.type === 'PROBONO'
        ? { tone: 'cimh', title: 'With CIMH for review', text: `Staff review Pro Bono requests and email ${who} the decision.` }
        : { tone: 'cimh', title: 'With CIMH for a quote', text: `CIMH is preparing the quote and emails ${who} when it is ready. Nothing is needed until then.` }
    case 'QUOTING':
      return { tone: 'cimh', title: 'CIMH is preparing the quote', text: `CIMH emails ${who} when it is ready. Nothing is needed until then.` }
    case 'QUOTED': {
      const total = formatMoney(pricedQuote(r).total, r.currency ?? 'BBD')
      if (!currentAgreement(r))  // a quote sent before 2026-11-17: staff re-send it with its agreement
        return { tone: 'cimh', title: 'CIMH is updating the quote', text: `CIMH emails ${who} when the quote and its agreement are ready to sign.` }
      const last = r.history?.at(-1)
      if (mine.value && last?.from === 'ACCEPTED' && last.to === 'QUOTED')  // staff rejected the signed copy
        return { tone: turn, title: 'Upload the signed agreement again', text: `CIMH could not accept the signed copy (${last.reason ?? 'no reason given'}). Your quote still stands: sign the agreement again and upload it.` }
      return mine.value
        ? {
            tone: turn,
            title: `Your quote is ready: ${total}`,
            text: 'The agreement lists every item, where it comes from and its price. The head of your organisation signs the document on its behalf, and then upload the signed copy here. If you no longer need the items, cancel the request.',
          }
        : { tone: 'cimh', title: `The quote is ready: ${total}`, text: `${r.customerName} signs the agreement or cancels the request.` }
    }
    case 'ACCEPTED': {
      const next = [
        sources.value.supplier && 'order the supplier items (shipped straight to you)',
        sources.value.cimh && 'prepare the items from CIMH stock',
      ].filter(Boolean)
      return {
        tone: 'done',
        title: 'Signed agreement received',
        text: `CIMH staff check the signature${next.length ? `, then ${next.join(' and ')}` : ''}. CIMH emails every step.`,
      }
    }
    case 'PURCHASING': {
      const doing = [sources.value.supplier && 'ordering the supplier items', sources.value.cimh && 'picking the items from its stock'].filter(Boolean)
      return {
        tone: 'cimh',
        title: 'Signature verified',
        text: `CIMH is ${doing.join(' and ') || 'preparing the items'}.${sources.value.supplier ? ' Supplier items are shipped straight to the delivery address.' : ''}`,
      }
    }
    case 'APPROVED':
    case 'PICKING':
      return { tone: 'cimh', title: 'Approved', text: 'CIMH is picking the items. An email follows when they are shipped.' }
    case 'SHIPPED':
      return { tone: 'cimh', title: 'On its way', text: 'Each parcel and its tracking link is under Delivery.' }
    case 'DELIVERED':
      if (r.paymentStatus === 'DUE')
        return mine.value
          ? {
              tone: 'due',
              title: `Payment required${r.amountDue ? `: ${formatMoney(r.amountDue, r.currency ?? 'BBD')}` : ''}`,
              text: 'Everything has been delivered. Pay the invoice under Papers, then send CIMH the proof of payment (a bank receipt or transfer confirmation).',
            }
          : { tone: 'due', title: 'Payment required', text: `Delivered. ${r.customerName} pays the invoice and sends CIMH the proof of payment.` }
      if (r.paymentStatus === 'PAID')
        return { tone: 'done', title: 'Paid', text: `CIMH recorded the payment${r.paidAt ? ` on ${formatDate(r.paidAt)}` : ''}. Thank you. The invoice stays under Papers.` }
      if (r.paymentStatus === 'PROOF_SENT')
        return { tone: 'done', title: 'Proof of payment sent', text: 'Everything has been delivered. CIMH checks the payment against the invoice.' }
      return {
        tone: 'done',
        title: 'Delivered',
        text: r.type === 'PROBONO'
          ? 'Everything on this request has been delivered. The delivery note is under Papers.'
          : 'Everything on this request has been delivered. The invoice for the agreed total is under Papers.',
      }
    case 'REJECTED':
      return { tone: 'stop', title: 'Not approved', text: closingReason.value ? `CIMH did not approve it: ${closingReason.value}.` : 'This request was not approved.' }
    default:
      return isClosed(r.status)
        ? { tone: 'stop', title: 'Cancelled', text: `Nothing will be ordered for this request.${closingReason.value ? ` Reason: ${closingReason.value}.` : ''}` }
        : null
  }
});

const closingReason = computed(() => {
  const r = request.value
  return (r?.cancellation as { reason?: string } | null)?.reason ?? (r?.rejection as { reason?: string } | null)?.reason ?? null
});

/** Where the items come from, for the words after signing (no supplier sentence on an all-stock request). */
const sources = computed(() => ({
  cimh: !!request.value?.lines.some((l) => l.source === 'CIMH'),
  supplier: !!request.value?.lines.some((l) => l.source === 'SUPPLIER'),
}))

/** What happened when, in the path's words (one progress model; the path shows where it stands). */
function changeText(h: NonNullable<OrderRequest['history']>[number]): string {
  switch (h.to) {
    case 'SUBMITTED':
      return 'Sent to CIMH'
    case 'QUOTING':
      return 'CIMH started the quote'
    case 'QUOTED':
      return h.from === 'ACCEPTED' ? 'Signed copy not accepted' : h.from === 'QUOTED' ? 'Quote revised' : 'Quote sent'
    case 'ACCEPTED':
      return 'Signed agreement received'
    case 'PURCHASING':
      return 'Signature verified, items ordered'
    case 'APPROVED':
      return 'Approved'
    case 'PICKING':
      return 'Picking started'
    case 'SHIPPED':
      return 'Shipped'
    case 'DELIVERED':
      return 'Delivered'
    case 'REJECTED':
      return 'Not approved'
    case 'CANCELLED':
    case 'DECLINED':
      return 'Cancelled'
    default:
      return statusLabel(h.to)
  }
}

const changes = computed(() => [...(request.value?.history ?? [])].reverse())

/**
 * The papers after signing (critique fix 4, owner chose "page tiles"): what was signed and what CIMH sent, page 1 as a
 * small sheet each, opening the full-size reader. Signed copy, invoices, the agreement as sent, then the quotes behind
 * the prices (the agreed version's). An invoice still to come is a dashed sheet until delivery. Before signing the
 * papers live on View and sign; a Pro Bono request shows its papers once CIMH has made any.
 */
type Paper = { key: string; id?: string; mime: string; label: string; kind: string }
const SIGNED = ['ACCEPTED', 'PURCHASING', 'SHIPPED', 'DELIVERED']
const INVOICES = ['invoice', 'commercial_invoice', 'probono_invoice']
/** Captions stay one short line under a sheet: the file type only when it is not a PDF (a phone photo, say). */
const typeNote = (mime: string) => (mime === 'application/pdf' ? '' : mime === 'image/png' ? ' · PNG' : mime === 'image/jpeg' ? ' · JPG' : '')
const papers = computed<Paper[]>(() => {
  const r = request.value
  if (!r) return []
  const files = r.files ?? []
  const byId = (id: string | null | undefined) => (id ? files.find((f) => f.id === id) : undefined)
  const out: Paper[] = []
  const ag = r.agreement
  const signedState = r.type === 'PAID' && SIGNED.includes(r.status) && !!ag
  const signed = signedState ? byId(ag?.signedFileId) : undefined
  if (signed) out.push({ key: signed.id, id: signed.id, mime: signed.mime, label: 'Signed agreement', kind: `Yours${signed.uploadedAt ? `, sent ${formatDate(signed.uploadedAt)}` : ''}${typeNote(signed.mime)}` })
  const invoices = files.filter((f) => INVOICES.includes(f.kind))
  // One current invoice and commercial invoice: named by number; a corrected one says so (earlier copies never show).
  const current = (f: (typeof files)[number]) => {
    const rec = f.kind === 'invoice' || f.kind === 'commercial_invoice' ? r.invoices?.[f.kind] : undefined
    return rec?.fileId === f.id ? rec : undefined
  }
  for (const f of invoices) {
    const rec = current(f)
    const label = rec?.number ? `${FILE_KIND_LABELS[f.kind]} ${rec.number}` : FILE_KIND_LABELS[f.kind]
    const kind = rec && rec.rev > 1 ? `From CIMH, corrected (revision ${rec.rev})` : 'From CIMH'
    out.push({ key: f.id, id: f.id, mime: f.mime, label, kind: `${kind}${typeNote(f.mime)}` })
  }
  for (const f of files.filter((f) => f.kind === 'payment_proof'))
    out.push({ key: f.id, id: f.id, mime: f.mime, label: 'Proof of payment', kind: `Yours${f.uploadedAt ? `, sent ${formatDate(f.uploadedAt)}` : ''}${typeNote(f.mime)}` })
  if (signedState && !invoices.some((f) => f.kind === 'invoice') && r.status !== 'DELIVERED')
    out.push({ key: 'invoice-to-come', mime: '', label: 'Invoice', kind: 'Comes when the items are delivered' })
  if (!signedState) return out
  const v = ag!.quoteVersion
  const agreementFile = byId(ag!.fileId)
  if (agreementFile) out.push({ key: agreementFile.id, id: agreementFile.id, mime: agreementFile.mime, label: 'Agreement', kind: `As sent, version ${v}` })
  for (const f of files.filter((f) => f.kind === 'cimh_quote' && f.quoteVersion === v))
    out.push({ key: f.id, id: f.id, mime: f.mime, label: 'CIMH quote', kind: 'CIMH stock' })
  for (const q of r.quotes ?? []) {
    if (q.version !== v) continue
    for (const id of q.fileIds ?? []) {
      const f = byId(id)
      if (f) out.push({ key: f.id, id: f.id, mime: f.mime, label: q.supplier ?? 'Supplier quote', kind: `Supplier quote${typeNote(f.mime)}` })
    }
  }
  return out
})

const paidLines = computed(() => request.value?.lines.filter((l) => !l.product.probono) ?? [])
const probonoLines = computed(() => request.value?.lines.filter((l) => l.product.probono) ?? [])
/** Where each line comes from, for the Items list once the quote has been sent. */
const sourceOf = (l: OrderRequest['lines'][number]) =>
  l.source === 'CIMH' ? 'From CIMH stock' : l.source === 'SUPPLIER' ? `From ${l.supplier ?? 'a supplier'}, shipped directly` : ''
// The hand-off shows no prices (View and sign has them). A live quote someone else signs (or one waiting for its
// agreement) still leads; later the quote is a record after the items.
const order = computed(() => (handoff.value ? ['items'] : quoteLive.value ? ['quote', 'items'] : ['items', 'quote']))
/** Once signed (or closed) the quote is a record: folded under the items, its total named in the summary. */
const quoteRecord = computed(() => {
  const r = request.value
  if (!r || quoteLive.value || !showQuote.value) return null
  const total = pricedQuote(r).total
  const word = SIGNED.includes(r.status) ? 'Agreed total' : 'Quoted total'
  return total ? `${word} ${formatMoney(total, r.currency ?? 'BBD')}` : word
})

/** Delivered paid request: the requester pays and sends a proof of payment (owner, 2026-11-23). */
const payable = computed(() => mine.value && !!request.value?.paymentStatus)
const payOpen = ref(false)
function onProofSent(r: OrderRequest) {
  request.value = r
  emit('changed', r)
}

const dialog = ref<null | 'decline' | 'cancel'>(null)
const busy = ref(false)
async function run(kind: 'decline' | 'cancel', reason: string) {
  if (!request.value) return
  busy.value = true
  try {
    request.value = await act(request.value, `/requests/{requestId}/${kind}`, { reason })
    notify.toast('Request cancelled', 'success')
    dialog.value = null
    emit('changed', request.value)
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) await load()
    notify.report(e)
  } finally {
    busy.value = false
  }
}
</script>



<style scoped>
.sheet {
  container-type: inline-size;
  transition: opacity 160ms ease-out;
}
.sheet.switching {
  opacity: 0.45;
}
/* Motion (impeccable animate). Each request is keyed, so opening another replays the sequence:
   the sheet slides in from the side of the list it came from (--dir: 1 = from below, -1 = from above),
   the path fills to its stage while the dots light in order, then the whose-move well arrives. */
.content {
  --ease: cubic-bezier(0.16, 1, 0.3, 1);
  --fill-ms: 620ms;
  animation: sheet-in 280ms var(--ease);
}
@keyframes sheet-in {
  from {
    opacity: 0.85;
    transform: translateY(calc(var(--dir, 1) * 10px));
  }
}
/* On its own page the page transition (App.vue page-quiet) is the arrival: no second rise. The same request
   just seen beside the list (or on its page) arrives settled: no fill, no well entrance. */
.own-page .content,
.settled .content,
.settled .stage :deep(.v-timeline-divider__before),
.settled .stage :deep(.v-timeline-divider__after),
.settled .stage :deep(.v-timeline-divider__dot),
.settled .stage.current .stage-label,
.settled .well {
  animation: none !important;
}
.settled .path.your-turn .stage.current :deep(.v-timeline-divider__dot)::after {
  animation-delay: 400ms;
}
.settled .well-cta {
  animation-delay: 400ms;
}
/* The fill runs node to node along the timeline's line segments: the half after node i-1, then the half
   before node i, each a share of --fill-ms, so it reaches node i when that node lights. */
.path {
  --step: calc(var(--fill-ms) * 0.8 / max(var(--at), 1));
}
.stage.done :deep(.v-timeline-divider__after) {
  animation: path-fill calc(var(--step) / 2) linear backwards;
  animation-delay: calc(120ms + var(--step) * var(--i));
}
.stage.done :deep(.v-timeline-divider__before),
.stage.current :deep(.v-timeline-divider__before) {
  animation: path-fill calc(var(--step) / 2) linear backwards;
  animation-delay: calc(120ms + var(--step) * (var(--i) - 0.5));
}
@keyframes path-fill {
  from {
    background-size: 0% 100%;
  }
}
/* A dot lights when the fill reaches it: its delay is its share of the fill. */
.stage.done :deep(.v-timeline-divider__dot),
.stage.current :deep(.v-timeline-divider__dot) {
  animation: dot-light 260ms var(--ease) backwards;
  animation-delay: calc(120ms + var(--step) * var(--i));
}
@keyframes dot-light {
  from {
    opacity: 0.5;
    transform: scale(0.7);
  }
}
.stage.current .stage-label {
  animation: label-in 240ms var(--ease) calc(120ms + var(--fill-ms) * 0.8) backwards;
}
@keyframes label-in {
  from {
    opacity: 0.4;
  }
}
/* The customer's turn: the current stage breathes (ring swells and fades), like the cart's active step. */
.path.your-turn .stage.current :deep(.v-timeline-divider__dot)::after {
  content: '';
  position: absolute;
  inset: -7px;
  border-radius: 50%;
  border: 2px solid rgba(var(--v-theme-primary), 0.5);
  opacity: 0;
  pointer-events: none;
  animation: stage-pulse 2400ms var(--ease) calc(var(--fill-ms) + 400ms) infinite;
}
@keyframes stage-pulse {
  0% {
    transform: scale(0.8);
    opacity: 0.9;
  }
  70%,
  100% {
    transform: scale(1.6);
    opacity: 0;
  }
}
.well {
  animation: well-in 360ms var(--ease) calc(var(--fill-ms) * 0.6) backwards;
}
/* The customer's move (owner, 2026-11-18): until View and sign is first pressed (`ctaSeen`), it sits in a soft
   primary halo (the shade) and sends out a ring every 2 s once the well has landed. Paint-only: the button's own
   box-shadow, which its overflow doesn't clip. Hovering or focusing it pauses the ring (the halo stays); reduced
   motion keeps only the halo. */
.well-cta {
  --halo: 0 0 0 5px rgba(var(--v-theme-primary), 0.2);
  box-shadow: var(--halo);
  animation: cta-pulse 2000ms var(--ease) calc(var(--fill-ms) * 0.6 + 400ms) infinite;
}
.well-cta:hover,
.well-cta:focus-visible {
  animation-play-state: paused;
}
@keyframes cta-pulse {
  0% {
    box-shadow: var(--halo), 0 0 0 5px rgba(var(--v-theme-primary), 0.5);
  }
  70%,
  100% {
    box-shadow: var(--halo), 0 0 0 16px rgba(var(--v-theme-primary), 0);
  }
}
@keyframes well-in {
  from {
    opacity: 0;
    transform: translateY(8px);
    box-shadow: 0 0 0 0 transparent;
  }
}
.missing {
  padding: var(--sp-8) 0;
}

/* ---- head: reference over the title, the status chip beside it */
.ref {
  margin: 0;
  font-size: 13px;
  line-height: 18px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  overflow-wrap: anywhere;
}
.ref .t-mono {
  font-size: 12px;
}
.title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-4);
  margin-top: var(--sp-1);
}
.title {
  margin: 0;
  font-size: clamp(24px, 2.4vw + 10px, 32px);
  line-height: 1.2;
  font-weight: 700;
  letter-spacing: -0.015em;
  text-wrap: balance;
  overflow-wrap: anywhere;
  outline: none;
}
.title-row :deep(.v-chip) {
  flex: none;
  margin-top: 4px;
}
.title-side {
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--sp-2);
}

/* ---- the request path (Vuetify v-timeline): same grammar as the cart's, small and on the page ground.
   16 px nodes, a 3 px line in equal columns; labels close under the nodes. */
.path {
  margin: var(--sp-6) 0 var(--sp-5, 20px);
  grid-auto-columns: minmax(0, 1fr);
  column-gap: 0 !important;
}
.path :deep(.v-timeline-item__body) {
  padding: var(--sp-2) 0 0 !important;
  text-align: center;
}
.path :deep(.v-timeline-divider__dot) {
  width: 16px;
  height: 16px;
  position: relative;
  background: rgb(var(--v-theme-surface));
  box-shadow: inset 0 0 0 2px rgba(var(--v-border-color), 0.45);
}
.path :deep(.v-timeline-divider__inner-dot) {
  background: transparent;
}
.path :deep(.v-timeline-divider__inner-dot .v-icon) {
  font-size: 12px;
  width: 12px;
  height: 12px;
}
.stage.done :deep(.v-timeline-divider__dot) {
  box-shadow: none;
}
.stage.done :deep(.v-timeline-divider__inner-dot) {
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}
.stage.current :deep(.v-timeline-divider__dot) {
  box-shadow:
    inset 0 0 0 4px rgb(var(--v-theme-primary)),
    0 0 0 4px rgba(var(--v-theme-primary), 0.16);
}
/* Solid line colours: Vuetify's segments overlap between items, so a translucent line showed darker dashes. */
.path :deep(.v-timeline-divider__before),
.path :deep(.v-timeline-divider__after) {
  background-color: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 20%, rgb(var(--v-theme-background)));
  border-radius: 2px;
}
/* The line is primary into and out of every done stage and into the current one: drawn as segments. */
.stage.done :deep(.v-timeline-divider__before),
.stage.done :deep(.v-timeline-divider__after),
.stage.current :deep(.v-timeline-divider__before) {
  background-image: linear-gradient(rgb(var(--v-theme-primary)), rgb(var(--v-theme-primary)));
  background-repeat: no-repeat;
  background-size: 100% 100%;
}
.stage-label {
  font-size: 13px;
  line-height: 16px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.stage.current .stage-label {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 700;
}

/* ---- the whose-move well */
.well {
  --tone: var(--v-theme-on-surface);
  display: flex;
  align-items: center;
  gap: var(--sp-4) var(--sp-6);
  padding: var(--sp-5, 20px) var(--sp-6);
  border-radius: 12px;
  border: 1px solid rgba(var(--tone), 0.4);
  background: rgba(var(--tone), 0.06);
}
.well.turn {
  --tone: var(--v-theme-primary);
}
.well.warn {
  --tone: var(--v-theme-warning);
}
.well.done {
  --tone: var(--v-theme-success);
}
.well.stop,
.well.due {
  --tone: var(--v-theme-error);
}
.well.cimh {
  border-color: rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgb(var(--v-theme-surface-variant));
}
/* Dark: a 6 % wash disappears on the dark ground, so "your turn" read as a plain box; the tone washes stronger. */
.v-theme--cimhDark .well:not(.cimh) {
  background: rgba(var(--tone), 0.14);
  border-color: rgba(var(--tone), 0.6);
}
.well-text {
  flex: 1;
  min-width: 0;
}
.well-text p {
  margin: 0;
}
.well-title {
  font-size: 19px;
  line-height: 26px;
  font-weight: 700;
}
.well-body {
  font-size: 15px;
  line-height: 22px;
  margin-top: 2px !important;
  max-width: 68ch;
  text-wrap: pretty;
}
.well-expiry {
  margin-top: var(--sp-2) !important;
  font-size: 14px;
  line-height: 20px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 4px;
}
.well-expiry.soon {
  color: rgb(var(--v-theme-error));
}
.well-return {
  margin-top: var(--sp-3) !important;
  padding-top: var(--sp-3);
  border-top: 1px solid rgba(var(--tone), 0.25);
  font-size: 15px;
  line-height: 24px;
}
.well-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 24px;
  margin-left: 4px;
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
  text-underline-offset: 3px;
}
.well-acts {
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  /* Room between View and sign and Cancel request (owner, 2026-11-18), and for View and sign's ring. */
  gap: var(--sp-4);
}
.well-act {
  flex: none;
}
.readonly {
  margin: var(--sp-3) 0 0;
}

/* ---- sections: ruled heads, no cards */
.section {
  margin-top: var(--sp-8);
}
.sec-title {
  margin: 0 0 var(--sp-3);
  padding-bottom: var(--sp-2);
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  font-size: 13px;
  line-height: 18px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
/* Papers: A4 tiles on the page ground, name and kind under each; the whole tile opens the reader. */
.papers-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-3);
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  margin-bottom: var(--sp-4);
}
.papers-title {
  border-bottom: 0;
  margin-bottom: 0;
}
.papers-hint {
  font-size: 13px;
  line-height: 18px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.tiles {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(156px, 1fr));
  gap: var(--sp-5, 20px) var(--sp-4);
}
.tile {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: 0;
  background: none;
  border: 0;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  border-radius: 4px;
}
.tile :deep(.thumb-sheet) {
  margin-bottom: var(--sp-2);
  transition: transform 200ms cubic-bezier(0.16, 1, 0.3, 1), box-shadow 200ms ease-out;
}
.tile:hover :deep(.thumb-sheet) {
  transform: translateY(-2px);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.18), 0 8px 18px -6px rgba(0, 0, 0, 0.22);
}
.tile:hover .tile-name {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.tile:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 4px;
}
.tile-name {
  font-size: 15px;
  line-height: 22px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.tile-kind {
  font-size: 13px;
  line-height: 18px;
  color: rgb(var(--v-theme-on-surface-variant));
}
/* A paper still to come: an empty dashed sheet of the same size. */
.tile.wait {
  cursor: default;
}
.tile-empty {
  display: grid;
  place-items: center;
  aspect-ratio: 210 / 297;
  margin-bottom: var(--sp-2);
  border: 2px dashed rgb(var(--v-theme-field-outline));
  border-radius: 3px;
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface-variant));
}
@media (prefers-reduced-motion: reduce) {
  .tile :deep(.thumb-sheet) {
    transition: none;
  }
  .tile:hover :deep(.thumb-sheet) {
    transform: none;
  }
}

/* History: a ruled section head that opens the dated list in place (native details: keyboard and readers). */
.history-sum,
.record-sum {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  min-height: 32px;
  margin-bottom: 0;
  cursor: pointer;
  list-style: none;
}
.history-sum::-webkit-details-marker,
.record-sum::-webkit-details-marker {
  display: none;
}
.history-sum:hover > span:first-child,
.record-sum:hover > span:first-child {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.history-sum:focus-visible,
.record-sum:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
  border-radius: 2px;
}
.history-n,
.record-total {
  font-weight: 400;
  letter-spacing: 0;
}
.history-chev {
  margin-left: auto;
  transition: transform 200ms cubic-bezier(0.16, 1, 0.3, 1);
}
.history[open] .history-chev,
.quote-record[open] .history-chev {
  transform: rotate(180deg);
}
.history[open] .history-sum,
.quote-record[open] .record-sum {
  margin-bottom: var(--sp-1);
}
.changes {
  margin: var(--sp-2) 0 var(--sp-1);
  row-gap: var(--sp-3) !important;
}
.change :deep(.v-timeline-item__body) {
  display: flex;
  flex-direction: column;
  padding-inline-start: var(--sp-3) !important;
  font-size: 14px;
  line-height: 20px;
}
/* 12 px nodes: the latest change filled primary, earlier ones a hollow ring (3:1 on the ground). */
.change :deep(.v-timeline-divider__dot) {
  width: 12px;
  height: 12px;
  margin-top: 4px;
  background: transparent;
  box-shadow: inset 0 0 0 2px rgba(var(--v-theme-on-surface), 0.45);
}
.change :deep(.v-timeline-divider__inner-dot) {
  background: transparent;
}
.change.latest :deep(.v-timeline-divider__dot) {
  box-shadow: none;
}
.change.latest :deep(.v-timeline-divider__inner-dot) {
  background: rgb(var(--v-theme-primary));
}
.change :deep(.v-timeline-divider__before),
.change :deep(.v-timeline-divider__after) {
  background: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 20%, rgb(var(--v-theme-background)));
}
.ch-when {
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.ch-what {
  font-weight: 600;
  overflow-wrap: anywhere;
}
.ch-why {
  font-weight: 400;
}
.group-label {
  margin: var(--sp-4) 0 var(--sp-1);
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.items {
  list-style: none;
  margin: 0;
  padding: 0;
}
.items li {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--sp-4);
  padding: var(--sp-3) 0;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.thumb {
  width: 64px;
  height: 48px;
  border-radius: 6px;
  background: rgb(var(--v-theme-photo-ground));
  display: grid;
  place-items: center;
  overflow: hidden;
}
.no-photo {
  color: rgba(var(--v-theme-on-surface), 0.35);
}
.thumb img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  mix-blend-mode: multiply;
}
.item-main {
  display: flex;
  flex-direction: column;
  font-size: 14px;
  line-height: 20px;
  overflow-wrap: anywhere;
}
.item-name {
  font-size: 15px;
  line-height: 24px; /* a 24 px target (WCAG 2.5.8) */
  display: inline-block;
  font-weight: 600;
  color: inherit;
  text-decoration: none;
}
.item-name:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.item-end {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  font-weight: 600;
}
.small {
  font-size: 13px;
  font-weight: 400;
}
.facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--sp-4) var(--sp-8);
  margin: 0;
}
.facts dt {
  font-size: 13px;
  line-height: 18px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  margin-bottom: 2px;
}
.facts dd {
  margin: 0;
  font-size: 14px;
  line-height: 22px;
}
.parcels {
  list-style: none;
  margin: var(--sp-4) 0 0;
  padding: 0;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.parcel {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  gap: var(--sp-3);
  align-items: start;
  padding: var(--sp-3) 0;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.parcel-icon {
  margin-top: 1px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.parcel p {
  margin: 0;
}
.parcel-head {
  display: flex;
  flex-wrap: wrap;
  gap: 0 var(--sp-2);
  font-size: 14px;
  line-height: 22px;
}
.parcel-meta,
.parcel-items {
  font-size: 14px;
  line-height: 20px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.track {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 24px;
  font-weight: 500;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.waiting .parcel-head {
  color: rgb(var(--v-theme-on-surface-variant));
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-3);
  justify-content: flex-end;
  margin: var(--sp-8) 0 var(--sp-6);
  padding-top: var(--sp-4);
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

/* Narrow sheets (phones, or a tight docket): action under the text, labels only on the current stage. */
@container (max-width: 560px) {
  .well {
    flex-direction: column;
    align-items: stretch;
    padding: var(--sp-4);
  }
  .stage:not(.current) .stage-label {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
  /* The one label shown runs past its column; at either end it hangs inward from the node, not off the sheet. */
  .stage.current .stage-label {
    white-space: nowrap;
  }
  .stage:first-child.current :deep(.v-timeline-item__body) {
    justify-self: start;
    text-align: start;
  }
  .stage:last-child.current :deep(.v-timeline-item__body) {
    justify-self: end;
    text-align: end;
  }
  .items li {
    grid-template-columns: 48px minmax(0, 1fr) auto;
    gap: var(--sp-3);
  }
  /* The source line ("From …, shipped directly") wraps under the quantity instead of taking the name's room
     (an auto column sized to the whole sentence left the name one letter wide at 360 px). */
  .item-end {
    max-width: 9rem;
    text-align: end;
  }
  .tiles {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .thumb {
    width: 48px;
    height: 36px;
  }
}
@media (prefers-reduced-motion: reduce) {
  /* Reduced motion: no travel, no fill or pulse; the sheet and the well still fade in, so a swap is visible. */
  .content {
    animation-name: fade-in;
  }
  .well {
    animation-name: fade-in;
  }
  .stage :deep(.v-timeline-divider__before),
  .stage :deep(.v-timeline-divider__after),
  .stage :deep(.v-timeline-divider__dot),
  .stage.current .stage-label,
  .path.your-turn .stage.current :deep(.v-timeline-divider__dot)::after,
  .well-cta {
    animation: none;
  }
}
@keyframes fade-in {
  from {
    opacity: 0;
  }
}
</style>
