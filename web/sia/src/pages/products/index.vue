<script setup lang="ts">
/**
 * A-05 products: search (name, model, keywords, serials), filters (type, department, sellable, Pro Bono,
 * inactive), table with stock count. Row -> A-07, "New product" -> A-06. Filters live in the URL.
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
import { mdiFormatListBulleted, mdiMagnify, mdiPlus, mdiViewGridOutline } from '@mdi/js'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

definePage({ meta: { guard: 'staff', title: 'Products' } })
const route = useRoute()
const router = useRouter()
const { reference } = useReference()

const str = (v: unknown) => (typeof v === 'string' && v ? v : null)
const q = ref(str(route.query.q) ?? '')
const type = ref(str(route.query.type) as ProductType | null)
const department = ref(str(route.query.department))
const sellable = ref(boolParam(route.query.sellable) ?? null)
const probono = ref(boolParam(route.query.probono) ?? null)
const inactive = ref(boolParam(route.query.inactive) === true)

const searching = computed(() => q.value.trim().length >= 2)
// Grid or list, as in the legacy products page; remembered on this device.
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

let timer: ReturnType<typeof setTimeout> | undefined
watch([q, type, department, sellable, probono, inactive], () => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    const query: Record<string, string> = {}
    if (q.value.trim()) query.q = q.value.trim()
    if (type.value) query.type = type.value
    if (department.value) query.department = department.value
    if (sellable.value !== null) query.sellable = String(sellable.value)
    if (probono.value !== null) query.probono = String(probono.value)
    if (inactive.value) query.inactive = 'true'
    void router.replace({ query })
    void list.reload()
  }, 250)
})

const YESNO = [
  { value: true, title: 'Yes' },
  { value: false, title: 'No' },
]
const typeItems = computed(() => PRODUCT_TYPES.map((k) => ({ value: k, title: typeLabel(reference.value, k) })))
const headers = [
  { title: 'Name', key: 'name', sortable: false },
  { title: 'Model number', key: 'modelnumber', sortable: false },
  { title: 'Type', key: 'type', sortable: false },
  { title: 'Department', key: 'department', sortable: false },
  { title: 'In stock', key: 'stockCount', sortable: false, align: 'end' as const },
  { title: 'Shown to customers', key: 'flags', sortable: false },
]
</script>

<template>
  <div class="page">
    <div class="page-header">
      <span class="t-label muted">View</span>
      <v-btn-toggle v-model="view" mandatory density="compact" variant="outlined" divided rounded="lg" aria-label="View">
        <v-btn value="grid" :icon="mdiViewGridOutline" aria-label="Grid" />
        <v-btn value="list" :icon="mdiFormatListBulleted" aria-label="List" />
      </v-btn-toggle>
      <span class="spacer" />
      <v-btn to="/products/new" color="primary" :prepend-icon="mdiPlus">New product</v-btn>
    </div>
    <div class="filters">
      <v-text-field v-model="q" :prepend-inner-icon="mdiMagnify" label="Name, model, keyword or serial" clearable hide-details @click:clear="q = ''" />
      <v-select v-model="type" :items="typeItems" label="Type" clearable hide-details />
      <v-select v-model="department" :items="reference?.departments ?? []" label="Department" clearable hide-details />
      <v-select v-model="sellable" :items="YESNO" label="Sellable" clearable hide-details :disabled="searching" />
      <v-select v-model="probono" :items="YESNO" label="Pro Bono" clearable hide-details />
      <v-checkbox v-model="inactive" label="Include inactive" hide-details density="compact" :disabled="searching" />
    </div>
    <p v-if="searching" class="t-caption muted mb-2">Search shows active products, best matches first; serial and model-number matches come first.</p>
    <div v-if="view === 'grid'" class="grid-view">
      <template v-if="!list.loaded.value && list.loading.value">
        <v-skeleton-loader v-for="i in 8" :key="i" type="image, list-item-two-line" />
      </template>
      <router-link v-for="p in list.items.value" :key="p.id" :to="`/products/${p.id}`" class="pcard">
        <div class="ptile">
          <ProductImage :image="primaryImage(p)" :alt="p.name" small sizes="220px" />
          <span v-if="!p.active" class="ptag off">Inactive</span>
          <span v-else-if="p.probono" class="ptag probono-tag">Pro Bono</span>
        </div>
        <span class="pname">{{ p.name }}</span>
        <span class="t-caption muted t-mono">{{ p.modelnumber || p.id }}</span>
        <span class="t-caption">In stock: <strong class="tnum">{{ p.stockCount ?? '—' }}</strong> · {{ p.sellable ? 'Shown to customers' : 'Hidden' }}</span>
      </router-link>
      <p v-if="list.loaded.value && !list.items.value.length" class="t-body muted">No products match. <router-link to="/products/new">Create one</router-link>.</p>
    </div>
    <div v-if="view === 'grid' && list.nextCursor.value" class="row-end py-4">
      <v-btn variant="outlined" :loading="list.loading.value" @click="list.loadMore">Load more</v-btn>
    </div>
    <v-card v-if="view === 'list'">
      <v-data-table
        :headers="headers"
        :items="list.items.value"
        :loading="list.loading.value"
        item-value="id"
        :items-per-page="-1"
        hide-default-footer
        hover
        @click:row="(_e: unknown, row: { item: ProductStaff }) => router.push(`/products/${row.item.id}`)"
      >
        <template #[`item.name`]="{ item }">
          <router-link :to="`/products/${item.id}`">{{ item.name }}</router-link>
          <v-chip v-if="!item.active" size="x-small" class="ml-2" label>Inactive</v-chip>
        </template>
        <template #[`item.modelnumber`]="{ item }"><span class="t-mono">{{ item.modelnumber || '—' }}</span></template>
        <template #[`item.type`]="{ item }">{{ typeLabel(reference, item.type) }}</template>
        <template #[`item.stockCount`]="{ item }"><span class="tnum">{{ item.stockCount ?? '—' }}</span></template>
        <template #[`item.flags`]="{ item }">
          <div class="row flags">
            <span>{{ item.sellable ? 'Yes' : 'No' }}</span>
            <span v-if="item.probono" class="probono">Pro Bono<template v-if="item.probonoMaxPerRequest"> · max {{ item.probonoMaxPerRequest }}</template></span>
          </div>
        </template>
        <template #no-data><p class="t-body pa-6">No products match. <router-link to="/products/new">Create one</router-link>.</p></template>
      </v-data-table>
      <div v-if="list.nextCursor.value" class="row-end pa-4">
        <v-btn variant="outlined" :loading="list.loading.value" @click="list.loadMore">Load more</v-btn>
      </div>
    </v-card>
  </div>
</template>

<style scoped>
.filters {
  display: grid;
  grid-template-columns: minmax(240px, 2fr) repeat(4, minmax(130px, 1fr)) max-content;
  gap: var(--sp-3);
  margin-bottom: var(--sp-4);
  align-items: center;
}
@media (max-width: 1100px) {
  .filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
.grid-view {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: var(--sp-6) var(--sp-4);
}
.pcard {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: inherit;
  text-decoration: none;
}
.ptile {
  position: relative;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: var(--sp-2);
}
.pcard:hover .ptile {
  box-shadow: 0 4px 14px rgba(15, 26, 36, 0.12);
}
.pcard:hover .pname {
  color: rgb(var(--v-theme-primary));
}
.pname {
  font-weight: 600;
  line-height: 1.3;
}
.ptag {
  position: absolute;
  top: 8px;
  left: 8px;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 6px;
}
.ptag.off {
  background: #f1d4d1;
  color: #8a1c13;
}
.probono-tag {
  background: #f5c400;
  color: #0f1a24;
}
.flags {
  gap: var(--sp-2);
}
.probono {
  background: #f5c400;
  color: #0f1a24;
  font-size: 12px;
  font-weight: 600;
  padding: 0 6px;
  border-radius: 4px;
}
</style>
