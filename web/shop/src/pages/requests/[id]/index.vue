<script setup lang="ts">
/**
 * S-11 request detail. Title = what was requested (the id is a reference line under it). Then a banner that
 * says where the request stands and who acts next (the customer's turn in the primary tone with the action;
 * waiting on CIMH in a neutral tone; amber only when a quote expires within a week). While a quote waits
 * for the customer (QUOTED, AWAITING_AGREEMENT) the Quote section comes first, with its expiry and, once
 * chosen, the chosen option per line and the labelled agreement total; afterwards it follows the status
 * and the items. Then delivery facts, files and the actions the server allows (decline, cancel).
 * Same-organisation users see the request read-only (the server sends no actions for them).
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
import { mdiArrowLeft, mdiClockAlertOutline, mdiOpenInNew } from '@mdi/js'
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

definePage({ meta: { guard: 'customer', title: 'Request' } })
const route = useRoute('/requests/[id]/')
const session = useSession()
const notify = useNotify()
const request = ref<OrderRequest | null>(null)
const missing = ref(false)

const title = computed(() => {
  const r = request.value
  return r ? requestTitle(r.lines[0]?.product.name, r.lines.length, r.type) : ''
})

async function load() {
  try {
    request.value = await getRequest(route.params.id)
    document.title = `${title.value} · CIMH Stores`
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) missing.value = true
    else notify.report(e)
  }
}
watch(() => route.params.id, () => void load(), { immediate: true })

const can = (a: string) => request.value?.allowedActions?.includes(a as never) ?? false
const mine = computed(() => request.value?.customer === session.account?.id)
const showQuote = computed(() => !!request.value?.quotes?.length && request.value.type === 'PAID')
const quoteLive = computed(() => request.value?.status === 'QUOTED' || request.value?.status === 'AWAITING_AGREEMENT')
const expiry = computed(() => (quoteLive.value ? expiryNote(request.value?.quoteExpiresAt) : null))

/** Where the request stands and who acts next. `turn`: mine = the customer's move, cimh = waiting on CIMH. */
const banner = computed<{ tone: 'info' | 'warning' | 'success' | 'error' | undefined; title: string; text: string } | null>(() => {
  const r = request.value
  if (!r) return null
  const who = mine.value ? 'you' : r.customerName
  const tone = expiry.value?.soon ? 'warning' : 'info'
  switch (r.status) {
    case 'SUBMITTED':
      return r.type === 'PROBONO'
        ? { tone: undefined, title: 'With CIMH for review', text: `Staff review Pro Bono requests and email ${who} the decision.` }
        : { tone: undefined, title: 'With CIMH for a quote', text: `CIMH is preparing the quote and emails ${who} when it is ready. Nothing is needed until then.` }
    case 'QUOTING':
      return { tone: undefined, title: 'CIMH is preparing the quote', text: `CIMH emails ${who} when it is ready. Nothing is needed until then.` }
    case 'QUOTED':
      return mine.value
        ? { tone, title: 'Your quote is ready', text: 'Choose your options to get the agreement.' }
        : { tone: undefined, title: 'The quote is ready', text: `${r.customerName} chooses the options and signs the agreement.` }
    case 'AWAITING_AGREEMENT':
      return mine.value
        ? { tone, title: 'Sign the agreement', text: 'Download it, sign it and upload the signed copy to accept the quote.' }
        : { tone: undefined, title: 'Waiting for the signed agreement', text: `${r.customerName} signs the agreement and uploads it.` }
    case 'ACCEPTED':
      return {
        tone: 'success',
        title: 'Quote accepted',
        text: 'CIMH staff now check the signature on the agreement. Items from CIMH stock are reserved; supplier items are ordered once the signature is verified. CIMH emails every step.',
      }
    case 'PURCHASING':
      return { tone: undefined, title: 'Signature verified', text: 'CIMH is ordering the supplier items and picking the items from its stock. Supplier items are shipped straight to the delivery address.' }
    case 'APPROVED':
    case 'PICKING':
      return { tone: undefined, title: 'Approved', text: 'CIMH is picking the items. An email follows when they are shipped.' }
    case 'SHIPPED':
      return { tone: undefined, title: 'On its way', text: 'The shipping details are below.' }
    case 'DELIVERED':
      return { tone: 'success', title: 'Delivered', text: 'The invoice, if there is one, is under Files.' }
    case 'REJECTED':
      return { tone: 'error', title: 'Not approved', text: 'This request was not approved. The reason is under Status.' }
    default:
      return isClosed(r.status) ? { tone: 'error', title: 'Cancelled', text: 'Nothing will be ordered for this request.' } : null
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
/** The customer's choices (agreement first, then the accepted ones), for marking the quote table. */
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
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) await load()
    notify.report(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <v-container class="page" max-width="1200">
    <v-btn to="/requests" variant="text" :prepend-icon="mdiArrowLeft" class="back">My requests</v-btn>
    <div v-if="missing" class="stack">
      <p class="t-body">This request doesn't exist or isn't shared with you.</p>
    </div>
    <v-skeleton-loader v-else-if="!request" type="heading, paragraph, table" />
    <template v-else>
      <header class="head">
        <div class="head-main">
          <h1 class="t-h1">{{ title }}</h1>
          <p class="t-body muted ref">
            {{ request.type === 'PROBONO' ? 'Pro Bono request' : 'Request' }} <span class="t-mono" :title="request.id">{{ shortRef(request.id) }}</span>
            · sent {{ formatDate(request.submittedAt) }}
          </p>
        </div>
        <StatusChip :status="request.status" />
      </header>

      <v-alert v-if="banner" :type="banner.tone" :title="banner.title" variant="tonal" class="banner">
        {{ banner.text }}
        <template v-if="can('agreement')" #append>
          <v-btn :to="`/requests/${request.id}/agreement`" color="primary" variant="flat">
            {{ request.status === 'AWAITING_AGREEMENT' ? 'Continue' : 'Choose options' }}
          </v-btn>
        </template>
      </v-alert>
      <p v-if="!mine" class="t-body muted">Requested by {{ request.customerName }} (same organisation). You can view it; only they can act on it.</p>

      <template v-for="part in order" :key="part">
        <section v-if="part === 'quote' && showQuote" class="section">
          <h2 class="t-h2">Quote</h2>
          <dl v-if="quoteLive || agreementTotal" class="quote-facts">
            <div v-if="expiry && request.quoteExpiresAt" :class="{ soon: expiry.soon }">
              <dt>Valid until</dt>
              <dd>
                <v-icon v-if="expiry.soon" :icon="mdiClockAlertOutline" size="18" />
                {{ formatDate(request.quoteExpiresAt) }} <span class="left">({{ expiry.text }})</span>
              </dd>
            </div>
            <div v-if="agreementTotal">
              <dt>Agreement total</dt>
              <dd class="tnum">{{ agreementTotal }}</dd>
            </div>
            <div v-else-if="request.status === 'QUOTED'">
              <dt>Total</dt>
              <dd>Depends on the options you choose</dd>
            </div>
          </dl>
          <QuoteTable :request="request" :picked="picked" />
        </section>

        <section v-else-if="part === 'status'" class="section">
          <h2 class="t-h3">Status</h2>
          <RequestTimeline :request="request" />
        </section>

        <section v-else-if="part === 'items'" class="section">
          <template v-if="paidLines.length">
            <h2 class="t-h3">Items requested</h2>
            <ul class="items">
              <li v-for="l in paidLines" :key="l.lineId">
                <v-img v-if="l.product.image" :src="l.product.image" width="72" height="54" cover class="thumb" alt="" />
                <span class="item-main">
                  <router-link :to="`/catalogue/${l.productId}`" class="item-name">{{ l.product.name }}</router-link>
                  <span class="t-body muted">{{ [l.product.make, l.product.modelname].filter(Boolean).join(' · ') }}</span>
                </span>
                <span class="item-end">
                  <span class="tnum">Qty {{ l.qty }}</span>
                  <span v-if="l.choice" class="t-caption muted">{{ l.choice === 'CIMH' ? 'From CIMH stock' : 'From a supplier' }}</span>
                </span>
              </li>
            </ul>
          </template>
          <template v-if="probonoLines.length">
            <h2 class="t-h3" :class="{ 'probono-title': paidLines.length }">{{ paidLines.length ? 'Pro Bono items' : 'Items requested' }}</h2>
            <ul class="items">
              <li v-for="l in probonoLines" :key="l.lineId">
                <v-img v-if="l.product.image" :src="l.product.image" width="72" height="54" cover class="thumb" alt="" />
                <span class="item-main">
                  <router-link :to="`/catalogue/${l.productId}`" class="item-name">{{ l.product.name }}</router-link>
                  <span class="t-body muted">{{ [l.product.make, l.product.modelname].filter(Boolean).join(' · ') }}</span>
                </span>
                <span class="item-end"><span class="tnum">Qty {{ l.qty }}</span></span>
              </li>
            </ul>
          </template>
        </section>
      </template>

      <section class="section">
        <h2 class="t-h3">Delivery</h2>
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

      <RequestFiles :files="request.files ?? []" class="section" />

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
    </template>
  </v-container>
</template>

<style scoped>
.back {
  margin-bottom: var(--sp-2);
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--sp-4);
  flex-wrap: wrap;
}
.head-main {
  min-width: 0;
}
.head h1 {
  overflow-wrap: anywhere;
}
.ref {
  margin: var(--sp-1) 0 0;
  overflow-wrap: anywhere;
}
.banner {
  margin: var(--sp-4) 0;
}
.banner :deep(.v-alert-title) {
  font-size: 18px;
  line-height: 26px;
  font-weight: 600;
}
/* Phones: the action goes under the text (beside it, the text wrapped to six lines). */
@media (max-width: 599px) {
  .banner :deep(.v-alert__content) {
    min-width: 0;
  }
  .banner {
    grid-template-columns: auto minmax(0, 1fr);
    grid-template-areas: 'prepend content' 'append append';
  }
  .banner :deep(.v-alert__append) {
    margin-inline-start: 0;
    padding-top: var(--sp-3);
  }
}
.section {
  margin-top: var(--sp-8);
}
.section h2 {
  margin-bottom: var(--sp-3);
}

/* Quote facts: the expiry and the total, large enough to be the first thing read. */
.quote-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-3) var(--sp-12);
  margin: 0 0 var(--sp-4);
}
.quote-facts dt {
  font-size: 13px;
  line-height: 18px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.quote-facts dd {
  margin: 0;
  font-size: 18px;
  line-height: 26px;
  font-weight: 600;
}
.quote-facts .left {
  font-weight: 400;
}
.quote-facts .soon dd {
  color: rgb(var(--v-theme-error));
}

.items {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.items li {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) 0;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.thumb {
  flex: none;
  border-radius: 6px;
}
.item-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
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
}
.item-end {
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}
.probono-title {
  margin-top: var(--sp-6);
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
}
</style>
