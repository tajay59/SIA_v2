<script setup lang="ts">
/**
 * A-07 product record (own page, and beside the list in A-05): identity header with the stock meter and actions, then tabs Overview (photos, description,
 * facts), Details (edit, If-Match), Images, Stock (by shelf), History (admins: audit entries).
 * Deactivate = soft delete (hidden from customers, kept for history and requests).
 */
import {
  ApiError,
  type AuditEntry,
  call,
  catalog,
  identity,
  ifMatch,
  inventory,
  type ProductStock,
  type ProductPatch,
  type ProductStaff,
  primaryImage,
  removeDraft,
  ProductBadges,
  ProductImage,
  typeLabel,
  useNotify,
  useReference,
  useSession,
} from '@cimh/web-app'
import { formatDateTime } from '@cimh/web-ui'
import { mdiArrowLeft, mdiTagOutline } from '@mdi/js'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ProductForm from './ProductForm.vue'
import ProductImagesPanel from './ProductImagesPanel.vue'
import StockMeter from './StockMeter.vue'
import { revealInStrip } from '../strip'

const props = defineProps<{ productId: string; embedded?: boolean }>()
const emit = defineEmits<{ updated: [product: ProductStaff] }>()
const route = useRoute()
const router = useRouter()
const session = useSession()
const notify = useNotify()
const { reference } = useReference()

const product = ref<ProductStaff | null>(null)
const missing = ref(false)
const saving = ref(false)
const errors = ref<Record<string, string>>({})
const TABS = computed(() => [
  { value: 'overview', title: 'Overview' },
  { value: 'details', title: 'Edit details' },
  { value: 'images', title: `Images (${product.value?.images.length ?? 0})` },
  { value: 'stock', title: 'Stock' },
  ...(session.isAdmin ? [{ value: 'history', title: 'History' }] : []),
])
const tab = computed({
  get: () => {
    const t = typeof route.query.tab === 'string' ? route.query.tab : 'overview'
    return TABS.value.some((x) => x.value === t) ? t : 'overview'
  },
  set: (t: string) => void router.replace({ query: { ...route.query, tab: t } }),
})

async function load() {
  try {
    product.value = (await call(() =>
      catalog.GET('/products/{productId}', { params: { path: { productId: props.productId } } }),
    )) as ProductStaff
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) missing.value = true
    else notify.report(e, { retry: load })
  }
}

async function save(body: Record<string, unknown>) {
  const p = product.value
  if (!p) return
  if (!Object.keys(body).length) return notify.toast('Nothing changed', 'info')
  saving.value = true
  errors.value = {}
  try {
    const before = `product:${p.id}:v${p.version}`
    product.value = (await call(() =>
      catalog.PATCH('/products/{productId}', {
        params: { path: { productId: p.id }, header: { 'If-Match': ifMatch(p.version) } },
        body: body as ProductPatch,
      }),
    )) as ProductStaff
    removeDraft(before)
    notify.toast('Product saved', 'success')
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) errors.value = e.fieldErrors()
    notify.report(e, { retry: load })
  } finally {
    saving.value = false
  }
}

const shown = ref<string | null>(null)
const shownImage = computed(() => {
  const imgs = product.value?.images ?? []
  return imgs.find((i) => i.fileId === shown.value) ?? (product.value ? (primaryImage(product.value) ?? null) : null)
})
const model = computed(() => [product.value?.make, product.value?.modelname].filter(Boolean).join(' '))
const serials = computed(() => [product.value?.sn, product.value?.sn1].filter(Boolean).join(', '))
const project = computed(() => {
  const code = product.value?.project
  if (!code) return null
  return reference.value?.projects?.find((p) => p.code === code)?.name ?? code
})
const visibility = computed(() => {
  const p = product.value
  if (!p) return ''
  if (!p.active) return 'Inactive: hidden from customers'
  return p.sellable ? 'Shown to customers' : 'Hidden from customers'
})

const deactivateOpen = ref(false)
async function deactivate() {
  const p = product.value
  if (!p) return
  saving.value = true
  try {
    await call(() =>
      catalog.DELETE('/products/{productId}', { params: { path: { productId: p.id }, header: { 'If-Match': ifMatch(p.version) } } }),
    )
    deactivateOpen.value = false
    notify.toast(`${p.name} is no longer shown to customers`, 'success')
    await load()
  } catch (e) {
    notify.report(e, { retry: load })
  } finally {
    saving.value = false
  }
}

// Stock: counts and units per shelf, from inventory-svc (header meter, Overview, Stock tab).
const stock = ref<ProductStock | null>(null)
const stockError = ref(false)
async function loadStock() {
  if (!product.value) return
  stockError.value = false
  try {
    stock.value = await call(() => inventory.GET('/products/{productId}/stock', { params: { path: { productId: product.value!.id } } }))
  } catch (e) {
    stockError.value = true
    if (tab.value === 'stock') notify.report(e)
  }
}
watch(() => product.value?.id, loadStock, { immediate: true })

// History (admins): audit entries recorded for this product (cost changes, deactivation…).
const history = ref<AuditEntry[] | null>(null)
watch(
  () => [tab.value, product.value?.id],
  async () => {
    if (tab.value !== 'history' || !product.value || !session.isAdmin) return
    try {
      const page = await call(() =>
        identity.GET('/audit', { params: { query: { entityType: 'product', entityId: product.value!.id, limit: 100 } } }),
      )
      history.value = page.items
    } catch (e) {
      notify.report(e)
    }
  },
  { immediate: true },
)
const actionLabel = (a: string) => {
  const s = a.replace('product.', '').replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}
// Tab ink: one bar slides to the chosen tab. Placed without animation first (then `settled`); the pane
// arrives from the side of the previous tab.
const tabsEl = ref<HTMLElement | null>(null)
const ink = ref({ x: 0, w: 0 })
const inkReady = ref(false)
const tabDir = ref<'fwd' | 'back'>('fwd')
function placeInk() {
  const strip = tabsEl.value
  const el = strip?.querySelector<HTMLElement>(`[data-tab="${tab.value}"]`)
  if (!strip || !el) return
  // Phones: the strip scrolls; keep the chosen tab on screen. The ink lives inside the strip and scrolls with it.
  revealInStrip(strip, el)
  ink.value = { x: el.offsetLeft, w: el.offsetWidth }
}
watch(tab, (now, before) => {
  const order = TABS.value.map((t) => t.value)
  tabDir.value = order.indexOf(now) >= order.indexOf(before) ? 'fwd' : 'back'
  void nextTick(placeInk)
})
// The tab strip appears once the product has loaded; place the ink then, before it may animate.
watch(tabsEl, (el) => {
  if (!el) return
  placeInk()
  void document.fonts?.ready.then(placeInk)
  requestAnimationFrame(() => (inkReady.value = true))
})
watch(() => TABS.value.map((t) => t.title).join('|'), () => void nextTick(placeInk))
onMounted(() => addEventListener('resize', placeInk))
onBeforeUnmount(() => removeEventListener('resize', placeInk))

// Declared last: resets state that is defined above when another product opens.
watch(
  () => props.productId,
  () => {
    missing.value = false
    stock.value = null
    history.value = null
    shown.value = null
    void load()
  },
  { immediate: true },
)
watch(product, (p) => p && emit('updated', p))
</script>

<template>
  <div class="pp" :class="{ embedded }">
    <div v-if="missing" class="missing">
      <h1 class="t-h2">Product not found</h1>
      <p class="t-body muted">It may have been mistyped or removed from the catalogue.</p>
      <div><v-btn class="m3" variant="outlined" to="/products">Back to products</v-btn></div>
    </div>
    <div v-else-if="!product" class="loading">
      <div class="console-skel sk-head" />
      <div class="console-skel sk-body" />
    </div>
    <template v-else>
      <router-link v-if="!embedded" to="/products" class="back t-label"><v-icon :icon="mdiArrowLeft" size="18" />Products</router-link>

      <!-- Identity -->
      <header class="head">
        <div class="thumb"><ProductImage :image="primaryImage(product)" alt="" small sizes="72px" /></div>
        <div class="ident">
          <component :is="embedded ? 'h2' : 'h1'" class="name">{{ product.name }}</component>
          <div class="meta">
            <span>{{ typeLabel(reference, product.type) }}</span>
            <span aria-hidden="true">·</span>
            <span>{{ product.department }}</span>
            <template v-if="product.modelnumber">
              <span aria-hidden="true">·</span>
              <span class="console-mono">{{ product.modelnumber }}</span>
            </template>
            <ProductBadges :product="product" show-limit />
            <span class="vis" :class="{ off: !product.active }">{{ visibility }}</span>
          </div>
        </div>
        <div class="stockbox">
          <StockMeter :available="stock?.available ?? product.stockCount" :threshold="product.threshold" size="large" />
          <span class="t-caption muted">available<template v-if="product.threshold"> · alert at {{ product.threshold }}</template></span>
        </div>
        <div class="acts">
          <v-btn class="m3" color="primary" :prepend-icon="mdiTagOutline" :to="{ path: '/inventory', query: { op: 'labels', product: product.id } }">Create labels</v-btn>
        </div>
      </header>

      <nav ref="tabsEl" class="tabs" :class="{ settled: inkReady }" aria-label="Product sections" role="tablist">
        <button
          v-for="t in TABS"
          :key="t.value"
          type="button"
          role="tab"
          class="tab"
          :data-tab="t.value"
          :aria-selected="tab === t.value"
          @click="tab = t.value"
        >
          {{ t.title }}
        </button>
        <span class="tab-ink" aria-hidden="true" :style="{ transform: `translateX(${ink.x}px) scaleX(${ink.w})` }" />
      </nav>

      <!-- Overview -->
      <div v-if="tab === 'overview'" class="pane overview" :class="tabDir">
        <section class="gallery" aria-label="Photos">
          <Transition name="photo" mode="out-in">
            <ProductImage :key="shownImage?.fileId ?? 'none'" :image="shownImage" :alt="product.name" sizes="(max-width: 960px) 100vw, 560px" />
          </Transition>
          <div v-if="product.images.length > 1" class="thumbs" role="group" aria-label="Choose photo">
            <button
              v-for="(img, i) in product.images"
              :key="img.fileId"
              type="button"
              class="th"
              :class="{ on: shownImage?.fileId === img.fileId }"
              :aria-label="`Photo ${i + 1} of ${product.images.length}`"
              :aria-pressed="shownImage?.fileId === img.fileId"
              @click="shown = img.fileId"
            >
              <ProductImage :image="img" alt="" small sizes="64px" />
            </button>
          </div>
          <p v-if="!product.images.length" class="t-caption muted">
            No photos yet. <button type="button" class="console-retry" @click="tab = 'images'">Add photos</button>
          </p>
        </section>

        <div class="cols">
          <section class="panel">
            <div class="console-head"><h2 class="console-title">Description</h2></div>
            <div class="panel-body">
              <p class="t-body prose">{{ product.description || 'No description yet. Customers see this text on the product page.' }}</p>
              <p v-if="product.details" class="t-body muted prose details">{{ product.details }}</p>
              <div v-if="product.keywords?.length" class="kw">
                <span v-for="k in product.keywords" :key="k" class="kw-chip">{{ k }}</span>
              </div>
            </div>
          </section>

          <section class="panel">
            <div class="console-head"><h2 class="console-title">Facts</h2></div>
            <dl class="facts panel-body">
              <template v-if="model"><dt>Make and model</dt><dd>{{ model }}</dd></template>
              <template v-if="product.modelnumber"><dt>Model number</dt><dd class="console-mono">{{ product.modelnumber }}</dd></template>
              <template v-if="serials"><dt>Serials (staff only)</dt><dd class="console-mono">{{ serials }}</dd></template>
              <dt>Cost (staff only)</dt><dd class="console-mono">{{ product.cost ? `${product.cost} BBD` : '—' }}</dd>
              <dt>Units per pack</dt><dd class="console-mono">{{ product.unitquantity ?? 1 }}</dd>
              <template v-if="product.weight"><dt>Weight</dt><dd class="console-mono">{{ product.weight }} kg</dd></template>
              <template v-if="product.dimension"><dt>Dimensions</dt><dd>{{ product.dimension }}</dd></template>
              <template v-if="project"><dt>Project</dt><dd>{{ project }}</dd></template>
              <dt>Id</dt><dd class="console-mono id">{{ product.id }}</dd>
            </dl>
          </section>

          <section class="panel">
            <div class="console-head">
              <h2 class="console-title">Shelves</h2>
              <button type="button" class="console-retry t-caption" @click="tab = 'stock'">Stock details</button>
            </div>
            <div class="panel-body">
              <div v-if="!stock && !stockError" class="console-skel sk-small" />
              <p v-else-if="stockError" class="t-body muted">Stock could not be loaded. <button type="button" class="console-retry" @click="loadStock">Try again</button></p>
              <p v-else-if="stock && !stock.byLocation.length" class="t-body muted">Nothing of this product is on a shelf.</p>
              <ul v-else-if="stock" class="shelves">
                <li v-for="b in stock.byLocation.slice(0, 5)" :key="b.shelf">
                  <span>{{ b.siteName ?? b.site }} › {{ b.locationName ?? b.location }} › Shelf {{ b.shelfNumber ?? '?' }}</span>
                  <span class="console-mono">{{ b.count }}</span>
                </li>
              </ul>
            </div>
          </section>
        </div>
      </div>

      <!-- Edit details -->
      <div v-else-if="tab === 'details'" class="pane" :class="tabDir">
        <ProductForm :product="product" :saving="saving" :errors="errors" :draft-key="`product:${product.id}:v${product.version}`" @save="save" />
        <section v-if="product.active" class="danger">
          <div>
            <h2 class="t-label">Deactivate this product</h2>
            <p class="t-caption muted">Hides it from customers. Requests keep their copy; staff still find it with “Include inactive”.</p>
          </div>
          <v-btn class="m3 m3-danger" variant="outlined" @click="deactivateOpen = true">Deactivate</v-btn>
        </section>
      </div>

      <!-- Images -->
      <div v-else-if="tab === 'images'" class="pane" :class="tabDir">
        <ProductImagesPanel :product="product" :expect="Number(route.query.processing) || 0" @updated="(p) => (product = p)" />
      </div>

      <!-- Stock -->
      <div v-else-if="tab === 'stock'" class="pane" :class="tabDir">
        <div v-if="!stock && !stockError" class="console-skel sk-body" />
        <p v-else-if="stockError" class="t-body muted">Stock could not be loaded. <button type="button" class="console-retry" @click="loadStock">Try again</button></p>
        <template v-else-if="stock">
          <div class="stat-row">
            <div class="stat"><span class="console-mono v">{{ stock.available }}</span><span class="t-caption muted">available</span></div>
            <div class="stat"><span class="console-mono v">{{ stock.reserved }}</span><span class="t-caption muted">reserved</span></div>
            <div class="stat"><span class="console-mono v">{{ stock.assigned ?? 0 }}</span><span class="t-caption muted">issued</span></div>
            <div class="stat"><span class="console-mono v">{{ stock.picked }}</span><span class="t-caption muted">picked</span></div>
          </div>
          <p class="sr-only">
            {{ stock.available }} available · {{ stock.reserved }} reserved · {{ stock.assigned ?? 0 }} issued · {{ stock.picked }} picked
          </p>
          <section class="panel">
            <div class="console-head"><h2 class="console-title">On the shelves</h2></div>
            <p v-if="!stock.byLocation.length" class="t-body muted panel-body">Nothing of this product is on a shelf.</p>
            <table v-else class="stable">
              <thead><tr><th>Site</th><th>Location</th><th>Shelf</th><th class="num">Units</th></tr></thead>
              <tbody>
                <tr v-for="b in stock.byLocation" :key="b.shelf">
                  <td>{{ b.siteName ?? b.site }}</td>
                  <td>{{ b.locationName ?? b.location }}</td>
                  <td><router-link :to="{ path: '/inventory', query: { op: 'lookup', code: b.shelf } }">Shelf {{ b.shelfNumber ?? '?' }}</router-link></td>
                  <td class="num console-mono">{{ b.count }}</td>
                </tr>
              </tbody>
            </table>
          </section>
        </template>
      </div>

      <!-- History -->
      <div v-else-if="tab === 'history' && session.isAdmin" class="pane" :class="tabDir">
        <section class="panel">
          <div class="console-head"><h2 class="console-title">Recorded changes</h2></div>
          <div v-if="history === null" class="panel-body"><div class="console-skel sk-small" /></div>
          <p v-else-if="!history.length" class="t-body muted panel-body">No recorded changes yet. Cost changes and deactivation are recorded here.</p>
          <ol v-else class="hist">
            <li v-for="h in history" :key="h.id">
              <span class="h-what">{{ actionLabel(h.action) }}</span>
              <span v-if="h.from !== undefined || h.to !== undefined" class="console-mono h-change">{{ h.from ?? '—' }} → {{ h.to ?? '—' }}</span>
              <span class="t-caption muted">{{ h.actor.name }} · <span class="tnum">{{ formatDateTime(h.at) }}</span></span>
            </li>
          </ol>
        </section>
      </div>
    </template>

    <v-dialog v-model="deactivateOpen" max-width="480">
      <v-card>
        <v-card-title class="t-h3">Deactivate this product?</v-card-title>
        <v-card-text>
          <p class="t-body">Customers will no longer see it. Existing requests keep their copy of the product, and staff can still find it with “Include inactive”.</p>
        </v-card-text>
        <v-card-actions class="row-end">
          <v-btn class="m3" variant="text" @click="deactivateOpen = false">Keep product</v-btn>
          <v-btn class="m3 m3-danger" variant="outlined" :loading="saving" @click="deactivate">Deactivate</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.pp {
  font-size: 14px;
  max-width: 1440px;
  margin-inline: auto;
  padding: var(--sp-4) var(--sp-6) var(--sp-12);
}
.pp.embedded {
  max-width: none;
  padding: var(--sp-4);
}
.pp.embedded .head {
  grid-template-columns: 56px minmax(0, 1fr);
}
.pp.embedded .thumb :deep(.frame) {
  width: 56px;
}
.pp.embedded .name {
  font-size: 22px;
  line-height: 28px;
}
.pp.embedded .stockbox,
.pp.embedded .acts {
  grid-column: 2;
  padding-left: 0;
  border-left: 0;
}
.pp.embedded .overview {
  grid-template-columns: minmax(0, 1fr);
}
.pp.embedded .gallery {
  max-width: 420px;
}
.pp.embedded :deep(.pform) {
  grid-template-columns: minmax(0, 1fr);
}
.pp.embedded :deep(.pform > .index) {
  display: none;
}
.back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: rgb(var(--v-theme-secondary));
  text-decoration: none;
  margin-bottom: var(--sp-3);
}
.back:hover {
  color: rgb(var(--v-theme-primary));
}

/* ---- Identity header */
.head {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr) minmax(200px, 280px) auto;
  gap: var(--sp-4);
  align-items: center;
  padding: var(--sp-4);
  border: 1px solid rgb(var(--v-theme-seam));
  border-bottom: 0;
  border-radius: 4px 4px 0 0;
  background: rgb(var(--v-theme-surface));
}
.thumb :deep(.frame) {
  width: 72px;
  border-radius: 4px;
  overflow: hidden;
}
.name {
  margin: 0;
  font-size: 28px;
  line-height: 36px;
  font-weight: 600;
  letter-spacing: -0.3px;
  text-wrap: balance;
}
.meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
  color: rgb(var(--v-theme-secondary));
}
.vis {
  margin-left: var(--sp-2);
  padding-left: var(--sp-3);
  border-left: 1px solid rgb(var(--v-theme-seam));
}
.vis.off {
  color: rgb(var(--v-theme-error));
}
.stockbox {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-left: var(--sp-4);
  border-left: 1px solid rgb(var(--v-theme-seam));
}

/* ---- Tabs (underline, as /pick) */
.tabs {
  display: flex;
  gap: var(--sp-1);
  padding: 0 var(--sp-2);
  overflow-x: auto;
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 0 0 4px 4px;
  background: rgb(var(--v-theme-surface));
  scrollbar-width: none;
}
.tab {
  position: relative;
  min-height: 44px;
  padding: 0 var(--sp-4);
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  color: rgb(var(--v-theme-secondary));
  background: none;
  border: 0;
  cursor: pointer;
}
.tab:hover {
  color: rgb(var(--v-theme-on-surface));
}
.tab[aria-selected='true'] {
  color: rgb(var(--v-theme-on-surface));
}
/* One ink bar slides to the chosen tab (1 px wide, scaled to the tab's width; transform only). */
.tabs {
  position: relative;
}
.tab-ink {
  position: absolute;
  left: 0;
  bottom: 0;
  width: 1px;
  height: 2px;
  background: rgb(var(--v-theme-primary));
  transform-origin: 0 0;
  pointer-events: none;
}
.tabs.settled .tab-ink {
  transition: transform 260ms var(--ease-out);
}
/* The pane arrives from the side of the tab it came from. */
.pane {
  padding-top: var(--sp-6);
  animation: pane-in-fwd 220ms var(--ease-out) both;
}
.pane.back {
  animation-name: pane-in-back;
}
@keyframes pane-in-fwd {
  from {
    opacity: 0;
    transform: translateX(12px);
  }
}
@keyframes pane-in-back {
  from {
    opacity: 0;
    transform: translateX(-12px);
  }
}
/* Opening another product beside the list: the record swaps in from the list's side. */
.pp.embedded {
  animation: console-swap-in 220ms var(--ease-out) both;
}
/* Photo cross-fade when another thumbnail is chosen. */
.photo-enter-active {
  transition: opacity 200ms var(--ease-out);
}
.photo-leave-active {
  transition: opacity 100ms ease-in;
}
.photo-enter-from,
.photo-leave-to {
  opacity: 0;
}
.th {
  transition: outline-color 150ms ease, opacity 150ms ease;
}
.th:not(.on):hover {
  opacity: 0.8;
}
@media (prefers-reduced-motion: reduce) {
  .pane,
  .pane.back,
  .pp.embedded {
    animation-name: console-fade-in;
  }
}

/* ---- Overview */
.overview {
  display: grid;
  grid-template-columns: minmax(0, 5fr) minmax(0, 7fr);
  gap: var(--sp-6);
  align-items: start;
}
.gallery {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.gallery > :deep(.frame) {
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  overflow: hidden;
}
.thumbs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
}
.th {
  width: 64px;
  padding: 0;
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  overflow: hidden;
  background: none;
  cursor: pointer;
}
.th.on {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 1px;
}
.cols {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.panel {
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
}
.panel-body {
  padding: var(--sp-4);
  margin: 0;
}
.details {
  white-space: pre-line;
  margin-top: var(--sp-3);
}
.kw {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: var(--sp-3);
}
.kw-chip {
  font-size: 12px;
  line-height: 20px;
  padding: 0 8px;
  border-radius: 8px;
  border: 1px solid rgb(var(--v-theme-seam));
  color: rgb(var(--v-theme-secondary));
}
.facts {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: var(--sp-2) var(--sp-6);
}
.facts dt {
  color: rgb(var(--v-theme-secondary));
}
.facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.id {
  font-size: 12px;
}
.shelves {
  list-style: none;
  margin: 0;
  padding: 0;
}
.shelves li {
  display: flex;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: 4px 0;
}

/* ---- Edit: isolated deactivate */
.danger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-4);
  max-width: 880px;
  margin-top: var(--sp-8);
  padding-top: var(--sp-4);
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.danger h2,
.danger p {
  margin: 0;
}

/* ---- Stock */
.stat-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
  margin-bottom: var(--sp-4);
}
.stat {
  display: flex;
  flex-direction: column;
  padding: var(--sp-3) var(--sp-4);
}
.stat + .stat {
  border-left: 1px solid rgb(var(--v-theme-seam));
}
.stat .v {
  font-size: 20px;
  line-height: 28px;
}
.stable {
  width: 100%;
  border-collapse: collapse;
}
.stable th {
  height: 36px;
  padding: 0 var(--sp-4);
  text-align: left;
  font-size: 12px;
  font-weight: 500;
  color: rgb(var(--v-theme-secondary));
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.stable td {
  height: 44px;
  padding: 0 var(--sp-4);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.stable tr:last-child td {
  border-bottom: 0;
}
.num {
  text-align: right !important;
}

/* ---- History */
.hist {
  list-style: none;
  margin: 0;
  padding: 0;
}
.hist li {
  display: grid;
  grid-template-columns: minmax(140px, max-content) 1fr auto;
  gap: var(--sp-4);
  align-items: baseline;
  padding: var(--sp-3) var(--sp-4);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.hist li:last-child {
  border-bottom: 0;
}
.h-what {
  font-weight: 500;
}

/* ---- States */
.missing {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding-top: var(--sp-8);
}
.missing p {
  margin: 0;
}
.loading {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.sk-head {
  height: 104px;
  border-radius: 4px;
}
.sk-body {
  height: 320px;
  border-radius: 4px;
}
.sk-small {
  height: 60px;
  border-radius: 4px;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

@media (max-width: 1099.98px) {
  .head {
    grid-template-columns: 72px minmax(0, 1fr);
  }
  .stockbox {
    grid-column: 1 / -1;
    padding-left: 0;
    border-left: 0;
  }
  .acts {
    grid-column: 1 / -1;
  }
  .overview {
    grid-template-columns: minmax(0, 1fr);
  }
  .gallery {
    max-width: 560px;
  }
}
@media (max-width: 599.98px) {
  .pp {
    padding: var(--sp-3) var(--sp-4) var(--sp-8);
  }
  .head {
    grid-template-columns: 48px minmax(0, 1fr);
    gap: var(--sp-3);
  }
  .thumb :deep(.frame) {
    width: 48px;
  }
  .name {
    font-size: 22px;
    line-height: 28px;
  }
  .vis {
    margin-left: 0;
    padding-left: 0;
    border-left: 0;
    flex-basis: 100%;
  }
  .stat-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .stat:nth-child(3) {
    border-left: 0;
  }
  .stat:nth-child(n + 3) {
    border-top: 1px solid rgb(var(--v-theme-seam));
  }
  .hist li {
    grid-template-columns: 1fr;
    gap: 2px;
  }
  .danger {
    flex-direction: column;
    align-items: flex-start;
  }
}
@media (prefers-reduced-motion: reduce) {
  .pane {
    animation: none;
  }
}
</style>
