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
/** Actors without a stored name come through as their email; show the part before @ (full email on hover) so the column never breaks mid-word. */
const byName = (n: string) => (n.includes('@') ? n.slice(0, n.indexOf('@')) : n)
</script>

<template>
  <div class="rt">
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
          <td class="tnum when">{{ formatDateTime(h.at) }}</td>
          <td class="what">{{ h.from ? `${statusLabel(h.from)} → ` : '' }}{{ statusLabel(h.to) }}</td>
          <td class="by" :title="h.by.name">{{ byName(h.by.name) }} <span class="muted">({{ h.by.role }})</span></td>
          <td v-if="h.reason" class="why">{{ h.reason }}</td>
          <td v-else class="why empty" />
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
/* Not reached yet: medium emphasis in the theme's AA text colour (an opacity fade measured 3.1:1). */
.timeline .todo {
  color: rgb(var(--v-theme-on-surface-variant));
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
.rt {
  container: rtimeline / inline-size;
}
.history td {
  overflow-wrap: anywhere;
}
.history .when {
  white-space: nowrap;
}
/* Narrow panels (phones, the request beside the queue): each entry stacks (when, then what, then who and why)
   instead of a four-column table whose dates wrapped to four lines and whose names were cut. */
@container rtimeline (max-width: 559.98px) {
  .history thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }
  .history :deep(table),
  .history tbody,
  .history tr,
  .history td {
    display: block;
  }
  .history tr {
    padding: var(--sp-2) 0;
    border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  }
  .history :deep(tbody tr > td) {
    height: auto !important;
    padding: 0 !important;
    border: 0 !important;
  }
  .history .when {
    font-size: 12px;
    color: rgb(var(--v-theme-secondary));
  }
  .history .what {
    font-weight: 600;
  }
  .history .why.empty {
    display: none;
  }
}
</style>
