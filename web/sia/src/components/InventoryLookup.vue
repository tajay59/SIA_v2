<script setup lang="ts">
/**
 * A-11 lookup result, the record beside the Places tree on /inventory. The code comes from the page's scan
 * field, the header scan box or the tree (`?code=`): a shelf shows its units (paged) and its QR label, a unit
 * shows its card with actions, a product shows stock against its alert level and stock by shelf.
 * Sites and locations are handled by the page (InventorySite / InventoryLocation).
 */
import {
  ApiError,
  call,
  catalog,
  codeKind,
  inventory,
  type ProductStaff,
  type ProductStock,
  type Shelf,
  type Unit,
  unitState,
  useCursorList,
  useNotify,
} from '@cimh/web-app'
import { mdiAccountArrowRight, mdiAlertCircleOutline, mdiBookmarkOutline, mdiCheckCircle, mdiCircleOutline, mdiPrinterOutline, mdiTagOutline } from '@mdi/js'
import { ref, watch } from 'vue'
import { shelfLabel } from '../places'
import LabelSheet from './LabelSheet.vue'
import StockMeter from './StockMeter.vue'
import UnitCard from './UnitCard.vue'

const props = defineProps<{ code: string }>()
const emit = defineEmits<{ place: [where: { site?: string | null; location?: string | null } | null] }>()
const notify = useNotify()

const shelf = ref<Shelf | null>(null)
const unit = ref<Unit | null>(null)
const stock = ref<ProductStock | null>(null)
const product = ref<ProductStaff | null>(null)
const message = ref('')
const loading = ref(false)
const open = ref<string | null>(null)
const qr = ref(false)

const units = useCursorList<Unit>((cursor) =>
  call(() => inventory.GET('/shelves/{barcode}/units', { params: { path: { barcode: shelf.value!.barcode }, query: { cursor, limit: 25 } } })),
)

async function show(raw: string) {
  shelf.value = unit.value = stock.value = product.value = null
  message.value = ''
  open.value = null
  qr.value = false
  const c = raw.trim()
  loading.value = true
  try {
    const kind = codeKind(c)
    if (kind === 'shelf') {
      shelf.value = await call(() => inventory.GET('/shelves/{barcode}', { params: { path: { barcode: c } } }))
      emit('place', { site: shelf.value.site, location: shelf.value.location })
      await units.reload()
    } else if (kind === 'unit') {
      unit.value = await call(() => inventory.GET('/units/{barcode}', { params: { path: { barcode: c } } }))
      emit('place', unit.value.stowed ? { site: unit.value.site, location: unit.value.location } : null)
    } else if (kind === 'request') {
      message.value = 'That is a request code. Requests open on the request desk.'
    } else {
      product.value = (await call(() => catalog.GET('/products/{productId}', { params: { path: { productId: c } } }))) as ProductStaff
      stock.value = await call(() => inventory.GET('/products/{productId}/stock', { params: { path: { productId: c } } }))
      emit('place', null)
    }
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) message.value = `Nothing has the code ${c}. Check the label, or find the product by name.`
    else notify.report(e, { retry: () => void show(c) })
  } finally {
    loading.value = false
  }
}
watch(() => props.code, show, { immediate: true })

function onUpdated(u: Unit) {
  if (unit.value?.barcode === u.barcode) unit.value = u
  units.items.value = units.items.value.map((x) => (x.barcode === u.barcode ? u : x))
}
const tone = (u: Unit) => `tone-${unitState(u).tone}`
const ICON = { success: mdiCheckCircle, warning: mdiBookmarkOutline, info: mdiAccountArrowRight, neutral: mdiCircleOutline } as const
const icon = (u: Unit) => ICON[unitState(u).tone]
</script>

<template>
  <div class="result">
    <div v-if="loading && !shelf && !unit && !product" class="pad" aria-busy="true">
      <div class="skel console-skel" style="width: 40%; height: 26px" />
      <div v-for="n in 4" :key="n" class="skel console-skel" />
    </div>

    <div v-else-if="message" class="pad empty" role="status">
      <v-icon :icon="mdiAlertCircleOutline" size="22" />
      <p class="t-body">{{ message }}</p>
    </div>

    <!-- Shelf: its units -->
    <template v-else-if="shelf">
      <header class="pad hd">
        <div class="who">
          <h2 class="t-h3">{{ shelf.locationName ?? shelf.location }} · shelf {{ shelf.number }}</h2>
          <p class="t-caption muted">{{ shelf.siteName }} · <span class="console-mono">{{ shelf.barcode }}</span></p>
        </div>
        <v-btn class="m3" variant="outlined" :prepend-icon="mdiPrinterOutline" :aria-expanded="qr" @click="qr = !qr">Shelf QR label</v-btn>
      </header>
      <Transition name="reveal"><div v-if="qr" class="pad sheet"><LabelSheet :items="[shelfLabel(shelf)]" :heading="`Shelf ${shelf.number} label`" /></div></Transition>
      <div class="sub console-head">
        <h3 class="console-title">On this shelf</h3>
        <span v-if="units.loaded.value" class="console-mono t-caption muted">{{ units.items.value.length }}{{ units.nextCursor.value ? '+' : '' }} {{ units.items.value.length === 1 && !units.nextCursor.value ? 'unit' : 'units' }}</span>
      </div>
      <p v-if="units.loaded.value && !units.items.value.length" class="pad t-body muted">Nothing on this shelf. Stow units here under Pick → Stow · Relocate.</p>
      <ul v-else class="units" role="list">
        <li v-for="u in units.items.value" :key="u.barcode">
          <button type="button" class="unit" :aria-expanded="open === u.barcode" @click="open = open === u.barcode ? null : u.barcode">
            <span class="nm">{{ u.productName ?? u.product }}</span>
            <span class="console-mono code">{{ u.barcode }}</span>
            <span class="state" :class="tone(u)"><v-icon :icon="icon(u)" size="14" />{{ unitState(u).label }}</span>
          </button>
          <Transition name="reveal"><div v-if="open === u.barcode" class="pad inset"><UnitCard :unit="u" @updated="onUpdated" /></div></Transition>
        </li>
      </ul>
      <div v-if="units.nextCursor.value" class="pad"><v-btn class="m3" variant="text" :loading="units.loading.value" @click="units.loadMore">Load more</v-btn></div>
    </template>

    <!-- Unit -->
    <div v-else-if="unit" class="pad"><UnitCard :unit="unit" @updated="onUpdated" /></div>

    <!-- Product: stock against its alert level, then by shelf -->
    <template v-else-if="stock && product">
      <header class="pad hd">
        <div class="who">
          <h2 class="t-h3"><router-link :to="`/products/${product.id}`">{{ product.name }}</router-link></h2>
          <p class="t-caption muted console-mono">{{ product.id }}</p>
        </div>
        <v-btn class="m3" variant="outlined" :active="false" :prepend-icon="mdiTagOutline" :to="{ path: '/inventory', query: { op: 'labels', product: product.id } }">Create labels</v-btn>
      </header>
      <div class="pad meter"><StockMeter :available="stock.available" :threshold="stock.threshold" size="large" /></div>
      <dl class="counts">
        <div><dt>Reserved</dt><dd class="console-mono"><span :key="stock.reserved" class="console-roll">{{ stock.reserved }}</span></dd></div>
        <div><dt>Issued</dt><dd class="console-mono"><span :key="stock.assigned ?? 0" class="console-roll">{{ stock.assigned ?? 0 }}</span></dd></div>
        <div><dt>Picked</dt><dd class="console-mono"><span :key="stock.picked" class="console-roll">{{ stock.picked }}</span></dd></div>
        <div><dt>Alert at</dt><dd class="console-mono">{{ stock.threshold }}</dd></div>
      </dl>
      <div class="sub console-head"><h3 class="console-title">Where it is</h3></div>
      <p v-if="!stock.byLocation.length" class="pad t-body muted">Nothing of this product is on a shelf.</p>
      <ul v-else class="units" role="list">
        <li v-for="b in stock.byLocation" :key="b.shelf">
          <router-link class="unit" :to="{ path: '/inventory', query: { code: b.shelf } }">
            <span class="nm">{{ b.locationName ?? b.location }} · shelf {{ b.shelfNumber ?? '?' }}</span>
            <span class="t-caption muted code">{{ b.siteName ?? b.site }}</span>
            <span class="console-mono qty">{{ b.count }}</span>
          </router-link>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.result {
  animation: console-swap-in 220ms var(--ease-out);
}
.pad {
  padding: var(--sp-4);
}
.skel {
  height: 18px;
  margin-top: var(--sp-3);
  border-radius: 4px;
}
.empty {
  display: flex;
  gap: var(--sp-3);
  align-items: flex-start;
  color: rgb(var(--v-theme-secondary));
}
.hd {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-3);
  align-items: flex-start;
  justify-content: space-between;
}
.who {
  min-width: 0;
}
.who h2 a {
  color: inherit;
}
.sheet {
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.sub {
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.units {
  list-style: none;
  margin: 0;
  padding: 0;
}
.unit {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: var(--sp-3);
  align-items: center;
  width: 100%;
  min-height: 44px;
  padding: 0 var(--sp-4);
  border: 0;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
  background: none;
  color: rgb(var(--v-theme-on-surface));
  font: inherit;
  text-align: left;
  text-decoration: none;
  cursor: pointer;
}
.unit:hover,
.unit[aria-expanded='true'] {
  background: rgb(var(--v-theme-surface-variant));
}
.nm {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.code {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: rgb(var(--v-theme-secondary));
}
.qty {
  min-width: 3ch;
  text-align: right;
}
.state {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 8px;
  border: 1px solid rgb(var(--v-theme-seam));
}
.tone-success {
  color: rgb(var(--v-theme-success));
}
.tone-warning {
  color: rgb(var(--v-theme-warning));
}
.tone-info {
  color: rgb(var(--v-theme-primary));
}
/* A unit card or QR label opens in place: it unrolls from under its row. */
.reveal-enter-active {
  transition:
    opacity 200ms var(--ease-out),
    transform 220ms var(--ease-out),
    clip-path 240ms var(--ease-out);
}
.reveal-leave-active {
  transition: opacity 120ms ease-in;
}
.reveal-enter-from {
  opacity: 0;
  transform: translateY(-6px);
  clip-path: inset(0 0 100% 0);
}
.reveal-leave-to {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .reveal-enter-active {
    transition: opacity 120ms;
  }
  .reveal-enter-from {
    transform: none;
    clip-path: none;
  }
}
.inset {
  background: rgb(var(--v-theme-background));
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.meter {
  padding-top: 0;
}
.counts {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin: 0;
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.counts > div {
  padding: var(--sp-3) var(--sp-4);
}
.counts > div + div {
  border-left: 1px solid rgb(var(--v-theme-seam));
}
.counts dt {
  font-size: 12px;
  color: rgb(var(--v-theme-secondary));
}
.counts dd {
  margin: 0;
  font-size: 20px;
  line-height: 28px;
  font-weight: 600;
}
@media (max-width: 599px) {
  .unit {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .unit .code {
    grid-column: 1;
    grid-row: 2;
    margin-top: -10px;
    padding-bottom: 6px;
  }
  .counts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .counts > div:nth-child(3) {
    border-left: 0;
    border-top: 1px solid rgb(var(--v-theme-seam));
  }
  .counts > div:nth-child(4) {
    border-top: 1px solid rgb(var(--v-theme-seam));
  }
}
</style>
