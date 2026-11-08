<script setup lang="ts">
/**
 * A-10 pick (legacy SIA /pick: operation buttons Pick · Relocate · Pick Order; v2 adds Issue / Return,
 * the legacy "self-stow"). Every scan is one request with its own Idempotency-Key; the list shows ✓ / ✗.
 *   Pick       reason once, then scan units (reserved units can only be picked for their request)
 *   Relocate   scan the target shelf, then the units to move there
 *   Issue      choose the person, then scan units (Return: scan units coming back)
 *   Pick Order open a request (scan or type its id; A-03 "Pick" opens it prefilled), then scan units: each
 *              goes to the first line of that product still short (order-svc → inventory, reserved units only)
 */
import {
  type AccountSummary,
  ApiError,
  call,
  getRequest,
  inventory,
  newScanKey,
  type OrderRequest,
  pickForRequest,
  scan,
  scanError,
  type Shelf,
  unitWhere,
} from '@cimh/web-app'
import { mdiAccountArrowRightOutline, mdiArrowDecisionOutline, mdiClipboardListOutline, mdiHandBackRightOutline } from '@mdi/js'
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PersonPicker from '../components/PersonPicker.vue'
import ScanField from '../components/ScanField.vue'
import ScanLog, { type ScanEntry } from '../components/ScanLog.vue'

definePage({ meta: { guard: 'staff', title: 'Pick' } })
const route = useRoute()
const router = useRouter()

const OPS = [
  { key: 'pick', title: 'Pick', icon: mdiHandBackRightOutline, text: 'Take units off the shelf, with a reason' },
  { key: 'relocate', title: 'Relocate', icon: mdiArrowDecisionOutline, text: 'Move units to another shelf' },
  { key: 'issue', title: 'Issue / Return', icon: mdiAccountArrowRightOutline, text: 'Units a person takes and brings back' },
  { key: 'order', title: 'Pick Order', icon: mdiClipboardListOutline, text: 'Pick the reserved units of a request' },
] as const
type Op = (typeof OPS)[number]['key']
const op = computed<Op | null>(() => (OPS.some((o) => o.key === route.query.op) ? (route.query.op as Op) : null))
function choose(key: Op) {
  entries.value = []
  void router.replace({ query: op.value === key ? {} : { op: key } })
}

const entries = ref<ScanEntry[]>([])
let seq = 0
function run(code: string, path: '/pick' | '/relocate' | '/assign' | '/unassign', body: Record<string, unknown>, done: string, key = newScanKey(), id = ++seq) {
  const entry: ScanEntry = { id, code, ok: null, text: 'Saving…' }
  entries.value = [entry, ...entries.value.filter((e) => e.id !== id)]
  scan(path, { unit: code, ...body }, key)
    .then((u) => set(id, { ok: true, text: `${u.productName ?? u.product} · ${done === 'where' ? unitWhere(u) : done}` }))
    .catch((e) => set(id, { ok: false, text: scanError(e), retry: () => run(code, path, body, done, key, id) }))
}
function set(id: number, patch: Partial<ScanEntry>) {
  entries.value = entries.value.map((e) => (e.id === id ? { ...e, ...patch, retry: patch.retry } : e))
}

// Pick. Focus the reason when the panel opens (not Vuetify autofocus: it can fire late and steal a scan).
const reason = ref('')
const reasonField = ref<{ focus: () => void } | null>(null)
watch(op, (o) => o === 'pick' && void nextTick(() => reasonField.value?.focus()), { immediate: true })
// Relocate
const target = ref<Shelf | null>(null)
const targetError = ref('')
async function chooseTarget(code: string) {
  targetError.value = ''
  try {
    target.value = await call(() => inventory.GET('/shelves/{barcode}', { params: { path: { barcode: code } } }))
  } catch (e) {
    targetError.value = e instanceof ApiError && e.status === 404 ? 'No shelf with this code.' : scanError(e)
  }
}
// Issue / Return
const person = ref<AccountSummary | null>(null)
const issueMode = ref<'issue' | 'return'>('issue')
// Pick Order
const order = ref<OrderRequest | null>(null)
const orderError = ref('')
const pickable = computed(() =>
  (order.value?.lines ?? []).filter((l) => order.value!.type === 'PROBONO' || l.choice === 'CIMH'),
)
async function openOrder(code: string) {
  orderError.value = ''
  try {
    const r = await getRequest(code.trim())
    if (!r.allowedActions?.includes('pick')) {
      orderError.value = `Request ${r.id} has nothing to pick now (status ${r.status.toLowerCase().replace(/_/g, ' ')}).`
      return
    }
    order.value = r
  } catch (e) {
    orderError.value = e instanceof ApiError && e.status === 404 ? 'No request with this id.' : scanError(e)
  }
}
watch(
  () => [op.value, route.query.request] as const,
  ([o, id]) => o === 'order' && typeof id === 'string' && id && order.value?.id !== id && void openOrder(id),
  { immediate: true },
)
function pickUnit(code: string, key = newScanKey(), id = ++seq) {
  const r = order.value
  if (!r) return
  const line = pickable.value.find(
    (l) => (code.includes('_') ? code.startsWith(`${l.productId}_`) : true) && (l.picked?.length ?? 0) < l.qty,
  )
  entries.value = [{ id, code, ok: null, text: 'Saving…' }, ...entries.value.filter((e) => e.id !== id)]
  if (!line) return set(id, { ok: false, text: 'No line of this request still needs this product' })
  pickForRequest(r.id, line.lineId, code, key)
    .then((u) => {
      order.value = u
      const l = u.lines.find((x) => x.lineId === line.lineId)!
      set(id, { ok: true, text: `${l.product.name} · ${l.picked?.length ?? 0} of ${l.qty} picked` })
    })
    .catch((e) => set(id, { ok: false, text: scanError(e), retry: () => pickUnit(code, key, id) }))
}
const allPicked = computed(() => pickable.value.every((l) => (l.picked?.length ?? 0) >= l.qty))
</script>

<template>
  <div class="page stack">
    <div class="ops" role="group" aria-label="Pick operations">
      <button
        v-for="o in OPS"
        :key="o.key"
        type="button"
        class="op"
        :class="{ on: op === o.key, dim: op && op !== o.key }"
        :aria-pressed="op === o.key"
        @click="choose(o.key)"
      >
        <v-icon :icon="o.icon" size="28" />
        <span class="t-h3">{{ o.title }}</span>
        <span class="t-caption muted">{{ o.text }}</span>
      </button>
    </div>

    <section v-if="op === 'pick'" class="step">
      <div class="instructions">
        <h2 class="t-h3">Pick with a reason</h2>
        <p class="t-body muted">Write why the units leave the shelf (repair, station visit…), then scan each unit. Units reserved for a request are picked from the request.</p>
      </div>
      <div class="stack">
        <v-text-field ref="reasonField" v-model="reason" label="Reason" counter="300" maxlength="300" />
        <ScanField label="Unit" :loading="false" @scan="(c) => reason.trim() && run(c, '/pick', { reason: reason.trim() }, 'picked')" />
        <p v-if="!reason.trim()" class="t-caption muted">Enter a reason first.</p>
        <ScanLog :entries="entries" />
      </div>
    </section>

    <section v-else-if="op === 'relocate'" class="step">
      <div class="instructions">
        <h2 class="t-h3">Move units</h2>
        <p class="t-body muted">Scan the shelf the units go to, then scan each unit.</p>
      </div>
      <div class="stack">
        <ScanField v-if="!target" label="Target shelf" autofocus @scan="chooseTarget" />
        <v-alert v-if="targetError" type="error" variant="tonal" density="compact">{{ targetError }}</v-alert>
        <div v-if="target" class="row">
          <span class="t-body">Moving to <strong>{{ target.locationName ?? target.location }} · shelf {{ target.number }}</strong></span>
          <v-btn size="small" variant="outlined" @click="target = null">Change shelf</v-btn>
        </div>
        <template v-if="target">
          <ScanField label="Unit" autofocus @scan="(c) => run(c, '/relocate', { toShelf: target!.barcode }, 'where')" />
          <ScanLog :entries="entries" />
        </template>
      </div>
    </section>

    <section v-else-if="op === 'issue'" class="step">
      <div class="instructions">
        <h2 class="t-h3">Issue or return</h2>
        <p class="t-body muted">Issued units leave the shelf and show under Reports → Who has what. Returned units must be stowed again.</p>
        <v-btn-toggle v-model="issueMode" mandatory color="primary" density="comfortable" variant="outlined">
          <v-btn value="issue">Issue</v-btn>
          <v-btn value="return">Return</v-btn>
        </v-btn-toggle>
      </div>
      <div class="stack">
        <template v-if="issueMode === 'issue'">
          <PersonPicker v-model="person" label="Issue to" />
          <ScanField v-if="person" label="Unit" autofocus @scan="(c) => run(c, '/assign', { accountId: person!.id }, `with ${person!.firstname} ${person!.lastname}`)" />
        </template>
        <ScanField v-else label="Unit coming back" autofocus @scan="(c) => run(c, '/unassign', {}, 'returned; stow it on a shelf')" />
        <ScanLog :entries="entries" />
      </div>
    </section>

    <section v-else-if="op === 'order'" class="step">
      <div class="instructions">
        <h2 class="t-h3">Pick a request</h2>
      </div>
      <div class="stack">
        <ScanField v-if="!order" label="Request id" autofocus @scan="openOrder" />
        <v-alert v-if="orderError" type="error" variant="tonal" density="compact">{{ orderError }}</v-alert>
        <template v-if="order">
          <div class="row">
            <span class="t-body">Request <router-link :to="`/requests/${order.id}`" class="t-mono">{{ order.id }}</router-link> · {{ order.customerName }}</span>
            <v-btn size="small" variant="outlined" @click="(order = null), (entries = [])">Other request</v-btn>
          </div>
          <v-table density="compact">
            <thead><tr><th>Item</th><th>Reserved units</th><th class="text-right">Picked</th></tr></thead>
            <tbody>
              <tr v-for="l in pickable" :key="l.lineId">
                <td>{{ l.product.name }}</td>
                <td class="t-mono t-caption">{{ (l.reservation?.units ?? []).join(', ') || (l.reservation?.status === 'FAILED' ? 'Not enough stock: requote' : 'Reserving…') }}</td>
                <td class="text-right tnum">{{ l.picked?.length ?? 0 }} / {{ l.qty }}</td>
              </tr>
            </tbody>
          </v-table>
          <v-alert v-if="allPicked" type="success" variant="tonal" density="compact">
            Everything is picked. <router-link :to="`/requests/${order.id}`">Record the shipment</router-link> on the request.
          </v-alert>
          <ScanField v-else label="Unit" autofocus @scan="(c) => pickUnit(c)" />
          <ScanLog :entries="entries" />
        </template>
      </div>
    </section>

    <p v-else class="t-body muted">Choose an operation.</p>
  </div>
</template>

<style scoped>
.page {
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
}
.ops {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--sp-4);
}
.op {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--sp-1);
  padding: var(--sp-4);
  border-radius: 12px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgb(var(--v-theme-surface));
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.op:hover,
.op:focus-visible {
  border-color: rgb(var(--v-theme-primary));
}
.op.on {
  border: 2px solid rgb(var(--v-theme-primary));
  padding: calc(var(--sp-4) - 1px);
}
.op.on .v-icon {
  color: rgb(var(--v-theme-primary));
}
.op.dim {
  opacity: 0.7;
}
.step {
  display: grid;
  grid-template-columns: minmax(200px, 1fr) minmax(0, 2fr);
  gap: var(--sp-6);
  align-items: start;
}
@media (max-width: 959px) {
  .step {
    grid-template-columns: minmax(0, 1fr);
  }
}
.instructions {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  align-items: flex-start;
}
</style>
