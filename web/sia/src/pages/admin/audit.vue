<script setup lang="ts">
/**
 * A-20 audit log (admin) as a day ledger: filter strip (record kind, record id, action, date presets) and the
 * entries grouped by Barbados day, newest first. Each entry: time, who (with role), what happened, the record it
 * touched (linked), the change from → to and the reason. Filters live in the URL.
 */
import { type AuditEntry, call, DateField, identity, shortRef, useAccountNames, useCursorList } from '@cimh/web-app'
import { statusLabel } from '@cimh/web-ui'
import { mdiArrowRight, mdiMagnify } from '@mdi/js'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { dayKey, dayLabel, type Preset, PRESETS, timeOf } from '../../history'

definePage({ meta: { guard: 'admin', title: 'Audit log', ownHeading: true } })

const route = useRoute()
const router = useRouter()
const s = (v: unknown) => (typeof v === 'string' ? v : '')
const f = reactive({
  entityType: s(route.query.entity),
  entityId: s(route.query.id),
  action: s(route.query.action),
  preset: ((s(route.query.when) || 'all') as Preset),
  from: s(route.query.from),
  to: s(route.query.to),
})

const range = computed(() => {
  const today = dayKey(new Date())
  const back = (d: number) => dayKey(new Date(Date.now() - d * 864e5))
  if (f.preset === 'today') return { from: today, to: today }
  if (f.preset === '7d') return { from: back(6), to: today }
  if (f.preset === '30d') return { from: back(29), to: today }
  if (f.preset === 'custom') return { from: f.from, to: f.to }
  return { from: '', to: '' }
})
const list = useCursorList<AuditEntry>((cursor) =>
  call(() =>
    identity.GET('/audit', {
      params: {
        query: {
          entityType: f.entityType || undefined,
          entityId: f.entityId.trim() || undefined,
          action: f.action.trim() || undefined,
          from: range.value.from ? `${range.value.from}T00:00:00-04:00` : undefined,
          to: range.value.to ? `${range.value.to}T23:59:59-04:00` : undefined,
          cursor,
          limit: 50,
        },
      },
    }),
  ),
)
onMounted(list.reload)
let timer: ReturnType<typeof setTimeout> | undefined
// A pending debounce must not fire after the page is left (router.replace would navigate back here).
onBeforeUnmount(() => clearTimeout(timer))
watch(f, () => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    const query: Record<string, string> = {}
    if (f.entityType) query.entity = f.entityType
    if (f.entityId.trim()) query.id = f.entityId.trim()
    if (f.action.trim()) query.action = f.action.trim()
    if (f.preset !== 'all') query.when = f.preset
    if (f.preset === 'custom' && f.from) query.from = f.from
    if (f.preset === 'custom' && f.to) query.to = f.to
    void router.replace({ query })
    void list.reload()
  }, 300)
})

const KINDS = [
  { value: '', title: 'Everything' },
  { value: 'account', title: 'Accounts' },
  { value: 'organisation', title: 'Organisations' },
]
const filtered = computed(() => !!(f.entityType || f.entityId.trim() || f.action.trim() || f.preset !== 'all'))
function clearAll() {
  Object.assign(f, { entityType: '', entityId: '', action: '', preset: 'all', from: '', to: '' })
}

// ---- names: people via the shared account cache, organisations looked up here once per id
const { name: accountName } = useAccountNames()
const orgNames = reactive(new Map<string, string>())
function orgName(id: string): string {
  if (!orgNames.has(id)) {
    orgNames.set(id, shortRef(id))
    call(() => identity.GET('/organisations/{organisationId}', { params: { path: { organisationId: id } } }))
      .then((o) => orgNames.set(id, o.name))
      .catch(() => undefined)
  }
  return orgNames.get(id)!
}
type Actor = AuditEntry['actor']
const isSystem = (a: Actor) => a.role === 'service' || a.role === 'system' || a.id === 'system' || a.id.startsWith('svc:')
/** Who did it: "System" for services and jobs (older rows say "identity-svc"); people by name, not email or id. */
function actorName(a: Actor): string {
  if (isSystem(a)) return 'System'
  const n = accountName(a.id)
  return n === a.id ? a.name || a.id : n
}
const ROLE: Record<string, string> = { admin: 'Administrator', staff: 'Staff', user: 'Customer', system: 'Automatic', service: 'Automatic' }

/** The record by name: accounts and organisations looked up, other kinds by a short reference. */
function recordName(e: AuditEntry): string {
  const { type, id } = e.entity
  if (type === 'account') {
    const n = accountName(id)
    return n === id ? `Account ${shortRef(id)}` : n
  }
  if (type === 'organisation') return orgName(id)
  if (type === 'project') return `Project ${id.toUpperCase()}`
  return `${type.charAt(0).toUpperCase()}${type.slice(1)} ${shortRef(id)}`
}
const link = (e: AuditEntry) =>
  e.entity.type === 'account'
    ? `/admin/accounts/${e.entity.id}`
    : e.entity.type === 'organisation'
      ? { path: '/admin/organisations', query: { open: e.entity.id } }
      : e.entity.type === 'product'
        ? `/products/${e.entity.id}`
        : null

/** What happened, as words. Unknown actions fall back to "Kind what". */
const SENTENCE: Record<string, string> = {
  'account.approved': 'Approved the account',
  'account.rejected': 'Denied the account',
  'account.suspended': 'Suspended the account',
  'account.reactivated': 'Reactivated the account',
  'account.erased': "Erased the account's personal data",
  'account.expired': 'Account expired: email never verified',
  'account.deleted': 'Account purged after 90 days',
  'account.mfa_reset': 'Reset two-step sign-in',
  'role.changed': 'Changed the role',
  'organisation.created': 'Created the organisation',
  'organisation.updated': 'Edited the organisation',
  'organisation.merged': 'Merged the organisation into another',
  'auth.admin_login': 'Administrator signed in',
  'auth.locked': 'Locked out after failed sign-ins',
  'auth.password_reset': 'Password reset with an email code',
  'auth.password_changed': 'Changed their password',
  'auth.mfa_enabled': 'Turned on two-step sign-in',
  'privacy.exported': 'Downloaded a copy of the personal data',
  'privacy.erasure_requested': 'Asked for their data to be erased',
  'product.deactivated': 'Deactivated the product',
  'project.created': 'Created the project',
  'project.updated': 'Edited the project',
  'file.quarantined': 'Upload refused: a virus was found',
  'file.deleted': 'Deleted a file',
}
function actionTitle(a: string) {
  if (SENTENCE[a]) return SENTENCE[a]
  const [kind, ...rest] = a.split('.')
  if (!kind || !rest.length) return a
  return `${kind.charAt(0).toUpperCase()}${kind.slice(1)} ${rest.join(' ').replace(/[_-]+/g, ' ')}`
}

// ---- change details in words ("Field: value"), never JSON
const FIELD: Record<string, string> = {
  role: 'Role',
  organisationId: 'Organisation',
  mergedInto: 'Merged into',
  accountsMoved: 'Accounts moved',
  name: 'Name',
  country: 'Country',
  type: 'Type',
  domains: 'Email domains',
  domain: 'Email domain',
  seconds: 'Locked for',
  active: 'Active',
  requestId: 'Request',
  signature: 'Virus found',
}
const ROLE_WORD: Record<string, string> = { admin: 'Administrator', staff: 'Staff', user: 'Customer' }
function value(k: string, v: unknown): string {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  if (k === 'role' && typeof v === 'string') return ROLE_WORD[v] ?? v
  if ((k === 'organisationId' || k === 'mergedInto') && typeof v === 'string') return orgName(v)
  if (k === 'requestId' && typeof v === 'string') return v // in full: details wrap, so the whole id always fits
  if (k === 'seconds' && typeof v === 'number') return v >= 120 ? `${Math.round(v / 60)} minutes` : `${v} seconds`
  if (Array.isArray(v)) return v.map((x) => value(k, x)).join(', ')
  if (typeof v === 'object') {
    return Object.entries(v as Record<string, unknown>)
      .map(([kk, vv]) => `${FIELD[kk] ?? kk}: ${value(kk, vv)}`)
      .join(' · ')
  }
  return typeof v === 'string' ? statusLabel(v) : String(v)
}
/** One side of a change. A sign-in's `newIp: false` says nothing, so it is dropped. */
function show(v: unknown): string | null {
  if (v === null || v === undefined || v === '') return null
  if (typeof v === 'object' && !Array.isArray(v)) {
    const o = Object.fromEntries(Object.entries(v as Record<string, unknown>).filter(([k, x]) => !(k === 'newIp' && x === false)))
    if (!Object.keys(o).length) return null
    if (o.newIp === true) return 'From a new IP address'
    return value('', o)
  }
  return value('', v)
}

// ---- days, with routine sign-in runs folded so approvals and erasures between them stay visible
const ROUTINE = new Set(['auth.admin_login', 'auth.password_changed', 'auth.password_reset', 'auth.mfa_enabled', 'privacy.exported'])
type Row = { kind: 'entry'; e: AuditEntry } | { kind: 'fold'; key: string; items: AuditEntry[] }
const unfolded = ref(new Set<string>())
const days = computed(() => {
  const out: { key: string; label: string; count: number; rows: Row[] }[] = []
  for (const e of list.items.value) {
    const k = dayKey(e.at)
    let day = out[out.length - 1]
    if (day?.key !== k) out.push((day = { key: k, label: dayLabel(k), count: 0, rows: [] }))
    day.count++
    const last = day.rows[day.rows.length - 1]
    if (ROUTINE.has(e.action) && last?.kind === 'fold') last.items.push(e)
    else if (ROUTINE.has(e.action)) day.rows.push({ kind: 'fold', key: `f-${e.id}`, items: [e] })
    else day.rows.push({ kind: 'entry', e })
  }
  // A run of one is just an entry; an opened run shows its entries.
  for (const d of out) {
    d.rows = d.rows.flatMap((r): Row[] =>
      r.kind === 'fold' && (r.items.length < 2 || unfolded.value.has(r.key)) ? r.items.map((e) => ({ kind: 'entry' as const, e })) : [r],
    )
  }
  return out
})
function unfold(key: string) {
  unfolded.value = new Set([...unfolded.value, key])
}
function foldText(items: AuditEntry[]) {
  const people = new Set(items.map((e) => actorName(e.actor)))
  return `${items.length} sign-in and routine account entries ${people.size === 1 ? `by ${[...people][0]}` : `by ${people.size} people`}`
}
const rowKey = (r: Row) => (r.kind === 'fold' ? r.key : r.e.id)
</script>

<template>
  <div class="audit">
    <h1 class="t-h1">Audit log</h1>

    <div class="strip">
      <div class="fields">
        <v-text-field v-model="f.action" data-page-search :prepend-inner-icon="mdiMagnify" label="Action, e.g. account.approved" hide-details clearable class="act" @click:clear="f.action = ''" />
        <v-text-field v-model="f.entityId" label="Record id" hide-details clearable class="mono-in" @click:clear="f.entityId = ''" />
        <v-btn-toggle v-model="f.preset" mandatory class="presets" density="compact" aria-label="When">
          <v-btn v-for="p in PRESETS" :key="p.value" :value="p.value" size="small">{{ p.title }}</v-btn>
        </v-btn-toggle>
      </div>
      <div v-if="f.preset === 'custom'" class="custom">
        <DateField v-model="f.from" label="From" clearable hide-details />
        <DateField v-model="f.to" label="To" clearable hide-details />
      </div>
      <div class="kinds" role="radiogroup" aria-label="Record kind">
        <button v-for="k in KINDS" :key="k.value" type="button" role="radio" class="chip" :aria-checked="f.entityType === k.value" @click="f.entityType = k.value">
          {{ k.title }}
        </button>
        <button v-if="filtered" type="button" class="console-retry clear" @click="clearAll">Clear filters</button>
      </div>
    </div>

    <section class="log" aria-label="Audit entries">
      <div v-if="!list.loaded.value" class="pad" aria-busy="true"><div v-for="n in 6" :key="n" class="console-skel sk" /></div>
      <div v-else-if="!list.items.value.length" class="pad empty">
        <p class="t-body">No entries match these filters.</p>
        <p class="t-caption muted">Widen the dates or clear a filter.</p>
      </div>
      <template v-else>
        <section v-for="d in days" :key="d.key" class="day" :aria-label="d.label">
          <header class="day-head">
            <h2 class="console-title">{{ d.label }}</h2>
            <span class="console-mono t-caption muted">{{ d.count }}{{ d === days[days.length - 1] && list.nextCursor.value ? '+' : '' }} {{ d.count === 1 ? 'entry' : 'entries' }}</span>
          </header>
          <TransitionGroup tag="ol" name="row" class="rows">
            <li v-for="(row, i) in d.rows" :key="rowKey(row)" class="entry" :class="{ fold: row.kind === 'fold' }" :style="{ '--i': Math.min(i, 10) }">
              <template v-if="row.kind === 'fold'">
                <span class="t console-mono">{{ timeOf(row.items[row.items.length - 1]!.at) }}</span>
                <p class="fold-text">
                  {{ foldText(row.items) }}
                  <button type="button" class="console-retry" @click="unfold(row.key)">Show them</button>
                </p>
              </template>
              <template v-else>
                <span class="t console-mono">{{ timeOf(row.e.at) }}</span>
                <div class="main">
                  <p class="what">
                    <span class="w-title">{{ actionTitle(row.e.action) }}</span>
                    <span class="code console-mono">{{ row.e.action }}</span>
                  </p>
                  <p v-if="show(row.e.from) || show(row.e.to)" class="change">
                    <span v-if="show(row.e.from)" class="from">{{ show(row.e.from) }}</span>
                    <svg v-if="show(row.e.from)" viewBox="0 0 24 24" width="14" height="14" aria-label="to"><path :d="mdiArrowRight" fill="currentColor" /></svg>
                    <span class="to">{{ show(row.e.to) ?? '—' }}</span>
                  </p>
                  <p v-if="row.e.reason" class="reason">“{{ row.e.reason }}”</p>
                </div>
                <span class="rec">
                  <router-link v-if="link(row.e)" :to="link(row.e)!">{{ recordName(row.e) }}</router-link>
                  <span v-else>{{ recordName(row.e) }}</span>
                </span>
                <span class="who">{{ actorName(row.e.actor) }}<span class="role">{{ ROLE[row.e.actor.role] ?? row.e.actor.role }}</span></span>
              </template>
            </li>
          </TransitionGroup>
        </section>
        <div v-if="list.nextCursor.value" class="load-more">
          <v-btn class="m3" variant="outlined" :loading="list.loading.value" @click="list.loadMore">Load older entries</v-btn>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.audit {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  max-width: 1440px;
  margin-inline: auto;
  padding: var(--sp-4) var(--sp-6) var(--sp-6);
  font-size: 14px;
}
.strip {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.fields {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-3);
}
.act {
  flex: 1 1 280px;
  max-width: 400px;
}
.mono-in {
  flex: 0 1 240px;
}
.mono-in :deep(input) {
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
}
.custom {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 220px));
  gap: var(--sp-3);
}
.kinds {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.chip {
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
  transition: background-color 150ms ease, border-color 150ms ease;
}
.chip:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.chip[aria-checked='true'] {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.14);
}
.clear {
  margin-left: var(--sp-2);
}
.log {
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
}
.pad {
  padding: var(--sp-6);
}
.sk {
  height: 40px;
  margin-bottom: var(--sp-3);
  border-radius: 4px;
}
.empty p {
  margin: 0 0 var(--sp-1);
}
.day + .day {
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.day-head {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 44px;
  padding: 0 var(--sp-4);
  background: rgb(var(--v-theme-surface));
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
@media (max-width: 1279.98px) {
  .day-head {
    top: 56px;
  }
}
.rows {
  list-style: none;
  margin: 0;
  padding: 0;
}
.entry {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr) minmax(150px, 200px) minmax(150px, 220px);
  gap: var(--sp-4);
  align-items: start;
  padding: 10px var(--sp-4);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.entry:last-child {
  border-bottom: 0;
}
.fold {
  align-items: center;
}
.fold-text {
  grid-column: 2 / -1;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--sp-2);
  margin: 0;
  font-size: 13px;
  color: rgb(var(--v-theme-secondary));
}
.t {
  font-size: 13px;
  line-height: 22px;
  color: rgb(var(--v-theme-secondary));
}
.main p {
  margin: 0;
}
.what {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px var(--sp-2);
  line-height: 22px;
}
.w-title {
  font-weight: 500;
}
.code {
  font-size: 12px;
  color: rgb(var(--v-theme-secondary));
}
.change {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 2px !important;
  overflow-wrap: anywhere;
}
.change svg {
  flex-shrink: 0;
  color: rgb(var(--v-theme-secondary));
}
.from {
  color: rgb(var(--v-theme-secondary));
}
.reason {
  margin-top: 4px !important;
  max-width: 70ch;
  font-size: 13px;
  color: rgb(var(--v-theme-secondary));
}
.rec,
.who {
  min-width: 0;
  line-height: 22px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rec {
  font-size: 13px;
}
.who {
  display: flex;
  flex-direction: column;
  white-space: normal;
}
.role {
  font-size: 12px;
  line-height: 16px;
  color: rgb(var(--v-theme-secondary));
}
.load-more {
  display: flex;
  justify-content: center;
  padding: var(--sp-4);
  border-top: 1px solid rgb(var(--v-theme-seam));
}
@media (max-width: 899.98px) {
  .entry {
    grid-template-columns: 48px minmax(0, 1fr);
    gap: 2px var(--sp-3);
  }
  .rec,
  .who {
    grid-column: 2;
  }
  .who {
    flex-direction: row;
    gap: var(--sp-2);
    align-items: baseline;
  }
}
@media (max-width: 599.98px) {
  .audit {
    padding: var(--sp-3) var(--sp-4) var(--sp-6);
  }
  .act,
  .mono-in {
    max-width: none;
    flex-basis: 100%;
  }
  .presets {
    overflow-x: auto;
    max-width: 100%;
  }
  .custom {
    grid-template-columns: 1fr 1fr;
  }
}
.row-enter-active {
  transition: opacity 220ms var(--ease-out), transform 220ms var(--ease-out);
  transition-delay: calc(var(--i, 0) * 24ms);
}
.row-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
@media (prefers-reduced-motion: reduce) {
  .row-enter-active {
    transition: opacity 160ms ease;
    transition-delay: 0ms;
  }
  .row-enter-from {
    transform: none;
  }
}
</style>
