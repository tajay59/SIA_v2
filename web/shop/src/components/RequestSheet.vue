<script setup lang="ts">
/**
 * One request as the customer sees it (S-11), shared by the docket on /requests (beside the list) and the
 * request's own page. Reading order: reference + title, the request path (one rule, a node per stage, filled
 * to where it stands), the "whose move" well (the customer's turn in the primary tone with its action; CIMH's
 * turn neutral; amber only when a quote expires within a week), then Quote (first while it waits for the
 * customer), Status, Items, Delivery, Files and the actions the server allows (decline, cancel).
 * Same-organisation users see it read-only (the server sends no actions for them).
 */
import {
  act,
  ApiError,
  expiryNote,
  getRequest,
  isClosed,
  type LineChoice,
  type OrderRequest,
  QuoteTable,
  ReasonDialog,
  RequestFiles,
  RequestTimeline,
  requestTitle,
  shortRef,
  StatusChip,
  useNotify,
  useSession,
} from '@cimh/web-app'
import { formatDate, formatMoney } from '@cimh/web-ui'
import { mdiCheck, mdiClockAlertOutline, mdiOpenInNew, mdiPackageVariantClosed } from '@mdi/js'
import { computed, nextTick, ref, watch } from 'vue'

const props = withDefaults(defineProps<{ id: string; level?: 1 | 2; setTitle?: boolean; dir?: 1 | -1 }>(), { level: 1, setTitle: false, dir: 1 })
const emit = defineEmits<{ changed: [OrderRequest] }>()
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

const can = (a: string) => request.value?.allowedActions?.includes(a as never) ?? false
const mine = computed(() => request.value?.customer === session.account?.id)
const showQuote = computed(() => !!request.value?.quotes?.length && request.value.type === 'PAID')
const quoteLive = computed(() => request.value?.status === 'QUOTED' || request.value?.status === 'AWAITING_AGREEMENT')
const expiry = computed(() => (quoteLive.value ? expiryNote(request.value?.quoteExpiresAt) : null))

/** The request path the customer reads: fewer, plainer stages than the status list (stages group statuses). */
const STAGES = {
  PAID: [
    { label: 'Sent', statuses: ['SUBMITTED'] },
    { label: 'Quote', statuses: ['QUOTING', 'QUOTED'] },
    { label: 'Agreement', statuses: ['AWAITING_AGREEMENT', 'ACCEPTED'] },
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
type Tone = 'turn' | 'warn' | 'cimh' | 'done' | 'stop'
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
    case 'QUOTED':
      return mine.value
        ? { tone: turn, title: 'Your quote is ready', text: 'Choose your options to get the agreement.' }
        : { tone: 'cimh', title: 'The quote is ready', text: `${r.customerName} chooses the options and signs the agreement.` }
    case 'AWAITING_AGREEMENT':
      return mine.value
        ? { tone: turn, title: 'Sign the agreement', text: 'Download it, sign it and upload the signed copy to accept the quote.' }
        : { tone: 'cimh', title: 'Waiting for the signed agreement', text: `${r.customerName} signs the agreement and uploads it.` }
    case 'ACCEPTED':
      return {
        tone: 'done',
        title: 'Quote accepted',
        text: 'CIMH staff now check the signature on the agreement. Items from CIMH stock are reserved; supplier items are ordered once the signature is verified. CIMH emails every step.',
      }
    case 'PURCHASING':
      return { tone: 'cimh', title: 'Signature verified', text: 'CIMH is ordering the supplier items and picking the items from its stock. Supplier items are shipped straight to the delivery address.' }
    case 'APPROVED':
    case 'PICKING':
      return { tone: 'cimh', title: 'Approved', text: 'CIMH is picking the items. An email follows when they are shipped.' }
    case 'SHIPPED':
      return { tone: 'cimh', title: 'On its way', text: 'The shipping details are under Delivery.' }
    case 'DELIVERED':
      return { tone: 'done', title: 'Delivered', text: 'The invoice, if there is one, is under Files.' }
    case 'REJECTED':
      return { tone: 'stop', title: 'Not approved', text: 'This request was not approved. The reason is under Status.' }
    default:
      return isClosed(r.status) ? { tone: 'stop', title: 'Cancelled', text: 'Nothing will be ordered for this request.' } : null
  }
})

const paidLines = computed(() => request.value?.lines.filter((l) => !l.product.probono) ?? [])
const probonoLines = computed(() => request.value?.lines.filter((l) => l.product.probono) ?? [])
// An agreement made for an earlier quote version is void once staff send a revised quote (it stays on the record).
const agreement = computed(() => {
  const r = request.value
  const latest = Math.max(0, ...(r?.quotes ?? []).map((q) => q.version))
  return r?.agreement && r.agreement.quoteVersion === latest ? r.agreement : null
})
const agreementTotal = computed(() =>
  agreement.value?.total ? formatMoney(agreement.value.total, request.value?.currency ?? 'BBD') : null,
)
const picked = computed<Record<string, LineChoice> | undefined>(() => {
  const list = agreement.value?.choices
  if (!list?.length) return undefined
  return Object.fromEntries(list.filter((c) => c.lineId && c.choice).map((c) => [c.lineId!, c.choice!]))
})
// A live quote is the thing to decide on, so it leads; later it is a record and follows the status and items.
const order = computed(() => (quoteLive.value ? ['quote', 'status', 'items'] : ['status', 'items', 'quote']))

const dialog = ref<null | 'decline' | 'cancel'>(null)
const busy = ref(false)
async function run(kind: 'decline' | 'cancel', reason: string) {
  if (!request.value) return
  busy.value = true
  try {
    request.value = await act(request.value, `/requests/{requestId}/${kind}`, { reason })
    notify.toast(kind === 'decline' ? 'Quote declined' : 'Request cancelled', 'success')
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

<template>
  <div class="sheet" :class="{ switching }" :style="{ '--dir': dir }" :inert="switching || undefined" :aria-busy="switching || undefined">
    <div v-if="missing" class="missing">
      <p class="t-body">This request doesn't exist or isn't shared with you.</p>
    </div>
    <v-skeleton-loader v-else-if="!request" type="heading, paragraph, table" />
    <div v-else :key="request.id" class="content">
      <header class="head">
        <p class="ref">
          {{ request.type === 'PROBONO' ? 'Pro Bono request' : 'Request' }}
          <span class="t-mono">{{ request.id }}</span>
          · sent {{ formatDate(request.submittedAt) }}
        </p>
        <div class="title-row">
          <component :is="`h${level}`" ref="heading" tabindex="-1" class="title">{{ title }}</component>
          <StatusChip :status="request.status" />
        </div>
      </header>

      <!-- The request path: one rule, one node per stage, filled to where it stands. -->
      <ol
        v-if="!closed"
        class="path"
        :class="{ 'your-turn': well?.tone === 'turn' || well?.tone === 'warn' }"
        :style="{ '--n': stages.length, '--fill': Math.max(0, stageAt) / (stages.length - 1) }"
        aria-label="Request progress"
      >
        <li
          v-for="(s, i) in stages"
          :key="s.label"
          class="stage"
          :style="{ '--i': i, '--at': Math.max(0, stageAt) }"
          :class="{ done: i < stageAt || (finished && i === stageAt), current: i === stageAt && !finished }"
          :aria-current="i === stageAt ? 'step' : undefined"
        >
          <span class="dot"><v-icon v-if="i < stageAt || finished" :icon="mdiCheck" size="12" /></span>
          <span class="stage-label">{{ s.label }}</span>
        </li>
      </ol>

      <section v-if="well" class="well" :class="well.tone" aria-label="Where it stands">
        <div class="well-text">
          <p class="well-title">{{ well.title }}</p>
          <p class="well-body">{{ well.text }}</p>
          <p v-if="expiry && request.quoteExpiresAt" class="well-expiry" :class="{ soon: expiry.soon }">
            <v-icon v-if="expiry.soon" :icon="mdiClockAlertOutline" size="16" />
            Quote valid until {{ formatDate(request.quoteExpiresAt) }} ({{ expiry.text }})
          </p>
        </div>
        <v-btn v-if="can('agreement')" :to="`/requests/${request.id}/agreement`" color="primary" variant="flat" size="large" class="well-act">
          {{ request.status === 'AWAITING_AGREEMENT' ? 'Continue' : 'Choose options' }}
        </v-btn>
      </section>
      <p v-if="!mine" class="t-body muted readonly">Requested by {{ request.customerName }} (same organisation). You can view it; only they can act on it.</p>

      <template v-for="part in order" :key="part">
        <section v-if="part === 'quote' && showQuote" class="section" aria-labelledby="sec-quote">
          <h3 id="sec-quote" class="sec-title">Quote</h3>
          <dl v-if="agreementTotal || request.status === 'QUOTED'" class="quote-facts">
            <div v-if="agreementTotal">
              <dt>Agreement total</dt>
              <dd class="tnum">{{ agreementTotal }}</dd>
            </div>
            <div v-else>
              <dt>Total</dt>
              <dd>Depends on the options you choose</dd>
            </div>
          </dl>
          <QuoteTable :request="request" :picked="picked" />
        </section>

        <section v-else-if="part === 'status'" class="section" aria-labelledby="sec-status">
          <h3 id="sec-status" class="sec-title">Status</h3>
          <RequestTimeline :request="request" />
        </section>

        <section v-else-if="part === 'items'" class="section" aria-labelledby="sec-items">
          <h3 id="sec-items" class="sec-title">{{ paidLines.length && probonoLines.length ? 'Items' : 'Items requested' }}</h3>
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
                    <span v-if="l.choice" class="muted small">{{ l.choice === 'CIMH' ? 'From CIMH stock' : 'From a supplier' }}</span>
                  </span>
                </li>
              </ul>
            </template>
          </template>
        </section>
      </template>

      <section class="section" aria-labelledby="sec-delivery">
        <h3 id="sec-delivery" class="sec-title">Delivery</h3>
        <dl class="facts">
          <div v-if="request.shipTo">
            <dt>Deliver to</dt>
            <dd>
              {{ request.shipTo.firstname }} {{ request.shipTo.lastname }}<br />
              <template v-if="request.shipTo.organisation">{{ request.shipTo.organisation }}<br /></template>
              {{ request.shipTo.line1 }}<template v-if="request.shipTo.line2">, {{ request.shipTo.line2 }}</template><br />
              {{ [request.shipTo.city, request.shipTo.parish, request.shipTo.zip].filter(Boolean).join(' ') }}<br />
              {{ request.shipTo.country }}
            </dd>
          </div>
          <div v-if="request.currency">
            <dt>Quote currency</dt>
            <dd>{{ request.currency }}</dd>
          </div>
          <div v-if="request.shipping">
            <dt>Shipped</dt>
            <dd>
              {{ request.shipping.date ? formatDate(request.shipping.date) : '' }} by
              {{ request.shipping.carrier === 'HAND' ? 'hand delivery' : request.shipping.carrier }}
              <template v-if="request.shipping.tracking">
                <br />Tracking:
                <a v-if="request.shipping.trackingUrl" :href="request.shipping.trackingUrl" target="_blank" rel="noopener" class="t-mono">
                  {{ request.shipping.tracking }} <v-icon :icon="mdiOpenInNew" size="14" />
                </a>
                <span v-else class="t-mono">{{ request.shipping.tracking }}</span>
              </template>
              <template v-if="request.shipping.note"><br />{{ request.shipping.note }}</template>
            </dd>
          </div>
        </dl>
      </section>

      <section class="section" aria-labelledby="sec-files">
        <h3 id="sec-files" class="sec-title">Files</h3>
        <RequestFiles :files="request.files ?? []" bare />
      </section>

      <div v-if="can('decline') || can('cancel')" class="actions">
        <v-btn v-if="can('decline')" variant="outlined" @click="dialog = 'decline'">Decline quote</v-btn>
        <v-btn v-if="can('cancel')" variant="outlined" color="error" @click="dialog = 'cancel'">Cancel request</v-btn>
      </div>

      <ReasonDialog
        :model-value="dialog !== null"
        :title="dialog === 'decline' ? 'Decline the quote?' : 'Cancel this request?'"
        :text="dialog === 'decline' ? 'The request will be closed. You can send a new request later.' : 'Nothing will be ordered for this request.'"
        :confirm="dialog === 'decline' ? 'Decline quote' : 'Cancel request'"
        danger
        :busy="busy"
        @update:model-value="(v: boolean) => !v && (dialog = null)"
        @submit="(reason: string) => run(dialog!, reason)"
      />
    </div>
  </div>
</template>

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
    opacity: 0;
    transform: translateY(calc(var(--dir, 1) * 10px));
  }
}
.path::after {
  animation: path-fill var(--fill-ms) var(--ease) 120ms backwards;
}
@keyframes path-fill {
  from {
    transform: scaleX(0);
  }
}
/* A dot lights when the fill reaches it: its delay is its share of the fill. */
.stage.done .dot,
.stage.current .dot {
  animation: dot-light 260ms var(--ease) backwards;
  animation-delay: calc(120ms + var(--fill-ms) * var(--i) / max(var(--at), 1) * 0.8);
}
@keyframes dot-light {
  from {
    background: rgb(var(--v-theme-surface));
    border-color: rgba(var(--v-border-color), 0.45);
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
.path.your-turn .stage.current .dot {
  position: relative;
}
.path.your-turn .stage.current .dot::after {
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

/* ---- the request path: same grammar as the cart's, small and on the page ground */
.path {
  --dot: 16px;
  list-style: none;
  margin: var(--sp-6) 0 var(--sp-5, 20px);
  padding: 0;
  display: grid;
  grid-template-columns: repeat(var(--n), minmax(0, 1fr));
  position: relative;
}
.path::before,
.path::after {
  content: '';
  position: absolute;
  top: calc(var(--dot) / 2 - 1.5px);
  left: calc(50% / var(--n));
  width: calc(100% - 100% / var(--n));
  height: 3px;
  border-radius: 2px;
  background: rgba(var(--v-border-color), 0.2);
}
.path::after {
  background: rgb(var(--v-theme-primary));
  transform-origin: left center;
  transform: scaleX(var(--fill));
  transition: transform 560ms cubic-bezier(0.16, 1, 0.3, 1);
}
.stage {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-2);
  text-align: center;
}
.dot {
  display: grid;
  place-items: center;
  width: var(--dot);
  height: var(--dot);
  border-radius: 50%;
  background: rgb(var(--v-theme-surface));
  border: 2px solid rgba(var(--v-border-color), 0.45);
  color: rgb(var(--v-theme-on-primary));
}
.stage.done .dot {
  background: rgb(var(--v-theme-primary));
  border-color: rgb(var(--v-theme-primary));
}
.stage.current .dot {
  border: 4px solid rgb(var(--v-theme-primary));
  box-shadow: 0 0 0 4px rgba(var(--v-theme-primary), 0.16);
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
.well.stop {
  --tone: var(--v-theme-error);
}
.well.cimh {
  border-color: rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgb(var(--v-theme-surface-variant));
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
.quote-facts {
  margin: 0 0 var(--sp-4);
}
.quote-facts dt {
  font-size: 13px;
  line-height: 18px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.quote-facts dd {
  margin: 0;
  font-size: 22px;
  line-height: 30px;
  font-weight: 700;
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
  line-height: 22px;
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
  .stage.current {
    z-index: 2;
  }
  .stage.current .stage-label {
    white-space: nowrap;
  }
  .stage:first-child.current {
    align-items: flex-start;
  }
  .stage:last-child.current {
    align-items: flex-end;
  }
  .items li {
    grid-template-columns: 48px minmax(0, 1fr) auto;
    gap: var(--sp-3);
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
  .path::after,
  .stage.done .dot,
  .stage.current .dot,
  .stage.current .stage-label,
  .path.your-turn .stage.current .dot::after {
    animation: none;
  }
  .path::after {
    transition: none;
  }
}
@keyframes fade-in {
  from {
    opacity: 0;
  }
}
</style>
