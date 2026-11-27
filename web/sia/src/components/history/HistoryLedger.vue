<script setup lang="ts">
/** A-15 Day ledger: filter strip (unit, scanned by, date presets, operation chips); movements grouped by Barbados day, newest first. */
import { DateField, OPERATION_LABELS, ShortRef } from '@cimh/web-app'
import { mdiArrowRight, mdiCheck } from '@mdi/js'
import { markRaw, onMounted, ref } from 'vue'
import { useFitToWindow } from '../../fit-scroller'
import QrScan from '../../icons/QrScan.vue'
import PersonPicker from '../PersonPicker.vue'
import { OP_ICONS, OPERATIONS, personPart, place, PRESETS, requestLink, shortUnit, timeOf, unitLink, useMovementHistory } from '../../history'

const scanIcon = markRaw(QrScan)

const { f, list, reload, active, clearAll, days, name } = useMovementHistory()

// Only the log scrolls (owner, 2026-11-26): it fills the window under the filters (fit-scroller.ts).
const strip = ref<HTMLElement | null>(null)
const log = ref<HTMLElement | null>(null)
const logFit = useFitToWindow(log, [strip])
onMounted(reload)
</script>

<template>
  <div class="ledger">
    <form ref="strip" class="strip" @submit.prevent="reload">
      <div class="fields">
        <v-text-field v-model="f.unit" label="Unit code" :prepend-inner-icon="scanIcon" class="mono-in" hide-details clearable @click:clear="(f.unit = ''), reload()" />
        <PersonPicker v-model="f.person" label="Scanned by" clearable hide-details />
        <v-btn-toggle v-model="f.preset" mandatory class="presets" density="compact" aria-label="When">
          <v-btn v-for="p in PRESETS" :key="p.value" :value="p.value" size="small">{{ p.title }}</v-btn>
        </v-btn-toggle>
        <v-btn type="submit" class="m3" variant="outlined">Apply</v-btn>
      </div>
      <div v-if="f.preset === 'custom'" class="custom">
        <DateField v-model="f.from" label="From" clearable hide-details />
        <DateField v-model="f.to" label="To" clearable hide-details />
      </div>
      <div class="ops" role="radiogroup" aria-label="Operation">
        <!-- Tonal buttons (owner 2026-11-25), as the /products type filters: the chosen one tonal primary with a check. -->
        <v-btn
          class="op-chip"
          variant="tonal"
          role="radio"
          :color="f.operation === null ? 'primary' : undefined"
          :prepend-icon="f.operation === null ? mdiCheck : undefined"
          :aria-checked="f.operation === null ? 'true' : 'false'"
          @click="f.operation = null"
        >All</v-btn>
        <v-btn
          v-for="op in OPERATIONS"
          :key="op"
          class="op-chip"
          variant="tonal"
          role="radio"
          :color="f.operation === op ? 'primary' : undefined"
          :prepend-icon="f.operation === op ? mdiCheck : OP_ICONS[op]"
          :aria-checked="f.operation === op ? 'true' : 'false'"
          @click="f.operation = f.operation === op ? null : op"
        >{{ OPERATION_LABELS[op] }}</v-btn>
        <button v-if="active.length" type="button" class="console-retry clear" @click="clearAll">Clear filters</button>
      </div>
    </form>

    <section ref="log" class="log" aria-label="Movements" tabindex="0" :style="logFit.style()">
      <div v-if="!list.loaded.value" class="pad" aria-busy="true"><div v-for="n in 6" :key="n" class="console-skel sk" /></div>
      <div v-else-if="!list.items.value.length" class="pad empty">
        <p class="t-body">No movements match.</p>
        <p class="t-caption muted">Widen the dates or clear a filter.</p>
      </div>
      <template v-else>
        <section v-for="d in days" :key="d.key" class="day" :aria-label="d.label">
          <header class="day-head">
            <h2 class="console-title">{{ d.label }}</h2>
            <span class="console-mono t-caption muted">{{ d.items.length }}{{ d === days[days.length - 1] && list.nextCursor.value ? '+' : '' }} {{ d.items.length === 1 ? 'move' : 'moves' }}</span>
          </header>
          <table class="rows">
            <thead class="sr-only"><tr><th>Time</th><th>What</th><th>Unit</th><th>Where</th><th>By</th></tr></thead>
            <TransitionGroup tag="tbody" name="row">
              <tr v-for="(h, i) in d.items" :key="`${h.unit}-${h.date}-${i}`" :style="{ '--i': Math.min(i, 10) }">
                <td class="t console-mono">{{ timeOf(h.date) }}</td>
                <td class="what" :data-op="h.operation">
                  <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path :d="OP_ICONS[h.operation]" fill="currentColor" /></svg>{{ OPERATION_LABELS[h.operation] }}
                </td>
                <td class="u"><router-link class="console-mono" :to="unitLink(h.unit)" :title="h.unit">{{ shortUnit(h.unit) }}</router-link></td>
                <td class="where">
                  <template v-if="h.from && place(h.from)"><span>{{ place(h.from) }}</span><svg viewBox="0 0 24 24" width="14" height="14" aria-label="to"><path :d="mdiArrowRight" fill="currentColor" /></svg></template>
                  <router-link v-if="h.shelf" class="place-link" :to="unitLink(h.shelf)">{{ place(h) }}</router-link>
                  <span v-if="personPart(h, name)">{{ personPart(h, name) }}</span>
                  <router-link v-if="h.orderId" class="console-mono" :to="requestLink(h.orderId)"><ShortRef :id="h.orderId" /></router-link>
                  <span v-if="h.reason" class="muted">“{{ h.reason }}”</span>
                </td>
                <td class="by">{{ name(h.user) }}</td>
              </tr>
            </TransitionGroup>
          </table>
        </section>
        <div v-if="list.nextCursor.value" class="pad"><v-btn class="m3" variant="outlined" :loading="list.loading.value" @click="list.loadMore">Load more</v-btn></div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.ledger {
  display: grid;
  gap: var(--sp-4);
}
.strip {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--sp-3);
}
.fields {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-3);
  align-items: center;
}
.fields > .v-input {
  flex: 1 1 220px;
}
.custom {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 220px));
  gap: var(--sp-3);
}
.mono-in :deep(input) {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}
.presets {
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  height: 40px;
}
.ops {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
  align-items: center;
}
.op-chip {
  flex: none; /* phones scroll the row sideways; buttons keep their width */
  height: 36px;
  font-size: 14px;
  letter-spacing: 0;
  text-transform: none;
  white-space: nowrap;
}
.op-chip:active {
  transform: scale(0.97);
}
/* The operation's icon is quiet on an unchosen button; the chosen one shows a check in the button's colour. */
.op-chip:not([aria-checked='true']) :deep(.v-btn__prepend) {
  color: rgb(var(--v-theme-secondary));
}
.clear {
  margin-left: var(--sp-2);
  font-size: 13px;
}
.log {
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
  /* The one scroller on the page (height set in the script). */
  overflow-y: auto;
  position: relative; /* contains absolute children (sr-only heads), so they scroll with it */
  overscroll-behavior: contain;
}
.log:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.day-head {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 44px;
  padding: 0 var(--sp-4);
  background: rgb(var(--v-theme-surface));
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.day + .day .day-head {
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.rows {
  width: 100%;
  border-collapse: collapse;
}
.rows td {
  padding: 10px var(--sp-3);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
  vertical-align: baseline;
}
.rows tr:last-child td {
  border-bottom: 0;
}
.rows tr:hover td {
  background: rgb(var(--v-theme-surface-bright));
}
.rows td:first-child {
  padding-left: var(--sp-4);
}
.t {
  width: 56px;
  font-size: 13px;
  color: rgb(var(--v-theme-secondary));
}
.what {
  width: 132px;
  font-weight: 500;
  white-space: nowrap;
}
.what svg {
  vertical-align: -4px;
  margin-right: 6px;
  color: rgb(var(--v-theme-secondary));
}
.u {
  width: 1%;
  white-space: nowrap;
  font-size: 13px;
}
.where {
  font-size: 13px;
}
.where a,
.u a {
  display: inline-block;
  min-height: 24px;
  line-height: 24px;
}
.where > * + * {
  margin-left: 8px;
}
.where svg {
  vertical-align: -2px;
  color: rgb(var(--v-theme-secondary));
}
.by {
  text-align: right;
  white-space: nowrap;
  color: rgb(var(--v-theme-secondary));
}
.pad {
  padding: var(--sp-4);
  display: grid;
  gap: var(--sp-3);
}
.sk {
  height: 28px;
}
.empty p {
  margin: 0;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
@media (max-width: 899.98px) {
  .rows,
  .rows tbody,
  .rows tr {
    display: block;
  }
  .rows tr {
    display: grid;
    grid-template-columns: 48px minmax(0, 1fr) auto;
    gap: 2px var(--sp-2);
    padding: 10px var(--sp-4);
    border-bottom: 1px solid rgb(var(--v-theme-seam));
  }
  .rows td {
    padding: 0 !important;
    border: 0;
    width: auto;
  }
  .u,
  .where {
    grid-column: 2 / -1;
  }
  .u {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .where {
    min-width: 0;
    overflow-wrap: anywhere; /* order ids (ORD + 32 hex) in "picked for" lines */
  }
  .by {
    grid-row: 1;
    grid-column: 3;
  }
}
@media (max-width: 599.98px) {
}
</style>
<style scoped>
/* Rows arrive with a short capped stagger; filtering swaps them in place. */
.row-enter-active {
  transition: opacity 220ms var(--ease-out), transform 220ms var(--ease-out);
  transition-delay: calc(var(--i, 0) * 24ms);
}
.row-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
@media (prefers-reduced-motion: reduce) {
  .row-enter-from {
    transform: none;
  }
}
/* Phones: the operation chips scroll sideways in one row instead of stacking four deep; so do the date
   presets (five buttons are ~400 px, wider than a 360 px screen). */
@media (max-width: 599.98px) {
  .presets {
    flex: 1 1 100%;
    min-width: 0;
    max-width: 100%;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .presets > .v-btn {
    flex: none;
  }
  .custom {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .ops {
    flex-wrap: nowrap;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .op-chip {
    flex: none;
  }
}
</style>
