<script setup lang="ts">
/**
 * A-13 stock levels, a restock board: products at or below their low-stock alert (none left first, then
 * the furthest under their alert) beside the open product's stock record (`?open=<productId>`): meter
 * against the alert level, where the units are, what is held back. The finder opens any product here.
 */
import { call, inventory, type ProductStaff, type ProductStock, useCursorList } from '@cimh/web-app'
import { mdiAlertCircle, mdiAlertOutline, mdiArrowRight, mdiCheckCircleOutline, mdiTagOutline } from '@mdi/js'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ProductPicker from '../../components/ProductPicker.vue'
import StockMeter from '../../components/StockMeter.vue'

definePage({ meta: { guard: 'staff', title: 'Stock levels' } })
const route = useRoute()
const router = useRouter()

const LOW_CAP = 500
const low = useCursorList<ProductStock>((cursor) => call(() => inventory.GET('/stock/low', { params: { query: { cursor, limit: 100 } } })))
// The list reports its own errors (`failed` + a notice); the empty error state shows only before any row arrived.
const lowError = computed(() => low.failed.value && !low.items.value.length)
async function loadLow() {
  await low.reload()
  // The server pages by name; "worst first" is only true over the whole list, so fetch it all (bounded).
  while (low.nextCursor.value && !low.failed.value && low.items.value.length < LOW_CAP) await low.loadMore()
}
onMounted(loadLow)

/** None left first, then the furthest under the alert level, then by name. */
const rank = (s: ProductStock) => (s.available <= 0 ? -1 : s.available / Math.max(1, s.threshold))
const rows = computed(() =>
  [...low.items.value].sort((a, b) => rank(a) - rank(b) || (a.productName ?? a.productId).localeCompare(b.productName ?? b.productId)),
)
const noneCount = computed(() => low.items.value.filter((s) => s.available <= 0).length)
// Most urgent first; draw 60 at a time (534 rows made a 16,000 px page on phones). An opened row stays in view.
const shown = ref(60)
const visibleRows = computed(() => {
  const v = rows.value.slice(0, shown.value)
  const open = rows.value.find((s) => s.productId === openId.value)
  return open && !v.includes(open) ? [...v, open] : v
})

// ---- Open record (?open=)
const openId = computed(() => (typeof route.query.open === 'string' ? route.query.open : null))
const record = ref<ProductStock | null>(null)
const recordError = ref(false)
let gen = 0
async function loadRecord(id: string) {
  const g = ++gen
  recordError.value = false
  // Show the copy from the list at once; the fresh one replaces it.
  const cached = low.items.value.find((s) => s.productId === id)
  record.value = cached ?? (record.value?.productId === id ? record.value : null)
  try {
    const s = await call(() => inventory.GET('/products/{productId}/stock', { params: { path: { productId: id } } }))
    if (g === gen) record.value = s
  } catch {
    if (g === gen && !record.value) recordError.value = true
  }
}
watch(openId, (id) => (id ? void loadRecord(id) : (record.value = null)), { immediate: true })
// Keep the open product's row in sight when it is chosen from the finder or a link.
watch([openId, rows], () => void nextTick(() => document.querySelector(".lrow.selected")?.scrollIntoView({ block: "nearest" })))
// Wide screens: nothing chosen yet → open the most urgent product.
watch(rows, (r) => {
  if (!openId.value && r.length && window.matchMedia('(min-width: 1280px)').matches) void router.replace({ query: { ...route.query, open: r[0]!.productId } })
})

const picked = ref<ProductStaff | null>(null)
watch(picked, (p) => {
  if (!p) return
  void router.push({ query: { ...route.query, open: p.id } })
  picked.value = null
})

const recordName = computed(() => record.value?.productName ?? record.value?.productId ?? '')
const state = computed(() => {
  const s = record.value
  if (!s) return null
  if (s.available <= 0) return 'none'
  if (s.threshold > 0 && s.available <= s.threshold) return 'low'
  return 'ok'
})
const onShelves = computed(() => (record.value?.byLocation ?? []).reduce((n, b) => n + b.count, 0))
/** Shelves grouped by site, largest first, so the place to fetch from reads at the top. */
const sites = computed(() => {
  const map = new Map<string, { name: string; total: number; shelves: ProductStock['byLocation'] }>()
  for (const b of record.value?.byLocation ?? []) {
    const g = map.get(b.site) ?? { name: b.siteName ?? b.site, total: 0, shelves: [] }
    g.total += b.count
    g.shelves.push(b)
    map.set(b.site, g)
  }
  const out = [...map.values()].sort((a, b) => b.total - a.total)
  for (const g of out) g.shelves.sort((a, b) => b.count - a.count)
  return out
})
const maxShelf = computed(() => Math.max(1, ...(record.value?.byLocation ?? []).map((b) => b.count)))
const held = computed(() => {
  const s = record.value
  if (!s) return []
  return [
    { key: 'reserved', label: 'Reserved', hint: 'Held for accepted requests', n: s.reserved },
    { key: 'issued', label: 'Issued', hint: 'Out with people', n: s.assigned ?? 0 },
    { key: 'picked', label: 'Picked', hint: 'Off the shelf for a request', n: s.picked },
  ]
})
const shortBy = computed(() => (record.value && record.value.threshold > 0 ? Math.max(0, record.value.threshold - record.value.available + 1) : 0))
</script>

<template>
  <div class="board">
    <div class="finder"><ProductPicker v-model="picked" label="Stock of any product" /></div>

    <div class="frame" :class="{ open: !!openId }">
      <!-- Low stock list -->
      <section class="list" aria-labelledby="low-title">
        <header class="console-head">
          <h2 id="low-title" class="console-title">Low stock</h2>
          <span v-if="low.loaded.value && rows.length" class="head-count t-caption">
            <span class="console-mono">{{ rows.length }}{{ low.nextCursor.value ? '+' : '' }}</span> at or under alert<template v-if="noneCount"> · <span class="none-word"><span class="console-mono">{{ noneCount }}</span> with none</span></template>
          </span>
        </header>
        <div class="console-scroll">
          <p class="intro t-caption muted">Available units at or under the product's alert level. Staff on the low-stock email list are told when a product drops this far.</p>
          <div v-if="lowError" class="empty">
            <p class="t-body">The low-stock list could not be loaded.</p>
            <button type="button" class="console-retry" @click="loadLow">Try again</button>
          </div>
          <div v-else-if="!low.loaded.value" class="skel-rows" aria-busy="true" aria-label="Loading low stock">
            <div v-for="n in 5" :key="n" class="console-skel sk-row" />
          </div>
          <div v-else-if="!rows.length" class="empty">
            <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" class="ok-icon"><path :d="mdiCheckCircleOutline" fill="currentColor" /></svg>
            <p class="t-body">Nothing is low on stock.</p>
            <p class="t-caption muted">Use the finder above to check any product.</p>
          </div>
          <template v-else>
            <!-- The meaning of Held is on the page, not in a tooltip; the record splits it per kind. -->
            <p class="legend t-caption muted">Held = units reserved for requests, issued to people or picked: not free for new requests.</p>
            <div class="cols t-caption muted" aria-hidden="true">
              <span>Product</span><span>Available</span><span class="num">Held</span>
            </div>
            <TransitionGroup tag="ul" name="row" class="rows">
              <li v-for="(s, i) in visibleRows" :key="s.productId" :style="{ '--i': Math.min(i, 10) }">
                <router-link
                  class="lrow"
                  :class="{ selected: s.productId === openId }"
                  :to="{ query: { ...route.query, open: s.productId } }"
                  :aria-current="s.productId === openId ? 'true' : undefined"
                >
                  <span class="name">{{ s.productName ?? s.productId }}</span>
                  <StockMeter :available="s.available" :threshold="s.threshold" />
                  <span class="num console-mono held-n" :title="`${s.reserved} reserved · ${s.assigned ?? 0} issued · ${s.picked} picked`">{{ s.reserved + (s.assigned ?? 0) + s.picked }}</span>
                </router-link>
              </li>
            </TransitionGroup>
            <div v-if="rows.length > shown" class="more">
              <v-btn class="m3" variant="outlined" @click="shown += 60">Show {{ Math.min(60, rows.length - shown) }} more of {{ rows.length }}</v-btn>
            </div>
            <div v-else-if="low.nextCursor.value" class="more">
              <v-btn class="m3" variant="outlined" :loading="low.loading.value" @click="low.loadMore">Load more</v-btn>
            </div>
          </template>
        </div>
      </section>

      <!-- Open record -->
      <section class="record" aria-live="polite" aria-labelledby="rec-title">
        <header class="console-head">
          <h2 id="rec-title" class="console-title">Stock record</h2>
          <router-link v-if="openId" class="close t-caption" :to="{ query: { ...route.query, open: undefined } }">Close</router-link>
        </header>
        <div class="console-scroll">
          <div v-if="!openId" class="empty">
            <p class="t-body">Choose a product to see where its units are.</p>
            <p class="t-caption muted">Pick one from the list, or find any product above.</p>
          </div>
          <div v-else-if="recordError" class="empty">
            <p class="t-body">This product's stock could not be loaded.</p>
            <button type="button" class="console-retry" @click="loadRecord(openId)">Try again</button>
          </div>
          <div v-else-if="!record" class="rec-body" aria-busy="true">
            <div class="console-skel sk-title" />
            <div class="console-skel sk-meter" />
            <div class="console-skel sk-block" />
          </div>
          <Transition v-else name="swap" mode="out-in">
            <div :key="record.productId" class="rec-body">
              <div class="ident">
                <h3 class="rec-name">{{ recordName }}</h3>
                <span class="console-mono t-caption muted">{{ record.productId }}</span>
              </div>

              <div class="gauge">
                <StockMeter :available="record.available" :threshold="record.threshold" size="large" />
                <p class="verdict t-body" :class="state">
                  <svg v-if="state !== 'ok'" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path :d="state === 'none' ? mdiAlertCircle : mdiAlertOutline" fill="currentColor" /></svg>
                  <span v-if="state === 'none'">None available. Restock or reorder before the next request.</span>
                  <span v-else-if="state === 'low'">Low: at or under its alert level of <span class="console-mono">{{ record.threshold }}</span>. <span class="console-mono">{{ shortBy }}</span> more {{ shortBy === 1 ? 'unit brings' : 'units bring' }} it above.</span>
                  <span v-else-if="record.threshold > 0">Above its alert level of <span class="console-mono">{{ record.threshold }}</span>.</span>
                  <span v-else>No alert level set for this product.</span>
                </p>
              </div>

              <dl class="held">
                <div v-for="h in held" :key="h.key">
                  <dt class="t-caption muted">{{ h.label }}</dt>
                  <dd class="console-mono" :class="{ zero: !h.n }">{{ h.n }}</dd>
                  <dd class="t-caption muted">{{ h.hint }}</dd>
                </div>
              </dl>

              <div class="where">
                <h4 class="t-label">On the shelves <span class="console-mono muted">{{ onShelves }}</span></h4>
                <p v-if="!sites.length" class="t-body muted">Nothing of this product is on a shelf.</p>
                <div v-for="g in sites" :key="g.name" class="site">
                  <div class="site-head">
                    <span class="t-label">{{ g.name }}</span>
                    <span class="console-mono muted">{{ g.total }}</span>
                  </div>
                  <ul class="shelves">
                    <li v-for="b in g.shelves" :key="b.shelf">
                      <router-link :to="{ path: '/inventory', query: { code: b.shelf } }">{{ b.locationName ?? b.location }} › Shelf {{ b.shelfNumber ?? '?' }}</router-link>
                      <span class="bar" aria-hidden="true"><span :style="{ transform: `scaleX(${b.count / maxShelf})` }" /></span>
                      <span class="console-mono">{{ b.count }}</span>
                    </li>
                  </ul>
                </div>
              </div>

              <div class="actions">
                <v-btn class="m3" color="primary" :prepend-icon="mdiTagOutline" :to="{ path: '/inventory', query: { op: 'labels', product: record.productId } }">Create labels</v-btn>
                <v-btn class="m3" variant="outlined" :append-icon="mdiArrowRight" :to="`/products/${record.productId}?tab=stock`">Open product</v-btn>
              </div>
            </div>
          </Transition>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.board {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
  max-width: 1500px;
  width: 100%;
  margin: 0 auto;
}
.finder {
  max-width: 480px;
}
.frame {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(340px, 2fr);
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
}
.record {
  border-left: 1px solid rgb(var(--v-theme-seam));
  min-width: 0;
}
.list {
  min-width: 0;
}
.head-count {
  color: rgb(var(--v-theme-secondary));
}
.none-word {
  color: rgb(var(--v-theme-error));
}
.intro {
  margin: 0;
  padding: var(--sp-3) var(--sp-4);
  max-width: 70ch;
}

/* Rows */
.legend {
  margin: 0;
  padding: var(--sp-2) var(--sp-4) 0;
}
.cols,
.lrow {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 190px 48px;
  align-items: center;
  gap: var(--sp-3);
  padding: 0 var(--sp-4);
}
.cols {
  height: 28px;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.rows {
  list-style: none;
  margin: 0;
  padding: 0;
}
.lrow {
  position: relative;
  min-height: 44px;
  color: inherit;
  text-decoration: none;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
  transition: background-color 120ms ease;
}
.lrow:hover {
  background: rgb(var(--v-theme-surface-bright));
}
.lrow.selected {
  background: rgb(var(--v-theme-primary-subtle));
}
.lrow.selected::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 2px;
  background: rgb(var(--v-theme-primary));
}
.lrow :deep(.meter) {
  justify-self: start;
}
.name {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.num {
  text-align: right;
}
.held-n {
  font-size: 13px;
  color: rgb(var(--v-theme-secondary));
}
.more {
  padding: var(--sp-3) var(--sp-4);
}

/* Empty / loading */
.empty {
  padding: var(--sp-8) var(--sp-4);
  display: grid;
  justify-items: start;
  gap: var(--sp-1);
}
.empty p {
  margin: 0;
}
.ok-icon {
  color: rgb(var(--v-theme-success));
  margin-bottom: var(--sp-1);
}
.skel-rows {
  padding: var(--sp-2) var(--sp-4);
  display: grid;
  gap: var(--sp-3);
}
.sk-row {
  height: 28px;
}
.sk-title {
  height: 26px;
  width: 60%;
}
.sk-meter {
  height: 44px;
}
.sk-block {
  height: 140px;
}

/* Record */
.close {
  color: rgb(var(--v-theme-primary));
}
.rec-body {
  padding: var(--sp-4);
  display: grid;
  gap: var(--sp-6);
}
.ident {
  display: grid;
  gap: 2px;
}
.rec-name {
  margin: 0;
  font-size: 20px;
  line-height: 26px;
  font-weight: 600;
  letter-spacing: -0.01em;
  text-wrap: balance;
}
.gauge {
  display: grid;
  gap: var(--sp-2);
}
.verdict {
  margin: 0;
  display: flex;
  gap: var(--sp-2);
  align-items: flex-start;
}
.verdict svg {
  flex: none;
  margin-top: 1px;
}
.verdict.none {
  color: rgb(var(--v-theme-error));
}
.verdict.low {
  color: rgb(var(--v-theme-warning));
}
.verdict.ok {
  color: rgb(var(--v-theme-secondary));
}
.held {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin: 0;
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
}
.held > div {
  align-content: start;
  padding: var(--sp-3);
  display: grid;
  gap: 2px;
}
.held > div + div {
  border-left: 1px solid rgb(var(--v-theme-seam));
}
.held dd {
  margin: 0;
}
.held dd.console-mono {
  font-size: 20px;
  line-height: 26px;
  font-weight: 500;
}
.held dd.zero {
  color: rgb(var(--v-theme-secondary));
}
.where {
  display: grid;
  gap: var(--sp-3);
}
.where h4 {
  margin: 0;
  display: flex;
  gap: var(--sp-2);
}
.site-head {
  display: flex;
  justify-content: space-between;
  padding-bottom: var(--sp-1);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.shelves {
  list-style: none;
  margin: 0;
  padding: 0;
}
.shelves li {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 72px 3ch;
  gap: var(--sp-3);
  align-items: center;
  min-height: 36px;
}
.shelves a {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.shelves .console-mono {
  text-align: right;
}
.bar {
  height: 4px;
  border-radius: 2px;
  background: rgb(var(--v-theme-seam));
  overflow: hidden;
}
.bar span {
  display: block;
  height: 100%;
  background: rgb(var(--v-theme-on-surface));
  opacity: 0.55;
  transform-origin: 0 50%;
  transition: transform 520ms var(--ease-out);
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
  padding-top: var(--sp-4);
  border-top: 1px solid rgb(var(--v-theme-seam));
}

/* Motion */
.lrow-enter-active {
  transition: opacity 220ms var(--ease-out), transform 220ms var(--ease-out);
  transition-delay: calc(var(--i, 0) * 24ms);
}
.lrow-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.lrow-leave-active {
  transition: opacity 140ms ease-in;
}
.lrow-leave-to {
  opacity: 0;
}
.lrow-move {
  transition: transform 280ms var(--ease-out);
}
.swap-enter-active {
  transition: opacity 200ms var(--ease-out), transform 200ms var(--ease-out);
}
.swap-enter-from {
  opacity: 0;
  transform: translateX(8px);
}
.swap-leave-active {
  transition: opacity 100ms ease-in;
}
.swap-leave-to {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .row-enter-from,
  .swap-enter-from {
    transform: none;
  }
}

/* Wide: fits the window, panel bodies scroll */
@media (min-width: 1280px) {
  .board {
    height: calc(100dvh - 140px);
    min-height: 480px;
  }
  .frame {
    flex: 1 1 0;
    min-height: 0;
  }
  .list,
  .record {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .console-scroll {
    flex: 1 1 0;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
  }
}
/* Narrower: one column; an open record comes first */
@media (max-width: 1279.98px) {
  .frame {
    grid-template-columns: 1fr;
  }
  .record {
    border-left: 0;
    border-bottom: 1px solid rgb(var(--v-theme-seam));
    order: -1;
  }
  .frame:not(.open) .record {
    display: none;
  }
}
@media (max-width: 599.98px) {
  .cols,
  .lrow {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .cols span:last-child,
  .held-n {
    display: none;
  }
  .lrow {
    padding-block: var(--sp-2);
  }
  .held dd.t-caption {
    display: none;
  }
}
</style>
