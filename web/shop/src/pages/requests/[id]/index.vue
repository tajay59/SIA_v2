<script setup lang="ts">
/**
 * S-11 request detail, in the legacy SHOP OrdersPage structure: "Request" title with the id; a status banner
 * (legacy "Payment required" / "Order cancelled"); "Ship to" and date cards side by side; the Files card;
 * the status (timeline); "Items requested". v2 adds the quote panel (QUOTED onwards), the actions the server
 * allows (choose options, decline, cancel) and shipping with a tracking link. Same-organisation users see
 * the request read-only (the server sends no actions for them).
 */
import {
  act,
  ApiError,
  getRequest,
  isClosed,
  type OrderRequest,
  QuoteTable,
  ReasonDialog,
  RequestFiles,
  RequestTimeline,
  StatusChip,
  useNotify,
  useSession,
} from '@cimh/web-app'
import { formatDate, formatMoney } from '@cimh/web-ui'
import { mdiArrowLeft, mdiOpenInNew } from '@mdi/js'
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

definePage({ meta: { guard: 'customer', title: 'Request' } })
const route = useRoute('/requests/[id]/')
const session = useSession()
const notify = useNotify()
const request = ref<OrderRequest | null>(null)
const missing = ref(false)

async function load() {
  try {
    request.value = await getRequest(route.params.id)
    document.title = `Request ${request.value.id} · CIMH Stores`
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) missing.value = true
    else notify.report(e)
  }
}
watch(() => route.params.id, () => void load(), { immediate: true })

const can = (a: string) => request.value?.allowedActions?.includes(a as never) ?? false
const mine = computed(() => request.value?.customer === session.account?.id)
const showQuote = computed(() => !!request.value?.quotes?.length && request.value.type === 'PAID')
const banner = computed(() => {
  const r = request.value
  if (!r) return null
  if (r.status === 'QUOTED') return { tone: 'info', text: 'Your quote is ready. Choose your options to get the agreement.' }
  if (r.status === 'AWAITING_AGREEMENT') return { tone: 'warning', text: 'Sign the agreement and upload it to accept the quote.' }
  if (isClosed(r.status)) return { tone: 'error', text: r.status === 'REJECTED' ? 'This request was not approved.' : 'This request was cancelled.' }
  if (r.status === 'DELIVERED') return { tone: 'success', text: 'Delivered.' }
  return null
})
const paidLines = computed(() => request.value?.lines.filter((l) => !l.product.probono) ?? [])
const probonoLines = computed(() => request.value?.lines.filter((l) => l.product.probono) ?? [])
const agreementTotal = computed(() =>
  request.value?.agreement?.total ? formatMoney(request.value.agreement.total, request.value.currency ?? 'BBD') : null,
)

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
    <div v-if="missing" class="t-body">This request doesn't exist or isn't shared with you.</div>
    <v-skeleton-loader v-else-if="!request" type="heading, paragraph, table" />
    <template v-else>
      <header class="head">
        <div>
          <h1 class="t-h1">{{ request.type === 'PROBONO' ? 'Pro Bono request' : 'Request' }}</h1>
          <p class="t-caption t-mono">{{ request.id }}</p>
        </div>
        <div class="head-right">
          <StatusChip :status="request.status" />
          <p v-if="agreementTotal" class="t-h3 tnum">{{ agreementTotal }}</p>
        </div>
      </header>

      <v-alert v-if="banner" :type="banner.tone as any" variant="tonal" class="banner">
        {{ banner.text }}
        <template v-if="can('agreement')" #append>
          <v-btn :to="`/requests/${request.id}/agreement`" color="primary" variant="flat">
            {{ request.status === 'AWAITING_AGREEMENT' ? 'Continue' : 'Choose options' }}
          </v-btn>
        </template>
      </v-alert>
      <p v-if="!mine" class="t-caption muted">Requested by {{ request.customerName }} (same organisation). You can view it; only they can act on it.</p>

      <div class="cards">
        <v-card v-if="request.shipTo" flat border>
          <v-card-subtitle>Ship to</v-card-subtitle>
          <v-card-text class="t-body">
            <strong>{{ request.shipTo.firstname }} {{ request.shipTo.lastname }}</strong><br />
            <template v-if="request.shipTo.organisation">{{ request.shipTo.organisation }}<br /></template>
            {{ request.shipTo.line1 }}<template v-if="request.shipTo.line2">, {{ request.shipTo.line2 }}</template><br />
            {{ [request.shipTo.city, request.shipTo.parish, request.shipTo.zip].filter(Boolean).join(' ') }}<br />
            {{ request.shipTo.country }}
          </v-card-text>
        </v-card>
        <v-card flat border>
          <v-card-subtitle>Requested</v-card-subtitle>
          <v-card-text class="t-body">
            {{ formatDate(request.submittedAt) }}
            <template v-if="request.currency"><br />Quote currency: {{ request.currency }}</template>
            <template v-if="request.shipping">
              <br />Shipped {{ request.shipping.date ? formatDate(request.shipping.date) : '' }} by
              {{ request.shipping.carrier === 'HAND' ? 'hand delivery' : request.shipping.carrier }}
              <template v-if="request.shipping.tracking">
                <br />Tracking:
                <a v-if="request.shipping.trackingUrl" :href="request.shipping.trackingUrl" target="_blank" rel="noopener" class="t-mono">
                  {{ request.shipping.tracking }} <v-icon :icon="mdiOpenInNew" size="14" />
                </a>
                <span v-else class="t-mono">{{ request.shipping.tracking }}</span>
              </template>
              <template v-if="request.shipping.note"><br />{{ request.shipping.note }}</template>
            </template>
          </v-card-text>
        </v-card>
      </div>

      <RequestFiles :files="request.files ?? []" class="section" />

      <section class="section">
        <h2 class="t-h3">Status</h2>
        <RequestTimeline :request="request" />
      </section>

      <section v-if="showQuote" class="section">
        <h2 class="t-h3">Quote</h2>
        <QuoteTable :request="request" />
      </section>

      <section class="section">
        <h2 class="t-h3">Items requested</h2>
        <v-list lines="two">
          <template v-for="(l, i) in paidLines" :key="l.lineId">
            <v-divider v-if="i" />
            <v-list-item :title="l.product.name" :subtitle="[l.product.make, l.product.modelname].filter(Boolean).join(' · ')">
              <template #prepend><v-img :src="l.product.image ?? undefined" width="72" height="54" cover class="thumb" /></template>
              <template #append>
                <span class="tnum">Qty {{ l.qty }}</span>
                <v-chip v-if="l.choice" size="small" label class="choice">{{ l.choice === 'CIMH' ? 'From CIMH stock' : 'From supplier' }}</v-chip>
              </template>
            </v-list-item>
          </template>
        </v-list>
        <template v-if="probonoLines.length">
          <h2 class="t-h3 probono-title">Pro Bono items</h2>
          <v-list lines="two">
            <v-list-item v-for="l in probonoLines" :key="l.lineId" :title="l.product.name">
              <template #prepend><v-img :src="l.product.image ?? undefined" width="72" height="54" cover class="thumb" /></template>
              <template #append><span class="tnum">Qty {{ l.qty }}</span></template>
            </v-list-item>
          </v-list>
        </template>
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
.head-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--sp-2);
}
.banner {
  margin: var(--sp-4) 0;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--sp-4);
  margin-top: var(--sp-4);
}
.section {
  margin-top: var(--sp-6);
}
.section h2 {
  margin-bottom: var(--sp-3);
}
.thumb {
  border-radius: 6px;
  margin-right: var(--sp-3);
}
.choice {
  margin-left: var(--sp-2);
}
.probono-title {
  margin-top: var(--sp-4);
}
.actions {
  display: flex;
  gap: var(--sp-3);
  justify-content: flex-end;
  margin: var(--sp-6) 0;
}
</style>
