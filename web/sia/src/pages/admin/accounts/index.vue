<script setup lang="ts">
/**
 * A-17 accounts, the console's list-beside-record pattern: filter strip (name/email prefix, status chips,
 * role, "Asked to be deleted"), account list on the left, the account record beside it on wide screens
 * (`?open=<id>`); narrow screens open the account page. Filters live in the URL. Staff read; admins act.
 */
import { type Account, type AccountSummary, call, identity, StatusChip, useCursorList } from '@cimh/web-app'
import { formatDate } from '@cimh/web-ui'
import { mdiDeleteClockOutline, mdiMagnify } from '@mdi/js'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useRoute, useRouter } from 'vue-router'
import AccountRecord from '../../../components/AccountRecord.vue'
import { pinLeaving } from '../../../list-motion'

definePage({ meta: { guard: 'staff', title: 'Accounts', ownHeading: true } })

const route = useRoute()
const router = useRouter()
const display = useDisplay()
type Status = AccountSummary['status']
type RoleT = AccountSummary['role']
const str = (v: unknown) => (typeof v === 'string' && v ? v : null)
const status = ref<Status | null>(str(route.query.status) as Status | null)
const role = ref<RoleT | null>(str(route.query.role) as RoleT | null)
const q = ref(str(route.query.q) ?? '')
const erasure = ref(route.query.erasure === '1')
const openId = computed(() => str(route.query.open))

const list = useCursorList<AccountSummary>((cursor) =>
  call(() =>
    identity.GET('/admin/accounts', {
      params: {
        query: {
          status: status.value ?? undefined,
          role: role.value ?? undefined,
          q: q.value.trim() || undefined,
          erasureRequested: erasure.value || undefined,
          cursor,
          limit: 50,
        },
      },
    }),
  ),
)
onMounted(list.reload)

function queryFor(open: string | null) {
  const query: Record<string, string> = {}
  if (status.value) query.status = status.value
  if (role.value) query.role = role.value
  if (q.value.trim()) query.q = q.value.trim()
  if (erasure.value) query.erasure = '1'
  if (open) query.open = open
  return query
}
let timer: ReturnType<typeof setTimeout> | undefined
onBeforeUnmount(() => clearTimeout(timer))
watch([status, role, q, erasure], () => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    void router.replace({ query: queryFor(openId.value) })
    void list.reload()
  }, 250)
})

const STATUS_CHIPS: { value: Status | null; title: string }[] = [
  { value: null, title: 'All' },
  { value: 'ACTIVE', title: 'Active' },
  { value: 'PENDING_APPROVAL', title: 'Pending approval' },
  { value: 'PENDING_VERIFICATION', title: 'Pending verification' },
  { value: 'SUSPENDED', title: 'Suspended' },
  { value: 'REJECTED', title: 'Rejected' },
  { value: 'EXPIRED', title: 'Expired' },
]
const ROLES = [
  { value: 'user', title: 'Customer' },
  { value: 'staff', title: 'Staff' },
  { value: 'admin', title: 'Administrator' },
]
const roleTitle = (r: string) => ROLES.find((x) => x.value === r)?.title ?? r
const orgOf = (a: AccountSummary) => a.organisationName ?? (a.organisationText ? `${a.organisationText} (not linked)` : a.isCimh ? 'CIMH' : '—')
const filtered = computed(() => !!(status.value || role.value || erasure.value || q.value.trim()))
function clearFilters() {
  status.value = null
  role.value = null
  erasure.value = false
  q.value = ''
}

const wide = computed(() => display.width.value >= 1280)
const showRecord = computed(() => wide.value && !!openId.value)
function open(a: AccountSummary) {
  if (!wide.value) return void router.push(`/admin/accounts/${a.id}`)
  void router.replace({ query: queryFor(a.id) })
}
function close() {
  void router.replace({ query: queryFor(null) })
}
// Narrow screens have no room beside the list, so a `?open=` link (admin overview, a shared URL, a window made
// narrower) goes to the account's own page instead of silently showing only the list.
watch(
  [wide, openId],
  ([w, id]) => {
    if (!w && id) void router.replace(`/admin/accounts/${id}`)
  },
  { immediate: true },
)
function onRowKey(e: KeyboardEvent, i: number) {
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
  e.preventDefault()
  const items = list.items.value
  const next = items[Math.max(0, Math.min(items.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))]
  if (!next) return
  document.getElementById(`arow-${next.id}`)?.focus()
  if (showRecord.value) open(next)
}
/** Keep the row in step with changes made in the record (status, role, organisation). */
function onUpdated(a: Account) {
  const i = list.items.value.findIndex((x) => x.id === a.id)
  const row = list.items.value[i]
  if (row) list.items.value.splice(i, 1, { ...row, status: a.status, role: a.role, organisationName: a.organisationName, erasureRequestedAt: a.erasureRequestedAt })
}
function onErased(id: string) {
  list.items.value = list.items.value.filter((x) => x.id !== id)
  close()
}
const summary = computed(() => {
  if (!list.loaded.value) return 'Loading…'
  const n = list.items.value.length
  return `${n}${list.nextCursor.value ? '+' : ''} ${n === 1 ? 'account' : 'accounts'} · newest first`
})
</script>

<template>
  <div class="accounts">
    <div class="top">
      <h1 class="t-h1">Accounts</h1>
    </div>

    <div class="strip">
      <v-text-field
        v-model="q"
        data-page-search
        :prepend-inner-icon="mdiMagnify"
        label="Name or email starts with"
        clearable
        hide-details
        density="compact"
        class="search"
        @click:clear="q = ''"
      />
      <v-select v-model="role" :items="ROLES" label="Role" clearable hide-details density="compact" class="role" />
      <button type="button" class="chip" :aria-pressed="erasure" @click="erasure = !erasure">
        <v-icon :icon="mdiDeleteClockOutline" size="16" />Asked to be deleted
      </button>
    </div>
    <div class="chips" role="group" aria-label="Status">
      <button v-for="c in STATUS_CHIPS" :key="c.title" type="button" class="chip" :aria-pressed="status === c.value" @click="status = c.value">
        {{ c.title }}
      </button>
    </div>

    <div class="console-panels panels" :class="{ split: showRecord }">
      <section class="alist" aria-label="Accounts">
        <div class="console-head">
          <h2 class="console-title" aria-live="polite">{{ summary }}</h2>
        </div>
        <div class="console-scroll">
          <div v-if="!list.loaded.value && list.loading.value" class="skel-rows">
            <div v-for="i in 8" :key="i" class="console-skel skel-row" />
          </div>
          <div v-else-if="list.loaded.value && !list.items.value.length" class="empty">
            <p class="t-body">No accounts match{{ q.trim() ? ` “${q.trim()}”` : ' these filters' }}.</p>
            <div v-if="filtered" class="row"><v-btn class="m3" variant="outlined" @click="clearFilters">Clear filters</v-btn></div>
          </div>
          <TransitionGroup v-else tag="ul" name="arow" class="rows" @before-leave="pinLeaving">
            <li v-if="!showRecord" key="head" class="row-h" aria-hidden="true">
              <span>Name</span>
              <span class="c-org">Organisation</span>
              <span class="c-role">Role</span>
              <span>Status</span>
              <span class="c-date">Created</span>
            </li>
            <li v-for="(a, i) in list.items.value" :key="a.id" :style="{ '--i': Math.min(i, 12) }">
              <router-link
                :id="`arow-${a.id}`"
                :to="`/admin/accounts/${a.id}`"
                class="arow"
                :class="{ on: openId === a.id && showRecord }"
                :aria-current="openId === a.id && showRecord ? 'true' : undefined"
                @click.prevent="open(a)"
                @keydown="onRowKey($event, i)"
              >
                <span class="c-name">
                  <span class="aname">{{ `${a.firstname} ${a.lastname}`.trim() || a.email }}</span>
                  <span class="sub">{{ a.email }}</span>
                </span>
                <span class="c-org">{{ orgOf(a) }}</span>
                <span class="c-role">{{ roleTitle(a.role) }}</span>
                <span class="c-status">
                  <StatusChip :status="a.status" />
                  <span v-if="a.erasureRequestedAt" class="del"><v-icon :icon="mdiDeleteClockOutline" size="16" />Delete requested</span>
                </span>
                <span class="c-date console-mono">{{ a.createdAt ? formatDate(a.createdAt) : '—' }}</span>
              </router-link>
            </li>
          </TransitionGroup>
          <div v-if="list.nextCursor.value" class="load-more">
            <v-btn class="m3" variant="outlined" :loading="list.loading.value" @click="list.loadMore">Load more</v-btn>
          </div>
        </div>
      </section>

      <section v-if="showRecord && openId" class="record" aria-label="Selected account">
        <div class="console-head">
          <h2 class="console-title">Selected account</h2>
          <span class="row head-acts">
            <v-btn variant="text" size="small" class="m3" :to="`/admin/accounts/${openId}`">Open full page</v-btn>
            <v-btn variant="text" size="small" class="m3" @click="close">Close</v-btn>
          </span>
        </div>
        <div class="console-scroll">
          <AccountRecord :key="openId" :account-id="openId" embedded @updated="onUpdated" @erased="onErased" />
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.accounts {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding: var(--sp-4) var(--sp-6) var(--sp-6);
  font-size: 14px;
}
@media (min-width: 1280px) {
  .accounts {
    height: 100dvh;
    min-height: 560px;
  }
  .accounts > :not(.panels) {
    flex-shrink: 0;
  }
}
.top {
  display: flex;
  align-items: center;
  margin-bottom: var(--sp-3); /* + the 12 px gap = 24 px under the title */
}
.strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-3);
}
.search {
  flex: 1 1 280px;
  max-width: 420px;
}
.role {
  flex: 0 1 200px;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px;
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 8px;
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  color: inherit;
  background: none;
  cursor: pointer;
  white-space: nowrap;
  transition: background-color 150ms ease, border-color 150ms ease;
}
.chip:active {
  transform: scale(0.97);
}
.chip:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.chip[aria-pressed='true'] {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.14);
}
.panels {
  grid-template-columns: minmax(0, 1fr);
}
.panels.split {
  grid-template-columns: minmax(320px, 400px) minmax(0, 1fr);
}
.record {
  border-left: 1px solid rgb(var(--v-theme-seam));
  background: rgb(var(--v-theme-background));
  min-width: 0;
}
.head-acts {
  gap: var(--sp-1);
}
.rows {
  list-style: none;
  position: relative;
  margin: 0;
  padding: 0;
}
.row-h,
.arow {
  display: grid;
  grid-template-columns: minmax(220px, 2.4fr) minmax(140px, 1.6fr) 110px minmax(170px, auto) 100px;
  align-items: center;
  gap: var(--sp-3);
  padding: 0 var(--sp-4);
}
.split .arow {
  grid-template-columns: minmax(0, 1fr) auto;
}
.split .c-org,
.split .c-role,
.split .c-date {
  display: none;
}
.row-h {
  position: sticky;
  top: 0;
  z-index: 1;
  height: 36px;
  font-size: 12px;
  font-weight: 500;
  color: rgb(var(--v-theme-secondary));
  background: rgb(var(--v-theme-surface));
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.arow {
  min-height: 56px;
  padding-block: 8px;
  color: inherit;
  text-decoration: none;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
  transition: background-color 120ms ease;
}
.arow:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.arow.on {
  background: rgba(var(--v-theme-primary), 0.14);
  box-shadow: inset 2px 0 rgb(var(--v-theme-primary));
}
.arow:focus-visible {
  outline-offset: -2px;
}
.c-name {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.aname {
  font-weight: 500;
  line-height: 20px;
}
.sub,
.c-org,
.c-role {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sub {
  font-size: 12px;
  color: rgb(var(--v-theme-secondary));
}
.c-status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  justify-self: start;
}
.split .c-status {
  justify-self: end;
  justify-content: flex-end;
}
.del {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  color: rgb(var(--v-theme-warning));
}
.c-date {
  font-size: 12px;
  color: rgb(var(--v-theme-secondary));
}
.skel-rows {
  padding: var(--sp-2) var(--sp-4);
}
.skel-row {
  height: 40px;
  margin: 12px 0;
  border-radius: 4px;
}
.empty {
  padding: var(--sp-8) var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.load-more {
  display: flex;
  justify-content: center;
  padding: var(--sp-4);
}
@media (max-width: 1099.98px) {
  .row-h,
  .arow {
    grid-template-columns: minmax(0, 2fr) minmax(0, 1.4fr) minmax(150px, auto);
  }
  .c-role,
  .c-date {
    display: none;
  }
}
@media (max-width: 759.98px) {
  .accounts {
    padding: var(--sp-3) var(--sp-4) var(--sp-6);
  }
  .row-h,
  .arow {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .c-org {
    display: none;
  }
  .search {
    max-width: none;
  }
  .chips {
    flex-wrap: nowrap;
    overflow-x: auto;
    scrollbar-width: none;
  }
}
.arow-enter-active {
  transition: opacity 220ms var(--ease-out), transform 220ms var(--ease-out);
  transition-delay: calc(var(--i, 0) * 24ms);
}
.arow-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.arow-leave-active {
  position: absolute;
  transition: opacity 140ms ease-in;
}
.arow-leave-to {
  opacity: 0;
}
.arow-move {
  transition: transform 280ms var(--ease-out);
}
@media (prefers-reduced-motion: reduce) {
  .arow-enter-active {
    transition: opacity 160ms ease;
    transition-delay: 0ms;
  }
  .arow-enter-from,
  .chip:active {
    transform: none;
  }
  .arow-move {
    transition: none;
  }
}
</style>
