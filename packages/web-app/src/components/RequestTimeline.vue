<script setup lang="ts">
/**
 * Status timeline of a request (DESIGN_BRIEF "status timeline"): the steps of its flow, done ones ticked
 * with the date, the current one highlighted. A closed request (cancelled, rejected) ends with that status
 * and its reason. The full history (who, when) is listed below when `history` is on (staff).
 */
import { formatDateTime, statusLabel } from '@cimh/web-ui'
import { mdiCheck, mdiClose } from '@mdi/js'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { isClosed, type OrderRequest, statusSteps } from '../orders'

const props = defineProps<{ request: OrderRequest; history?: boolean }>()

// Vuetify v-timeline: across the panel when every step gets ~132 px (dates fit on one line), else down it
// (phones, the request beside the queue). Measured on the panel, not the window.
const STEP_MIN = 132
const root = ref<HTMLElement | null>(null)
const width = ref(0)
let ro: ResizeObserver | null = null
onMounted(() => {
  if (!root.value) return
  width.value = root.value.clientWidth
  // Applied on the next frame: flipping horizontal/vertical inside the callback resizes what it watches in the same
  // frame (a "ResizeObserver loop" error).
  let frame = 0
  ro = new ResizeObserver(([e]) => {
    const w = e?.contentRect.width ?? width.value
    cancelAnimationFrame(frame)
    frame = requestAnimationFrame(() => (width.value = w))
  })
  ro.observe(root.value)
})
onBeforeUnmount(() => ro?.disconnect())
const horizontal = computed(() => width.value >= steps.value.length * STEP_MIN)

type StepState = 'done' | 'current' | 'todo' | 'closed'
const DOT: Record<StepState, { color?: string; icon?: string }> = {
  done: { color: 'success', icon: mdiCheck },
  current: { color: 'primary' },
  todo: {},
  closed: { color: 'error', icon: mdiClose },
}

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
      state: (s === r.status ? 'current' : reached.has(s) ? 'done' : 'todo') as StepState,
    }))
  if (closed) out.push({ status: r.status, at: reached.get(r.status) ?? null, state: 'closed' as StepState })
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
  <div ref="root" class="rt">
    <!-- v-timeline renders divs, so the list semantics are given by role (an <ol> may only hold <li>). -->
    <v-timeline
      role="list"
      aria-label="Request status"
      class="timeline"
      :class="{ across: horizontal }"
      :direction="horizontal ? 'horizontal' : 'vertical'"
      :align="horizontal ? 'center' : 'start'"
      side="end"
      density="compact"
      size="x-small"
      line-thickness="2"
      truncate-line="both"
    >
      <v-timeline-item
        v-for="s in steps"
        :key="s.status"
        role="listitem"
        class="step"
        :class="s.state"
        :aria-current="s.state === 'current' ? 'step' : undefined"
        :dot-color="DOT[s.state].color"
        :icon="DOT[s.state].icon"
        :fill-dot="s.state !== 'todo'"
      >
        <span class="t-label step-name">{{ statusLabel(s.status) }}</span>
        <span v-if="s.at" class="t-caption step-at">{{ formatDateTime(s.at) }}</span>
        <span v-else-if="s.state === 'todo'" class="d-sr-only">not reached yet</span>
      </v-timeline-item>
    </v-timeline>
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
/* ---- Vuetify v-timeline, tuned to the console: 22 px dots, labels close under (or beside) them. */
.timeline.across {
  grid-auto-columns: minmax(0, 1fr);
  column-gap: 0;
}
.timeline.v-timeline--vertical {
  row-gap: var(--sp-3);
}
.step :deep(.v-timeline-item__body) {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.across .step :deep(.v-timeline-item__body) {
  padding-block-start: var(--sp-2) !important;
  align-items: center;
  text-align: center;
}
.timeline.v-timeline--vertical .step :deep(.v-timeline-item__body) {
  padding-inline-start: var(--sp-3) !important;
  min-height: 22px;
  justify-content: center;
}
.step-name {
  color: rgb(var(--v-theme-on-surface));
}
.step-at {
  color: rgb(var(--v-theme-on-surface-variant));
  white-space: nowrap;
}
.current .step-name {
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
}
.current .step-at {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 600;
}
/* Not reached yet: medium emphasis in the theme's AA text colour (an opacity fade measured 3.1:1). */
.todo .step-name {
  color: rgb(var(--v-theme-on-surface-variant));
}
.closed .step-name {
  color: rgb(var(--v-theme-error));
  font-weight: 600;
}
/* Dots: done = success with a tick, current = primary with a soft ring, closed = error with a cross,
   not reached = a hollow ring in the medium-emphasis colour (3:1 on the panel, WCAG 1.4.11). */
.current :deep(.v-timeline-divider__dot) {
  box-shadow: 0 0 0 4px rgba(var(--v-theme-primary), 0.24);
}
.todo :deep(.v-timeline-divider__dot) {
  background: transparent;
  box-shadow: inset 0 0 0 2px rgb(var(--v-theme-on-surface-variant));
}
.todo :deep(.v-timeline-divider__inner-dot) {
  background: transparent;
}
/* The line is filled as far as the request has got: into and out of every done step, into the current one. */
/* Solid colour: Vuetify's segments overlap between items, so a translucent line showed darker dashes. */
.step :deep(.v-timeline-divider__before),
.step :deep(.v-timeline-divider__after) {
  background: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 20%, rgb(var(--v-theme-surface)));
}
.done :deep(.v-timeline-divider__before),
.done :deep(.v-timeline-divider__after),
.current :deep(.v-timeline-divider__before) {
  background: rgb(var(--v-theme-success));
}
.closed :deep(.v-timeline-divider__before) {
  background: rgb(var(--v-theme-error));
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
