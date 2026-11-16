<script setup lang="ts">
/**
 * A-02 request desk, Graphite Console (surface brief web/sia): the dashboard's queue + detail panels for every
 * request. Stage tabs with counts (the same stages as the dashboard strip, plus Shipped, Closed, All) pick
 * the statuses; search and "More filters" (statuses, type, year, organisation, sort) refine; staff act in the
 * detail panel without leaving the list. The URL is the only filter state: tabs, filters and dashboard links
 * all change the query, and the list follows it (also when already on this page). Phones: tap opens.
 */
import { call, type Organisation, orders, type RequestStatus, type RequestSummary, useCursorList } from '@cimh/web-app'
import { statusLabel } from '@cimh/web-ui'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { type LocationQuery, useRoute, useRouter } from 'vue-router'
import OrganisationPicker from '../../components/OrganisationPicker.vue'
import RequestDetail from '../../components/RequestDetail.vue'
import RequestView from '../../components/RequestView.vue'
import RequestQueue from '../../components/RequestQueue.vue'
import { ALL_STATUS, BTN, CLOSED_STATUS, OPEN_STATUS } from '../../request-queue'
import { type CountKey, countLabel, useWorkCounts } from '../../work-counts'

definePage({ meta: { guard: 'staff', title: 'Requests' } })
const route = useRoute()
const router = useRouter()
const { counts, refresh: refreshCounts } = useWorkCounts()

// ---- filters <-> URL (validated; unknown values are dropped, never sent)
type Sort = 'waiting' | 'newest' | 'oldest'
type Filters = {
  status: RequestStatus[]
  type: 'PAID' | 'PROBONO' | null
  year: number | null
  org: string | null
  orgName: string
  q: string
  sort: Sort
}
const thisYear = new Date().getFullYear()
const years = Array.from({ length: thisYear - 2019 }, (_, i) => thisYear - i)
const str = (q: LocationQuery, k: string) => (typeof q[k] === 'string' ? (q[k] as string) : '')

function parse(q: LocationQuery): Filters {
  const raw = str(q, 'status')
  const picked = raw === 'all' ? ALL_STATUS : raw.split(',').filter((s): s is RequestStatus => ALL_STATUS.includes(s as RequestStatus))
  const type = str(q, 'type')
  const year = Number(str(q, 'year'))
  const sort = str(q, 'sort')
  return {
    status: picked.length ? picked : OPEN_STATUS,
    type: type === 'PAID' || type === 'PROBONO' ? type : null,
    year: years.includes(year) ? year : null,
    org: str(q, 'org') || null,
    orgName: str(q, 'orgName'),
    q: str(q, 'q').slice(0, 100),
    sort: sort === 'newest' || sort === 'oldest' ? sort : 'waiting',
  }
}
const same = (a: RequestStatus[], b: RequestStatus[]) => a.length === b.length && a.every((s) => b.includes(s))
function serialize(f: Filters): Record<string, string> {
  const out: Record<string, string> = {}
  if (same(f.status, ALL_STATUS)) out.status = 'all'
  else if (!same(f.status, OPEN_STATUS)) out.status = f.status.join(',')
  if (f.type) out.type = f.type
  if (f.year) out.year = String(f.year)
  if (f.org) {
    out.org = f.org
    if (f.orgName) out.orgName = f.orgName
  }
  if (f.q.trim()) out.q = f.q.trim()
  if (f.sort !== 'waiting') out.sort = f.sort
  return out
}
const onDesk = () => route.path === '/requests' || route.path === '/requests/'
const filters = computed(() => parse(route.query))
// `open` (a request shown beside the list) is not a filter: keep it when filters change.
const keepOpen = (q: Record<string, string>) => (str(route.query, 'open') ? { ...q, open: str(route.query, 'open') } : q)
const update = (patch: Partial<Filters>) => void router.replace({ query: keepOpen(serialize({ ...filters.value, ...patch })) })

// ---- stage tabs: the dashboard's stages + Shipped, Closed, All
const TABS: { key: string; title: string; status: RequestStatus[]; count?: CountKey }[] = [
  { key: 'open', title: 'Open', status: OPEN_STATUS },
  { key: 'new', title: 'New', status: ['SUBMITTED'], count: 'new' },
  { key: 'quoting', title: 'Quoting', status: ['QUOTING'], count: 'quoting' },
  { key: 'quoted', title: 'Quoted', status: ['QUOTED'], count: 'quoted' },
  { key: 'signature', title: 'Awaiting signature', status: ['AWAITING_AGREEMENT'], count: 'signature' },
  { key: 'verify', title: 'To verify', status: ['ACCEPTED'], count: 'verify' },
  { key: 'fulfil', title: 'Pick & purchase', status: ['APPROVED', 'PICKING', 'PURCHASING'], count: 'fulfil' },
  { key: 'shipped', title: 'Shipped', status: ['SHIPPED'] },
  { key: 'closed', title: 'Closed', status: CLOSED_STATUS },
  { key: 'all', title: 'All', status: ALL_STATUS },
]
const activeTab = computed(() => TABS.find((t) => same(t.status, filters.value.status))?.key ?? null)
const tabTo = (t: (typeof TABS)[number]) => ({ query: keepOpen(serialize({ ...filters.value, status: t.status })) })

// ---- search (debounced into the URL; follows the URL when it changes elsewhere)
const search = ref(filters.value.q)
let timer: ReturnType<typeof setTimeout> | undefined
// A pending debounce must not fire after the page is left (router.replace would navigate back here).
onBeforeUnmount(() => clearTimeout(timer))
watch(search, (v) => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    if (onDesk() && (v ?? '').trim() !== filters.value.q) update({ q: v ?? '' })
  }, 250)
})
watch(
  () => filters.value.q,
  (q) => {
    if (q !== (search.value ?? '').trim()) search.value = q
  },
)

// ---- more filters
const moreOpen = ref(false)
const extraCount = computed(
  () =>
    [filters.value.type, filters.value.year, filters.value.org, filters.value.sort !== 'waiting' || null, activeTab.value ? null : 1].filter(
      Boolean,
    ).length,
)
const statusModel = computed({
  get: () => filters.value.status,
  set: (v: RequestStatus[]) => update({ status: v.length ? v : ALL_STATUS }),
})
const orgModel = computed<Organisation | null>({
  get: () => (filters.value.org ? ({ id: filters.value.org, name: filters.value.orgName } as Organisation) : null),
  set: (o) => update({ org: o?.id ?? null, orgName: o?.name ?? '' }),
})
const filtered = computed(() => Object.keys(serialize(filters.value)).length > 0)
function clearFilters() {
  search.value = ''
  void router.replace({ query: {} })
}

// ---- list (re-fetched whenever the filters in the URL change)
const list = useCursorList<RequestSummary>((cursor) =>
  call(() =>
    orders.GET('/requests', {
      params: {
        query: {
          scope: 'all',
          status: filters.value.status.join(','),
          type: filters.value.type ?? undefined,
          year: filters.value.year ?? undefined,
          organisationId: filters.value.org ?? undefined,
          q: filters.value.q.trim() || undefined,
          sort: filters.value.sort,
          cursor,
          limit: 50,
        } as never,
      },
    }),
  ) as Promise<{ items: RequestSummary[]; nextCursor: string | null }>,
)
const loadedAt = ref<Date | null>(null)
async function reload() {
  await list.reload()
  loadedAt.value = new Date()
}
onMounted(reload)
watch(
  () => JSON.stringify(serialize(filters.value)),
  () => {
    if (onDesk()) void reload()
  },
)
function refreshAll() {
  void reload()
  void refreshCounts()
}

const items = computed(() => (list.loaded.value ? list.items.value : null))
const selectedId = ref<string | null>(null)
const selected = computed(() => items.value?.find((r) => r.id === selectedId.value) ?? null)
watch(items, (rows) => {
  if (rows && !rows.some((r) => r.id === selectedId.value)) selectedId.value = rows[0]?.id ?? null
})

// ---- A-03 beside the list (`?open=<id>`): the queue narrows, the full request takes the rest.
const openId = computed(() => str(route.query, 'open') || null)
const openIn = (id: string) => ({ query: { ...route.query, open: id } })
const queueSelected = computed<string | null>({
  get: () => openId.value ?? selectedId.value,
  set: (id) => {
    if (openId.value && id) void router.replace(openIn(id))
    else selectedId.value = id
  },
})
// Which way the open request moved in the queue: the next one slides up from below, the previous from above.
const direction = ref<'next' | 'prev' | 'none'>('none')
watch(openId, (now, before) => {
  const rows = items.value ?? []
  const a = rows.findIndex((x) => x.id === before)
  const b = rows.findIndex((x) => x.id === now)
  direction.value = a < 0 || b < 0 ? 'none' : b > a ? 'next' : 'prev'
})
function closeOpen() {
  selectedId.value = openId.value
  const q = { ...route.query }
  delete q.open
  void router.replace({ query: q })
}

const SORT_WORDS: Record<Sort, string> = { waiting: 'longest wait first', newest: 'newest first', oldest: 'oldest first' }
const caption = computed(() => {
  if (!items.value) return ''
  const n = `${items.value.length}${list.nextCursor.value ? '+' : ''}`
  return `${n} · ${SORT_WORDS[filters.value.sort]}`
})
const time = computed(() =>
  loadedAt.value ? loadedAt.value.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : '',
)
</script>

<template>
  <div class="desk">
    <div class="toolbar">
      <v-text-field
        v-model="search"
        data-page-search
        :prepend-inner-icon="BTN.search"
        label="Request id, customer or organisation"
        hide-details
        clearable
        density="compact"
        class="search"
      />
      <v-btn
        variant="outlined"
        class="m3"
        :prepend-icon="BTN.filter"
        :append-icon="BTN.more"
        :aria-expanded="moreOpen"
        aria-controls="more-filters"
        :class="{ open: moreOpen }"
        @click="moreOpen = !moreOpen"
      >
        More filters<span v-if="extraCount" class="badge console-mono">{{ extraCount }}</span>
      </v-btn>
      <span class="updated">
        <span v-if="time" class="t-caption muted">Updated {{ time }}</span>
        <v-btn variant="text" size="small" :icon="BTN.retry" :loading="list.loading.value" aria-label="Refresh requests and counts" @click="refreshAll" />
      </span>
    </div>

    <v-expand-transition>
      <div v-show="moreOpen" id="more-filters" class="more">
        <v-select
          v-model="statusModel"
          :items="ALL_STATUS.map((s) => ({ title: statusLabel(s), value: s }))"
          label="Statuses"
          multiple
          chips
          closable-chips
          hide-details
          density="compact"
          class="f-status"
        />
        <v-select
          :model-value="filters.type"
          :items="[{ title: 'Any type', value: null }, { title: 'Paid', value: 'PAID' }, { title: 'Pro Bono', value: 'PROBONO' }]"
          label="Type"
          hide-details
          density="compact"
          class="f-small"
          @update:model-value="(v: Filters['type']) => update({ type: v })"
        />
        <v-select
          :model-value="filters.year"
          :items="[{ title: 'Any year', value: null }, ...years.map((y) => ({ title: String(y), value: y }))]"
          label="Year"
          hide-details
          density="compact"
          class="f-small"
          @update:model-value="(v: number | null) => update({ year: v })"
        />
        <OrganisationPicker v-model="orgModel" :initial-query="filters.orgName" class="f-org" />
        <v-select
          :model-value="filters.sort"
          :items="[{ title: 'Waiting longest', value: 'waiting' }, { title: 'Newest', value: 'newest' }, { title: 'Oldest', value: 'oldest' }]"
          label="Sort"
          hide-details
          density="compact"
          class="f-small"
          @update:model-value="(v: Sort) => update({ sort: v })"
        />
        <v-btn variant="text" class="m3" :disabled="!filtered" @click="clearFilters">Clear filters</v-btn>
      </div>
    </v-expand-transition>

    <nav class="tabs" aria-label="Requests by stage">
      <router-link
        v-for="t in TABS"
        :key="t.key"
        :to="tabTo(t)"
        replace
        class="tab"
        :class="{ active: activeTab === t.key, urgent: t.key === 'verify' && (counts.verify.n ?? 0) > 0 }"
        :aria-current="activeTab === t.key ? 'page' : undefined"
      >
        {{ t.title }}
        <span v-if="t.count" class="tab-n console-mono"><span :key="countLabel(counts[t.count])" class="console-roll">{{ countLabel(counts[t.count]) }}</span></span>
      </router-link>
    </nav>

    <div class="console-panels" :class="{ expanded: !!openId }">
      <RequestQueue
        v-model:selected="queueSelected"
        :items="items"
        :failed="list.failed.value"
        :title="activeTab ? TABS.find((t) => t.key === activeTab)!.title + ' requests' : 'Filtered requests'"
        label="Requests"
        :caption="caption"
        :show-status="!openId"
        :compact="!!openId"
        :link-to="openIn"
        :overdue-days="5"
        :empty-title="filtered ? 'No requests match these filters.' : 'No open requests.'"
        :empty-text="filtered ? 'Try another stage, or clear the filters.' : 'New requests from customers appear here.'"
        @retry="reload"
      >
        <template #empty>
          <v-btn v-if="filtered" variant="outlined" class="m3" @click="clearFilters">Clear filters</v-btn>
        </template>
        <template #foot>
          <div v-if="list.nextCursor.value" class="load-more">
            <v-btn variant="outlined" class="m3" :prepend-icon="BTN.more" :loading="list.loading.value" @click="list.loadMore">Load more</v-btn>
          </div>
        </template>
      </RequestQueue>
      <RequestView v-if="openId" :id="openId" :direction="direction" embedded class="request-detail open-view console-scroll" @changed="refreshAll" @close="closeOpen" />
      <RequestDetail v-else :summary="selected" :open-to="selected ? openIn(selected.id) : undefined" @changed="refreshAll" />
    </div>
  </div>
</template>

<style scoped>
.desk {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  width: 100%;
  max-width: 1500px;
  margin-inline: auto;
  padding: var(--sp-4) var(--sp-6) var(--sp-6);
}
.toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-3);
}
.search {
  flex: 1 1 320px;
  max-width: 560px;
}
.toolbar .v-btn.m3 :deep(.v-btn__append) {
  margin-inline: 4px 0;
  transition: transform 200ms var(--ease-out);
}
.toolbar .v-btn.m3.open :deep(.v-btn__append) {
  transform: rotate(180deg);
}
.badge {
  margin-left: 6px;
  min-width: 20px;
  padding: 0 6px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 20px;
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}
.updated {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: var(--sp-1);
}
.more {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3);
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
}
.f-status {
  flex: 2 1 320px;
}
.f-org {
  flex: 1 1 220px;
}
.f-small {
  flex: 0 1 160px;
}

/* Stage tabs: one connected strip cut by seams; the current stage carries the action-blue underline. */
.tabs {
  display: flex;
  overflow-x: auto;
  scrollbar-width: none;
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
}
.tab {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  min-height: 44px;
  padding: 0 var(--sp-4);
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  color: rgb(var(--v-theme-secondary));
  text-decoration: none;
  transition:
    background-color 120ms ease-out,
    box-shadow 200ms var(--ease-out),
    color 120ms ease-out;
}
.tab + .tab {
  border-left: 1px solid rgb(var(--v-theme-seam));
}
.tab:hover {
  background: rgb(var(--v-theme-surface-variant));
  color: rgb(var(--v-theme-on-surface));
}
.tab:focus-visible {
  outline-offset: -2px;
}
.tab.active {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 600;
  background: rgb(var(--v-theme-primary-subtle));
  box-shadow: inset 0 -2px 0 rgb(var(--v-theme-primary));
}
.tab-n {
  display: inline-block;
  overflow: hidden;
  font-size: 12px;
  font-weight: 500;
  color: rgb(var(--v-theme-secondary));
}
.tab.urgent,
.tab.urgent .tab-n {
  color: rgb(var(--v-theme-warning));
  font-weight: 600;
}
/* A request open beside the list: narrow queue + full request. Below 900 px the request takes the whole
   width (its close button returns to the list). */
.console-panels.expanded {
  grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
}
.console-panels.expanded > .open-view {
  display: flex;
  border-top: 0;
  border-left: 1px solid rgb(var(--v-theme-seam));
  background: rgb(var(--v-theme-background));
}
@media (max-width: 899.98px) {
  .console-panels.expanded {
    grid-template-columns: minmax(0, 1fr);
  }
  .console-panels.expanded > .request-queue {
    display: none;
  }
  .console-panels.expanded > .open-view {
    border-left: 0;
  }
}
.load-more {
  display: flex;
  justify-content: center;
  padding: var(--sp-3);
}

/* Wide screens: the desk fits the window under the shell header; the panels scroll. */
@media (min-width: 1280px) {
  .desk {
    /* Shell page title (≈72 px) sits above; the desk takes the rest of the window. */
    height: calc(100dvh - 72px);
    min-height: 520px;
  }
  .desk > :not(.console-panels) {
    flex-shrink: 0;
  }
}
@media (max-width: 599.98px) {
  .desk {
    padding: var(--sp-3) var(--sp-4) var(--sp-4);
  }
  .updated {
    margin-left: 0;
  }
  .search {
    max-width: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .toolbar .v-btn.m3 :deep(.v-btn__append),
  .tab {
    transition: none;
  }
}
</style>
