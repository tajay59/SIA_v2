<script setup lang="ts">
/**
 * S-10 My requests. Top: "Waiting for you" (own requests with a quote to review or an agreement to sign,
 * soonest expiry first, with the expiry date), shown while no status or year filter is set. Then the filters
 * (Mine / My organisation, status, year) and one list. Rows are named by what was requested ("Aneroid
 * barometer and 2 more"); the id is a small reference under it. "Load more" paging. An empty result with
 * filters set offers Clear filters; without filters it explains how a request starts.
 */
import {
  call,
  customerActionNeeded,
  expiryNote,
  orders,
  type RequestStatus,
  type RequestSummary,
  requestTitle,
  shortRef,
  StatusChip,
  useCursorList,
  useNotify,
} from '@cimh/web-app'
import { formatDate } from '@cimh/web-ui'
import { mdiAlertOutline, mdiChevronRight, mdiClipboardTextOutline, mdiGiftOutline, mdiPackageVariant } from '@mdi/js'
import { computed, onMounted, ref, watch } from 'vue'

definePage({ meta: { guard: 'customer', title: 'My requests' } })
const notify = useNotify()

const scope = ref<'mine' | 'organisation'>('mine')
const thisYear = new Date().getFullYear()
const years = Array.from({ length: thisYear - 2019 }, (_, i) => thisYear - i)
const year = ref<number | null>(null)
const WAITING: RequestStatus[] = ['QUOTED', 'AWAITING_AGREEMENT']
const STATUS_GROUPS: { title: string; value: RequestStatus[] | null }[] = [
  { title: 'All statuses', value: null },
  { title: 'Waiting for me', value: WAITING },
  { title: 'In progress', value: ['SUBMITTED', 'QUOTING', 'ACCEPTED', 'PURCHASING', 'APPROVED', 'PICKING', 'SHIPPED'] },
  { title: 'Delivered', value: ['DELIVERED'] },
  { title: 'Closed', value: ['CANCELLED', 'REJECTED', 'DECLINED'] },
]
const status = ref<RequestStatus[] | null>(null)
const filtered = computed(() => !!status.value || !!year.value)
function clearFilters() {
  status.value = null
  year.value = null
}

type Page = { items: RequestSummary[]; nextCursor: string | null }
const list = useCursorList<RequestSummary>(async (cursor) => {
  const query: Record<string, unknown> = { scope: scope.value, limit: 25, sort: 'newest' }
  if (cursor) query.cursor = cursor
  if (year.value) query.year = year.value
  if (status.value) query.status = status.value.join(',')
  return (await call(() => orders.GET('/requests', { params: { query: query as any } }))) as Page
})
watch([scope, year, status], () => void list.reload(), { immediate: true })

// Own requests that wait for the customer; a separate query, so they lead the page whatever the paging.
const waiting = ref<RequestSummary[]>([])
onMounted(async () => {
  try {
    const query = { scope: 'mine', status: WAITING.join(','), limit: 25, sort: 'newest' }
    const page = (await call(() => orders.GET('/requests', { params: { query: query as any } }))) as Page
    waiting.value = [...page.items].sort((a, b) => (a.quoteExpiresAt ?? '9').localeCompare(b.quoteExpiresAt ?? '9'))
  } catch (e) {
    notify.report(e)
  }
})
const showWaiting = computed(() => scope.value === 'mine' && !filtered.value && waiting.value.length > 0)
const waitingIds = computed(() => new Set(showWaiting.value ? waiting.value.map((r) => r.id) : []))
const rows = computed(() => list.items.value.filter((r) => !waitingIds.value.has(r.id)))
// Status/Year only once there is something to narrow (or a filter is set, so it can be changed back).
const canFilter = computed(() => filtered.value || list.items.value.length > 0 || !!list.nextCursor.value)

const title = (r: RequestSummary) => requestTitle(r.firstItemName, r.lineCount, r.type)
const nextStep = (r: RequestSummary) => (r.status === 'QUOTED' ? 'Review the quote' : 'Sign the agreement')
</script>

<template>
  <v-container class="page" max-width="1200">
    <div class="page-header"><h1 class="t-h1">My requests</h1></div>

    <section v-if="showWaiting" class="waiting" aria-labelledby="waiting-title">
      <h2 id="waiting-title" class="t-h3">Waiting for you</h2>
      <ul class="rows">
        <li v-for="r in waiting" :key="r.id">
          <router-link :to="`/requests/${r.id}`" class="req">
            <span class="req-main">
              <span class="req-title">{{ title(r) }}</span>
              <span class="req-meta">
                <strong>{{ customerActionNeeded(r) }}</strong>
                <template v-if="r.quoteExpiresAt">
                  · valid until {{ formatDate(r.quoteExpiresAt) }}
                  <span :class="{ soon: expiryNote(r.quoteExpiresAt)?.soon }">
                    <v-icon v-if="expiryNote(r.quoteExpiresAt)?.soon" :icon="mdiAlertOutline" size="14" />
                    ({{ expiryNote(r.quoteExpiresAt)?.text }})
                  </span>
                </template>
              </span>
              <span class="req-id t-mono" :title="r.id">{{ shortRef(r.id) }}</span>
            </span>
            <span class="req-next">{{ nextStep(r) }}<v-icon :icon="mdiChevronRight" size="18" /></span>
          </router-link>
        </li>
      </ul>
    </section>

    <div class="filters">
      <v-chip-group v-model="scope" mandatory selected-class="text-primary" aria-label="Whose requests">
        <v-chip value="mine" variant="outlined" filter>Mine</v-chip>
        <v-chip value="organisation" variant="outlined" filter>My organisation</v-chip>
      </v-chip-group>
      <template v-if="canFilter">
      <v-select v-model="status" :items="STATUS_GROUPS" label="Status" density="compact" hide-details class="filter" />
      <v-select v-model="year" :items="[{ title: 'Any year', value: null }, ...years.map((y) => ({ title: String(y), value: y }))]"
                label="Year" density="compact" hide-details class="filter year" />
      </template>
    </div>

    <v-skeleton-loader v-if="list.loading.value && !list.loaded.value" type="list-item-avatar-three-line@4" />
    <template v-else-if="list.loaded.value && !rows.length">
      <div v-if="filtered" class="empty">
        <h2 class="t-h3">No requests match these filters</h2>
        <p class="t-body muted">Try another status or year.</p>
        <v-btn variant="outlined" @click="clearFilters">Clear filters</v-btn>
      </div>
      <p v-else-if="showWaiting" class="t-body muted none">No other requests.</p>
      <div v-else-if="scope === 'organisation'" class="empty">
        <h2 class="t-h3">No requests from your organisation yet</h2>
        <p class="t-body muted">Requests sent by colleagues in your organisation appear here. You can read them; only the requester can act on them.</p>
      </div>
      <div v-else class="empty">
        <v-icon :icon="mdiClipboardTextOutline" size="40" class="muted" />
        <h2 class="t-h3">No requests yet</h2>
        <p class="t-body muted">Add items from the catalogue to your cart and send it as a request. CIMH replies with a quote, and you follow every step here.</p>
        <v-btn to="/catalogue" color="primary">Browse the catalogue</v-btn>
      </div>
    </template>
    <ul v-else class="rows list">
      <li v-for="r in rows" :key="r.id">
        <router-link :to="`/requests/${r.id}`" class="req">
          <span class="req-icon" :class="{ probono: r.type === 'PROBONO' }">
            <v-icon :icon="r.type === 'PROBONO' ? mdiGiftOutline : mdiPackageVariant" size="20" />
          </span>
          <span class="req-main">
            <span class="req-title">{{ title(r) }}</span>
            <span class="req-meta">
              {{ formatDate(r.submittedAt) }} · {{ r.lineCount }} {{ r.lineCount === 1 ? 'item' : 'items' }}
              <template v-if="scope === 'organisation'"> · {{ r.customerName }}</template>
              <template v-if="r.type === 'PROBONO'"> · Pro Bono</template>
            </span>
            <span class="req-id t-mono" :title="r.id">{{ shortRef(r.id) }}</span>
          </span>
          <span class="req-right">
            <StatusChip :status="r.status" />
            <span v-if="customerActionNeeded(r)" class="t-caption req-flag">{{ customerActionNeeded(r) }}</span>
          </span>
        </router-link>
      </li>
    </ul>
    <div v-if="list.nextCursor.value" class="more">
      <v-btn variant="outlined" :loading="list.loading.value" @click="list.loadMore">Load more</v-btn>
    </div>
  </v-container>
</template>

<style scoped>
.page-header {
  margin-bottom: var(--sp-4);
}
.rows {
  list-style: none;
  margin: 0;
  padding: 0;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
  overflow: hidden;
}
.rows li + li {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.req {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4);
  color: inherit;
  text-decoration: none;
}
.req:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.req:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.req-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.req-title {
  font-size: 16px;
  line-height: 24px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.req-meta {
  font-size: 14px;
  line-height: 22px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.req-meta strong {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 600;
}
.req-id {
  font-size: 12px;
  line-height: 16px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  overflow-wrap: anywhere;
}
.soon {
  color: rgb(var(--v-theme-error));
  font-weight: 600;
  white-space: nowrap;
}
.req-icon {
  flex: none;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: rgb(var(--v-theme-surface-variant));
}
.req-icon.probono {
  background: rgb(var(--v-theme-accent-probono));
  color: var(--probono-ink);
}
.req-right {
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--sp-1);
}
.req-flag {
  font-weight: 600;
}

/* Waiting for you: the same rows, led by a primary rule and ending in the next step. */
.waiting {
  margin-bottom: var(--sp-8);
}
.waiting h2 {
  margin-bottom: var(--sp-3);
}
.waiting .rows {
  border-color: rgb(var(--v-theme-primary));
}
.req-next {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 14px;
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
}
@media (max-width: 599px) {
  .req {
    flex-wrap: wrap;
  }
  .req-icon {
    display: none;
  }
  .req-main {
    flex-basis: 100%;
  }
  .req-right {
    flex-direction: row;
    align-items: center;
    gap: var(--sp-2);
  }
}

.filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-3);
  margin: 0 0 var(--sp-4);
}
.filter {
  max-width: 220px;
}
.filter.year {
  max-width: 150px;
}
.empty {
  padding: var(--sp-12) var(--sp-6);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-3);
  text-align: center;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
}
.empty p {
  max-width: 56ch;
  margin: 0;
}
.none {
  margin: 0;
}
.more {
  display: flex;
  justify-content: center;
  margin: var(--sp-4) 0;
}
</style>
