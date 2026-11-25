<script setup lang="ts">
/**
 * S-10 My requests ("Docket", impeccable 2026-11-16). The navy band names the page and carries the scope
 * (Mine · My organisation). Below, the list grouped by whose move it is: "Waiting for you" (own requests with
 * a quote to review or an agreement to sign, newest first; a separate query so they lead whatever the
 * paging), "With CIMH", "On its way", "Done". Rows are named by what was requested; the id is a short reference.
 * Wide screens (≥ 1100 px) open the request beside the list (`?open=<id>`, the shared `RequestSheet`); narrower
 * screens go to the request's own page. Status and year narrow the list once there is something to narrow.
 */
import {
  call,
  customerActionNeeded,
  expiryNote,
  isClosed,
  orders,
  paymentDue,
  type OrderRequest,
  type RequestStatus,
  type RequestSummary,
  requestTitle,
  shopDir,
  ShortRef,
  useCursorList,
  useNotify,
} from '@cimh/web-app'
import { formatDate } from '@cimh/web-ui'
import { mdiAlertOutline, mdiChevronRight, mdiClipboardTextOutline } from '@mdi/js'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import RequestSheet from '../../components/RequestSheet.vue'

definePage({ meta: { guard: 'customer', title: 'Orders' } })
const notify = useNotify()
const route = useRoute()
const router = useRouter()
const { width } = useDisplay()
const wide = computed(() => width.value >= 1100)

const scope = ref<'mine' | 'organisation'>('mine')
const thisYear = new Date().getFullYear()
const years = Array.from({ length: thisYear - 2019 }, (_, i) => thisYear - i)
const year = ref<number | null>(null)
const WAITING: RequestStatus[] = ['QUOTED'] // view and sign, or cancel
/** Option values are plain keys: an array value makes v-select treat it as several selections. */
const STATUS_GROUPS: { title: string; value: string; statuses: RequestStatus[] | null; payment?: true }[] = [
  { title: 'All statuses', value: 'all', statuses: null },
  { title: 'Waiting for me', value: 'waiting', statuses: WAITING },
  { title: 'Payment required', value: 'payment', statuses: null, payment: true },
  { title: 'In progress', value: 'progress', statuses: ['SUBMITTED', 'QUOTING', 'ACCEPTED', 'PURCHASING', 'APPROVED', 'PICKING', 'SHIPPED'] },
  { title: 'Delivered', value: 'delivered', statuses: ['DELIVERED'] },
  { title: 'Closed', value: 'closed', statuses: ['CANCELLED', 'REJECTED', 'DECLINED'] },
]
// `?status=payment` (the sign-in payments dialog) opens the list on that filter.
const statusKey = ref(STATUS_GROUPS.some((g) => g.value === route.query.status) ? String(route.query.status) : 'all')
watch(
  () => route.query.status,
  (q) => {
    if (typeof q === 'string' && STATUS_GROUPS.some((g) => g.value === q)) statusKey.value = q
  },
)
const status = computed(() => STATUS_GROUPS.find((g) => g.value === statusKey.value)?.statuses ?? null)
/** Delivered paid requests with no proof of payment yet (server filter `payment=due`). */
const paymentFilter = computed(() => statusKey.value === 'payment')
const filtered = computed(() => !!status.value || paymentFilter.value || !!year.value)
function clearFilters() {
  statusKey.value = 'all'
  year.value = null
}

type Page = { items: RequestSummary[]; nextCursor: string | null }
/** Every group lists its requests by date sent, newest first (owner, 2026-11-16). */
const newestFirst = (list: RequestSummary[]) => [...list].sort((a, b) => (b.submittedAt ?? '').localeCompare(a.submittedAt ?? ''))
const list = useCursorList<RequestSummary>(async (cursor) => {
  const query: Record<string, unknown> = { scope: scope.value, limit: 25, sort: 'newest' }
  if (cursor) query.cursor = cursor
  if (year.value) query.year = year.value
  if (status.value) query.status = status.value.join(',')
  if (paymentFilter.value) query.payment = 'due'
  return (await call(() => orders.GET('/requests', { params: { query: query as any } }))) as Page
})
watch([scope, year, statusKey], () => void list.reload(), { immediate: true })

const waiting = ref<RequestSummary[]>([])
async function loadWaiting() {
  try {
    const query = { scope: 'mine', status: WAITING.join(','), limit: 25, sort: 'newest' }
    const page = (await call(() => orders.GET('/requests', { params: { query: query as any } }))) as Page
    waiting.value = newestFirst(page.items)
  } catch (e) {
    notify.report(e)
  }
}
const waitingDone = ref(false)
onMounted(() => void loadWaiting().finally(() => (waitingDone.value = true)))
// Back from a request's own page (shopDir 'quiet'): the page cross-fades, so the rows arrive still; the usual
// staggered entrance returns once this arrival's lists are on screen (scope or filter changes).
const rowsAppear = ref(shopDir.value !== 'quiet')
if (!rowsAppear.value) {
  const stop = watch([() => list.loaded.value, waitingDone], async ([a, b]) => {
    if (!a || !b) return
    await nextTick()
    rowsAppear.value = true
    stop()
  })
}
const showWaiting = computed(() => scope.value === 'mine' && !filtered.value && waiting.value.length > 0)
const waitingIds = computed(() => new Set(showWaiting.value ? waiting.value.map((r) => r.id) : []))
const rows = computed(() => list.items.value.filter((r) => !waitingIds.value.has(r.id)))
const canFilter = computed(() => filtered.value || list.items.value.length > 0 || !!list.nextCursor.value)

/** The rest of the list by whose move it is (page order kept inside each group). */
const groups = computed(() => {
  const out = [
    { key: 'cimh', title: 'With CIMH', rows: [] as RequestSummary[] },
    { key: 'yours', title: scope.value === 'mine' ? 'Waiting for you' : 'Waiting for the requester', rows: [] as RequestSummary[] },
    { key: 'way', title: 'On its way', rows: [] as RequestSummary[] },
    { key: 'done', title: 'Done', rows: [] as RequestSummary[] },
  ]
  for (const r of rows.value) {
    if (paymentDue(r)) out[1]!.rows.push(r)
    else if (r.status === 'DELIVERED' || isClosed(r.status)) out[3]!.rows.push(r)
    else if (r.status === 'SHIPPED') out[2]!.rows.push(r)
    else if (WAITING.includes(r.status)) out[1]!.rows.push(r)
    else out[0]!.rows.push(r)
  }
  return out.filter((g) => g.rows.length).map((g) => ({ ...g, rows: newestFirst(g.rows) }))
})

const title = (r: RequestSummary) => requestTitle(r.firstItemName, r.lineCount, r.type)
const STATE: Partial<Record<RequestStatus, string>> = {
  SUBMITTED: 'Sent',
  QUOTING: 'Quote being prepared',
  QUOTED: 'Quote to sign',
  ACCEPTED: 'Signed',
  PURCHASING: 'Being ordered',
  APPROVED: 'Approved',
  PICKING: 'Being picked',
  SHIPPED: 'Shipped',
  DELIVERED: 'Delivered',
  CANCELLED: 'Cancelled',
  DECLINED: 'Quote declined',
  REJECTED: 'Not approved',
}
const stateText = (r: RequestSummary) =>
  paymentDue(r) ? 'Delivered · payment required' : r.paymentStatus === 'PROOF_SENT' ? 'Delivered · proof of payment sent' : r.paymentStatus === 'PAID' ? 'Delivered · paid' : (STATE[r.status] ?? r.status)

// The open request (wide screens): ?open=<id>, else the first that waits for the customer, else the newest.
const openId = computed<string | null>(() => {
  if (!wide.value) return null
  const q = route.query.open
  if (typeof q === 'string' && q) return q
  return (showWaiting.value ? waiting.value[0]?.id : undefined) ?? rows.value[0]?.id ?? null
})
const rowLink = (r: RequestSummary) => (wide.value ? { query: { ...route.query, open: r.id } } : `/requests/${r.id}`)
// On a narrow screen an ?open= link (shared or after resizing) goes to the request's own page.
watch(
  [wide, () => route.query.open],
  ([w, q]) => {
    if (!w && typeof q === 'string' && q) void router.replace(`/requests/${q}`)
  },
  { immediate: true },
)
// The sheet slides in from the side of the list the new request sits on (below the old one = from below).
const order = computed(() => [...(showWaiting.value ? waiting.value : []), ...groups.value.flatMap((g) => g.rows)].map((r) => r.id))
const dir = ref<1 | -1>(1)
watch(openId, (now, before) => {
  if (!now || !before) return
  dir.value = order.value.indexOf(now) < order.value.indexOf(before) ? -1 : 1
})

// One underline for the scope tabs, slid to the selected tab (transform only).
const scopeEl = ref<HTMLElement | null>(null)
const ink = ref<Record<string, string>>({ opacity: '0' })
async function placeInk() {
  await nextTick()
  const tab = scopeEl.value?.querySelector<HTMLElement>('[aria-selected="true"]')
  if (!tab) return
  ink.value = { width: `${tab.offsetWidth}px`, transform: `translateX(${tab.offsetLeft}px)` }
}
watch(scope, placeInk)
onMounted(() => {
  void placeInk()
  void document.fonts?.ready.then(placeInk)
})

function onChanged(r: OrderRequest) {
  void list.reload()
  if (!WAITING.includes(r.status)) waiting.value = waiting.value.filter((w) => w.id !== r.id)
}
</script>

<template>
  <div class="requests-page">
    <div class="band">
      <div class="band-in">
        <h1 class="band-title">Orders</h1>
        <div ref="scopeEl" class="scope" role="tablist" aria-label="Whose requests">
          <span class="scope-ink" aria-hidden="true" :style="ink" />
          <button
            v-for="s in [{ v: 'mine', t: 'Mine' }, { v: 'organisation', t: 'My organisation' }] as const"
            :key="s.v"
            type="button"
            role="tab"
            class="scope-tab"
            :aria-selected="scope === s.v"
            @click="scope = s.v"
          >
            {{ s.t }}
          </button>
        </div>
      </div>
    </div>

    <div class="docket" :class="{ wide }">
      <nav class="list" aria-label="Orders">
        <div v-if="canFilter" class="filters">
          
          <v-select v-model="statusKey" :items="STATUS_GROUPS" label="Status" density="compact" hide-details class="filter" />
          <v-select
            v-model="year"
            :items="[{ title: 'Any year', value: null }, ...years.map((y) => ({ title: String(y), value: y }))]"
            label="Year"
            density="compact"
            hide-details
            class="filter year"
          />
        </div>

        <section v-if="showWaiting" class="group yours" aria-labelledby="g-waiting">
          <h2 id="g-waiting" class="group-title">Waiting for you <span class="count">{{ waiting.length }}</span></h2>
          <TransitionGroup tag="ul" name="row" :appear="rowsAppear" class="rows">
            <li v-for="(r, i) in waiting" :key="r.id" :style="{ '--i': Math.min(i, 7) }">
              <router-link :to="rowLink(r)" class="row" :class="{ open: r.id === openId }" :aria-current="r.id === openId ? 'true' : undefined">
                <span class="row-main">
                  <span class="row-title">{{ title(r) }}</span>
                  <span class="row-meta">
                    <strong>{{ customerActionNeeded(r) }}</strong>
                    <template v-if="r.quoteExpiresAt">
                      · valid until {{ formatDate(r.quoteExpiresAt) }}
                      <span :class="{ soon: expiryNote(r.quoteExpiresAt)?.soon }">
                        <v-icon v-if="expiryNote(r.quoteExpiresAt)?.soon" :icon="mdiAlertOutline" size="14" />
                        ({{ expiryNote(r.quoteExpiresAt)?.text }})
                      </span>
                    </template>
                  </span>
                  <span class="row-ref t-mono"><ShortRef :id="r.id" fit /></span>
                </span>
                <v-icon :icon="mdiChevronRight" size="18" class="row-go" />
              </router-link>
            </li>
          </TransitionGroup>
        </section>

        <v-skeleton-loader v-if="list.loading.value && !list.loaded.value" type="list-item-three-line@4" />
        <template v-else-if="list.loaded.value && !rows.length">
          <div v-if="filtered" class="empty">
            <h2 class="t-h3">No requests match these filters</h2>
            <p class="muted">{{ paymentFilter ? 'No delivered request is waiting for a payment.' : 'Try another status or year.' }}</p>
            <v-btn variant="outlined" @click="clearFilters">Clear filters</v-btn>
          </div>
          <p v-else-if="showWaiting" class="muted none">No other requests.</p>
          <div v-else-if="scope === 'organisation'" class="empty">
            <h2 class="t-h3">No requests from your organisation yet</h2>
            <p class="muted">Requests sent by colleagues in your organisation appear here. You can read them; only the requester can act on them.</p>
          </div>
          <div v-else class="empty">
            <v-icon :icon="mdiClipboardTextOutline" size="40" class="muted" />
            <h2 class="t-h3">No requests yet</h2>
            <p class="muted">Add items from the catalogue to your cart and send it as a request. CIMH replies with a quote, and you follow every step here.</p>
            <v-btn to="/catalogue" color="primary">Browse the catalogue</v-btn>
          </div>
        </template>
        <template v-else>
          <section v-for="g in groups" :key="g.key" class="group" :aria-labelledby="`g-${g.key}`">
            <h2 :id="`g-${g.key}`" class="group-title">{{ g.title }} <span class="count">{{ g.rows.length }}</span></h2>
            <TransitionGroup tag="ul" name="row" :appear="rowsAppear" class="rows">
              <li v-for="(r, i) in g.rows" :key="r.id" :style="{ '--i': Math.min(i, 7) }">
                <router-link :to="rowLink(r)" class="row" :class="{ open: r.id === openId, closed: isClosed(r.status) }" :aria-current="r.id === openId ? 'true' : undefined">
                  <span class="row-main">
                    <span class="row-title">
                      <span class="row-title-text">{{ title(r) }}</span>
                      <span v-if="r.type === 'PROBONO' || paymentDue(r)" class="row-badges">
                        <span v-if="r.type === 'PROBONO'" class="probono-badge">Pro Bono</span>
                        <span v-if="paymentDue(r)" class="pay-badge">Payment required</span>
                      </span>
                    </span>
                    <span class="row-meta">
                      {{ stateText(r) }} · sent {{ formatDate(r.submittedAt) }}
                      <template v-if="scope === 'organisation'"> · {{ r.customerName }}</template>
                    </span>
                    <span class="row-ref t-mono"><ShortRef :id="r.id" fit /></span>
                  </span>
                  <v-icon :icon="mdiChevronRight" size="18" class="row-go" />
                </router-link>
              </li>
            </TransitionGroup>
          </section>
        </template>
        <div v-if="list.nextCursor.value" class="more">
          <v-btn variant="outlined" :loading="list.loading.value" @click="list.loadMore">Load more</v-btn>
        </div>
      </nav>

      <section v-if="wide" class="detail" aria-label="Open request">
        <RequestSheet v-if="openId" :id="openId" :level="2" :dir="dir" @changed="onChanged" />
        <p v-else-if="list.loaded.value" class="muted pick">Choose a request to see it here.</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
/* ---- the band: the SHOP navy field with the logo-blue rule (home masthead, cart) */
.band {
  background: #0a2e4a;
  color: #fff;
  border-bottom: 4px solid #0084c8;
}
.band-in {
  max-width: 1440px;
  margin: 0 auto;
  padding: var(--sp-6) var(--sp-10, 40px) 0;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--sp-4) var(--sp-8);
  flex-wrap: wrap;
}
.band-title {
  margin: 0 0 var(--sp-5, 20px);
  font-size: clamp(26px, 2vw + 14px, 34px);
  line-height: 1.15;
  font-weight: 700;
  letter-spacing: -0.015em;
}
.scope {
  position: relative;
  display: flex;
  gap: var(--sp-6);
}
/* The sliding underline (the selected tab's own border stays transparent while the ink is placed). */
.scope-ink {
  position: absolute;
  left: 0;
  bottom: 0;
  height: 3px;
  border-radius: 2px 2px 0 0;
  background: #5cc2ff;
  pointer-events: none;
  transition: transform 300ms cubic-bezier(0.16, 1, 0.3, 1), width 300ms cubic-bezier(0.16, 1, 0.3, 1), opacity 160ms ease-out;
}
.scope-tab {
  background: none;
  border: 0;
  color: rgb(255 255 255 / 0.72);
  font: inherit;
  font-size: 15px;
  font-weight: 600;
  padding: var(--sp-3) 0;
  min-height: 44px;
  border-bottom: 3px solid transparent;
  cursor: pointer;
  transition: color 160ms ease-out, border-color 200ms ease-out;
}
.scope-tab:hover {
  color: #fff;
}
.scope-tab[aria-selected='true'] {
  color: #fff;
}
.scope-tab:focus-visible {
  outline: 2px solid #5cc2ff;
  outline-offset: 2px;
  border-radius: 2px;
}

/* ---- the docket: list beside the open request */
.docket {
  max-width: 1440px;
  margin: 0 auto;
}
.docket.wide {
  display: grid;
  grid-template-columns: minmax(360px, 420px) minmax(0, 1fr);
  min-height: calc(100vh - 180px);
}
.list {
  padding: var(--sp-4) var(--sp-4) var(--sp-8);
}
.wide .list {
  padding: var(--sp-4) 0 var(--sp-8);
  position: sticky;
  top: 64px;
  align-self: start;
  max-height: calc(100vh - 64px);
  overflow-y: auto;
  overscroll-behavior: contain;
}
.detail {
  border-left: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding: var(--sp-8) var(--sp-10, 40px) var(--sp-12);
  min-width: 0;
}
.pick {
  margin-top: var(--sp-8);
}

.filters {
  display: flex;
  gap: var(--sp-3);
  padding: 0 var(--sp-6) var(--sp-3);
}
.filter {
  flex: 1 1 0;
  min-width: 0;
}
.filter.year {
  flex: 0 0 132px;
}

.group + .group,
.group.yours + .group,
.yours + .v-skeleton-loader {
  margin-top: var(--sp-2);
}
.group-title {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin: 0;
  padding: var(--sp-4) var(--sp-6) var(--sp-2);
  font-size: 13px;
  line-height: 18px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.yours .group-title {
  color: rgb(var(--v-theme-primary));
}
.count {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  min-width: 20px;
  padding: 0 6px;
  border-radius: 10px;
  text-align: center;
  background: rgba(var(--v-theme-on-surface), 0.07);
  color: rgb(var(--v-theme-on-surface));
}
.yours .count {
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}
.rows {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.rows li {
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4) var(--sp-3) var(--sp-6);
  color: inherit;
  text-decoration: none;
  transition: background-color 140ms ease-out, transform 160ms cubic-bezier(0.16, 1, 0.3, 1);
}
.row:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.row:active {
  transform: scale(0.99);
  transition-duration: 80ms;
}
/* Rows arrive as a list (stagger capped at 8 × 35 ms); leaving rows just fade, fast. */
.row-enter-active {
  transition: opacity 260ms ease-out, transform 320ms cubic-bezier(0.16, 1, 0.3, 1);
  transition-delay: calc(var(--i, 0) * 35ms);
}
.row-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.row-leave-active {
  transition: opacity 120ms ease-in;
}
.row-leave-to {
  opacity: 0;
}
.row-move {
  transition: transform 280ms cubic-bezier(0.16, 1, 0.3, 1);
}
.row:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.row.open {
  background: rgba(var(--v-theme-primary), 0.1);
}
.row.open .row-title {
  color: rgb(var(--v-theme-primary));
}
.row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.row-title {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-2);
  font-size: 15px;
  line-height: 22px;
  font-weight: 600;
}
.row-title-text {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
/* Badges sit together at the right edge of the title line (owner 2026-11-25). */
.row-badges {
  flex: none;
  display: flex;
  gap: var(--sp-1);
  padding-top: 1px;
}
.pay-badge {
  display: inline-block;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 20px;
  font-weight: 600;
  vertical-align: 1px;
  white-space: nowrap;
  background: rgba(var(--v-theme-warning), 0.16);
  color: rgb(var(--v-theme-on-surface));
  border: 1px solid rgba(var(--v-theme-warning), 0.6);
}
.row.closed .row-title {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.row-meta {
  font-size: 14px;
  line-height: 20px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.row-meta strong {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 600;
}
.row-ref {
  font-size: 12px;
  line-height: 16px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.row-go {
  flex: none;
  opacity: 0.5;
  transition: transform 160ms ease-out, opacity 160ms ease-out;
}
.row:hover .row-go,
.row.open .row-go {
  opacity: 1;
  transform: translateX(2px);
}
.soon {
  color: rgb(var(--v-theme-error));
  font-weight: 600;
  white-space: nowrap;
}

.empty {
  margin: var(--sp-4) var(--sp-6);
  padding: var(--sp-10, 40px) var(--sp-4);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-3);
  text-align: center;
}
.empty p {
  max-width: 48ch;
  margin: 0;
}
.none {
  margin: var(--sp-4) var(--sp-6);
}
.more {
  display: flex;
  justify-content: center;
  margin: var(--sp-4) 0;
}

/* Narrow: one column of rows edge to edge, the request opens on its own page. */
@media (max-width: 1099.98px) {
  .band-in {
    padding: var(--sp-5, 20px) var(--sp-4) 0;
  }
  .list {
    max-width: 760px;
    margin: 0 auto;
    padding-inline: 0;
  }
  .filters {
    padding: 0 var(--sp-4) var(--sp-3);
  }
  .group-title,
  .row {
    padding-left: var(--sp-4);
  }
  .list {
    padding-bottom: 120px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .row,
  .row-go,
  .row-move,
  .scope-ink {
    transition: none;
  }
  .row:active {
    transform: none;
  }
  .row-enter-active {
    transition: opacity 200ms ease-out;
  }
  .row-enter-from {
    transform: none;
  }
}
</style>
