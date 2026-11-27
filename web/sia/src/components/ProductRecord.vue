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
import { ShortRef } from '@cimh/web-app'
import { mdiAlertCircleOutline, mdiArrowLeft, mdiChevronLeft, mdiChevronRight, mdiEyeOffOutline, mdiEyeOutline, mdiImagePlusOutline, mdiLockOutline, mdiTagOutline } from '@mdi/js'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ProductForm from './ProductForm.vue'
import ProductImagesPanel from './ProductImagesPanel.vue'
import StockMeter from './StockMeter.vue'
import { revealInStrip } from '../strip'
import { neighbours, productOrder, stepKey } from '../product-nav'

const props = defineProps<{ productId: string; embedded?: boolean }>()
const emit = defineEmits<{ updated: [product: ProductStaff]; step: [productId: string] }>()
const route = useRoute()
const router = useRouter()
const session = useSession()
const notify = useNotify()
const { reference } = useReference()

const product = ref<ProductStaff | null>(null)
const missing = ref(false)
/** The product could not be loaded (not a 404): said in place with Try again, instead of a skeleton for good. */
const loadError = ref(false)
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
  loadError.value = false
  try {
    product.value = (await call(() =>
      catalog.GET('/products/{productId}', { params: { path: { productId: props.productId } } }),
    )) as ProductStaff
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) missing.value = true
    else {
      loadError.value = true
      notify.report(e, { retry: load })
    }
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

// Reactivate (owner 2026-11-25): undoes Deactivate; reversible again, so no confirm.
async function reactivate() {
  const p = product.value
  if (!p) return
  saving.value = true
  try {
    product.value = (await call(() =>
      catalog.POST('/products/{productId}/reactivate', { params: { path: { productId: p.id }, header: { 'If-Match': ifMatch(p.version) } } }),
    )) as ProductStaff
    notify.toast(product.value.sellable ? `${p.name} is shown to customers again` : `${p.name} is active again`, 'success')
  } catch (e) {
    notify.report(e, { retry: load })
  } finally {
    saving.value = false
  }
}

// Previous / next product in the list (A-05 remembers its order). Beside the list the page moves the selection;
// on its own page the record moves to the next product's page, on the same tab. Alt+↑ / Alt+↓ outside a field.
const around = computed(() => neighbours(props.productId, productOrder.value))
function step(id: string | null) {
  if (!id) return
  if (props.embedded) return emit('step', id)
  void router.replace({ path: `/products/${id}`, query: typeof route.query.tab === 'string' ? { tab: route.query.tab } : {} })
}
function onStepKey(e: KeyboardEvent) {
  const dir = stepKey(e)
  if (!dir || !around.value) return
  const id = dir < 0 ? around.value.prev : around.value.next
  if (!id) return
  e.preventDefault()
  step(id)
}
onMounted(() => addEventListener('keydown', onStepKey))
onBeforeUnmount(() => removeEventListener('keydown', onStepKey))

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
const historyError = ref(false)
async function loadHistory() {
  if (tab.value !== 'history' || !product.value || !session.isAdmin) return
  historyError.value = false
  try {
    const page = await call(() =>
      identity.GET('/audit', { params: { query: { entityType: 'product', entityId: product.value!.id, limit: 100 } } }),
    )
    history.value = page.items
  } catch (e) {
    historyError.value = true
    notify.report(e)
  }
}
watch(() => [tab.value, product.value?.id], loadHistory, { immediate: true })
const actionLabel = (a: string) => {
  const s = a.replace('product.', '').replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}
/** Money the way the form shows it: BBD before the amount. A cost of 0 is a cost, not a missing one. */
const bbd = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : `BBD ${v}`)
const isCost = (a: string) => a.includes('cost')
/** Who made a change: the name, or the part before @ when only an address was recorded. */
const actorName = (n: string) => (n.includes('@') ? n.split('@')[0]! : n)

// Shelves, most units first (Overview shows the first five; the Stock tab all, each with its share of the stock).
const shelves = computed(() => [...(stock.value?.byLocation ?? [])].sort((a, b) => b.count - a.count))
const shelfMax = computed(() => Math.max(1, ...shelves.value.map((b) => b.count)))
const onShelves = computed(() => shelves.value.reduce((n, b) => n + b.count, 0))
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`
/** Headings one level under the record's name (h1 on its own page, h2 beside the list). */
const sh = computed(() => (props.embedded ? 'h3' : 'h2'))
// Tab ink: one bar slides to the chosen tab. Placed without animation first (then `settled`); the pane
// arrives from the side of the previous tab.
const tabsEl = ref<HTMLElement | null>(null)
const ink = ref({ x: 0, w: 0 })
const inkReady = ref(false)
const tabDir = ref<'fwd' | 'back'>('fwd')
/** Which ends of the tab strip have tabs out of view (it scrolls on phones): each gets an edge fade. */
const stripMore = ref({ start: false, end: false })
function measureStrip() {
  const el = tabsEl.value
  if (!el) return
  stripMore.value = { start: el.scrollLeft > 2, end: el.scrollLeft + el.clientWidth < el.scrollWidth - 2 }
}
function placeInk() {
  const strip = tabsEl.value
  const el = strip?.querySelector<HTMLElement>(`[data-tab="${tab.value}"]`)
  if (!strip || !el) return
  // Phones: the strip scrolls; keep the chosen tab on screen. The ink lives inside the strip and scrolls with it.
  revealInStrip(strip, el)
  ink.value = { x: el.offsetLeft, w: el.offsetWidth }
  requestAnimationFrame(measureStrip)
}
/** WAI-ARIA tabs: arrow keys move between tabs (and select them), Home/End jump to the ends. */
function tabKey(e: KeyboardEvent) {
  const order = TABS.value.map((t) => t.value)
  const i = order.indexOf(tab.value)
  const next = e.key === 'ArrowRight' ? (i + 1) % order.length : e.key === 'ArrowLeft' ? (i - 1 + order.length) % order.length : e.key === 'Home' ? 0 : e.key === 'End' ? order.length - 1 : -1
  if (next < 0) return
  e.preventDefault()
  tab.value = order[next]!
  void nextTick(() => tabsEl.value?.querySelector<HTMLElement>(`[data-tab="${order[next]}"]`)?.focus())
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
    <div v-else-if="!product && loadError" class="missing">
      <component :is="embedded ? 'h2' : 'h1'" class="sec-title">This product could not be loaded</component>
      <p class="prose muted">The catalogue did not answer. Check the connection, then try again.</p>
      <div><v-btn class="m3" variant="outlined" @click="load">Try again</v-btn></div>
    </div>
    <div v-else-if="!product" class="loading">
      <div class="console-skel sk-head" />
      <div class="console-skel sk-body" />
    </div>
    <template v-else>
      <div v-if="!embedded" class="backrow">
        <router-link to="/products" class="back-link"><v-icon :icon="mdiArrowLeft" size="18" />Inventory</router-link>
        <span v-if="around" class="stepper" role="group" :aria-label="`Product ${around.index + 1} of ${around.total} in the list (Alt+Up / Alt+Down)`">
          <v-btn variant="text" class="step-btn" :icon="mdiChevronLeft" :disabled="!around.prev" aria-label="Previous product" title="Previous product (Alt+↑)" aria-keyshortcuts="Alt+ArrowUp" @click="step(around.prev)" />
          <span class="step-pos console-mono" aria-hidden="true">{{ around.index + 1 }} of {{ around.total }}</span>
          <v-btn variant="text" class="step-btn" :icon="mdiChevronRight" :disabled="!around.next" aria-label="Next product" title="Next product (Alt+↓)" aria-keyshortcuts="Alt+ArrowDown" @click="step(around.next)" />
        </span>
      </div>

      <div class="top">
      <!-- Identity φ : stock 1. The name leads; what it is, then what customers see; the stock figure stands apart. -->
      <header class="head">
        <div class="who">
          <div v-if="product.images.length" class="thumb"><ProductImage :image="primaryImage(product)" alt="" small sizes="56px" /></div>
          <div class="ident">
            <component :is="embedded ? 'h2' : 'h1'" class="name">{{ product.name }}</component>
            <p class="kind">
              <span>{{ typeLabel(reference, product.type) }}</span>
              <span class="dot" aria-hidden="true">·</span>
              <span>{{ product.department }}</span>
              <template v-if="product.modelnumber">
                <span class="dot" aria-hidden="true">·</span>
                <span class="console-mono">{{ product.modelnumber }}</span>
              </template>
            </p>
            <div class="seen" :class="{ off: !product.active, hidden: product.active && !product.sellable }">
              <span class="vis">
                <v-icon :icon="!product.active ? mdiAlertCircleOutline : product.sellable ? mdiEyeOutline : mdiEyeOffOutline" size="16" />
                {{ visibility }}
              </span>
              <ProductBadges :product="product" show-limit />
            </div>
          </div>
        </div>
        <div class="stockbox">
          <span class="cap">Available</span>
          <StockMeter :available="stock?.available ?? product.stockCount" :threshold="product.threshold" size="large" />
          <span class="stock-sub">
            <template v-if="product.threshold">Alert at {{ product.threshold }}</template>
            <template v-else>No alert level</template>
            <template v-if="stock && shelves.length"> · on {{ plural(shelves.length, 'shelf', 'shelves') }}</template>
          </span>
          <v-btn class="m3 labels" color="primary" variant="tonal" :prepend-icon="mdiTagOutline" :to="{ path: '/inventory', query: { op: 'labels', product: product.id } }">Create labels</v-btn>
        </div>
      </header>

      <!-- WAI-ARIA tabs: one tab in the Tab order (the chosen one); arrow keys, Home and End move between them. -->
      <div ref="tabsEl" class="tabs" :class="{ settled: inkReady, 'more-start': stripMore.start, 'more-end': stripMore.end }" aria-label="Product sections" role="tablist" @keydown="tabKey" @scroll.passive="measureStrip">
        <button
          v-for="t in TABS"
          :id="`${product.id}-tab-${t.value}`"
          :key="t.value"
          type="button"
          role="tab"
          class="tab"
          :data-tab="t.value"
          :aria-selected="tab === t.value"
          :aria-controls="`${product.id}-panel`"
          :tabindex="tab === t.value ? 0 : -1"
          @click="tab = t.value"
        >
          {{ t.title }}
        </button>
        <span class="tab-ink" aria-hidden="true" :style="{ transform: `translateX(${ink.x}px) scaleX(${ink.w})` }" />
      </div>
      </div>

      <!-- Overview: photos 1 : what it is φ (one column in a narrow record). -->
      <div v-if="tab === 'overview'" class="pane overview" :class="`dir-${tabDir}`" role="tabpanel" :id="`${product.id}-panel`" :aria-labelledby="`${product.id}-tab-${tab}`">
        <section class="gallery" aria-label="Photos">
          <template v-if="product.images.length">
            <div class="plate">
              <Transition name="photo" mode="out-in">
                <ProductImage :key="shownImage?.fileId ?? 'none'" :image="shownImage" :alt="product.name" sizes="(max-width: 960px) 100vw, 420px" />
              </Transition>
            </div>
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
                <ProductImage :image="img" alt="" small sizes="56px" />
              </button>
            </div>
          </template>
          <div v-else class="no-photo">
            <v-icon :icon="mdiImagePlusOutline" size="34" />
            <p class="np-title">No photos yet</p>
            <p class="np-sub">Customers see a placeholder until one is added.</p>
            <v-btn class="m3" variant="tonal" size="small" @click="tab = 'images'">Add photos</v-btn>
          </div>
        </section>

        <div class="about">
          <section class="sec" :aria-labelledby="`${product.id}-shelves`">
            <div class="sec-h">
              <component :is="sh" :id="`${product.id}-shelves`" class="sec-title">Shelves</component>
              <button type="button" class="more" @click="tab = 'stock'">Stock details<v-icon :icon="mdiChevronRight" size="16" /></button>
            </div>
            <div v-if="!stock && !stockError" class="console-skel sk-small" />
            <p v-else-if="stockError" class="prose muted">Stock could not be loaded. <button type="button" class="console-retry" @click="loadStock">Try again</button></p>
            <p v-else-if="!shelves.length" class="prose muted">Nothing of this product is on a shelf.</p>
            <ul v-else class="shelves">
              <li v-for="b in shelves.slice(0, 5)" :key="b.shelf">
                <span class="where">
                  <router-link class="shelf-n" :to="{ path: '/inventory', query: { code: b.shelf } }">Shelf {{ b.shelfNumber ?? '?' }}</router-link>
                  <span class="path">{{ b.siteName ?? b.site }} › {{ b.locationName ?? b.location }}</span>
                  <span class="s-code console-mono"><ShortRef :id="b.shelf" :fit="false" /></span>
                </span>
                <span class="console-mono count">{{ b.count }}</span>
              </li>
            </ul>
            <p v-if="shelves.length > 5" class="staff-note">
              {{ plural(shelves.length - 5, 'more shelf', 'more shelves') }} in <button type="button" class="console-retry" @click="tab = 'stock'">Stock details</button>
            </p>
          </section>

          <section class="sec" :aria-labelledby="`${product.id}-facts`">
            <div class="sec-h">
              <component :is="sh" :id="`${product.id}-facts`" class="sec-title">Facts</component>
              <span class="sec-aside legend"><v-icon :icon="mdiLockOutline" size="14" aria-hidden="true" />Staff only, never shown to customers</span>
            </div>
            <dl class="facts">
              <div v-if="model" class="fact"><dt>Make and model</dt><dd>{{ model }}</dd></div>
              <div class="fact">
                <dt>Cost <v-icon :icon="mdiLockOutline" size="12" aria-hidden="true" /><span class="sr-only">(staff only)</span></dt>
                <dd class="console-mono">{{ bbd(product.cost) }}</dd>
              </div>
              <div v-if="serials" class="fact">
                <dt>Serials <v-icon :icon="mdiLockOutline" size="12" aria-hidden="true" /><span class="sr-only">(staff only)</span></dt>
                <dd class="console-mono">{{ serials }}</dd>
              </div>
              <div class="fact"><dt>Units per pack</dt><dd class="console-mono">{{ product.unitquantity ?? 1 }}</dd></div>
              <div v-if="product.weight" class="fact"><dt>Weight</dt><dd class="console-mono">{{ product.weight }} kg</dd></div>
              <div v-if="product.dimension" class="fact"><dt>Dimensions</dt><dd>{{ product.dimension }}</dd></div>
              <div v-if="project" class="fact"><dt>Project</dt><dd>{{ project }}</dd></div>
              <div class="fact wide"><dt>Id and barcode</dt><dd class="console-mono id"><ShortRef :id="product.id" copy what="product id" /></dd></div>
            </dl>
          </section>

          <section class="sec" :aria-labelledby="`${product.id}-desc`">
            <div class="sec-h"><component :is="sh" :id="`${product.id}-desc`" class="sec-title">Description</component></div>
            <p v-if="product.description" class="prose lead">{{ product.description }}</p>
            <p v-else class="prose muted">No description yet. Customers see this text on the product page. <button type="button" class="console-retry" @click="tab = 'details'">Write one</button></p>
            <p v-if="product.details" class="prose muted details">{{ product.details }}</p>
            <div v-if="product.keywords?.length" class="kw" aria-label="Search keywords">
              <span v-for="k in product.keywords" :key="k" class="kw-chip">{{ k }}</span>
            </div>
          </section>
        </div>
      </div>

      <!-- Edit details -->
      <div v-else-if="tab === 'details'" class="pane edit" :class="`dir-${tabDir}`" role="tabpanel" :id="`${product.id}-panel`" :aria-labelledby="`${product.id}-tab-${tab}`">
        <!-- Deactivate sits in the form's own column, under its save bar (fixes it floating beside the form). -->
        <ProductForm :product="product" :saving="saving" :errors="errors" :level="embedded ? 3 : 2" :draft-key="`product:${product.id}:v${product.version}`" @save="save">
          <template v-if="!product.active" #after>
            <section class="danger" :aria-labelledby="`${product.id}-react`">
              <div class="danger-text">
                <component :is="sh" :id="`${product.id}-react`" class="sec-title">Reactivate this product</component>
                <p class="prose muted">
                  It is inactive: hidden from customers. Reactivating shows it to customers again if it is marked “Customers can see and request it”
                  or Pro Bono.
                </p>
              </div>
              <v-btn class="m3" color="primary" variant="outlined" :loading="saving" @click="reactivate">Reactivate</v-btn>
            </section>
          </template>
          <template v-else #after>
            <section class="danger" :aria-labelledby="`${product.id}-deact`">
              <div class="danger-text">
                <component :is="sh" :id="`${product.id}-deact`" class="sec-title">Deactivate this product</component>
                <p class="prose muted">Hides it from customers. Requests keep their copy; staff still find it with “Include inactive”.</p>
              </div>
              <v-btn class="m3 m3-danger" variant="outlined" @click="deactivateOpen = true">Deactivate…</v-btn>
            </section>
          </template>
        </ProductForm>
      </div>

      <!-- Images -->
      <div v-else-if="tab === 'images'" class="pane" :class="`dir-${tabDir}`" role="tabpanel" :id="`${product.id}-panel`" :aria-labelledby="`${product.id}-tab-${tab}`">
        <ProductImagesPanel :product="product" :level="embedded ? 3 : 2" :expect="Number(route.query.processing) || 0" @updated="(p) => (product = p)" />
      </div>

      <!-- Stock: the four counts, then every shelf with its share. -->
      <div v-else-if="tab === 'stock'" class="pane" :class="`dir-${tabDir}`" role="tabpanel" :id="`${product.id}-panel`" :aria-labelledby="`${product.id}-tab-${tab}`">
        <div v-if="!stock && !stockError" class="console-skel sk-body" />
        <p v-else-if="stockError" class="prose muted">Stock could not be loaded. <button type="button" class="console-retry" @click="loadStock">Try again</button></p>
        <template v-else-if="stock">
          <dl class="counts" aria-hidden="true">
            <div class="count-cell lead"><dt>Available</dt><dd class="console-mono">{{ stock.available }}</dd><p>On a shelf, free to quote or pick</p></div>
            <div class="count-cell" :class="{ zero: !stock.reserved }"><dt>Reserved</dt><dd class="console-mono">{{ stock.reserved }}</dd><p>Held for sent quotes and approved requests</p></div>
            <div class="count-cell" :class="{ zero: !stock.assigned }"><dt>Issued</dt><dd class="console-mono">{{ stock.assigned ?? 0 }}</dd><p>With a person, to be returned</p></div>
            <div class="count-cell" :class="{ zero: !stock.picked }"><dt>Picked</dt><dd class="console-mono">{{ stock.picked }}</dd><p>Off the shelf for a request</p></div>
          </dl>
          <p class="sr-only">
            {{ stock.available }} available · {{ stock.reserved }} reserved · {{ stock.assigned ?? 0 }} issued · {{ stock.picked }} picked
          </p>
          <section class="sec" :aria-labelledby="`${product.id}-onshelves`">
            <div class="sec-h">
              <component :is="sh" :id="`${product.id}-onshelves`" class="sec-title">On the shelves</component>
              <span v-if="shelves.length" class="sec-aside">{{ plural(onShelves, 'unit') }} on {{ plural(shelves.length, 'shelf', 'shelves') }}</span>
            </div>
            <p v-if="!shelves.length" class="prose muted">Nothing of this product is on a shelf.</p>
            <table v-else class="stable">
              <thead><tr><th>Shelf</th><th>Site › Location</th><th class="num">Units</th></tr></thead>
              <tbody>
                <tr v-for="b in shelves" :key="b.shelf">
                  <td class="s-shelf"><router-link :to="{ path: '/inventory', query: { code: b.shelf } }">Shelf {{ b.shelfNumber ?? '?' }}</router-link></td>
                  <td class="s-path">{{ b.siteName ?? b.site }} › {{ b.locationName ?? b.location }}<span class="s-code console-mono"><ShortRef :id="b.shelf" :fit="false" /></span></td>
                  <td class="num">
                    <span class="share" aria-hidden="true"><span :style="{ transform: `scaleX(${b.count / shelfMax})` }" /></span>
                    <span class="console-mono">{{ b.count }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </section>
        </template>
      </div>

      <!-- History (admins): Vuetify v-timeline, newest first (filled node). Items render divs, hence the roles. -->
      <div v-else-if="tab === 'history' && session.isAdmin" class="pane" :class="`dir-${tabDir}`" role="tabpanel" :id="`${product.id}-panel`" :aria-labelledby="`${product.id}-tab-${tab}`">
        <section class="sec" :aria-labelledby="`${product.id}-hist`">
          <div class="sec-h">
            <component :is="sh" :id="`${product.id}-hist`" class="sec-title">Recorded changes</component>
            <span v-if="history?.length" class="sec-aside">Newest first</span>
          </div>
          <p v-if="historyError" class="prose muted">History could not be loaded. <button type="button" class="console-retry" @click="loadHistory">Try again</button></p>
          <div v-else-if="history === null" class="console-skel sk-small" />
          <p v-else-if="!history.length" class="prose muted">No recorded changes yet. Cost changes and deactivation are recorded here; other edits are not.</p>
          <v-timeline v-else role="list" :aria-labelledby="`${product.id}-hist`" class="hist" side="end" density="compact" align="start" truncate-line="both" line-thickness="2">
            <v-timeline-item
              v-for="(h, i) in history"
              :key="h.id"
              role="listitem"
              class="h-entry"
              :class="{ latest: i === 0 }"
              :dot-color="i === 0 ? 'primary' : undefined"
              fill-dot
            >
              <div class="h-top">
                <span class="h-what">{{ actionLabel(h.action) }}</span>
                <span class="h-when console-mono">{{ formatDateTime(h.at) }}</span>
              </div>
              <p v-if="h.from !== undefined || h.to !== undefined" class="h-change console-mono">
                <span class="h-from">{{ isCost(h.action) ? bbd(h.from) : (h.from ?? '—') }}</span>
                <span class="h-arrow" aria-label="changed to">→</span>
                <span class="h-to">{{ isCost(h.action) ? bbd(h.to) : (h.to ?? '—') }}</span>
              </p>
              <p class="h-by" :title="h.actor.name">by {{ actorName(h.actor.name) }}</p>
            </v-timeline-item>
          </v-timeline>
        </section>
      </div>
    </template>

    <v-dialog v-model="deactivateOpen" max-width="480">
      <v-card>
        <v-card-title class="t-h3">Deactivate this product?</v-card-title>
        <v-card-text>
          <p class="t-body">Customers will no longer see it. Existing requests keep their copy of the product, and staff can still find it with “Include inactive”. You can reactivate it later from Edit details.</p>
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
/* A-07 record on the golden-ratio system (owner 2026-11-25; the dialogs' and pick rails' system): type 11 px captions
   (14/√φ) · 14 px body · 17.8 px section heads (14·√φ) · 22.65 px key figures and the name beside the list (14·φ) ·
   28.8 px the name on its own page (17.8·φ). Space: Fibonacci 8 · 13 · 21 · 34. Splits φ : 1. Sections are plain
   heads over hairlines, never boxes inside the panel. The record lays itself out by its own width (container
   queries), so beside the list and on its own page follow the same rules. */
.pp {
  --f1: 8px;
  --f2: 13px;
  --f3: 21px;
  --f4: 34px;
  --muted: rgb(var(--v-theme-secondary));
  --rule: rgb(var(--v-theme-seam));
  --edge: var(--f3);
  --form-ground: rgb(var(--v-theme-background)); /* the form's sticky save bar sits on the ground under the head band */
  container: record / inline-size;
  font-size: 14px;
  line-height: 1.5;
  padding: var(--f3) var(--sp-6) var(--sp-12);
}
.pp.embedded {
  max-width: none;
  padding: 0 0 var(--f4);
  animation: console-swap-in 220ms var(--ease-out) both;
}
.back-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  min-height: 24px;
  color: var(--muted);
  text-decoration: none;
  margin-bottom: var(--f2);
}
.back-link:hover {
  color: rgb(var(--v-theme-primary));
}
.muted {
  color: var(--muted);
}
.prose {
  margin: 0;
  max-width: 68ch;
  text-wrap: pretty;
}

/* ---- Head: identity φ : stock 1, tabs under a hairline. On its own page the head is the page's one panel. */
.top {
  background: rgb(var(--v-theme-surface));
}
.pp:not(.embedded) .top {
  border: 1px solid var(--rule);
  border-radius: 4px;
}
.head {
  display: grid;
  grid-template-columns: minmax(0, 1.618fr) minmax(0, 1fr);
  gap: var(--f4);
  align-items: center;
  padding: var(--f3) var(--edge);
}
.who {
  display: flex;
  gap: var(--f2);
  align-items: flex-start;
  min-width: 0;
}
.thumb {
  flex: none;
}
.thumb :deep(.frame) {
  width: 56px;
  border-radius: 4px;
  overflow: hidden;
  box-shadow: 0 0 0 1px var(--rule);
}
.ident {
  min-width: 0;
}
.name {
  margin: 0;
  font-size: 22.65px;
  line-height: 1.236;
  font-weight: 600;
  letter-spacing: -0.01em;
  text-wrap: balance;
  overflow-wrap: anywhere;
}
.kind {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0 6px;
  margin: var(--f1) 0 0;
  font-size: 14px;
  color: var(--muted);
}
.kind .console-mono {
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface));
}
.dot {
  opacity: 0.7;
}
.seen {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--f1) var(--f2);
  margin-top: var(--f2);
}
.vis {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface));
}
.seen.hidden .vis {
  color: var(--muted);
}
.seen.off .vis {
  color: rgb(var(--v-theme-error));
  font-weight: 600;
}
.stockbox {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  min-width: 0;
  padding-left: var(--f3);
  border-left: 1px solid var(--rule);
}
.cap,
.facts dt,
.counts dt,
.stable th {
  font-size: 11px;
  line-height: 1.618;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}
.stockbox :deep(.meter.large) {
  margin-top: 2px;
}
.stock-sub {
  font-size: 14px;
  color: var(--muted);
}
.labels {
  margin-top: var(--f2);
}

/* ---- Tabs (underline, as /pick): 14 px, the chosen one in ink at 600. */
.tabs {
  position: relative;
  display: flex;
  gap: var(--f1);
  padding: 0 calc(var(--edge) - var(--f2));
  overflow-x: auto;
  border-top: 1px solid var(--rule);
  scrollbar-width: none;
}
.pp.embedded .tabs {
  border-bottom: 1px solid var(--rule);
}
.tab {
  position: relative;
  min-height: 44px;
  padding: 0 var(--f2);
  font: inherit;
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  color: var(--muted);
  background: none;
  border: 0;
  cursor: pointer;
  transition: color 150ms ease;
}
.tab:hover,
.tab[aria-selected='true'] {
  color: rgb(var(--v-theme-on-surface));
}
.tab[aria-selected='true'] {
  font-weight: 600;
}
/* One ink bar slides to the chosen tab (1 px wide, scaled to the tab's width; transform only). */
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
.tabs.more-end {
  mask-image: linear-gradient(to right, #000 calc(100% - 34px), transparent);
}
.tabs.more-start {
  mask-image: linear-gradient(to left, #000 calc(100% - 34px), transparent);
}
.tabs.more-start.more-end {
  mask-image: linear-gradient(to right, transparent, #000 34px, #000 calc(100% - 34px), transparent);
}
.tabs.settled .tab-ink {
  transition: transform 260ms var(--ease-out);
}

/* ---- Panes: the pane arrives from the side of the tab it came from. */
.pane {
  padding: var(--f4) 0 0;
  animation: pane-in-fwd 220ms var(--ease-out) both;
}
.pp.embedded .pane {
  padding: var(--f3) var(--edge) 0;
}
.pane.dir-back {
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
@media (prefers-reduced-motion: reduce) {
  .pane,
  .pane.dir-back,
  .pp.embedded {
    animation-name: console-fade-in;
  }
}

/* Sections: a 17.8 px head, 13 px to its content, 34 px and a hairline before the next. */
.sec + .sec {
  margin-top: var(--f2);
  padding-top: var(--f3);
  border-top: 1px solid var(--rule);
}
.sec-h {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--f2);
  margin-bottom: var(--f2);
}
.sec-title {
  margin: 0;
  font-size: 17.8px;
  line-height: 1.382;
  font-weight: 600;
  letter-spacing: -0.005em;
}
.sec-aside {
  font-size: 14px;
  color: var(--muted);
}
.legend {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.more {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 4px 0;
  min-height: 24px;
  font: inherit;
  font-size: 14px;
  font-weight: 500;
  color: rgb(var(--v-theme-primary));
  background: none;
  border: 0;
  cursor: pointer;
}
.more:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.staff-note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: var(--f2) 0 0;
  font-size: 12px;
  color: var(--muted);
}

/* ---- Overview: photos 1 : what it is φ. */
.overview {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.618fr);
  gap: var(--f4);
  align-items: start;
}
.gallery {
  display: flex;
  flex-direction: column;
  gap: var(--f1);
  position: sticky;
  top: var(--f3);
}
.plate {
  border: 1px solid var(--rule);
  border-radius: 4px;
  overflow: hidden;
  background: #fff;
}
.thumbs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--f1);
}
.th {
  width: 56px;
  padding: 0;
  border: 1px solid var(--rule);
  border-radius: 4px;
  overflow: hidden;
  background: #fff;
  cursor: pointer;
  transition: outline-color 150ms ease, opacity 150ms ease;
}
.th:not(.on):hover {
  opacity: 0.8;
}
.th.on {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.no-photo {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--f1);
  aspect-ratio: 4 / 3;
  padding: var(--f3);
  text-align: center;
  color: var(--muted);
  border: 1px dashed var(--rule);
  border-radius: 4px;
}
.no-photo p {
  margin: 0;
}
.np-title {
  font-size: 17.8px;
  line-height: 1.382;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
}
.np-sub {
  font-size: 14px;
  margin-bottom: var(--f1) !important;
}
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
.lead {
  font-size: 14px;
  line-height: 1.618;
  color: rgb(var(--v-theme-on-surface));
}
.details {
  white-space: pre-line;
  margin-top: var(--f2);
}
.kw {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: var(--f2);
}
.kw-chip {
  font-size: 12px;
  line-height: 22px;
  padding: 0 var(--f1);
  border-radius: 8px;
  border: 1px solid var(--rule);
  color: var(--muted);
}
.facts {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: var(--f3);
  margin: 0;
}
.fact.wide {
  grid-column: 1 / -1;
}
.facts dt {
  display: flex;
  align-items: center;
  gap: 4px;
}
.facts dd {
  margin: 2px 0 0;
  overflow-wrap: anywhere;
}
.facts dd.console-mono {
  font-size: 14px;
}
.id {
  font-size: 13px !important;
}
.shelves {
  list-style: none;
  margin: 0;
  padding: 0;
}
.shelves li {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: baseline;
  gap: var(--f2);
  padding: var(--f1) 0;
}
.shelves li + li {
  border-top: 1px solid var(--rule);
}
.where {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0 var(--f1);
  min-width: 0;
}
.shelf-n {
  font-weight: 600;
}
.path {
  color: var(--muted);
}
.count {
  font-size: 14px;
}

/* ---- Edit: the form, then Deactivate under it on the form's own width. */
.edit {
  max-width: 1114px; /* the form: index 200 + 34 + 880 */
}
/* Beside the list the record is too narrow for the form's section index: one column. */
.pp.embedded :deep(.pform) {
  grid-template-columns: minmax(0, 1fr);
}
.pp.embedded :deep(.pform > .index) {
  display: none;
}
.danger {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--f3);
  margin-top: var(--f4);
  padding-top: var(--f3);
  border-top: 1px solid var(--rule);
}
.danger-text .prose {
  margin-top: 4px;
}
.backrow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--f2);
  margin-bottom: var(--f2);
}
.backrow .back-link {
  margin-bottom: 0;
}
.stepper {
  display: inline-flex;
  align-items: center;
}
.step-pos {
  min-width: 6ch;
  text-align: center;
  font-size: 11px;
  color: var(--muted);
}

/* ---- Stock: four counts (available leads, zeros quiet), then the shelves with their share. */
.counts {
  display: grid;
  grid-template-columns: minmax(0, 1.618fr) repeat(3, minmax(0, 1fr));
  gap: var(--f3);
  margin: 0 0 var(--f4);
}
.count-cell {
  min-width: 0;
}
.count-cell + .count-cell {
  padding-left: var(--f3);
  border-left: 1px solid var(--rule);
}
.counts dd {
  margin: 2px 0 0;
  font-size: 17.8px;
  line-height: 1.382;
  font-weight: 500;
}
.count-cell.lead dd {
  font-size: 22.65px;
  line-height: 1.236;
  font-weight: 600;
}
.count-cell.zero dd {
  color: var(--muted);
}
.count-cell p {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--muted);
}
.stable {
  width: 100%;
  border-collapse: collapse;
}
.stable th {
  height: 34px;
  padding: 0 var(--f2) 0 0;
  text-align: left;
  border-bottom: 1px solid var(--rule);
}
.stable td {
  height: 44px;
  padding: 0 var(--f2) 0 0;
  border-bottom: 1px solid var(--rule);
}
.stable tr:last-child td {
  border-bottom: 0;
}
.stable th:last-child,
.stable td:last-child {
  padding-right: 0;
}
.s-shelf {
  font-weight: 600;
  white-space: nowrap;
}
.s-path {
  color: var(--muted);
}
.s-code {
  display: block;
  font-size: 12px;
  line-height: 1.5;
}
.s-path {
  overflow-wrap: anywhere;
}
.num {
  text-align: right !important;
  white-space: nowrap;
}
.num .console-mono {
  display: inline-block;
  min-width: 3ch;
}
/* A share bar: this shelf's units against the fullest shelf. */
.share {
  display: inline-block;
  vertical-align: middle;
  width: 89px;
  height: 4px;
  margin-right: var(--f2);
  border-radius: 2px;
  background: var(--rule);
  overflow: hidden;
}
.share > span {
  display: block;
  height: 100%;
  background: rgb(var(--v-theme-on-surface));
  opacity: 0.55;
  transform-origin: 0 50%;
}

/* ---- History: Vuetify v-timeline, newest first. */
.hist {
  row-gap: var(--f2) !important;
}
.h-entry :deep(.v-timeline-item__body) {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding-inline-start: var(--f2) !important;
}
.h-entry :deep(.v-timeline-divider__dot) {
  width: 12px;
  height: 12px;
  margin-top: 6px;
  background: transparent;
  box-shadow: inset 0 0 0 2px rgb(var(--v-theme-on-surface-variant));
}
.h-entry :deep(.v-timeline-divider__inner-dot) {
  background: transparent;
}
.h-entry.latest :deep(.v-timeline-divider__dot) {
  box-shadow: none;
}
.h-entry.latest :deep(.v-timeline-divider__inner-dot) {
  background: rgb(var(--v-theme-primary));
}
.h-entry :deep(.v-timeline-divider__before),
.h-entry :deep(.v-timeline-divider__after) {
  background: var(--rule);
}
.h-top {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0 var(--f2);
}
.h-what {
  font-weight: 600;
}
.h-when {
  font-size: 12px;
  color: var(--muted);
}
.h-change {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--f1);
  margin: 0;
  font-size: 14px;
}
.h-from {
  color: var(--muted);
}
.h-arrow {
  color: var(--muted);
}
.h-by {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
}

/* ---- States */
.missing {
  display: flex;
  flex-direction: column;
  gap: var(--f2);
  padding: var(--f4) var(--edge);
}
.missing p {
  margin: 0;
}
.loading {
  display: flex;
  flex-direction: column;
  gap: var(--f3);
  padding: var(--f3) var(--edge);
}
.sk-head {
  height: 120px;
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

/* ---- By the record's own width. */
@container record (min-width: 900px) {
  .pp:not(.embedded) .name {
    font-size: 28.8px;
    line-height: 1.236;
    letter-spacing: -0.015em;
  }
}
@container record (max-width: 759.98px) {
  .overview {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--f3);
  }
  .gallery {
    position: static;
    max-width: 233px;
  }
  .counts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .count-cell:nth-child(3) {
    padding-left: 0;
    border-left: 0;
  }
}
@container record (max-width: 639.98px) {
  .head {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--f3);
  }
  .stockbox {
    padding: var(--f3) 0 0;
    border-left: 0;
    border-top: 1px solid var(--rule);
  }
  .share {
    width: 55px;
  }
  /* The photo is one tab away; here the name gets the full width. */
  .thumb {
    display: none;
  }
}
@container record (max-width: 479.98px) {
  .share {
    display: none;
  }
  /* Available with Create labels on its right, then the meter across, then the alert line. */
  .stockbox {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas: 'cap cap' 'meter meter' 'sub labels';
    align-items: center;
    column-gap: var(--f2);
  }
  .stockbox .cap {
    grid-area: cap;
  }
  .stockbox :deep(.meter.large) {
    grid-area: meter;
  }
  .stockbox .stock-sub {
    grid-area: sub;
  }
  .stockbox .labels {
    grid-area: labels;
    margin-top: 0;
  }
  .seen {
    margin-top: var(--f1);
  }
}
@media (max-width: 599.98px) {
  .pp {
    padding: var(--f2) var(--f2) var(--f4);
    --edge: var(--f2);
  }
  .pp.embedded {
    padding: 0 0 var(--f4);
  }
  .danger {
    grid-template-columns: minmax(0, 1fr);
    justify-items: start;
  }
  .s-path {
    font-size: 13px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .pane {
    animation: none;
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
