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
  retryKey,
  type OrderRequest,
  pickForRequest,
  scan,
  scanError,
  type Shelf,
  unitWhere,
} from '@cimh/web-app'
import { orders, type RequestSummary, ShortRef } from '@cimh/web-app'
import { statusLabel } from '@cimh/web-ui'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PersonPicker from '../components/PersonPicker.vue'
import ScanField from '../components/ScanField.vue'
import ScanLog, { type ScanEntry } from '../components/ScanLog.vue'
import { waited } from '../request-queue'

definePage({ meta: { guard: 'staff', title: 'Pick' } })
const route = useRoute()
const router = useRouter()

// Pick Order first: it is the most frequent job (owner, 2026-11-12) and the page opens on it.
const OPS = [
  { key: 'order', title: 'Pick Order' },
  { key: 'pick', title: 'Pick' },
  { key: 'relocate', title: 'Stow · Relocate' },
  { key: 'issue', title: 'Issue / Return' },
] as const
type Op = (typeof OPS)[number]['key']
// `/stow` redirects to `?op=stow` (A-09 lives in this tab now).
const op = computed<Op>(() =>
  route.query.op === 'stow' ? 'relocate' : OPS.some((o) => o.key === route.query.op) ? (route.query.op as Op) : 'order',
)
// Choosing the active tab again (a stray click, or a scanner's Enter on a focused tab) never clears the log;
// it just puts the cursor back in the panel.
const panel = ref<HTMLElement | null>(null)
function choose(key: Op) {
  if (op.value === key) return focusPanel()
  entries.value = []
  void router.replace({ query: { op: key } })
}

// Pick Order queue: requests with something to pick (Pro Bono APPROVED/PICKING, paid PURCHASING), oldest first.
const queue = ref<RequestSummary[]>([])
const queueState = ref<'loading' | 'ready' | 'error'>('loading')
async function loadQueue() {
  if (!queue.value.length) queueState.value = 'loading'
  try {
    const res = (await call(() =>
      orders.GET('/requests', { params: { query: { scope: 'all', status: 'APPROVED,PICKING,PURCHASING', sort: 'oldest', limit: 50 } as never } }),
    )) as { items: RequestSummary[] }
    // Longest wait first, by the same number the rows show (days in the current status); stable for ties.
    queue.value = [...res.items].sort((a, b) => (b.waitingDays ?? 0) - (a.waitingDays ?? 0))
    queueState.value = 'ready'
  } catch {
    queueState.value = 'error'
  }
}
onMounted(loadQueue)
function openFromQueue(id: string) {
  if (order.value?.id === id) return focusPanel()
  void router.replace({ query: { op: 'order', request: id } })
}
// Tab ink: one 2 px bar that slides to the chosen tab (not four bars that blink), so a tab change reads as
// movement along the row. Placed without animation first, then transitions; the global reduced-motion rule
// makes it jump.
const tabEls: (HTMLElement | null)[] = []
const ink = ref({ x: 0, w: 0 })
const inkReady = ref(false)
function setTab(el: unknown, i: number) {
  tabEls[i] = (el as HTMLElement | null) ?? null
}
function placeInk() {
  const el = tabEls[OPS.findIndex((o) => o.key === op.value)]
  if (el) ink.value = { x: el.offsetLeft, w: el.offsetWidth }
}
// Direction of the last tab change, for the panel slide.
const tabDir = ref<'fwd' | 'back'>('fwd')
watch(op, (now, before) => {
  tabDir.value = OPS.findIndex((o) => o.key === now) >= OPS.findIndex((o) => o.key === before) ? 'fwd' : 'back'
  void nextTick(placeInk)
})
onMounted(() => {
  placeInk()
  void document.fonts?.ready.then(placeInk)
  requestAnimationFrame(() => (inkReady.value = true))
  addEventListener('resize', placeInk)
})
onBeforeUnmount(() => removeEventListener('resize', placeInk))

function focusPanel() {
  void nextTick(() => {
    if (op.value === 'pick') return focusPick()
    if (op.value === 'order' && order.value) return unitScan.value?.focus()
    panel.value?.querySelector<HTMLInputElement>('input:not([type=hidden]):not([disabled])')?.focus()
  })
}
// Pick Order: whenever a request opens (row click, slip scan, A-03 link) the cursor goes to Unit, so the
// scanner's next code is a unit, never a request id typed into the queue's field.
const unitScan = ref<{ focus: () => void } | null>(null)

const entries = ref<(ScanEntry & { shelf?: string })[]>([])
let seq = 0
function run(code: string, path: '/pick' | '/relocate' | '/assign' | '/unassign', body: Record<string, unknown>, done: string, key = newScanKey(), id = ++seq) {
  const entry: ScanEntry = { id, code, ok: null, text: 'Saving…' }
  entries.value = [entry, ...entries.value.filter((e) => e.id !== id)]
  scan(path, { unit: code, ...body }, key)
    .then((u) => set(id, { ok: true, text: `${u.productName ?? u.product} · ${done === 'where' ? unitWhere(u) : done}` }))
    .catch((e) => set(id, { ok: false, text: scanError(e), retry: () => run(code, path, body, done, retryKey(e, key), id) }))
}
function set(id: number, patch: Partial<ScanEntry>) {
  entries.value = entries.value.map((e) => (e.id === id ? { ...e, ...patch, retry: patch.retry } : e))
}

// Pick. A scan never disappears: without a reason it is logged as refused and the cursor goes to Reason.
// Focus on open: Reason while it is empty, else Unit (not Vuetify autofocus: it can fire late and steal a scan).
const REASONS = ['Repair', 'Station visit', 'Calibration', 'Loan'] as const
const reason = ref('')
const reasonField = ref<{ focus: () => void } | null>(null)
const unitField = ref<{ focus: () => void } | null>(null)
function focusPick() {
  if (reason.value.trim()) unitField.value?.focus()
  else reasonField.value?.focus()
}
watch(op, (o) => o === 'pick' && void nextTick(focusPick), { immediate: true })
function setReason(r: string) {
  reason.value = r
  void nextTick(() => unitField.value?.focus())
}
function reasonEnter() {
  if (reason.value.trim()) unitField.value?.focus()
}
function pickScan(code: string) {
  const r = reason.value.trim()
  if (r) return run(code, '/pick', { reason: r }, 'picked')
  entries.value = [{ id: ++seq, code, ok: false, text: 'Not picked: no reason yet. Choose or type a reason, then scan this unit again.' }, ...entries.value]
  // After ScanField's own refocus (it runs on nextTick after emitting).
  setTimeout(() => reasonField.value?.focus(), 0)
}
// Stow · Relocate (A-09 + A-10): one target shelf; each unit is stowed there, or moved there if it already sits
// on another shelf (the server answers UNIT_ALREADY_STOWED, and the scan goes on as a relocate).
// "Change shelf" keeps the log: every entry remembers its shelf, so a refused scan is retried on the shelf it
// was scanned for, not the newly chosen one.
const target = ref<Shelf | null>(null)
const targetError = ref('')
const checking = ref(false)
async function chooseTarget(code: string) {
  targetError.value = ''
  checking.value = true
  try {
    target.value = await call(() => inventory.GET('/shelves/{barcode}', { params: { path: { barcode: code } } }))
  } catch (e) {
    targetError.value = e instanceof ApiError && e.status === 404 ? 'No shelf with this code. Scan the QR code on the shelf.' : scanError(e)
  } finally {
    checking.value = false
  }
}
const shelfName = (s: Shelf) => [s.siteName, s.locationName ?? s.location, `Shelf ${s.number}`].filter(Boolean).join(' › ')
// A retry repeats the call that failed with its own key (same key after a network error, new one after a refusal).
function putAway(code: string, s: Shelf, key = newScanKey(), id = ++seq, move = false) {
  entries.value = [{ id, code, ok: null, text: 'Saving…', place: shelfName(s), shelf: s.barcode }, ...entries.value.filter((e) => e.id !== id)]
  const fail = (e: unknown, k: string, m: boolean) =>
    set(id, { ok: false, text: scanError(e), retry: () => putAway(code, s, retryKey(e, k), id, m) })
  const relocate = (k: string) =>
    scan('/relocate', { unit: code, toShelf: s.barcode }, k)
      .then((u) => set(id, { ok: true, text: `${u.productName ?? u.product} · moved here` }))
      .catch((e) => fail(e, k, true))
  if (move) return void relocate(key)
  scan('/stow', { unit: code, shelf: s.barcode }, key)
    .then((u) => set(id, { ok: true, text: `${u.productName ?? u.product} · stowed` }))
    .catch((e) => (e instanceof ApiError && e.code === 'UNIT_ALREADY_STOWED' ? relocate(newScanKey()) : fail(e, key, false)))
}
const onTarget = computed(() => entries.value.filter((e) => e.ok && e.shelf === target.value?.barcode).length)
const waitingRetry = computed(() => entries.value.filter((e) => e.ok === false && e.retry).length)
// Issue / Return
const person = ref<AccountSummary | null>(null)
const issueMode = ref<'issue' | 'return'>('issue')
watch(issueMode, () => {
  entries.value = [] // one log per mode: issued and returned units never mix
  focusPanel()
})
// Pick Order
const order = ref<OrderRequest | null>(null)
const orderError = ref('')
const pickable = computed(() =>
  (order.value?.lines ?? []).filter((l) => order.value!.type === 'PROBONO' || l.source === 'CIMH'),
)
async function openOrder(code: string) {
  orderError.value = ''
  try {
    const r = await getRequest(code.trim())
    if (!r.allowedActions?.includes('pick')) {
      orderError.value = `Request ${r.id} has nothing to pick now (status ${r.status.toLowerCase().replace(/_/g, ' ')}).`
      return
    }
    if (order.value?.id !== r.id) entries.value = [] // one log per request
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
  // The line whose reservation holds this exact unit; else (a unit not listed yet) a short line of its product.
  // Legacy labels have no "_<hex>" suffix, so only the reservation can place them.
  const short = pickable.value.filter((l) => (l.picked?.length ?? 0) < l.qty)
  const line =
    short.find((l) => (l.reservation?.units ?? []).includes(code)) ??
    short.find((l) => code.includes('_') && code.startsWith(`${l.productId}_`))
  entries.value = [{ id, code, ok: null, text: 'Saving…' }, ...entries.value.filter((e) => e.id !== id)]
  if (!line) {
    const text = code.includes('_') ? 'No line of this request still needs this product' : 'This unit is not reserved for this request'
    return set(id, { ok: false, text })
  }
  pickForRequest(r.id, line.lineId, code, key)
    .then((u) => {
      order.value = u
      // Replay the landing flash even when the same line gets another unit: drop the class for a frame.
      lastLine.value = null
      requestAnimationFrame(() => requestAnimationFrame(() => (lastLine.value = line.lineId)))
      const l = u.lines.find((x) => x.lineId === line.lineId)!
      set(id, { ok: true, text: `${l.product.name} · ${l.picked?.length ?? 0} of ${l.qty} picked` })
      if (u.status !== r.status || allPicked.value) void loadQueue() // APPROVED → PICKING, or done
    })
    .catch((e) => set(id, { ok: false, text: scanError(e), retry: () => pickUnit(code, retryKey(e, key), id) }))
}
/** A request id scanned or typed into the queue's field: same as clicking its row. */
function scanRequest(code: string) {
  orderError.value = ''
  const id = code.trim()
  if (route.query.request === id) return void openOrder(id)
  void router.replace({ query: { op: 'order', request: id } })
}
const picked = computed(() => pickable.value.reduce((n, l) => n + (l.picked?.length ?? 0), 0))
const total = computed(() => pickable.value.reduce((n, l) => n + l.qty, 0))
const lastLine = ref<string | null>(null)
watch(order, (o, prev) => {
  if (o?.id === prev?.id) return
  lastLine.value = null
  if (o) void nextTick(() => unitScan.value?.focus())
})
const allPicked = computed(() => pickable.value.every((l) => (l.picked?.length ?? 0) >= l.qty))

// Where each reserved unit sits ("Site › Location › Shelf n"), so the picker knows where to walk. Looked up once
// per unit; a unit that can't be looked up shows its code alone.
const where = ref<Record<string, string>>({})
function placeOf(u: { stowed: boolean; siteName?: string | null; locationName?: string | null; location?: string | null; shelfNumber?: number | null }) {
  if (!u.stowed) return 'Not on a shelf'
  return [u.siteName, u.locationName ?? u.location, u.shelfNumber != null ? `Shelf ${u.shelfNumber}` : null].filter(Boolean).join(' › ')
}
watch(
  pickable,
  (lines) => {
    const codes = lines.flatMap(unpicked)
    for (const c of codes.filter((c) => !(c in where.value))) {
      where.value = { ...where.value, [c]: '' }
      call(() => inventory.GET('/units/{barcode}', { params: { path: { barcode: c } } }))
        .then((u) => (where.value = { ...where.value, [c]: placeOf(u) }))
        .catch(() => undefined)
    }
  },
  { immediate: true },
)
type PickLine = { reservation?: { units?: string[] } | null; picked?: { barcode?: string }[] | null }
function unpicked(l: PickLine) {
  const done = new Set((l.picked ?? []).map((p) => p.barcode))
  return (l.reservation?.units ?? []).filter((c) => !done.has(c))
}
</script>

<template>
  <div class="page stack">
    <nav class="tabs" :class="{ settled: inkReady }" aria-label="Pick operations">
      <button
        v-for="(o, i) in OPS"
        :key="o.key"
        :ref="(el) => setTab(el, i)"
        type="button"
        class="tab"
        :class="{ on: op === o.key }"
        :aria-current="op === o.key ? 'page' : undefined"
        @click="choose(o.key)"
      >
        {{ o.title }}
      </button>
      <span class="tab-ink" aria-hidden="true" :style="{ transform: `translateX(${ink.x}px) scaleX(${ink.w})` }" />
    </nav>

    <Transition :name="`tab-${tabDir}`" mode="out-in" @after-enter="focusPanel">
    <section v-if="op === 'order'" ref="panel" class="desk" :class="{ open: !!order }">
      <aside class="queue panel" aria-label="Ready to pick">
        <div class="queue-head">
          <h2 class="t-h3">Ready to pick</h2>
          <span class="t-caption muted">{{ queueState === 'ready' ? `${queue.length} · longest wait first` : '' }}</span>
          <v-btn variant="text" size="small" :loading="queueState === 'loading'" @click="loadQueue">Refresh</v-btn>
        </div>
        <div class="queue-scan">
          <ScanField label="Request id" hint="Or scan the id on a pick slip" :autofocus="!route.query.request" @scan="scanRequest" />
          <v-alert v-if="orderError" type="error" variant="tonal" density="compact">{{ orderError }}</v-alert>
        </div>
        <div v-if="queueState === 'loading' && !queue.length" class="queue-empty"><v-progress-circular indeterminate size="24" /></div>
        <div v-else-if="queueState === 'error'" class="queue-empty">
          <p class="t-body">The list didn't load.</p>
          <v-btn variant="tonal" @click="loadQueue">Try again</v-btn>
        </div>
        <p v-else-if="!queue.length" class="queue-empty t-body muted">Nothing is waiting to be picked. Approved Pro Bono requests and paid requests in purchasing show up here.</p>
        <TransitionGroup v-else tag="ul" name="row" class="rows">
          <li v-for="(q, i) in queue" :key="q.id" :style="{ '--i': Math.min(i, 8) }">
            <button type="button" class="row-btn" :class="{ on: order?.id === q.id }" :aria-current="order?.id === q.id ? 'true' : undefined" @click="openFromQueue(q.id)">
              <span class="r1">
                <span class="t-body who">{{ q.organisationName ?? q.customerName ?? q.customer }}</span>
                <span class="age t-caption" :class="{ old: (q.waitingDays ?? 0) >= 3 }">{{ waited(q) }}</span>
              </span>
              <span class="r1">
                <span class="t-mono t-caption rid"><ShortRef :id="q.id" /></span>
                <span v-if="q.type === 'PROBONO'" class="probono-badge">Pro Bono</span>
              </span>
              <span class="t-caption muted">{{ q.lineCount }} {{ q.lineCount === 1 ? 'line' : 'lines' }} · {{ statusLabel(q.status) }}</span>
            </button>
          </li>
        </TransitionGroup>
      </aside>

      <div :key="order?.id ?? 'none'" class="work">
        <div v-if="!order" class="pane-empty panel">
          <h2 class="t-h3">Pick a request</h2>
          <p class="t-body muted">Choose a request on the left, or scan its id. Then scan each reserved unit: every unit goes to its line, and when all lines are full you record the shipment on the request.</p>
        </div>
        <template v-else>
          <v-alert v-if="allPicked" type="success" variant="tonal">
            Everything is picked. <router-link :to="`/requests/${order.id}`">Record the shipment</router-link> on the request.
          </v-alert>
          <ScanField v-else ref="unitScan" label="Unit" prominent placeholder="Scan a reserved unit" hint="" autofocus @scan="(c) => pickUnit(c)" />
          <div class="sum">
            <div class="sum-text">
              <h2 class="t-h2">{{ order.organisationName ?? order.customerName }}</h2>
              <span class="t-body muted">
                <router-link :to="`/requests/${order.id}`" class="t-mono">{{ order.id }}</router-link>
                · {{ order.type === 'PROBONO' ? 'Pro Bono' : 'Paid, CIMH stock lines' }} · {{ statusLabel(order.status) }}
              </span>
            </div>
            <span class="big tnum"><span :key="picked" class="console-roll">{{ picked }}</span> of {{ total }}<small>units picked</small></span>
          </div>
          <ul class="lines">
            <li v-for="l in pickable" :key="l.lineId" class="line panel" :class="{ full: (l.picked?.length ?? 0) >= l.qty, just: l.lineId === lastLine }">
              <div class="line-text">
                <span class="name">{{ l.product.name }}</span>
                <ul v-if="unpicked(l).length" class="spots">
                  <li v-for="c in unpicked(l)" :key="c">
                    <span class="t-body">{{ where[c] || 'Finding its shelf…' }}</span>
                    <span class="t-mono t-caption muted" :title="c">{{ c }}</span>
                  </li>
                </ul>
                <span class="t-mono t-caption muted units">
                  <template v-if="l.reservation?.units?.length"><template v-if="!unpicked(l).length">All reserved units picked</template></template>
                  <router-link v-else-if="l.reservation?.status === 'FAILED'" :to="`/requests/${order.id}`">Not enough stock: requote</router-link>
                  <template v-else>Reserving… <button type="button" class="linkish" @click="openOrder(order.id)">Refresh</button></template>
                </span>
              </div>
              <div class="bar" aria-hidden="true"><i :style="{ transform: `scaleX(${Math.min(1, (l.picked?.length ?? 0) / l.qty)})` }" /></div>
              <span class="n tnum"><span :key="l.picked?.length ?? 0" class="console-roll">{{ l.picked?.length ?? 0 }}</span> / {{ l.qty }}</span>
            </li>
          </ul>
          <ScanLog v-if="!allPicked || entries.length" :entries="entries" empty="Scan the first unit." />
        </template>
      </div>
    </section>

    <!-- Pick, Relocate, Issue / Return share Pick Order's composition: set-up rail left, work pane right. -->
    <section v-else-if="op === 'pick'" ref="panel" class="desk">
      <aside class="rail panel" aria-labelledby="purpose-title">
        <div class="rail-head"><h2 id="purpose-title" class="t-h3">Purpose</h2></div>
        <div class="rail-body">
          <p class="t-caption muted">Why the units leave the shelf. Units reserved for a request are picked under Pick Order.</p>
          <div class="reasons" role="group" aria-label="Common purposes">
            <v-chip v-for="r in REASONS" :key="r" :color="reason === r ? 'primary' : undefined" :variant="reason === r ? 'flat' : 'outlined'" @click="setReason(r)">{{ r }}</v-chip>
          </div>
          <v-text-field
            ref="reasonField"
            v-model="reason"
            label="Reason"
            counter="300"
            maxlength="300"
            :hint="reason.trim() ? 'Press Enter to start scanning' : 'Needed before the first scan'"
            persistent-hint
            @keydown.enter.prevent="reasonEnter"
          />
        </div>
      </aside>
      <div class="work">
        <!-- Before a purpose is chosen the field is plain and dimmed (it does not look ready), but it still takes a
             scan so nothing a scanner sends is lost: the scan is logged as refused and the cursor goes to Reason. -->
        <ScanField
          ref="unitField"
          :class="{ waiting: !reason.trim() }"
          label="Unit"
          :prominent="!!reason.trim()"
          :placeholder="reason.trim() ? 'Scan a unit to take off the shelf' : 'Choose a purpose first'"
          hint=""
          @scan="pickScan"
        />
        <p v-if="reason.trim()" class="context t-body">Picking for <strong>{{ reason.trim() }}</strong></p>
        <ScanLog :entries="entries" :empty="reason.trim() ? 'Scan each unit as you take it off the shelf.' : 'Choose a purpose first, then scan each unit.'" />
      </div>
    </section>

    <section v-else-if="op === 'relocate'" ref="panel" class="desk">
      <aside class="rail panel" aria-labelledby="target-title">
        <div class="rail-head"><h2 id="target-title" class="t-h3">Where the units go</h2></div>
        <div class="rail-body">
          <template v-if="!target">
            <p class="t-caption muted">Go to the shelf the units go on and scan its QR code.</p>
            <ScanField label="Shelf" hint="" :loading="checking" autofocus @scan="chooseTarget" />
            <v-alert v-if="targetError" type="error" variant="tonal" density="compact">{{ targetError }}</v-alert>
          </template>
          <div v-else class="target" role="status">
            <span class="t-caption muted">Putting units on</span>
            <span class="t-h2">Shelf {{ target.number }}</span>
            <span class="t-body">{{ target.locationName ?? target.location }}</span>
            <span class="t-caption muted">{{ target.siteName }}</span>
            <span class="t-body tally"><strong class="tnum">{{ onTarget }}</strong> put on this shelf</span>
            <v-btn variant="outlined" class="change" @click="target = null">Change shelf</v-btn>
          </div>
          <p v-if="waitingRetry" class="t-body">
            <strong class="tnum">{{ waitingRetry }}</strong> refused {{ waitingRetry === 1 ? 'scan waits' : 'scans wait' }} for Retry. Each one is retried on the shelf it was scanned for.
          </p>
        </div>
      </aside>
      <div class="work">
        <template v-if="target">
          <ScanField label="Unit" prominent :placeholder="`Scan a unit for shelf ${target.number}`" hint="" autofocus @scan="(c) => putAway(c, target!)" />
          <ScanLog :entries="entries" empty="Scan the label on each unit as you place it. New units are stowed; units from another shelf move here." />
        </template>
        <template v-else>
          <div class="pane-empty panel">
            <h2 class="t-h3">Stow or move units</h2>
            <p class="t-body muted">Scan the shelf first. Then scan each unit as you place it: a unit that is on no shelf is stowed, a unit from another shelf moves here.</p>
          </div>
          <ScanLog v-if="entries.length" :entries="entries" empty="" />
        </template>
      </div>
    </section>

    <section v-else-if="op === 'issue'" ref="panel" class="desk">
      <aside class="rail panel" aria-labelledby="issue-title">
        <div class="rail-head"><h2 id="issue-title" class="t-h3">{{ issueMode === 'issue' ? 'Issue to a person' : 'Take units back' }}</h2></div>
        <div class="rail-body">
          <v-btn-toggle v-model="issueMode" mandatory color="primary" density="comfortable" variant="outlined" divided class="mode">
            <v-btn value="issue">Issue</v-btn>
            <v-btn value="return">Return</v-btn>
          </v-btn-toggle>
          <template v-if="issueMode === 'issue'">
            <PersonPicker v-model="person" label="Issue to" />
            <p class="t-caption muted">Issued units leave the shelf and show under Reports → Who has what.</p>
          </template>
          <p v-else class="t-caption muted">Returned units are off every shelf until they are stowed again.</p>
        </div>
      </aside>
      <div class="work">
        <template v-if="issueMode === 'issue'">
          <template v-if="person">
            <ScanField label="Unit" prominent :placeholder="`Scan a unit for ${person.firstname} ${person.lastname}`" hint="" autofocus @scan="(c) => run(c, '/assign', { accountId: person!.id }, `with ${person!.firstname} ${person!.lastname}`)" />
            <ScanLog :entries="entries" empty="Scan each unit this person takes." />
          </template>
          <div v-else class="pane-empty panel">
            <h2 class="t-h3">Issue units</h2>
            <p class="t-body muted">Choose who takes the units, then scan each unit.</p>
          </div>
        </template>
        <template v-else>
          <ScanField label="Unit coming back" prominent placeholder="Scan a unit that came back" hint="" autofocus @scan="(c) => run(c, '/unassign', {}, 'returned; stow it on a shelf')" />
          <ScanLog :entries="entries" empty="Scan each unit as it comes back." />
          <p v-if="entries.some((e) => e.ok)" class="t-body"><router-link :to="{ query: { op: 'relocate' } }">Stow the returned units</router-link></p>
        </template>
      </div>
    </section>
    </Transition>
  </div>
</template>

<style scoped>
.page {
  max-width: 1320px;
  margin: 0 auto;
  width: 100%;
}
/* Underline tabs (owner's choice from the "Tabs and live log" sketch). */
.tabs {
  display: flex;
  gap: var(--sp-1);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
  overflow-x: auto;
  scrollbar-width: none;
}
.tab {
  padding: var(--sp-3) var(--sp-4);
  min-height: 44px;
  font: inherit;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.72);
  background: none;
  border: 0;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  white-space: nowrap;
  cursor: pointer;
  transition: color 150ms ease-out, border-color 150ms ease-out;
}
.tab:hover {
  color: rgb(var(--v-theme-on-surface));
}
.tab:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
  border-radius: 6px 6px 0 0;
}
.tab.on {
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
}
/* The sliding ink (1 px wide, scaled to the tab width; transform only). */
.tabs {
  position: relative;
}
.tab-ink {
  position: absolute;
  left: 0;
  bottom: -1px;
  width: 1px;
  height: 2px;
  background: rgb(var(--v-theme-primary));
  transform-origin: 0 0;
  pointer-events: none;
}
.tabs.settled .tab-ink {
  transition: transform 260ms var(--ease-out);
}
/* Graphite Console panel (console.css): 1 px seam, 4 px corners. */
.panel {
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
}

/* Pick Order: queue rail + work pane. */
.desk {
  display: grid;
  grid-template-columns: minmax(300px, 380px) minmax(0, 1fr);
  gap: var(--sp-4);
  align-items: start;
}
.queue {
  overflow: hidden;
  position: sticky;
  top: var(--sp-4);
}
.queue-head {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-3) var(--sp-2) var(--sp-4);
}
.queue-head .t-caption {
  flex: 1;
}
.queue-scan {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: 0 var(--sp-4) var(--sp-3);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.queue-empty {
  padding: var(--sp-6) var(--sp-4);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--sp-3);
}
.rows {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: calc(100vh - 300px);
  overflow-y: auto;
}
.rows li + li {
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.row-btn {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: var(--sp-3) var(--sp-4);
  font: inherit;
  color: inherit;
  text-align: left;
  background: none;
  border: 0;
  cursor: pointer;
  transition: background-color 150ms ease-out;
}
.row-btn:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.row-btn:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.row-btn.on {
  background: rgba(var(--v-theme-primary), 0.14);
}
.row-btn.on .who {
  font-weight: 600;
}
.r1 {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.r1 > * {
  min-width: 0;
}
.who {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rid {
  color: rgb(var(--v-theme-primary));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.probono-badge,
.age {
  flex: none;
  white-space: nowrap;
}
.age {
  margin-left: auto;
  color: rgba(var(--v-theme-on-surface), 0.72);
}
.age.old {
  color: rgb(var(--v-theme-warning));
  font-weight: 600;
}
.who {
  font-weight: 500;
}

.work {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
  min-width: 0;
}
.pane-empty {
  padding: var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.pane-empty p {
  max-width: 60ch;
  text-wrap: pretty;
}
.sum {
  display: flex;
  align-items: flex-end;
  gap: var(--sp-4);
}
.sum-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}
.big {
  font-size: 2rem;
  font-weight: 700;
  line-height: 1;
  text-align: right;
  white-space: nowrap;
}
.big small {
  display: block;
  margin-top: var(--sp-1);
  font-size: 0.8125rem;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.72);
}
.lines {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.line {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(80px, 180px) 64px;
  gap: var(--sp-4);
  align-items: center;
  padding: var(--sp-3) var(--sp-4);
  transition: border-color 200ms ease-out, background-color 200ms ease-out;
}
.line.full {
  border-color: rgba(var(--v-theme-success), 0.5);
}
.line.just {
  background: rgba(var(--v-theme-success), 0.08);
}
.line-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.name {
  font-weight: 600;
}
.units {
  overflow-wrap: anywhere;
}
.spots {
  list-style: none;
  margin: var(--sp-1) 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}
.spots li {
  display: flex;
  flex-wrap: wrap;
  column-gap: var(--sp-2);
  align-items: baseline;
}
.spots .t-mono {
  overflow-wrap: anywhere;
}
.bar {
  height: 8px;
  border-radius: 4px;
  background: rgba(var(--v-theme-on-surface), 0.12);
  overflow: hidden;
}
.bar i {
  display: block;
  width: 100%;
  height: 100%;
  background: rgb(var(--v-theme-success));
  transform-origin: 0 50%;
  transition: transform 320ms var(--ease-out);
}
.n {
  text-align: right;
  font-weight: 600;
}
.linkish {
  color: rgb(var(--v-theme-primary));
  text-decoration: underline;
  font: inherit;
  margin-left: var(--sp-1);
  cursor: pointer;
}
@media (max-width: 899px) {
  .desk {
    grid-template-columns: minmax(0, 1fr);
  }
  .queue {
    position: static;
  }
  .rows {
    max-height: none; /* the page scrolls on phones; no scroller inside a scroller */
  }
  /* With a request open, its scan field and lines come first; the queue follows. */
  .desk.open .work {
    order: -1;
  }
}
@media (max-width: 599px) {
  .sum {
    flex-wrap: wrap;
    align-items: baseline;
  }
  .sum-text .t-mono {
    overflow-wrap: anywhere;
  }
  .big {
    text-align: left;
  }
  .tab {
    flex: 1 1 auto;
    padding: var(--sp-3) var(--sp-2);
    font-size: 0.875rem;
  }
  .line {
    grid-template-columns: minmax(0, 1fr) 56px;
  }
  .bar {
    grid-column: 1 / -1;
    grid-row: 2;
  }
}
/* ---- Motion: a tab fades in; an opened request swaps in from the queue side; queue rows enter (staggered,
   capped), leave and re-sort in place; a unit landing on its line flashes the line, fills its bar and rolls
   the counts. The global reduced-motion rule (base.css) collapses all of it to instant state changes. */
/* Tab change (Vue Transition, out-in): the old panel fades out fast, the new one slides in 12 px from the
   side of the tab that was chosen, so the row of tabs and the panels move the same way. */
.tab-fwd-leave-active,
.tab-back-leave-active {
  transition: opacity 90ms ease-in;
}
.tab-fwd-leave-to,
.tab-back-leave-to {
  opacity: 0;
}
.tab-fwd-enter-active,
.tab-back-enter-active {
  transition: opacity 200ms var(--ease-out), transform 240ms var(--ease-out);
}
.tab-fwd-enter-from {
  opacity: 0;
  transform: translateX(12px);
}
.tab-back-enter-from {
  opacity: 0;
  transform: translateX(-12px);
}
.desk.open > .work {
  animation: console-swap-in 220ms var(--ease-out);
}
.rows {
  position: relative;
}
.row-enter-active {
  transition: opacity 220ms var(--ease-out), transform 220ms var(--ease-out);
  transition-delay: calc(var(--i, 0) * 24ms);
}
.row-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.row-leave-active {
  position: absolute;
  width: 100%;
  transition: opacity 140ms ease-in;
}
.row-leave-to {
  opacity: 0;
}
.row-move {
  transition: transform 280ms var(--ease-out);
}
@keyframes line-land {
  from {
    background-color: rgba(var(--v-theme-success), 0.24);
  }
}
.line.just {
  animation: line-land 900ms var(--ease-out);
}
.target {
  animation: console-swap-in 220ms var(--ease-out);
}

/* Pick, Relocate, Issue / Return: the set-up rail (same column and panel as Pick Order's queue). */
.rail {
  position: sticky;
  top: var(--sp-4);
  overflow: hidden;
}
.rail-head {
  padding: var(--sp-3) var(--sp-4);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.rail-body {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding: var(--sp-4);
}
.rail-body > p {
  margin: 0;
  text-wrap: pretty;
}
.target {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.target .tally {
  margin-top: var(--sp-2);
}
.target .change {
  align-self: flex-start;
  margin-top: var(--sp-3);
}
.mode {
  align-self: flex-start;
}
/* Not ready yet: dashed edge, no primary ring (contrast kept: no opacity). */
.waiting :deep(.v-field)::after {
  border-style: dashed;
}
.context {
  margin: 0;
  color: rgba(var(--v-theme-on-surface), 0.74);
}
@media (max-width: 899px) {
  .rail {
    position: static;
  }
}
.reasons {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
}
/* Tap targets for gloved hands: the app's compact chip is 18 px tall. */
.reasons :deep(.v-chip) {
  height: 36px;
  padding: 0 var(--sp-3);
  border-radius: 8px;
  font-size: 0.875rem;
}
</style>
