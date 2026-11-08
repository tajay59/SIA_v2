<script setup lang="ts">
/**
 * Status timeline of a request (DESIGN_BRIEF "status timeline"): the steps of its flow, done ones ticked
 * with the date, the current one highlighted. A closed request (cancelled, rejected) ends with that status
 * and its reason. The full history (who, when) is listed below when `history` is on (staff).
 */
import { formatDateTime, statusLabel } from '@cimh/web-ui'
import { mdiCheckCircle, mdiCircleOutline, mdiCloseCircle, mdiRadioboxMarked } from '@mdi/js'
import { computed } from 'vue'
import { isClosed, type OrderRequest, statusSteps } from '../orders'

const props = defineProps<{ request: OrderRequest; history?: boolean }>()

const steps = computed(() => {
  const r = props.request
  const reached = new Map<string, string>()
  for (const h of r.history ?? []) if (!reached.has(h.to)) reached.set(h.to, h.at)
  const flow = statusSteps(r.type)
  const closed = isClosed(r.status)
  const out = flow
    .filter((s) => !closed || reached.has(s))
    .map((s) => ({
      status: s,
      at: reached.get(s) ?? null,
      state: s === r.status ? 'current' : reached.has(s) ? 'done' : 'todo',
    }))
  if (closed) out.push({ status: r.status, at: reached.get(r.status) ?? null, state: 'closed' })
  return out
})
const closingReason = computed(() => {
  const r = props.request
  return (r.cancellation as { reason?: string } | null)?.reason ?? (r.rejection as { reason?: string } | null)?.reason ?? null
})
</script>

<template>
  <div>
    <ol class="timeline" aria-label="Request status">
      <li v-for="s in steps" :key="s.status" :class="s.state" :aria-current="s.state === 'current' ? 'step' : undefined">
        <v-icon
          size="20"
          :icon="s.state === 'done' ? mdiCheckCircle : s.state === 'current' ? mdiRadioboxMarked : s.state === 'closed' ? mdiCloseCircle : mdiCircleOutline"
        />
        <span class="t-label">{{ statusLabel(s.status) }}</span>
        <span v-if="s.at" class="t-caption muted">{{ formatDateTime(s.at) }}</span>
      </li>
    </ol>
    <p v-if="closingReason" class="t-body reason">Reason: {{ closingReason }}</p>
    <v-table v-if="history" density="compact" class="history">
      <thead>
        <tr><th>When</th><th>Status</th><th>By</th><th>Reason</th></tr>
      </thead>
      <tbody>
        <tr v-for="(h, i) in request.history" :key="i">
          <td class="tnum">{{ formatDateTime(h.at) }}</td>
          <td>{{ h.from ? `${statusLabel(h.from)} → ` : '' }}{{ statusLabel(h.to) }}</td>
          <td>{{ h.by.name }} <span class="muted">({{ h.by.role }})</span></td>
          <td>{{ h.reason ?? '' }}</td>
        </tr>
      </tbody>
    </v-table>
  </div>
</template>

<style scoped>
.timeline {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2) var(--sp-4);
  padding: 0;
  margin: 0;
}
.timeline li {
  display: grid;
  grid-template-columns: auto auto;
  column-gap: var(--sp-1);
  align-items: center;
}
.timeline li .t-caption {
  grid-column: 2;
}
.timeline .done {
  color: rgb(var(--v-theme-success));
}
.timeline .current {
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
}
.timeline .todo {
  opacity: 0.55;
}
.timeline .closed {
  color: rgb(var(--v-theme-error));
}
.reason {
  margin-top: var(--sp-2);
}
.history {
  margin-top: var(--sp-4);
}
</style>
