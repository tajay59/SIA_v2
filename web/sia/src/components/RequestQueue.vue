<script setup lang="ts">
/**
 * Request queue panel (Graphite Console), shared by the dashboard (A-01 "Needs you now") and the desk (A-02).
 * A listbox of rows: code (link to the full page), what was requested + customer, next step (icon + words; amber verify, red
 * expiring), optional status, time in this status. Arrow keys / Home / End move the selection, Enter opens.
 * Phones have no detail panel, so a tap opens the request. Rows enter, leave and re-order with motion.
 */
import { type RequestSummary, ShortRef, StatusChip } from '@cimh/web-app'
import IOverdue from '~icons/material-symbols/schedule-rounded'
import { type RouteLocationRaw, useRouter } from 'vue-router'
import { BTN, TONE_ICON, waited, why } from '../request-queue'

const props = withDefaults(
  defineProps<{
    items: RequestSummary[] | null
    failed?: boolean
    title: string
    label: string
    caption?: string
    showStatus?: boolean
    /** Days in one status after which "waiting" is flagged overdue (icon + word, amber). 0 = never. */
    overdueDays?: number
    emptyTitle: string
    emptyText?: string
    /** Where a request opens (code link, Enter). Default: its own page. The desk opens it beside the list. */
    linkTo?: (id: string) => RouteLocationRaw
    /** Narrow column next to an open request: two-line rows. */
    compact?: boolean
  }>(),
  { failed: false, caption: '', showStatus: false, overdueDays: 0, emptyText: '', linkTo: undefined, compact: false },
)
const selected = defineModel<string | null>('selected', { default: null })
defineEmits<{ retry: [] }>()

const router = useRouter()
const phone = () => typeof matchMedia !== 'undefined' && matchMedia('(max-width: 599.98px)').matches
function pick(id: string) {
  if (phone()) void router.push(`/requests/${id}`)
  else selected.value = id
}
const target = (id: string): RouteLocationRaw => props.linkTo?.(id) ?? `/requests/${id}`
// Delivered but not paid (no proof yet, or a proof to check): Delivered shrinks to its icon beside a red chip.
const unpaid = (r: RequestSummary) => r.paymentStatus === 'DUE' || r.paymentStatus === 'PROOF_SENT'
const overdue = (r: RequestSummary) => props.overdueDays > 0 && (r.waitingDays ?? 0) > props.overdueDays

function onRowKey(e: KeyboardEvent, i: number) {
  const list = props.items
  if (!list?.length) return
  if (e.key === 'Enter') {
    void router.push(target(list[i].id))
    return
  }
  const last = list.length - 1
  const moves: Record<string, number> = { ArrowDown: i + 1, ArrowUp: i - 1, Home: 0, End: last }
  const next = moves[e.key]
  if (next === undefined || next < 0 || next > last) return
  e.preventDefault()
  selected.value = list[next].id
  const host = (e.currentTarget as HTMLElement).parentElement
  ;(host?.querySelector(`[data-row="${next}"]`) as HTMLElement | null)?.focus()
}
</script>

<template>
  <section class="request-queue" :aria-label="title">
    <header class="console-head">
      <h2 class="console-title">{{ title }}</h2>
      <span class="head-right">
        <span v-if="caption" class="t-caption muted" aria-live="polite">{{ caption }}</span>
        <slot name="head-extra" />
      </span>
    </header>

    <div v-if="failed" class="empty">
      <p>Couldn't load the requests.</p>
      <v-btn variant="outlined" class="m3" :prepend-icon="BTN.retry" @click="$emit('retry')">Retry</v-btn>
    </div>
    <div v-else-if="items === null" class="rows console-scroll">
      <div v-for="i in 6" :key="i" class="row-skel console-skel" />
    </div>
    <div v-else-if="items.length === 0" class="empty">
      <p class="t-body-lg">{{ emptyTitle }}</p>
      <p v-if="emptyText" class="muted">{{ emptyText }}</p>
      <slot name="empty" />
    </div>
    <div v-else class="console-scroll scroller">
      <TransitionGroup tag="ul" name="row" appear class="rows" role="listbox" :aria-label="label">
        <li
          v-for="(r, i) in items"
          :key="r.id"
          :data-row="i"
          :style="{ '--i': Math.min(i, 8) }"
          role="option"
          :aria-selected="r.id === selected"
          :tabindex="r.id === selected || (!selected && i === 0) ? 0 : -1"
          class="row"
          :class="{ sel: r.id === selected, 'with-status': showStatus, compact }"
          @click="pick(r.id)"
          @keydown="onRowKey($event, i)"
        >
          <span class="code"><ShortRef :id="r.id" /></span>
          <span class="who">
            <span class="who-name">{{ r.customerName || r.customer }}</span>
            <span v-if="r.type === 'PROBONO'" class="probono-badge">Pro Bono</span>
            <span v-if="r.organisationName" class="who-sub">{{ r.organisationName }}</span>
          </span>
          <span class="why">
            <span class="pill" :class="why(r).tone"><v-icon :icon="TONE_ICON[why(r).tone]" size="14" /><span>{{ why(r).text }}</span></span>
          </span>
          <span v-if="showStatus" class="status">
            <template v-if="unpaid(r)">
              <StatusChip :status="r.status" icon-only />
              <StatusChip :status="r.status" label="Payment required" tone="error" icon="cash" />
            </template>
            <StatusChip v-else :status="r.status" />
          </span>
          <span class="wait tnum" :class="{ overdue: overdue(r) }">
            <v-icon v-if="overdue(r)" :icon="IOverdue" size="14" />
            {{ waited(r) }}<span v-if="overdue(r)" class="overdue-word"> · overdue</span>
          </span>
        </li>
      </TransitionGroup>
      <slot name="foot" />
    </div>
  </section>
</template>

<style scoped>
.head-right {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  min-width: 0;
}
.rows {
  position: relative;
  list-style: none;
  margin: 0;
  padding: 0;
}
.row {
  display: grid;
  grid-template-columns: minmax(120px, 0.9fr) minmax(0, 1.2fr) minmax(0, 1fr) 112px;
  gap: var(--sp-3);
  align-items: center;
  min-height: 44px;
  padding: 0 var(--sp-4);
  font-size: 14px;
  line-height: 20px;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
  cursor: pointer;
  transition:
    background-color 120ms ease-out,
    box-shadow 160ms var(--ease-out);
}
.row.with-status {
  /* The reason is why the queue exists: it gets the widest column (critique: cut to "Approve or re" at 1440 px). */
  grid-template-columns: minmax(96px, 0.6fr) minmax(0, 1.5fr) minmax(0, 1fr) 200px 96px;
}
.row:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.row.sel {
  background: rgb(var(--v-theme-primary-subtle));
  box-shadow: inset 2px 0 0 rgb(var(--v-theme-primary));
}
.row:focus-visible {
  outline-offset: -2px;
}
.row-skel {
  height: 44px;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.code {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 400 13px 'JetBrains Mono', ui-monospace, monospace;
  color: inherit;
  text-decoration: none;
}
.who {
  display: flex;
  flex-wrap: wrap; /* the Pro Bono badge drops under the name instead of squeezing it to "Cas…" */
  align-items: center;
  gap: var(--sp-2);
  min-width: 0;
}
/* Rows are titled by what was requested (as in SHOP); the customer is the second line. */
.who-sub {
  flex-basis: 100%;
  min-width: 0;
  font-size: 12px;
  line-height: 16px;
  color: rgb(var(--v-theme-secondary));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* Item titles run longer than customer names did: up to two lines before they are cut. */
.who-name {
  min-width: 0;
  max-width: 100%;
  font-weight: 500;
  overflow: hidden;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow-wrap: anywhere;
}
.why {
  min-width: 0;
  font-size: 13px;
  line-height: 18px;
}
.pill {
  display: inline-flex;
  align-items: flex-start;
  gap: 6px;
  max-width: 100%;
  /* Wraps to a second line rather than cutting the words (ellipsis never applied: the text is a flex item). */
  padding-block: 4px;
  color: rgb(var(--v-theme-on-surface));
}
.pill .v-icon {
  margin-top: 2px;
}
.pill .v-icon {
  flex: none;
  color: rgb(var(--v-theme-secondary));
}
.pill.wait,
.pill.closed {
  color: rgb(var(--v-theme-secondary));
}
.pill.urgent,
.pill.urgent .v-icon {
  color: rgb(var(--v-theme-warning));
  font-weight: 600;
}
.pill.expiring,
.pill.expiring .v-icon {
  color: rgb(var(--v-theme-error));
  font-weight: 600;
}
.wait {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  font-size: 13px;
  color: rgb(var(--v-theme-secondary));
  white-space: nowrap;
}
.wait.overdue {
  color: rgb(var(--v-theme-warning));
  font-weight: 600;
}
.overdue-word {
  font-weight: 500;
}
.empty {
  padding: var(--sp-8) var(--sp-4);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--sp-2);
}
.empty p {
  margin: 0;
}

/* Motion: capped stagger on arrival, fade on leave, remaining rows slide into place. */
.row-enter-active {
  transition:
    opacity 220ms var(--ease-out),
    transform 220ms var(--ease-out);
  transition-delay: calc(var(--i, 0) * 24ms);
}
.row-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.row-leave-active {
  position: absolute;
  left: 0;
  right: 0;
  transition: opacity 140ms ease-in;
}
.row-leave-to {
  opacity: 0;
}
.row-move {
  transition: transform 280ms var(--ease-out);
}
@media (prefers-reduced-motion: reduce) {
  .row-enter-from {
    transform: none;
  }
  .row-enter-active {
    transition-delay: 0ms;
  }
  .row-move {
    transition: none;
  }
}

/* Compact: the narrow list beside an open request; same two-line row as phones. */
.row.compact,
.row.compact.with-status {
  grid-template-columns: minmax(0, 1fr) auto;
  grid-template-areas: 'who wait' 'why code';
  row-gap: 2px;
  padding: var(--sp-2) var(--sp-4);
}
.row.compact .code {
  grid-area: code;
  max-width: 14ch;
  text-align: right;
  color: rgb(var(--v-theme-secondary));
}
.row.compact .who {
  grid-area: who;
}
.row.compact .why {
  grid-area: why;
}
.row.compact .wait {
  grid-area: wait;
}
.row .status {
  display: inline-flex;
  gap: 6px;
  min-width: 0;
}
.row.compact .status,
.row.compact .overdue-word {
  display: none;
}

@media (max-width: 1279.98px) {
  .row.with-status {
    grid-template-columns: minmax(110px, 0.8fr) minmax(0, 1.2fr) minmax(0, 1fr) 112px;
  }
  .row.with-status .status {
    display: none;
  }
}
@media (max-width: 599.98px) {
  .row,
  .row.with-status {
    grid-template-columns: minmax(0, 1fr) minmax(0, 42%);
    grid-template-areas: 'who wait' 'why code';
    row-gap: 2px;
    padding: var(--sp-2) var(--sp-4);
  }
  .code {
    grid-area: code;
    text-align: right;
    color: rgb(var(--v-theme-secondary));
  }
  .who {
    grid-area: who;
  }
  .why {
    grid-area: why;
  }
  .wait {
    grid-area: wait;
  }
  .overdue-word {
    display: none;
  }
}
</style>
