<script setup lang="ts">
/**
 * A-11 lookup (legacy Inventory → "Lookup" panel). Scan or type a shelf, unit or product code, or search a
 * product by name: a shelf shows its units (paged), a unit shows its card with actions, a product shows its
 * stock by location. The code is kept in the URL (`?code=`), so the header scan box can open it.
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
import { ref, watch } from 'vue'
import ProductPicker from './ProductPicker.vue'
import ScanField from './ScanField.vue'
import UnitCard from './UnitCard.vue'

const code = defineModel<string | null>('code', { default: null })
const notify = useNotify()

const shelf = ref<Shelf | null>(null)
const unit = ref<Unit | null>(null)
const stock = ref<ProductStock | null>(null)
const product = ref<ProductStaff | null>(null)
const picked = ref<ProductStaff | null>(null)
const message = ref('')
const loading = ref(false)
const open = ref<string | null>(null)

const units = useCursorList<Unit>((cursor) =>
  call(() => inventory.GET('/shelves/{barcode}/units', { params: { path: { barcode: shelf.value!.barcode }, query: { cursor, limit: 25 } } })),
)

function reset() {
  shelf.value = unit.value = stock.value = product.value = null
  message.value = ''
  open.value = null
}

async function show(raw: string | null) {
  reset()
  if (!raw) return
  const c = raw.trim()
  loading.value = true
  try {
    const kind = codeKind(c)
    if (kind === 'shelf') {
      shelf.value = await call(() => inventory.GET('/shelves/{barcode}', { params: { path: { barcode: c } } }))
      await units.reload()
    } else if (kind === 'unit') {
      unit.value = await call(() => inventory.GET('/units/{barcode}', { params: { path: { barcode: c } } }))
    } else if (kind === 'request') {
      message.value = 'Requests open on the request desk, which arrives with the orders service.'
    } else if (kind === 'site' || kind === 'location') {
      message.value = 'That is a site or location code. Open Location above to see its shelves.'
    } else {
      await showProduct(c)
    }
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) message.value = `Nothing found for ${c}.`
    else notify.report(e, { retry: () => void show(c) })
  } finally {
    loading.value = false
  }
}

async function showProduct(id: string) {
  product.value = (await call(() => catalog.GET('/products/{productId}', { params: { path: { productId: id } } }))) as ProductStaff
  stock.value = await call(() => inventory.GET('/products/{productId}/stock', { params: { path: { productId: id } } }))
}

watch(code, show, { immediate: true })
watch(picked, (p) => {
  if (p) code.value = p.id
})
function onUpdated(u: Unit) {
  unit.value = u
  units.items.value = units.items.value.map((x) => (x.barcode === u.barcode ? u : x))
}
</script>

<template>
  <div class="stack">
    <div class="finders">
      <ScanField label="Shelf, unit or product code" :loading="loading" autofocus @scan="(c) => (code = c)" />
      <ProductPicker v-model="picked" label="…or find a product by name" />
    </div>

    <p v-if="message" class="t-body muted" role="status">{{ message }}</p>

    <!-- Shelf: its units -->
    <section v-if="shelf" class="stack-sm">
      <h2 class="t-h3">{{ shelf.locationName ?? shelf.location }} · shelf {{ shelf.number }}</h2>
      <p class="t-caption muted">{{ shelf.siteName }} · <span class="t-mono">{{ shelf.barcode }}</span></p>
      <p v-if="units.loaded.value && !units.items.value.length" class="t-body muted">Nothing on this shelf.</p>
      <v-list v-else lines="two" density="compact" class="pa-0">
        <template v-for="u in units.items.value" :key="u.barcode">
          <v-list-item :title="u.productName ?? u.product" :subtitle="u.barcode" @click="open = open === u.barcode ? null : u.barcode">
            <template #append><v-chip size="x-small" label>{{ unitState(u).label }}</v-chip></template>
          </v-list-item>
          <div v-if="open === u.barcode" class="pa-2"><UnitCard :unit="u" @updated="onUpdated" /></div>
        </template>
      </v-list>
      <v-btn v-if="units.nextCursor.value" variant="text" :loading="units.loading.value" @click="units.loadMore">Load more</v-btn>
    </section>

    <!-- Unit -->
    <UnitCard v-if="unit" :unit="unit" @updated="onUpdated" />

    <!-- Product: stock by location -->
    <section v-if="stock && product" class="stack-sm">
      <div class="row">
        <router-link :to="`/products/${product.id}`" class="t-h3">{{ product.name }}</router-link>
        <span class="spacer" />
        <v-btn size="small" variant="outlined" :to="{ path: '/inventory', query: { op: 'labels', product: product.id } }">Create labels</v-btn>
      </div>
      <div class="counts">
        <div><span class="t-h2 tnum">{{ stock.available }}</span><span class="t-caption muted">available</span></div>
        <div><span class="t-h2 tnum">{{ stock.reserved }}</span><span class="t-caption muted">reserved</span></div>
        <div><span class="t-h2 tnum">{{ stock.assigned ?? 0 }}</span><span class="t-caption muted">issued</span></div>
        <div><span class="t-h2 tnum">{{ stock.picked }}</span><span class="t-caption muted">picked</span></div>
        <div><span class="t-h2 tnum">{{ stock.threshold }}</span><span class="t-caption muted">alert at</span></div>
      </div>
      <p v-if="!stock.byLocation.length" class="t-body muted">Nothing of this product is on a shelf.</p>
      <v-table v-else density="compact">
        <thead><tr><th>Site</th><th>Location</th><th>Shelf</th><th class="text-right">Units</th></tr></thead>
        <tbody>
          <tr v-for="b in stock.byLocation" :key="b.shelf" class="click" @click="code = b.shelf">
            <td>{{ b.siteName ?? b.site }}</td>
            <td>{{ b.locationName ?? b.location }}</td>
            <td>{{ b.shelfNumber ?? '?' }}</td>
            <td class="text-right tnum">{{ b.count }}</td>
          </tr>
        </tbody>
      </v-table>
    </section>
  </div>
</template>

<style scoped>
.finders {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--sp-4);
}
.counts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-6);
}
.counts > div {
  display: flex;
  flex-direction: column;
}
.click {
  cursor: pointer;
}
</style>
