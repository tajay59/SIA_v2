<script setup lang="ts">
/**
 * A-05 products, the desk's queue-plus-detail pattern: filter strip (search over name, model, keywords,
 * serials; type chips; More filters = department, shown to customers, Pro Bono, inactive), product list on
 * the left, the full product record (A-07: overview, edit, images, stock, history) beside it on wide screens
 * (`?open=<id>`). Narrow screens open the product page. Filters live in the URL.
 */
import {
  boolParam,
  call,
  catalog,
  type ProductStaff,
  primaryImage,
  PRODUCT_TYPES,
  ProductImage,
  ShortRef,
  type ProductType,
  typeLabel,
  useCursorList,
  useReference,
} from '@cimh/web-app'
import { mdiCheck, mdiChevronDown, mdiChevronLeft, mdiChevronRight, mdiFilterVariant, mdiFormatListBulleted, mdiImageMultipleOutline, mdiMagnify, mdiPlus } from '@mdi/js'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useRoute, useRouter } from 'vue-router'
import ProductRecord from '../../components/ProductRecord.vue'
import StockMeter from '../../components/StockMeter.vue'
import { neighbours, rememberProductOrder } from '../../product-nav'

definePage({ meta: { guard: 'staff', title: 'Inventory', ownHeading: true } })
const route = useRoute()
const router = useRouter()
const { reference } = useReference()
const display = useDisplay()

const str = (v: unknown) => (typeof v === 'string' && v ? v : null)
const q = ref(str(route.query.q) ?? '')
const type = ref(str(route.query.type) as ProductType | null)
const department = ref(str(route.query.department))
const sellable = ref(boolParam(route.query.sellable) ?? null)
const probono = ref(boolParam(route.query.probono) ?? null)
const inactive = ref(boolParam(route.query.inactive) === true)
const openId = computed(() => str(route.query.open))

const searching = computed(() => q.value.trim().length >= 2)
// Rows or photos (photos only while no product is open); remembered on this device.
const VIEW_KEY = 'sia.products.view'
const view = ref<'grid' | 'list'>(readView())
function readView(): 'grid' | 'list' {
  try {
    return localStorage.getItem(VIEW_KEY) === 'grid' ? 'grid' : 'list'
  } catch {
    return 'list'
  }
}
watch(view, (v) => {
  try {
    localStorage.setItem(VIEW_KEY, v)
  } catch {
    /* storage unavailable: keep the choice for this visit only */
  }
})

const list = useCursorList<ProductStaff>(async (cursor) => {
  const common = { type: type.value ?? undefined, department: department.value ?? undefined, probono: probono.value ?? undefined, cursor, limit: 50 }
  const page = searching.value
    ? await call(() => catalog.GET('/products/search', { params: { query: { q: q.value.trim(), ...common } } }))
    : await call(() =>
        catalog.GET('/products', {
          params: { query: { ...common, sellable: sellable.value ?? undefined, includeInactive: inactive.value || undefined } },
        }),
      )
  return page as { items: ProductStaff[]; nextCursor?: string | null }
})
onMounted(list.reload)

function queryFor(open: string | null, keep = true) {
  const query: Record<string, string> = {}
  if (q.value.trim()) query.q = q.value.trim()
  if (type.value) query.type = type.value
  if (department.value) query.department = department.value
  if (sellable.value !== null) query.sellable = String(sellable.value)
  if (probono.value !== null) query.probono = String(probono.value)
  if (inactive.value) query.inactive = 'true'
  if (open) query.open = open
  if (keep && open && typeof route.query.tab === 'string') query.tab = route.query.tab
  return query
}

let timer: ReturnType<typeof setTimeout> | undefined
// A pending debounce must not fire after the page is left (router.replace would navigate back here).
onBeforeUnmount(() => clearTimeout(timer))
watch([q, type, department, sellable, probono, inactive], () => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    void router.replace({ query: queryFor(openId.value) })
    void list.reload()
  }, 250)
})

// ---- Filters
const typeChips = computed(() => [
  { value: null as ProductType | null, title: 'All' },
  ...PRODUCT_TYPES.map((k) => ({ value: k as ProductType | null, title: typeLabel(reference.value, k) })),
])
const YESNO = [
  { value: true, title: 'Yes' },
  { value: false, title: 'No' },
]
const moreCount = computed(() => [department.value, sellable.value, probono.value].filter((v) => v !== null).length + (inactive.value ? 1 : 0))
const moreOpen = ref(moreCount.value > 0)

// View switch: the scroll box keeps its height while the old view leaves (below 1280 px the page scrolls and the
// box would otherwise collapse for a moment); released as soon as the new view is inserted, so it never jumps at
// the end either.
// Meters drawn by a view switch start at their level (the same counts; a refill on every row pulled the eye).
const switching = ref(false)
let switchTimer: ReturnType<typeof setTimeout> | undefined
watch(view, () => {
  switching.value = true
  // Safety: a switch while the list is loading or empty runs no transition, so after-enter never clears it.
  clearTimeout(switchTimer)
  switchTimer = setTimeout(() => (switching.value = false), 600)
})
onBeforeUnmount(() => clearTimeout(switchTimer))
function holdHeight(el: Element) {
  const box = (el as HTMLElement).parentElement
  if (box) box.style.minHeight = `${box.offsetHeight}px`
}
function releaseHeight(el: Element) {
  const box = (el as HTMLElement).parentElement
  if (box) box.style.minHeight = ''
}
function clearFilters() {
  type.value = null
  department.value = null
  sellable.value = null
  probono.value = null
  inactive.value = false
}
const filtered = computed(() => moreCount.value > 0 || type.value !== null)

// ---- Selection
const wide = computed(() => display.width.value >= 1280)
const showRecord = computed(() => wide.value && !!openId.value)
// No product on the page has a model number: drop the column instead of a row of dashes.
const noModels = computed(() => list.items.value.length > 0 && list.items.value.every((p) => !p.modelnumber))
function open(p: ProductStaff) {
  if (!wide.value) return void router.push(`/products/${p.id}`)
  void router.replace({ query: queryFor(p.id, false) })
}
function close() {
  void router.replace({ query: queryFor(null) })
}
function onRowKey(e: KeyboardEvent, i: number) {
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
  e.preventDefault()
  const items = list.items.value
  const next = items[Math.max(0, Math.min(items.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))]
  if (!next) return
  document.getElementById(`prow-${next.id}`)?.focus()
  if (showRecord.value) open(next)
}
// Previous / next inside the record (owner 2026-11-25): the record steps through the order shown here, keeping its tab.
watch(() => list.items.value.map((p) => p.id), rememberProductOrder, { immediate: true })
const around = computed(() => (openId.value ? neighbours(openId.value, list.items.value.map((p) => p.id)) : null))
function step(id: string | null) {
  if (!id) return
  void router.replace({ query: queryFor(id) })
  document.getElementById(`prow-${id}`)?.scrollIntoView({ block: 'nearest' })
}
/** Keep the row in step with saves made in the record (name, stock, flags). */
function onUpdated(p: ProductStaff) {
  const i = list.items.value.findIndex((x) => x.id === p.id)
  if (i >= 0) list.items.value.splice(i, 1, p)
}
const summary = computed(() => {
  if (!list.loaded.value) return 'Loading…'
  const n = list.items.value.length
  const more = list.nextCursor.value ? '+' : ''
  return searching.value ? `${n}${more} matches · best first` : `${n}${more} products · name A–Z`
})
</script>

<template>
  <div class="products">
    <div class="top">
      <h1 class="t-h1">Inventory</h1>
      <span class="spacer" />
      <v-btn class="m3 new-product" color="primary" :prepend-icon="mdiPlus" to="/products/new">New product</v-btn>
    </div>

    <!-- Filter strip -->
    <div class="strip">
      <v-text-field
        v-model="q"
        data-page-search
        :prepend-inner-icon="mdiMagnify"
        label="Name, model, keyword or serial"
        clearable
        hide-details
        density="compact"
        class="search"
        @click:clear="q = ''"
      />
      <div class="chips" role="group" aria-label="Type">
        <!-- Tonal buttons (owner 2026-11-25), as the /pick purposes: the chosen type tonal primary with a check. -->
        <v-btn
          v-for="c in typeChips"
          :key="c.title"
          class="chip"
          variant="tonal"
          :color="type === c.value ? 'primary' : undefined"
          :prepend-icon="type === c.value ? mdiCheck : undefined"
          :aria-pressed="type === c.value ? 'true' : 'false'"
          @click="type = c.value"
        >{{ c.title }}</v-btn>
      </div>
      <v-btn
        variant="outlined"
        class="m3 more-btn"
        :class="{ open: moreOpen }"
        :prepend-icon="mdiFilterVariant"
        :append-icon="mdiChevronDown"
        :aria-expanded="moreOpen"
        aria-controls="more-filters"
        @click="moreOpen = !moreOpen"
      >
        More filters<span v-if="moreCount" class="badge console-mono">{{ moreCount }}</span>
      </v-btn>
    </div>
    <!-- More filters unfold out of the strip (impeccable animate, 2026-11-25): a grid row 0fr → 1fr, so the real height
         animates with no JS measuring; the page gap folds in with it; the contents fade in a beat later. Closed, the
         contents are visibility: hidden (out of the tab order and the accessibility tree). -->
    <div class="more-wrap" :class="{ open: moreOpen }">
      <div class="more-clip">
      <div id="more-filters" class="more">
        <v-select v-model="department" :items="reference?.departments ?? []" label="Department" clearable hide-details density="compact" />
        <v-select v-model="sellable" :items="YESNO" label="Shown to customers" clearable hide-details density="compact" :disabled="searching" />
        <v-select v-model="probono" :items="YESNO" label="Pro Bono" clearable hide-details density="compact" />
        <v-switch v-model="inactive" label="Include inactive" color="primary" inset hide-details density="compact" :disabled="searching" />
        <v-btn variant="text" class="m3" :disabled="!filtered" @click="clearFilters">Clear filters</v-btn>
        <p v-if="searching" class="t-caption muted note">Search shows active products only; “Shown to customers” and “Include inactive” apply to browsing.</p>
      </div>
      </div>
    </div>

    <div class="console-panels panels" :class="{ split: showRecord }">
      <!-- List -->
      <section class="plist" aria-label="Products">
        <div class="console-head">
          <h2 class="console-title" aria-live="polite">{{ summary }}</h2>
          <!-- Tonal segmented pill (owner 2026-11-25): both halves on a tonal ground, the chosen view tonal primary. -->
          <v-btn-toggle v-if="!showRecord" v-model="view" mandatory variant="tonal" color="primary" rounded="pill" divided aria-label="View" class="view">
            <v-btn value="list" :icon="mdiFormatListBulleted" aria-label="Rows" />
            <v-btn value="grid" :icon="mdiImageMultipleOutline" aria-label="Photos" />
          </v-btn-toggle>
        </div>
        <div class="console-scroll">
          <div v-if="!list.loaded.value && list.loading.value" class="skel-rows">
            <div v-for="i in 8" :key="i" class="console-skel skel-row" />
          </div>

          <div v-else-if="list.loaded.value && !list.items.value.length" class="empty">
            <p class="t-body">No products match{{ searching ? ` “${q.trim()}”` : ' these filters' }}.</p>
            <div class="row">
              <v-btn v-if="filtered" class="m3" variant="outlined" @click="clearFilters">Clear filters</v-btn>
              <v-btn class="m3" variant="text" to="/products/new">Create a product</v-btn>
            </div>
          </div>

          <!-- Rows ↔ photos (impeccable animate, 2026-11-25): the old view fades out fast, the new one settles in; the
               scroll box keeps its height meanwhile, so narrow screens (page scroll) never collapse. -->
          <Transition
            v-else
            name="vswap"
            mode="out-in"
            @before-leave="holdHeight"
            @enter="releaseHeight"
            @leave-cancelled="releaseHeight"
            @enter-cancelled="releaseHeight"
            @after-enter="switching = false"
          >
          <!-- Keyed wrappers: a TransitionGroup cannot be a Transition's direct child (its leave never ran). -->
          <div v-if="view === 'list' || showRecord" key="rows" class="vbox">
          <TransitionGroup tag="ul" name="prow" class="rows" :class="{ 'no-model': noModels }">
            <li v-if="!showRecord" key="head" class="row-h" aria-hidden="true">
              <span />
              <span>Name</span>
              <span class="c-model">Model number</span>
              <span class="c-type">Type</span>
              <span class="c-dept">Department</span>
              <span>In stock</span>
            </li>
            <li v-for="(p, i) in list.items.value" :key="p.id" :style="{ '--i': Math.min(i, 12) }">
              <router-link
                :id="`prow-${p.id}`"
                :to="`/products/${p.id}`"
                class="prow"
                :class="{ on: openId === p.id && showRecord, off: !p.active }"
                :aria-current="openId === p.id && showRecord ? 'true' : undefined"
                @click.prevent="open(p)"
                @keydown="onRowKey($event, i)"
              >
                <span class="thumb"><ProductImage :image="primaryImage(p)" alt="" small sizes="40px" /></span>
                <span class="c-name">
                  <span class="pname">{{ p.name }}</span>
                  <span class="sub">
                    <span v-if="showRecord && p.modelnumber" class="console-mono">{{ p.modelnumber }}</span>
                    <span v-if="p.probono" class="probono-badge">Pro Bono<template v-if="p.probonoMaxPerRequest"> · max {{ p.probonoMaxPerRequest }}</template></span>
                    <span v-if="!p.active" class="flag">Inactive</span>
                    <span v-else-if="!p.sellable" class="flag">Hidden</span>
                  </span>
                </span>
                <span class="c-model console-mono">{{ p.modelnumber || '—' }}</span>
                <span class="c-type">{{ typeLabel(reference, p.type) }}</span>
                <span class="c-dept">{{ p.department }}</span>
                <span class="c-stock"><StockMeter :available="p.stockCount" :threshold="p.threshold" :still="switching" /></span>
              </router-link>
            </li>
          </TransitionGroup>

          </div>
          <div v-else key="grid" class="vbox vbox-grid">
          <TransitionGroup tag="ul" name="prow" class="pgrid">
            <li v-for="(p, i) in list.items.value" :key="p.id" :style="{ '--i': Math.min(i, 12) }">
              <router-link :to="`/products/${p.id}`" class="pcard" @click.prevent="open(p)">
                <span class="ptile">
                  <ProductImage :image="primaryImage(p)" :alt="p.name" small sizes="220px" />
                  <span v-if="p.probono" class="pflag probono-badge">Pro Bono</span>
                  <span v-if="!p.active" class="pflag pstate">Inactive</span>
                  <span v-else-if="!p.sellable" class="pflag pstate">Hidden</span>
                </span>
                <span class="pname">{{ p.name }}</span>
                <span class="pfoot">
                  <StockMeter :available="p.stockCount" :threshold="p.threshold" :still="switching" />
                  <span class="console-mono t-caption muted pid" :title="p.modelnumber || undefined"><template v-if="p.modelnumber">{{ p.modelnumber }}</template><ShortRef v-else :id="p.id" :fit="false" /></span>
                </span>
              </router-link>
            </li>
          </TransitionGroup>
          </div>
          </Transition>

          <div v-if="list.nextCursor.value" class="load-more">
            <v-btn class="m3" variant="outlined" :loading="list.loading.value" @click="list.loadMore">Load more</v-btn>
          </div>
        </div>
      </section>

      <!-- Record -->
      <section v-if="showRecord && openId" class="record" aria-label="Selected product">
        <div class="console-head">
          <h2 class="console-title">Selected product</h2>
          <span class="row head-acts">
            <span v-if="around" class="row stepper" role="group" :aria-label="`Product ${around.index + 1} of ${around.total} in the list (Alt+Up / Alt+Down)`">
              <v-btn variant="text" class="step-btn" :icon="mdiChevronLeft" :disabled="!around.prev" aria-label="Previous product" title="Previous product (Alt+↑)" aria-keyshortcuts="Alt+ArrowUp" @click="step(around.prev)" />
              <span class="step-pos console-mono" aria-hidden="true">{{ around.index + 1 }} of {{ around.total }}{{ list.nextCursor.value ? '+' : '' }}</span>
              <v-btn variant="text" class="step-btn" :icon="mdiChevronRight" :disabled="!around.next" aria-label="Next product" title="Next product (Alt+↓)" aria-keyshortcuts="Alt+ArrowDown" @click="step(around.next)" />
            </span>
            <v-btn variant="text" size="small" class="m3" :to="`/products/${openId}`">Open full page</v-btn>
            <v-btn variant="text" size="small" class="m3" @click="close">Close</v-btn>
          </span>
        </div>
        <div class="console-scroll">
          <ProductRecord :key="openId" :product-id="openId" embedded @updated="onUpdated" @step="step" />
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.products {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding: var(--sp-4) var(--sp-6) var(--sp-6);
  font-size: 14px;
}
@media (min-width: 1280px) {
  .products {
    height: 100dvh;
    min-height: 560px;
  }
  .products > :not(.panels) {
    flex-shrink: 0;
  }
}
.top {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  height: 36px; /* the title's line: the button may not push the title down */
  margin-bottom: var(--sp-3); /* + the page's 12 px gap = 24 px under the title, as every page */
}
.strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-3);
}
.search {
  flex: 1 1 280px;
  max-width: 420px;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip {
  flex: none; /* phones scroll the row sideways; buttons keep their width */
  height: 36px;
  font-size: 14px;
  letter-spacing: 0;
  text-transform: none;
  white-space: nowrap;
}
.chip:active {
  transform: scale(0.97);
}
.more-btn {
  margin-left: auto;
}
.more-btn :deep(.v-btn__append) {
  margin-inline: 4px 0;
  transition: transform 200ms var(--ease-out);
}
.more-btn.open :deep(.v-btn__append) {
  transform: rotate(180deg);
}
.badge {
  margin-left: 6px;
  min-width: 20px;
  padding: 0 6px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 20px;
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}
.more-wrap {
  display: grid;
  grid-template-rows: 0fr;
  margin-top: calc(-1 * var(--sp-3)); /* closed: cancel the page gap, so nothing jumps when it opens */
  transition:
    grid-template-rows 200ms cubic-bezier(0.4, 0, 0.2, 1),
    margin-top 200ms cubic-bezier(0.4, 0, 0.2, 1);
}
.more-wrap.open {
  grid-template-rows: 1fr;
  margin-top: 0;
  transition-duration: 300ms;
  transition-timing-function: var(--ease-out);
}
/* The panel's surface is the clip itself, so the fold reveals the panel's edge as it grows (motion review:
   the list was pushed by an empty hole while a fading box arrived 60 ms late). Drawn as an inset shadow: at
   0 height a box with an inset shadow paints nothing, where a border would leave a 2 px line. */
.more-clip {
  min-height: 0;
  overflow: hidden;
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
  box-shadow: inset 0 0 0 1px rgb(var(--v-theme-seam));
  visibility: hidden;
  transition: visibility 0s 200ms; /* hidden only once the fold has closed */
}
.more-wrap.open .more-clip {
  visibility: visible;
  transition: none;
}
/* Only the fields fade: in shortly after the fold starts, out before its edge reaches them. */
.more {
  opacity: 0;
  transform: translateY(-8px);
  transition:
    opacity 90ms ease-out,
    transform 200ms cubic-bezier(0.4, 0, 0.2, 1);
}
.more-wrap.open .more {
  opacity: 1;
  transform: none;
  transition:
    opacity 150ms ease-out 20ms,
    transform 300ms var(--ease-out);
}
/* Reduced motion: base.css makes every transition instant; only the movement is removed here. */
@media (prefers-reduced-motion: reduce) {
  .more {
    transform: none;
  }
}
.more {
  display: grid;
  grid-template-columns: repeat(3, minmax(160px, 220px)) max-content max-content;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3);
}
.note {
  grid-column: 1 / -1;
  margin: 0;
}
.panels {
  grid-template-columns: minmax(0, 1fr);
}
.panels.split {
  grid-template-columns: minmax(340px, 400px) minmax(0, 1fr);
}
.record {
  border-left: 1px solid rgb(var(--v-theme-seam));
  background: rgb(var(--v-theme-background));
  min-width: 0;
}
.head-acts {
  gap: var(--sp-1);
}
.stepper {
  gap: 0;
  align-items: center;
  margin-right: var(--sp-2);
}
.step-pos {
  min-width: 6ch;
  text-align: center;
  font-size: 11px;
  color: rgb(var(--v-theme-secondary));
}
.view {
  height: 32px;
}
.view {
  border-radius: 999px;
  overflow: hidden;
}
/* One pill split in two: the app's per-button pill (m3) is undone inside the group, so the group's own pill and
   its divider show. */
.view :deep(.v-btn) {
  width: 40px;
  min-width: 0;
  height: 32px;
  border-radius: 0 !important;
}
.view :deep(.v-btn .v-icon) {
  font-size: 18px;
}
/* The half not chosen: the tonal ground stays, the icon in medium ink (Vuetify tints it with the toggle colour). */
.view :deep(.v-btn:not(.v-btn--active)) {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.rows {
  list-style: none;
  position: relative;
  margin: 0;
  padding: 0;
}
.row-h,
.prow {
  display: grid;
  grid-template-columns: 40px minmax(200px, 3fr) minmax(110px, 1fr) minmax(110px, 1fr) minmax(110px, 1fr) 150px;
  align-items: center;
  gap: var(--sp-3);
  padding: 0 var(--sp-4);
}
.no-model .row-h,
.no-model .prow {
  grid-template-columns: 40px minmax(200px, 3fr) minmax(110px, 1fr) minmax(110px, 1fr) 150px;
}
.no-model .c-model {
  display: none;
}
.split .prow {
  grid-template-columns: 40px minmax(0, 1fr) auto;
}
.split .c-model,
.split .c-type,
.split .c-dept {
  display: none;
}
.row-h {
  position: sticky;
  top: 0;
  z-index: 1;
  height: 36px;
  font-size: 12px;
  font-weight: 500;
  color: rgb(var(--v-theme-secondary));
  background: rgb(var(--v-theme-surface));
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.prow {
  min-height: 56px;
  padding-block: 8px;
  color: inherit;
  text-decoration: none;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
  transition: background-color 120ms ease;
}
.prow:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.prow.on {
  background: rgba(var(--v-theme-primary), 0.14);
  box-shadow: inset 2px 0 rgb(var(--v-theme-primary));
}
.prow:focus-visible {
  outline-offset: -2px;
}
.prow.off .pname {
  color: rgb(var(--v-theme-secondary));
}
.thumb :deep(.frame) {
  width: 40px;
  height: 30px;
  aspect-ratio: auto;
  border-radius: 3px;
}
.thumb :deep(img) {
  height: 30px;
}
.c-name {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
/* One line: a long model number ends in an ellipsis (full on hover); a bare id is shortened (full in a tooltip). */
.pid {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pname {
  font-weight: 500;
  line-height: 20px;
}
.sub {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  color: rgb(var(--v-theme-secondary));
  font-size: 12px;
}
.sub:empty {
  display: none;
}
.flag {
  font-size: 12px;
  line-height: 18px;
  padding: 0 6px;
  border-radius: 3px;
  border: 1px solid rgb(var(--v-theme-seam));
  color: rgb(var(--v-theme-secondary));
}
.c-model,
.c-type,
.c-dept {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.skel-rows {
  padding: var(--sp-2) var(--sp-4);
}
.skel-row {
  height: 40px;
  margin: 12px 0;
  border-radius: 4px;
}
.empty {
  padding: var(--sp-8) var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.load-more {
  display: flex;
  justify-content: center;
  padding: var(--sp-4);
}
.pgrid {
  list-style: none;
  position: relative;
  margin: 0;
  padding: var(--sp-4);
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--sp-4);
}
/* Photo cards (2026-11-19, owner's reference): bordered card, photo on a tinted plate with flags in its
   corners, name, type tag, then a foot seam with the stock meter where a shop prints the price. */
.pcard {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 6px;
  height: 100%;
  padding: var(--sp-2) var(--sp-2) 0;
  color: inherit;
  text-decoration: none;
  border-radius: 8px;
  min-width: 0;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  transition: border-color 160ms ease-out, box-shadow 200ms ease-out;
}
.pcard:hover {
  border-color: rgba(var(--v-theme-primary), 0.7);
  box-shadow: 0 10px 22px -14px rgba(0, 0, 0, 0.5);
}
.pcard:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.ptile {
  position: relative;
  display: block;
  border-radius: 6px;
  overflow: hidden;
  background: #eef2f6;
}
.ptile :deep(.frame) {
  border-radius: 0;
  background: transparent;
}
.ptile :deep(img) {
  mix-blend-mode: multiply;
  transition: transform 300ms cubic-bezier(0.16, 1, 0.3, 1);
}
.pcard:hover .ptile :deep(img) {
  transform: scale(1.04);
}
.pflag {
  position: absolute;
  top: 6px;
  left: 6px;
}
.pflag.pstate {
  left: auto;
  right: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  background: #1b1e22;
  color: #fff;
}
.pname {
  margin-top: 4px;
  font-weight: 600;
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.ptag {
  align-self: flex-start;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.12);
}
.pfoot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
  margin: auto calc(-1 * var(--sp-2)) 0;
  padding: var(--sp-2);
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  min-width: 0;
}
.pfoot .pid {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pgrid > li {
  min-width: 0;
}
@media (prefers-reduced-motion: reduce) {
  .pcard:hover .ptile :deep(img) {
    transform: none;
  }
}
@media (max-width: 1099.98px) {
  .row-h,
  .prow {
    grid-template-columns: 40px minmax(0, 2fr) minmax(90px, 1fr) minmax(90px, 1fr) 150px;
  }
  .no-model .row-h,
  .no-model .prow {
    grid-template-columns: 40px minmax(0, 2fr) minmax(90px, 1fr) 150px;
  }
  .c-dept {
    display: none;
  }
  .more {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 759.98px) {
  .products {
    padding: var(--sp-3) var(--sp-4) var(--sp-6);
  }
  .row-h,
  .prow {
    grid-template-columns: 40px minmax(0, 1fr) auto;
  }
  .no-model .row-h,
  .no-model .prow {
    grid-template-columns: 40px minmax(0, 1fr) auto;
  }
  .c-model,
  .c-type {
    display: none;
  }
  .chips {
    flex-wrap: nowrap;
    overflow-x: auto;
    scrollbar-width: none;
    order: 3;
    flex-basis: 100%;
  }
  .search {
    max-width: none;
  }
  .more {
    grid-template-columns: minmax(0, 1fr);
  }
}
/* Rows ↔ photos: out 90 ms (fade), in 200 ms (fade + 6 px settle; photos from 98.5 % scale). */
.vswap-leave-active {
  transition: opacity 90ms ease-in;
}
.vswap-leave-to {
  opacity: 0;
}
.vswap-enter-active {
  transition:
    opacity 200ms ease-out,
    transform 260ms var(--ease-out);
}
.vswap-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.vbox-grid {
  transform-origin: 50% 0; /* top-anchored for the whole transition (on the -from class alone it ran from the centre) */
}
.vbox-grid.vswap-enter-from {
  transform: scale(0.985);
}
@media (prefers-reduced-motion: reduce) {
  .vswap-enter-from,
  .vbox-grid.vswap-enter-from {
    transform: none;
  }
}
/* Rows: enter with a capped stagger (fade + 6 px rise), slide to new places on re-sort, and leave at once: a type
   or filter change replaces most rows, and leaving rows taken out of flow (position: absolute, no top) all stacked
   on row one while they faded (owner, 2026-11-25). */
.prow-enter-active {
  transition: opacity 220ms var(--ease-out), transform 220ms var(--ease-out);
  transition-delay: calc(var(--i, 0) * 24ms);
}
.prow-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.prow-move {
  transition: transform 280ms var(--ease-out);
}
@media (prefers-reduced-motion: reduce) {
  .prow-enter-active {
    transition: opacity 160ms ease;
    transition-delay: 0ms;
  }
  .prow-enter-from {
    transform: none;
  }
  .prow-move {
    transition: none;
  }
}
/* Previous / next: 32 px targets in ink (the disabled end stays visible at Vuetify's disabled opacity). */
.step-btn {
  width: 32px !important;
  height: 32px !important;
  color: rgb(var(--v-theme-on-surface));
}
.step-btn :deep(.v-icon) {
  font-size: 20px;
  width: 20px;
  height: 20px;
}

</style>
