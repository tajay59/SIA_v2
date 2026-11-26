<script setup lang="ts">
/** A-15 Day ledger: filter strip (unit, scanned by, date presets, operation chips); movements grouped by Barbados day, newest first. */
import { DateField, OPERATION_LABELS, ShortRef } from '@cimh/web-app'
import { mdiArrowRight } from '@mdi/js'
import { markRaw, onMounted } from 'vue'
import QrScan from '../../icons/QrScan.vue'
import PersonPicker from '../PersonPicker.vue'
import { OP_ICONS, OPERATIONS, personPart, place, PRESETS, requestLink, shortUnit, timeOf, unitLink, useMovementHistory } from '../../history'

const scanIcon = markRaw(QrScan)

const { f, list, reload, active, clearAll, days, name } = useMovementHistory()
onMounted(reload)
</script>

<template>
  <div class="ledger">
    <form class="strip" @submit.prevent="reload">
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
        <button type="button" role="radio" class="op-chip" :aria-checked="f.operation === null" @click="f.operation = null">All</button>
        <button v-for="op in OPERATIONS" :key="op" type="button" role="radio" class="op-chip" :aria-checked="f.operation === op" @click="f.operation = f.operation === op ? null : op">
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path :d="OP_ICONS[op]" fill="currentColor" /></svg>{{ OPERATION_LABELS[op] }}
        </button>
        <button v-if="active.length" type="button" class="console-retry clear" @click="clearAll">Clear filters</button>
      </div>
    </form>

    <section class="log" aria-label="Movements">
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
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px 0 10px;
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 8px;
  font: 500 13px/18px inherit;
  color: rgb(var(--v-theme-on-surface));
  background: transparent;
  cursor: pointer;
  transition: background-color 120ms ease;
}
.op-chip:hover {
  background: rgb(var(--v-theme-surface-bright));
}
.op-chip[aria-checked='true'] {
  background: rgb(var(--v-theme-primary-subtle));
  border-color: rgb(var(--v-theme-primary));
}
.op-chip svg {
  color: rgb(var(--v-theme-secondary));
}
.op-chip[aria-checked='true'] svg {
  color: rgb(var(--v-theme-primary));
}
.clear {
  margin-left: var(--sp-2);
  font-size: 13px;
}
.log {
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
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
