<script setup lang="ts">
/**
 * A-16 pending accounts as a review queue, oldest first (J-08). Each row puts the two things to check side
 * by side (organisation given, email domain, in bold in the address) with a match line: does the domain
 * belong to an organisation on record, and does the name given match one? Then the wait (amber "Overdue" after 48 h, when the reminder
 * email goes out) and Approve / Deny. Select rows for a bulk decision (up to 100) from the panel head.
 */
import { type AccountSummary, call, identity, type Organisation, useCursorList } from '@cimh/web-app'
import { formatAge, formatDate } from '@cimh/web-ui'
import { mdiAccountCheckOutline, mdiAlertOutline, mdiCheckCircleOutline, mdiHelpCircleOutline } from '@mdi/js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import DecisionDialog from '../../components/DecisionDialog.vue'
import { pinLeaving } from '../../list-motion'

definePage({ meta: { guard: 'admin', title: 'Pending accounts', ownHeading: true } })

const list = useCursorList<AccountSummary>((cursor) =>
  call(() => identity.GET('/admin/accounts', { params: { query: { status: 'PENDING_APPROVAL', cursor, limit: 50 } } })),
)
onMounted(list.reload)

const selected = ref<string[]>([])
const dialog = ref(false)
const decision = ref<'approve' | 'deny'>('approve')
const target = ref<AccountSummary[]>([])
const chosen = computed(() => list.items.value.filter((a) => selected.value.includes(a.id)))
const allOn = computed(() => list.items.value.length > 0 && selected.value.length === list.items.value.length)
const someOn = computed(() => selected.value.length > 0 && !allOn.value)
function toggleAll() {
  selected.value = allOn.value ? [] : list.items.value.slice(0, 100).map((a) => a.id)
}

function decide(d: 'approve' | 'deny', accounts: AccountSummary[]) {
  decision.value = d
  target.value = accounts
  dialog.value = true
}
function done(okIds: string[]) {
  selected.value = selected.value.filter((id) => !okIds.includes(id))
  void list.reload()
}

const DAY = 86_400_000
const overdue = (a: AccountSummary) => !!a.createdAt && Date.now() - new Date(a.createdAt).getTime() > 2 * DAY
const local = (e: string) => e.slice(0, e.lastIndexOf('@') + 1)
const domain = (e: string) => e.slice(e.lastIndexOf('@') + 1)
// ---- Does the request match an organisation on record? Looked up once per domain / per organisation text.
const FREE_MAIL = new Set(['gmail.com', 'googlemail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'live.com', 'icloud.com', 'aol.com', 'proton.me', 'protonmail.com'])
const byDomain = reactive(new Map<string, Organisation | null>())
const byName = reactive(new Map<string, Organisation | null>())
function lookup(a: AccountSummary) {
  const d = domain(a.email).toLowerCase()
  if (!FREE_MAIL.has(d) && !byDomain.has(d)) {
    byDomain.set(d, null)
    call(() => identity.GET('/organisations', { params: { query: { emailDomain: d, limit: 1 } } }))
      .then((r) => byDomain.set(d, r.items[0] ?? null))
      .catch(() => byDomain.delete(d))
  }
  const t = a.organisationText?.trim().toLowerCase()
  if (t && !byName.has(t)) {
    byName.set(t, null)
    call(() => identity.GET('/organisations', { params: { query: { q: t, limit: 1 } } }))
      .then((r) => byName.set(t, r.items[0] ?? null))
      .catch(() => byName.delete(t))
  }
}
watch(() => list.items.value, (items) => items.forEach(lookup), { immediate: true })
type Match = { tone: 'ok' | 'warn' | 'none'; text: string }
function match(a: AccountSummary): Match {
  const d = domain(a.email).toLowerCase()
  const t = a.organisationText?.trim().toLowerCase() ?? ''
  const viaDomain = FREE_MAIL.has(d) ? null : byDomain.get(d)
  const viaName = t ? byName.get(t) : null
  // A typed organisation that matches no record is a mismatch, not a pass (critique 2026-11-15: every row was green).
  if (viaDomain && t && viaName === null && byName.has(t)) {
    return { tone: 'warn', text: `Gave "${a.organisationText?.trim()}"; domain belongs to ${viaDomain.name}` }
  }
  if (viaDomain && (!viaName || viaName.id === viaDomain.id)) return { tone: 'ok', text: `Domain belongs to ${viaDomain.name}` }
  if (viaDomain && viaName) return { tone: 'warn', text: `Domain belongs to ${viaDomain.name}, name given matches ${viaName.name}` }
  if (FREE_MAIL.has(d)) {
    return viaName
      ? { tone: 'warn', text: `Personal email; name given matches ${viaName.name}` }
      : { tone: 'warn', text: 'Personal email: no organisation domain to check' }
  }
  if (viaName) return { tone: 'warn', text: `Name matches ${viaName.name}; this domain isn't on its record` }
  return { tone: 'none', text: 'No organisation on record yet: you can create one when approving' }
}
const MATCH_ICON = { ok: mdiCheckCircleOutline, warn: mdiAlertOutline, none: mdiHelpCircleOutline } as const

const summary = computed(() => {
  if (!list.loaded.value) return 'Loading…'
  const n = list.items.value.length
  return `${n}${list.nextCursor.value ? '+' : ''} waiting · oldest first`
})
</script>

<template>
  <div class="approvals">
    <div class="top">
      <h1 class="t-h1">Pending accounts</h1>
      <p class="t-body muted intro">Check that the organisation they gave matches their email domain, then approve (linking an organisation) or deny with a reason.</p>
    </div>

    <section class="console-panels queue" aria-label="Accounts waiting for approval">
      <div class="console-head">
        <span v-if="list.items.value.length" class="ck all">
          <v-checkbox-btn :model-value="allOn" :indeterminate="someOn" density="compact" aria-label="Select all" @update:model-value="toggleAll" />
        </span>
        <h2 class="console-title" aria-live="polite">{{ selected.length ? `${selected.length} selected` : summary }}</h2>
        <span class="spacer" />
        <template v-if="selected.length">
          <v-btn class="m3" size="small" color="primary" variant="flat" @click="decide('approve', chosen)">Approve selected</v-btn>
          <v-btn class="m3 m3-danger" size="small" variant="outlined" @click="decide('deny', chosen)">Deny selected</v-btn>
        </template>
      </div>

      <div v-if="!list.loaded.value && list.loading.value" class="skel-rows">
        <div v-for="i in 5" :key="i" class="console-skel skel-row" />
      </div>
      <div v-else-if="list.loaded.value && !list.items.value.length" class="empty">
        <v-icon :icon="mdiAccountCheckOutline" size="28" class="muted" />
        <p class="t-body">No accounts are waiting for approval.</p>
        <router-link to="/admin/accounts" class="t-body">All accounts</router-link>
      </div>

      <TransitionGroup v-else tag="ul" name="rv" class="rows" @before-leave="pinLeaving">
        <li v-if="list.items.value.length" key="head" class="rv rv-h" aria-hidden="true">
          <span />
          <span>Person</span>
          <span>Organisation given</span>
          <span>Waiting</span>
          <span />
        </li>
        <li v-for="(a, i) in list.items.value" :key="a.id" class="rv" :class="{ on: selected.includes(a.id) }" :style="{ '--i': Math.min(i, 12) }" :aria-label="`${a.firstname} ${a.lastname} ${a.email}`">
          <span class="ck"><v-checkbox-btn v-model="selected" :value="a.id" density="compact" :aria-label="`Select ${a.firstname} ${a.lastname}`" /></span>
          <span class="who">
            <router-link :to="`/admin/accounts/${a.id}`" class="name">{{ a.firstname }} {{ a.lastname }}</router-link>
            <span class="mail" :title="a.email"><span class="lp">{{ local(a.email) }}</span><strong>{{ domain(a.email) }}</strong></span>
          </span>
          <span class="org">
            <span :class="{ muted: !a.organisationText }">{{ a.organisationText || 'None given' }}</span>
            <span class="match t-caption" :class="match(a).tone"><v-icon :icon="MATCH_ICON[match(a).tone]" size="14" />{{ match(a).text }}</span>
          </span>
          <span class="wait" :class="{ late: overdue(a) }" :title="a.createdAt ? formatDate(a.createdAt) : ''">
            <template v-if="overdue(a)"><v-icon :icon="mdiAlertOutline" size="16" />Overdue · </template>
            <span class="console-mono">{{ a.createdAt ? formatAge(a.createdAt) : '—' }}</span>
          </span>
          <span class="acts">
            <v-btn class="m3" size="small" color="primary" variant="tonal" @click="decide('approve', [a])">Approve</v-btn>
            <v-btn class="m3 m3-danger" size="small" variant="text" @click="decide('deny', [a])">Deny</v-btn>
          </span>
        </li>
      </TransitionGroup>
      <div v-if="list.nextCursor.value" class="load-more">
        <v-btn class="m3" variant="outlined" :loading="list.loading.value" @click="list.loadMore">Load more</v-btn>
      </div>
    </section>

    <DecisionDialog v-model="dialog" :accounts="target" :decision="decision" @done="done" />
  </div>
</template>

<style scoped>
.approvals {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
  max-width: 1400px;
  margin-inline: auto;
  padding: var(--sp-4) var(--sp-6) var(--sp-6);
  font-size: 14px;
}
.top {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}
.intro {
  margin: 0;
  max-width: 70ch;
}
.queue.console-panels {
  display: block;
  flex: none;
}
.queue.console-panels > * {
  display: block;
}
.queue.console-panels > .console-head {
  display: flex;
  flex-direction: row;
}
.ck {
  display: flex;
  width: 32px;
}
.ck :deep(.v-selection-control) {
  flex: none;
}
.all {
  display: flex;
  margin-left: -8px;
}
.spacer {
  flex: 1;
}
.rows {
  list-style: none;
  position: relative;
  margin: 0;
  padding: 0;
}
.rv {
  display: grid;
  grid-template-columns: 32px minmax(0, 2fr) minmax(0, 2.4fr) 150px 180px;
  align-items: center;
  gap: var(--sp-3);
  min-height: 60px;
  padding: 8px var(--sp-4) 8px 8px;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
  transition: background-color 120ms ease;
}
.rv:hover:not(.rv-h) {
  background: rgb(var(--v-theme-surface-variant));
}
.rv.on {
  background: rgba(var(--v-theme-primary), 0.14);
  box-shadow: inset 2px 0 rgb(var(--v-theme-primary));
}
.rv-h {
  min-height: 36px;
  padding-block: 0;
  font-size: 12px;
  font-weight: 500;
  color: rgb(var(--v-theme-secondary));
}
.who {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.name {
  font-weight: 500;
  color: inherit;
  text-decoration: none;
}
.name:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.mail {
  display: flex;
  min-width: 0;
  font-size: 12px;
  color: rgb(var(--v-theme-secondary));
  white-space: nowrap;
}
/* The domain is what staff judge an approval by: only the local part gives way when space runs out. */
.mail .lp {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mail strong {
  flex: none;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
}
.org {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  overflow-wrap: anywhere;
}
.match {
  display: inline-flex;
  align-items: flex-start;
  gap: 4px;
  color: rgb(var(--v-theme-secondary));
}
.match .v-icon {
  flex: none;
  margin-top: 1px;
}
.match.ok {
  color: rgb(var(--v-theme-on-surface));
}
.match.ok .v-icon {
  color: rgb(var(--v-theme-success));
}
.match.warn .v-icon {
  color: rgb(var(--v-theme-warning));
}
.wait {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: rgb(var(--v-theme-secondary));
}
.wait.late {
  color: rgb(var(--v-theme-warning));
  font-weight: 500;
}
.acts {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-1);
}
.skel-rows {
  padding: var(--sp-2) var(--sp-4);
}
.skel-row {
  height: 44px;
  margin: 12px 0;
  border-radius: 4px;
}
.empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--sp-2);
  padding: var(--sp-8) var(--sp-6);
}
.load-more {
  display: flex;
  justify-content: center;
  padding: var(--sp-4);
}
@media (max-width: 759.98px) {
  .approvals {
    padding: var(--sp-3) var(--sp-4) var(--sp-6);
  }
  .rv-h {
    display: none;
  }
  .rv {
    grid-template-columns: 32px minmax(0, 1fr) auto;
    grid-template-areas: 'c who wait' 'c org org' 'c acts acts';
    row-gap: 4px;
  }
  .rv > :first-child {
    grid-area: c;
    align-self: start;
  }
  .who {
    grid-area: who;
  }
  .wait {
    grid-area: wait;
    align-self: start;
  }
  .org {
    grid-area: org;
  }
  .acts {
    grid-area: acts;
    justify-content: flex-start;
  }
}
.rv-enter-active {
  transition: opacity 220ms var(--ease-out), transform 220ms var(--ease-out);
  transition-delay: calc(var(--i, 0) * 24ms);
}
.rv-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.rv-leave-active {
  position: absolute;
  transition: opacity 160ms ease-in, transform 160ms ease-in;
}
.rv-leave-to {
  opacity: 0;
  transform: translateX(12px);
}
.rv-move {
  transition: transform 280ms var(--ease-out);
}
@media (prefers-reduced-motion: reduce) {
  .rv-enter-active {
    transition: opacity 160ms ease;
    transition-delay: 0ms;
  }
  .rv-enter-from,
  .rv-leave-to {
    transform: none;
  }
  .rv-move {
    transition: none;
  }
}
</style>
