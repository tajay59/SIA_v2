<script setup lang="ts">
/**
 * Selected-request panel (Graphite Console), shared by the dashboard (A-01) and the desk (A-02): who it is
 * from, the next step with the actions allowed now (Start quoting / Approve run here; quote, purchase orders,
 * pick, ship and deliver open their screens), key facts, the items and customer note, then the way out to
 * the full request and, isolated, Reject. Emits `changed` after an action so the queue and counts refresh.
 */
import {
  act,
  ApiError,
  fileUrl,
  getRequest,
  type OrderRequest,
  ReasonDialog,
  requestTitle,
  ShortRef,
  type RequestSummary,
  StatusChip,
  useNotify,
} from '@cimh/web-app'
import { mdiArrowRight } from '@mdi/js'
import { computed, ref, watch } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import { BTN, expiresSoon, fmtDate, TONE_ICON, waited, why } from '../request-queue'

const props = defineProps<{ summary: RequestSummary | null; openTo?: RouteLocationRaw }>()
const emit = defineEmits<{ changed: [] }>()
const notify = useNotify()

const detail = ref<OrderRequest | null>(null)
const failed = ref(false)
const busy = ref(false)
const id = computed(() => props.summary?.id ?? null)

async function load(target: string | null) {
  detail.value = null
  failed.value = false
  if (!target) return
  try {
    const r = await getRequest(target)
    if (id.value === target) detail.value = r
  } catch {
    if (id.value === target) failed.value = true
  }
}
watch(id, (v) => void load(v), { immediate: true })
// A refreshed summary with a new status means the record moved on elsewhere: reload its actions.
watch(
  () => props.summary?.status,
  (s, before) => {
    if (before && s !== before && detail.value?.status !== s) void load(id.value)
  },
)

const can = (a: string) => detail.value?.allowedActions?.includes(a as never) ?? false
const signed = computed(() => detail.value?.agreement?.signedFileId ?? null)

async function run(path: Parameters<typeof act>[1], body: unknown, done: string): Promise<boolean> {
  if (!detail.value) return false
  busy.value = true
  try {
    detail.value = await act(detail.value, path, body)
    notify.toast(done, 'success')
    emit('changed')
    return true
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) await load(id.value)
    notify.report(e)
    return false
  } finally {
    busy.value = false
  }
}
const rejecting = ref(false)
async function submitReject(reason: string) {
  if (await run('/requests/{requestId}/reject', { reason }, 'Request rejected')) rejecting.value = false
}
</script>

<template>
  <section class="request-detail" aria-labelledby="d-title">
    <template v-if="summary">
      <header class="console-head head">
        <h2 id="d-title" class="console-title">Selected request</h2>
        <StatusChip :status="summary.status" />
      </header>
      <div :key="summary.id" class="body console-scroll">
        <div class="ident">
          <p class="ident-name">
            {{ requestTitle(summary.firstItemName, summary.lineCount, summary.type) }}
            <span v-if="summary.type === 'PROBONO'" class="probono-badge">Pro Bono</span>
          </p>
          <p class="ident-sub">
            {{ [summary.organisationName, summary.customerName || summary.customer].filter(Boolean).join(' · ') }}
          </p>
          <p class="code-full"><ShortRef :id="summary.id" /></p>
        </div>

        <section class="next" :class="why(summary).tone" aria-labelledby="next-title">
          <h3 id="next-title" class="sub-title console-title">Next step</h3>
          <p class="next-text">
            <v-icon :icon="TONE_ICON[why(summary).tone]" size="18" />{{ why(summary).text }}
          </p>
          <div class="next-actions" aria-live="polite">
            <p v-if="failed" class="t-caption muted">
              Couldn't load the actions ·
              <button type="button" class="console-retry" @click="load(id)">Retry</button>
            </p>
            <div v-else-if="!detail" class="act-skel console-skel" />
            <template v-else>
              <v-btn
                v-if="can('start-quoting')"
                class="m3"
                :prepend-icon="BTN.quote"
                color="primary"
                :loading="busy"
                @click="run('/requests/{requestId}/start-quoting', undefined, 'Quoting started; stock checked')"
              >Start quoting</v-btn>
              <v-btn v-if="can('quote-draft')" class="m3" :prepend-icon="BTN.draft" :to="`/requests/${detail.id}/quote`" :color="detail.status === 'QUOTED' ? undefined : 'primary'" :variant="detail.status === 'QUOTED' ? 'outlined' : 'flat'">
                {{ detail.status === 'QUOTED' ? 'Revise quote' : 'Build quote' }}
              </v-btn>
              <v-btn
                v-if="can('approve')"
                class="m3"
                :prepend-icon="BTN.approve"
                color="primary"
                :loading="busy"
                @click="run('/requests/{requestId}/approve', undefined, 'Approved; stock is being reserved')"
              >Approve</v-btn>
              <template v-if="can('purchase-orders')">
                <v-btn :to="`/requests/${detail.id}`" class="m3" color="primary" :prepend-icon="BTN.verify">Verify and purchase</v-btn>
                <v-btn v-if="signed" :href="fileUrl(signed)" target="_blank" variant="outlined" class="m3" :prepend-icon="BTN.signed">
                  Signed agreement
                </v-btn>
              </template>
              <v-btn v-if="can('pick')" class="m3" :prepend-icon="BTN.pick" :to="{ path: '/pick', query: { op: 'order', request: detail.id } }" color="primary">
                Pick
              </v-btn>
              <v-btn
                v-if="can('ship') || can('deliver')"
                class="m3"
                :prepend-icon="can('ship') ? BTN.ship : BTN.deliver"
                :to="`/requests/${detail.id}`"
                color="primary"
              >
                {{ can('ship') ? 'Record shipment' : 'Mark delivered' }}
              </v-btn>
              <p v-if="!detail.allowedActions?.length" class="t-caption muted">Nothing for staff to do on this request now.</p>
            </template>
          </div>
        </section>

        <dl class="facts">
          <div><dt>Type</dt><dd>{{ summary.type === 'PROBONO' ? 'Pro Bono' : 'Paid' }}</dd></div>
          <div v-if="summary.currency"><dt>Currency</dt><dd class="console-mono">{{ summary.currency }}</dd></div>
          <div><dt>Submitted</dt><dd class="console-mono">{{ fmtDate(summary.submittedAt) }}</dd></div>
          <div><dt>In this status</dt><dd class="console-mono">{{ waited(summary) }}</dd></div>
          <div v-if="summary.quoteExpiresAt">
            <dt>Quote expires</dt>
            <dd class="console-mono" :class="{ expiring: expiresSoon(summary) }">{{ fmtDate(summary.quoteExpiresAt) }}</dd>
          </div>
        </dl>

        <section class="items" aria-labelledby="items-title">
          <h3 id="items-title" class="sub-title console-title">
            Items <span class="console-mono muted">{{ summary.lineCount }}</span>
          </h3>
          <ul v-if="detail" class="item-list">
            <li v-for="l in detail.lines.slice(0, 6)" :key="l.lineId">
              <span class="item-qty console-mono">{{ l.qty }}×</span>
              <span class="item-name">{{ l.product.name }}</span>
            </li>
            <li v-if="detail.lines.length > 6" class="muted">and {{ detail.lines.length - 6 }} more</li>
          </ul>
          <div v-else-if="!failed" class="items-skel console-skel" />
          <p v-if="detail?.notes" class="note"><span class="muted">Customer note:</span> {{ detail.notes }}</p>
        </section>

        <footer class="foot">
          <router-link :to="openTo ?? `/requests/${summary.id}`" class="open-link">
            Open full request <v-icon :icon="mdiArrowRight" size="16" />
          </router-link>
          <v-btn v-if="can('reject')" variant="outlined" class="m3 m3-danger" :prepend-icon="BTN.reject" :disabled="busy" @click="rejecting = true">
            Reject request
          </v-btn>
        </footer>
      </div>
    </template>
    <div v-else class="empty">
      <p class="muted">Select a request to see it here.</p>
    </div>

    <ReasonDialog
      v-model="rejecting"
      title="Reject this Pro Bono request?"
      confirm="Reject request"
      text="The customer is told why."
      danger
      :busy="busy"
      @submit="submitReject"
    />
  </section>
</template>

<style scoped>
.head {
  background: rgb(var(--v-theme-primary-subtle));
}
.head .console-title {
  color: rgb(var(--v-theme-primary));
}
.body {
  padding: var(--sp-4);
  display: flex;
  flex-direction: column;
  gap: 20px;
  animation: console-swap-in 200ms var(--ease-out) both;
}
.body p {
  margin: 0;
}
.ident-name {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-2);
  font-size: 20px;
  line-height: 26px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.body .ident-sub {
  margin-top: 2px;
  font-size: 14px;
  color: rgb(var(--v-theme-secondary));
}
.body .code-full {
  margin-top: var(--sp-1);
  font: 400 12px/16px 'JetBrains Mono', ui-monospace, monospace;
  color: rgb(var(--v-theme-secondary));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sub-title {
  margin: 0;
  display: flex;
  align-items: baseline;
  gap: var(--sp-2); /* type from .console-title */
}
/* Next step: the one decision on this panel, so it is the one coloured region (impeccable colorize 2026-11-16).
   The tone owns the well: a wash and a full edge in its hue, the label and icon in the hue, the sentence in ink.
   Staff's move (act, fulfil) = Action Blue; urgent = amber; expiring = red. Waiting on the customer and closed
   stay graphite, so colour here always means "staff act now". */
.next {
  --tone: var(--v-theme-primary);
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-4) var(--sp-4) var(--sp-4);
  border: 1px solid rgba(var(--tone), 0.55);
  border-radius: 4px;
  background: rgba(var(--tone), 0.12);
  transition: background-color 240ms ease-out, border-color 240ms ease-out;
}
.next.urgent {
  --tone: var(--v-theme-warning);
}
.next.expiring {
  --tone: var(--v-theme-error);
}
.next.wait,
.next.closed {
  border-color: rgb(var(--v-theme-seam));
  background: rgb(var(--v-theme-surface-variant));
}
.next .sub-title {
  color: rgb(var(--tone));
}
.next.wait .sub-title,
.next.closed .sub-title {
  color: inherit;
}
.next-text {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: 18px;
  line-height: 24px;
  font-weight: 700;
  color: rgb(var(--v-theme-on-surface));
}
.next-text .v-icon {
  color: rgb(var(--tone));
}
.next.wait .next-text,
.next.closed .next-text {
  font-size: 16px;
  font-weight: 600;
}
.next.wait .next-text .v-icon,
.next.closed .next-text .v-icon {
  color: rgb(var(--v-theme-secondary));
}
.next-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-2);
  margin-top: var(--sp-1);
}
.next-actions .v-btn {
  animation: console-fade-in 180ms ease-out both;
}
.act-skel {
  width: 140px;
  height: 40px;
  border-radius: 999px;
}
.facts {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(112px, 1fr));
  margin: 0;
  border-top: 1px solid rgb(var(--v-theme-seam));
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.facts > div {
  padding: var(--sp-2) 0;
}
.facts dt {
  font-size: 12px;
  line-height: 16px;
  color: rgb(var(--v-theme-secondary));
}
.facts dd {
  margin: 2px 0 0;
  font-size: 14px;
  line-height: 20px;
}
.facts dd.expiring {
  color: rgb(var(--v-theme-error));
  font-weight: 600;
}
.items {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.item-list {
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: 14px;
  line-height: 20px;
  animation: console-fade-in 180ms ease-out both;
}
.item-list li {
  display: flex;
  gap: var(--sp-3);
  padding: 6px 0;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.item-list li:last-child {
  border-bottom: 0;
}
.item-qty {
  flex: none;
  min-width: 3ch;
  text-align: right;
  color: rgb(var(--v-theme-secondary));
}
.item-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.items-skel {
  height: 64px;
  border-radius: 4px;
}
.note {
  font-size: 13px;
  line-height: 18px;
  max-width: 65ch;
}
/* The way out on the left, the destructive action alone on the right. */
.foot {
  margin-top: auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--sp-3);
  padding-top: var(--sp-3);
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.open-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 24px;
  font-size: 14px;
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
}
.open-link .v-icon {
  transition: transform 160ms var(--ease-out);
}
.open-link:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.open-link:hover .v-icon {
  transform: translateX(3px);
}
.empty {
  padding: var(--sp-8) var(--sp-4);
}
.empty p {
  margin: 0;
}
@media (prefers-reduced-motion: reduce) {
  .body {
    animation-name: console-fade-in;
  }
  .open-link .v-icon {
    transition: none;
  }
}
</style>
