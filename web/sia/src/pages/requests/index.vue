<script setup lang="ts">
/**
 * A-02 request desk (legacy SIA Orders: one list of every order). Filters: status (several), type, year,
 * organisation, search (request id or customer/organisation name); sort newest, oldest or waiting longest.
 * Columns: id, customer, organisation, type, status, days waiting, quote expiry. Filters live in the URL so
 * dashboard counters (A-01) open the desk pre-filtered.
 */
import { call, orders, type RequestStatus, type RequestSummary, StatusChip, useCursorList } from '@cimh/web-app'
import { formatDate, statusLabel } from '@cimh/web-ui'
import { mdiMagnify } from '@mdi/js'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

definePage({ meta: { guard: 'staff', title: 'Requests' } })
const route = useRoute()
const router = useRouter()

const ALL: RequestStatus[] = ['SUBMITTED', 'QUOTING', 'QUOTED', 'AWAITING_AGREEMENT', 'ACCEPTED', 'PURCHASING', 'APPROVED',
  'PICKING', 'SHIPPED', 'DELIVERED', 'DECLINED', 'REJECTED', 'CANCELLED']  // prettier-ignore
const OPEN: RequestStatus[] = ALL.filter((s) => !['DELIVERED', 'DECLINED', 'REJECTED', 'CANCELLED'].includes(s))
const q1 = (k: string) => (typeof route.query[k] === 'string' ? (route.query[k] as string) : '')
const status = ref<RequestStatus[]>(q1('status') ? (q1('status').split(',') as RequestStatus[]) : OPEN)
const type = ref<'PAID' | 'PROBONO' | null>((q1('type') as 'PAID' | 'PROBONO') || null)
const thisYear = new Date().getFullYear()
const years = Array.from({ length: thisYear - 2019 }, (_, i) => thisYear - i)
const year = ref<number | null>(q1('year') ? Number(q1('year')) : null)
const q = ref(q1('q'))
const sort = ref<'newest' | 'oldest' | 'waiting'>((q1('sort') as 'newest') || 'waiting')

const list = useCursorList<RequestSummary>((cursor) =>
  call(() =>
    orders.GET('/requests', {
      params: {
        query: {
          scope: 'all',
          status: status.value.length ? status.value.join(',') : undefined,
          type: type.value ?? undefined,
          year: year.value ?? undefined,
          q: q.value.trim() || undefined,
          sort: sort.value,
          cursor,
          limit: 50,
        } as any,
      },
    }),
  ) as Promise<{ items: RequestSummary[]; nextCursor: string | null }>,
)
onMounted(list.reload)

let timer: ReturnType<typeof setTimeout> | undefined
// A pending debounce must not fire after the page is left (router.replace would navigate back here).
onBeforeUnmount(() => clearTimeout(timer))
watch([status, type, year, q, sort], () => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    const query: Record<string, string> = { status: status.value.join(','), sort: sort.value }
    if (type.value) query.type = type.value
    if (year.value) query.year = String(year.value)
    if (q.value.trim()) query.q = q.value.trim()
    void router.replace({ query })
    void list.reload()
  }, 250)
})
const expiresSoon = (r: RequestSummary) =>
  !!r.quoteExpiresAt && Date.parse(r.quoteExpiresAt) - Date.now() < 3 * 86_400_000
</script>

<template>
  <div class="page stack-md">
    <div class="filters">
      <v-text-field v-model="q" :prepend-inner-icon="mdiMagnify" label="Request id, customer or organisation" hide-details class="search" clearable />
      <v-select v-model="status" :items="ALL.map((s) => ({ title: statusLabel(s), value: s }))" label="Status" multiple chips hide-details class="status" />
      <v-select v-model="type" :items="[{ title: 'Any type', value: null }, { title: 'Paid', value: 'PAID' }, { title: 'Pro Bono', value: 'PROBONO' }]" label="Type" hide-details class="small" />
      <v-select v-model="year" :items="[{ title: 'Any year', value: null }, ...years.map((y) => ({ title: String(y), value: y }))]" label="Year" hide-details class="small" />
      <v-select v-model="sort" :items="[{ title: 'Waiting longest', value: 'waiting' }, { title: 'Newest', value: 'newest' }, { title: 'Oldest', value: 'oldest' }]" label="Sort" hide-details class="small" />
    </div>

    <v-card border flat>
      <v-table v-scroll-region="'Requests'" hover>
        <thead>
          <tr>
            <th>Request</th>
            <th>Customer</th>
            <th>Organisation</th>
            <th>Type</th>
            <th>Status</th>
            <th class="num">Waiting</th>
            <th>Quote expires</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in list.items.value" :key="r.id" class="row" @click="router.push(`/requests/${r.id}`)">
            <td><router-link :to="`/requests/${r.id}`" class="t-mono id" @click.stop>{{ r.id.slice(0, 15) }}…</router-link></td>
            <td>{{ r.customerName }}</td>
            <td>{{ r.organisationName ?? '—' }}</td>
            <td>{{ r.type === 'PROBONO' ? 'Pro Bono' : 'Paid' }}</td>
            <td><StatusChip :status="r.status" /></td>
            <td class="num tnum" :class="{ 'text-warning': (r.waitingDays ?? 0) > 5 }">{{ r.waitingDays ?? 0 }} d</td>
            <td :class="{ 'text-error': expiresSoon(r) }">{{ r.quoteExpiresAt ? formatDate(r.quoteExpiresAt) : '' }}</td>
          </tr>
          <tr v-if="list.loaded.value && !list.items.value.length">
            <td colspan="7" class="muted empty">No requests match these filters.</td>
          </tr>
        </tbody>
      </v-table>
      <v-progress-linear v-if="list.loading.value" indeterminate />
    </v-card>
    <div v-if="list.nextCursor.value" class="more">
      <v-btn variant="outlined" :loading="list.loading.value" @click="list.loadMore">Load more</v-btn>
    </div>
  </div>
</template>

<style scoped>
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-3);
}
.search {
  flex: 1 1 280px;
}
.status {
  flex: 2 1 320px;
}
.small {
  flex: 0 1 170px;
}
.row {
  cursor: pointer;
}
.id {
  color: inherit;
}
.num {
  text-align: right;
}
.empty {
  text-align: center;
  padding: var(--sp-8) 0;
}
.more {
  display: flex;
  justify-content: center;
}
</style>
