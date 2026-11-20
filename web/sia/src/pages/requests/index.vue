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
import SegmentedChoice from '../../components/SegmentedChoice.vue'
import ICheck from '~icons/material-symbols/check-rounded'
import { ALL_STATUS, BTN, CLOSED_STATUS, OPEN_STATUS } from '../../request-queue'
import { type CountKey, countLabel, useWorkCounts } from '../../work-counts'

definePage({ meta: { guard: 'staff', title: 'Orders' } })
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
    sort: sort === 'waiting' || sort === 'oldest' ? sort : 'newest',
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
  if (f.sort !== 'newest') out.sort = f.sort
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
  { key: 'quoted', title: 'Waiting for signature', status: ['QUOTED'], count: 'quoted' },
  { key: 'verify', title: 'Signature to check', status: ['ACCEPTED'], count: 'verify' },
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
    [filters.value.type, filters.value.year, filters.value.org, filters.value.sort !== 'newest' || null, activeTab.value ? null : 1].filter(
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
const STATUS_GROUPS = [
  { key: 'open', title: 'Open', status: OPEN_STATUS },
  { key: 'closed', title: 'Closed', status: CLOSED_STATUS },
]
function toggleStatus(s: RequestStatus) {
  const now = filters.value.status
  statusModel.value = now.includes(s) ? now.filter((x) => x !== s) : ALL_STATUS.filter((x) => x === s || now.includes(x))
}
// Segments cover the last three years; older ones sit in the "Earlier" menu (the segment then shows nothing chosen).
const recentYear = computed(() => (filters.value.year && years.slice(0, 3).includes(filters.value.year) ? filters.value.year : filters.value.year ? -1 : null))
// "Only open/closed" and Clear change many chips at once: their checks sweep in chip order.
const sweep = ref(false)
let sweepTimer: ReturnType<typeof setTimeout> | undefined
function sweepOnce() {
  sweep.value = true
  clearTimeout(sweepTimer)
  sweepTimer = setTimeout(() => (sweep.value = false), 500)
}
function onlyGroup(g: RequestStatus[]) {
  sweepOnce()
  statusModel.value = g
}
// Opening the panel: head and rows rise in behind the height transition (once per open).
const entering = ref(false)
let enterTimer: ReturnType<typeof setTimeout> | undefined
watch(moreOpen, (open) => {
  clearTimeout(enterTimer)
  entering.value = open
  if (open) enterTimer = setTimeout(() => (entering.value = false), 520)
})
onBeforeUnmount(() => {
  clearTimeout(sweepTimer)
  clearTimeout(enterTimer)
})
const moreSummary = computed(() => {
  const n = filters.value.status.length
  return n === ALL_STATUS.length ? 'Every status' : `${n} of ${ALL_STATUS.length} statuses`
})
const filtered = computed(() => Object.keys(serialize(filters.value)).length > 0)
function clearFilters() {
  sweepOnce()
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
        More filters<span v-if="extraCount" class="badge console-mono"><span :key="extraCount" class="console-roll">{{ extraCount }}</span></span>
      </v-btn>
      <span class="updated">
        <span v-if="time" class="t-caption muted">Updated {{ time }}</span>
        <v-btn variant="text" size="small" :icon="BTN.retry" :loading="list.loading.value" aria-label="Refresh requests and counts" @click="refreshAll" />
      </span>
    </div>

    <v-expand-transition>
      <section v-show="moreOpen" id="more-filters" class="more" :class="{ entering, sweep }" aria-labelledby="more-title">
        <header class="more-head">
          <h2 id="more-title" class="console-title">More filters</h2>
          <span class="t-caption muted roll-box"><span :key="moreSummary" class="console-roll">{{ moreSummary }}</span></span>
          <v-btn variant="text" size="small" class="m3 more-clear" :disabled="!filtered" @click="clearFilters">Clear filters</v-btn>
        </header>
        <fieldset class="cell cell-status">
          <legend class="cell-label">Statuses</legend>
          <div v-for="g in STATUS_GROUPS" :key="g.key" class="sgroup">
            <span class="sgroup-name">{{ g.title }}</span>
            <div class="schips">
              <label v-for="(s, i) in g.status" :key="s" :style="{ '--i': i }" class="schip" :class="{ on: filters.status.includes(s) }">
                <input type="checkbox" class="schip-input" :checked="filters.status.includes(s)" @change="toggleStatus(s)" />
                <Transition name="check"><ICheck v-if="filters.status.includes(s)" class="schip-check" aria-hidden="true" /></Transition>{{ statusLabel(s) }}
              </label>
            </div>
            <v-btn variant="text" size="small" class="sgroup-all" @click="onlyGroup(g.status)">Only {{ g.title.toLowerCase() }}</v-btn>
          </div>
        </fieldset>
        <div class="cells">
          <div class="cell">
            <span class="cell-label" aria-hidden="true">Type</span>
            <SegmentedChoice
              :model-value="filters.type"
              name="f-type"
              label="Type"
              :options="[{ title: 'Any', value: null }, { title: 'Paid', value: 'PAID' }, { title: 'Pro Bono', value: 'PROBONO' }]"
              @update:model-value="(v) => update({ type: v as Filters['type'] })"
            />
          </div>
          <div class="cell">
            <span class="cell-label" aria-hidden="true">Sent in</span>
            <SegmentedChoice
              :model-value="recentYear"
              name="f-year"
              label="Sent in"
              :options="[{ title: 'Any', value: null }, ...years.slice(0, 3).map((y) => ({ title: String(y), value: y }))]"
              @update:model-value="(v) => update({ year: v as number | null })"
            />
            <v-select
              v-if="years.length > 3"
              :model-value="recentYear === -1 ? filters.year : null"
              :items="years.slice(3)"
              placeholder="Earlier"
              aria-label="Earlier year"
              hide-details
              density="compact"
              class="f-earlier"
              @update:model-value="(v: number | null) => update({ year: v })"
            />
          </div>
          <div class="cell">
            <span class="cell-label" aria-hidden="true">Order</span>
            <SegmentedChoice
              :model-value="filters.sort"
              name="f-sort"
              label="Order"
              :options="[{ title: 'Newest', value: 'newest' }, { title: 'Waiting longest', value: 'waiting' }, { title: 'Oldest', value: 'oldest' }]"
              @update:model-value="(v) => update({ sort: v as Sort })"
            />
          </div>
          <div class="cell cell-org">
            <span class="cell-label" aria-hidden="true">Organisation</span>
            <OrganisationPicker v-model="orgModel" :initial-query="filters.orgName" label="Any organisation" />
        </div>
        </div>
      </section>
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
/* More filters: one console panel. The head bar names it and holds Clear; statuses span the panel as two
   toggle groups (Open, Closed); type, year, order and organisation sit in seamed cells below. */
.more {
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
}
.more-head {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  min-height: 44px;
  padding: 0 var(--sp-2) 0 var(--sp-4);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.more-head > * {
  white-space: nowrap;
}
.more-clear {
  margin-left: auto;
}
.cell > :deep(.seg) {
  flex-wrap: nowrap;
}
.cell {
  flex: 1 1 auto;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  align-content: start;
  gap: var(--sp-2) var(--sp-3);
  min-width: 0;
  margin: 0;
  padding: var(--sp-3) var(--sp-4) var(--sp-4);
  border: 0;
  border-right: 1px solid rgb(var(--v-theme-seam));
}
.cell:last-child {
  border-right: 0;
}
.cells > .cell {
  border-top: 1px solid rgb(var(--v-theme-seam));
  margin-top: -1px;
}
.cell-label {
  flex: 1 0 100%;
  padding: 0;
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--v-theme-secondary));
}
.cells {
  display: flex;
  flex-wrap: wrap;
}
.cell-status {
  display: grid;
  gap: var(--sp-2);
  border-right: 0;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.cell-status > legend {
  float: left;
  margin-bottom: var(--sp-1);
}
.sgroup {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--sp-3);
}
.sgroup-name {
  font-size: 13px;
  color: rgb(var(--v-theme-secondary));
}
.schips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.schip {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 32px;
  padding: 0 12px;
  border: 1px solid rgb(var(--v-theme-field-outline));
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  user-select: none;
  isolation: isolate;
  transition:
    background-color 160ms ease-out,
    border-color 200ms ease-out,
    padding 220ms var(--ease-out),
    transform 120ms ease-out;
}
/* The wash: fills from the left as the check wipes in, drains back to the left when turned off. */
.schip::before {
  content: '';
  position: absolute;
  inset: -1px;
  z-index: -1;
  border-radius: inherit;
  background: rgb(var(--v-theme-primary-subtle));
  transform: scaleX(0);
  transform-origin: left center;
  transition: transform 160ms ease-in;
}
.schip:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}
.schip:active {
  transform: scale(0.96);
}
.schip.on {
  padding-left: 8px;
  border-color: transparent;
}
.schip.on::before {
  transform: scaleX(1);
  transition: transform 260ms var(--ease-out);
}
.more.sweep .schip.on::before,
.more.sweep .schip {
  transition-delay: calc(var(--i, 0) * 28ms);
}
.schip-input {
  position: absolute;
  inset: 0;
  margin: 0;
  opacity: 0;
  cursor: pointer;
}
.schip:has(.schip-input:focus-visible) {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 1px;
}
.schip-check {
  width: 18px;
  height: 18px;
  color: rgb(var(--v-theme-primary));
}
/* A check wipes in from the left when its status is turned on (Vue Transition: only on insertion, never
   on first render or when the panel opens). Bulk changes sweep in chip order. */
/* The check also opens its own room (width 0 ↔ 18 px), so the chip grows and its neighbours glide instead of
   jumping. */
.check-enter-active {
  transition:
    clip-path 220ms var(--ease-out),
    width 220ms var(--ease-out),
    margin 220ms var(--ease-out);
}
.check-enter-from {
  clip-path: inset(0 100% 0 0);
  width: 0;
  margin-right: -4px;
}
.check-leave-active {
  transition:
    clip-path 160ms ease-in,
    opacity 160ms ease-in,
    width 180ms var(--ease-out),
    margin 180ms var(--ease-out);
}
.check-leave-to {
  clip-path: inset(0 0 0 100%);
  opacity: 0;
  width: 0;
  margin-right: -4px;
}
.more.sweep .check-enter-active {
  transition-delay: calc(var(--i, 0) * 28ms);
}
.roll-box {
  display: inline-block;
  overflow: hidden;
  vertical-align: bottom;
}
.more.entering > * {
  animation: filter-rise 300ms var(--ease-out) both;
}
.more.entering > :nth-child(2) {
  animation-delay: 40ms;
}
.more.entering > :nth-child(3) {
  animation-delay: 80ms;
}
@keyframes filter-rise {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }
}
.sgroup-all {
  justify-self: end;
}
.f-earlier {
  flex: 0 0 120px;
}
.cell-org {
  flex: 1 1 260px;
}
.cell-org :deep(.v-input) {
  flex: 1 1 220px;
}
@media (max-width: 1099.98px) {
  .cells {
    flex-direction: column;
  }
  .cell {
    border-right: 0;
    border-bottom: 1px solid rgb(var(--v-theme-seam));
  }
  .cell:last-child {
    border-bottom: 0;
  }
  .sgroup {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: var(--sp-1) var(--sp-3);
  }
  .sgroup-all {
    grid-row: 1;
    grid-column: 2;
  }
  .schips {
    grid-column: 1 / -1;
  }
}
@media (max-width: 599.98px) {
  .more-head .t-caption {
    display: none;
  }
  .cell > :deep(.seg) {
    flex-wrap: wrap;
  }
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
  .check-enter-active,
  .more.sweep .check-enter-active {
    transition: opacity 160ms ease-out;
    transition-delay: 0ms;
  }
  .check-enter-from,
  .check-leave-to {
    clip-path: none;
    opacity: 0;
  }
  /* Chips: the wash fades instead of filling, no squeeze, no padding slide. */
  .schip,
  .more.sweep .schip {
    transition: background-color 160ms ease-out;
    transition-delay: 0ms;
  }
  .schip:active {
    transform: none;
  }
  .schip::before,
  .schip.on::before,
  .more.sweep .schip.on::before {
    transform: none;
    opacity: 0;
    transition: opacity 160ms ease-out;
    transition-delay: 0ms;
  }
  .schip.on::before,
  .more.sweep .schip.on::before {
    opacity: 1;
  }
  .more.entering > * {
    animation: filter-fade 200ms ease-out both;
  }
  .toolbar .v-btn.m3 :deep(.v-btn__append),
  .schip,
  .tab {
    transition: none;
  }
}
@keyframes filter-fade {
  from {
    opacity: 0;
  }
}
</style>
