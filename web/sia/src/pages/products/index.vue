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
  type ProductType,
  typeLabel,
  useCursorList,
  useReference,
} from '@cimh/web-app'
import { mdiChevronDown, mdiFilterVariant, mdiFormatListBulleted, mdiImageMultipleOutline, mdiMagnify, mdiPlus } from '@mdi/js'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useRoute, useRouter } from 'vue-router'
import ProductRecord from '../../components/ProductRecord.vue'
import StockMeter from '../../components/StockMeter.vue'

definePage({ meta: { guard: 'staff', title: 'Products', ownHeading: true } })
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
      <h1 class="t-h1">Products</h1>
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
        <button v-for="c in typeChips" :key="c.title" type="button" class="chip" :aria-pressed="type === c.value" @click="type = c.value">
          {{ c.title }}
        </button>
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
    <v-expand-transition>
      <div v-show="moreOpen" id="more-filters" class="more">
        <v-select v-model="department" :items="reference?.departments ?? []" label="Department" clearable hide-details density="compact" />
        <v-select v-model="sellable" :items="YESNO" label="Shown to customers" clearable hide-details density="compact" :disabled="searching" />
        <v-select v-model="probono" :items="YESNO" label="Pro Bono" clearable hide-details density="compact" />
        <v-switch v-model="inactive" label="Include inactive" color="primary" inset hide-details density="compact" :disabled="searching" />
        <v-btn variant="text" class="m3" :disabled="!filtered" @click="clearFilters">Clear filters</v-btn>
        <p v-if="searching" class="t-caption muted note">Search shows active products only; “Shown to customers” and “Include inactive” apply to browsing.</p>
      </div>
    </v-expand-transition>

    <div class="console-panels panels" :class="{ split: showRecord }">
      <!-- List -->
      <section class="plist" aria-label="Products">
        <div class="console-head">
          <h2 class="console-title" aria-live="polite">{{ summary }}</h2>
          <v-btn-toggle v-if="!showRecord" v-model="view" mandatory density="compact" variant="text" aria-label="View" class="view">
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

          <TransitionGroup v-else-if="view === 'list' || showRecord" tag="ul" name="prow" class="rows" :class="{ 'no-model': noModels }">
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
                <span class="c-stock"><StockMeter :available="p.stockCount" :threshold="p.threshold" /></span>
              </router-link>
            </li>
          </TransitionGroup>

          <TransitionGroup v-else tag="ul" name="prow" class="pgrid">
            <li v-for="(p, i) in list.items.value" :key="p.id" :style="{ '--i': Math.min(i, 12) }">
              <router-link :to="`/products/${p.id}`" class="pcard" @click.prevent="open(p)">
                <span class="ptile"><ProductImage :image="primaryImage(p)" :alt="p.name" small sizes="220px" /></span>
                <span class="pname">{{ p.name }}</span>
                <span class="console-mono t-caption muted">{{ p.modelnumber || p.id }}</span>
                <span class="sub">
                  <StockMeter :available="p.stockCount" :threshold="p.threshold" />
                  <span v-if="p.probono" class="probono-badge">Pro Bono</span>
                  <span v-if="!p.active" class="flag">Inactive</span>
                  <span v-else-if="!p.sellable" class="flag">Hidden</span>
                </span>
              </router-link>
            </li>
          </TransitionGroup>

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
            <v-btn variant="text" size="small" class="m3" :to="`/products/${openId}`">Open full page</v-btn>
            <v-btn variant="text" size="small" class="m3" @click="close">Close</v-btn>
          </span>
        </div>
        <div class="console-scroll">
          <ProductRecord :key="openId" :product-id="openId" embedded @updated="onUpdated" />
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
  max-width: 1600px;
  margin-inline: auto;
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
  height: 32px;
  padding: 0 12px;
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 8px;
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  color: inherit;
  background: none;
  cursor: pointer;
  white-space: nowrap;
}
.chip {
  transition: background-color 150ms ease, border-color 150ms ease;
}
.chip:active {
  transform: scale(0.97);
}
.chip:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.chip[aria-pressed='true'] {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.14);
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
.more {
  display: grid;
  grid-template-columns: repeat(3, minmax(160px, 220px)) max-content max-content;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3);
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
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
.view {
  height: 32px;
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
.pcard {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: var(--sp-2);
  color: inherit;
  text-decoration: none;
  border-radius: 4px;
}
.pcard:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.ptile :deep(.frame) {
  border-radius: 3px;
  margin-bottom: var(--sp-1);
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
/* Rows: enter with a capped stagger (fade + 6 px rise), leave by fading, slide to new places on re-sort. */
.prow-enter-active {
  transition: opacity 220ms var(--ease-out), transform 220ms var(--ease-out);
  transition-delay: calc(var(--i, 0) * 24ms);
}
.prow-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.prow-leave-active {
  position: absolute;
  width: 100%;
  transition: opacity 140ms ease-in;
}
.pgrid .prow-leave-active {
  width: 180px;
}
.prow-leave-to {
  opacity: 0;
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
</style>
