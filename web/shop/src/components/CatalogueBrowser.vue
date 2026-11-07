<script setup lang="ts">
/**
 * S-02 / S-04 catalogue (DESIGN_BRIEF §10): filter column (240 px; a drawer on small screens) + product grid +
 * "Load more" (cursor). Filters live in the URL so a filtered list can be shared and survives Back.
 */
import { boolParam, call, catalog, type Product, type ProductType, useCursorList, useReference } from '@cimh/web-app'
import { mdiFilterVariant } from '@mdi/js'
import { computed, onMounted, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useRoute, useRouter } from 'vue-router'
import CatalogueFilters from './CatalogueFilters.vue'
import ProductGrid from './ProductGrid.vue'

const props = defineProps<{ probono?: boolean; title: string; intro: string }>()
const route = useRoute()
const router = useRouter()
const { mdAndUp } = useDisplay()
const { reference } = useReference()
const drawer = ref(false)

const str = (v: unknown) => (typeof v === 'string' && v ? v : null)
const type = computed(() => str(route.query.type) as ProductType | null)
const department = computed(() => str(route.query.department))
const project = computed(() => str(route.query.project))
const inStock = computed(() => boolParam(route.query.inStock) === true)
const active = computed(() => [type.value, department.value, project.value, inStock.value || null].filter(Boolean).length)

function setFilter(key: string, value: string | boolean | null) {
  const query = { ...route.query }
  if (value === null || value === false || value === '') delete query[key]
  else query[key] = String(value)
  void router.replace({ query })
}
const clear = () => void router.replace({ query: {} })
function search(text: string) {
  if (text.length >= 2) void router.push({ path: '/search', query: { q: text, ...(props.probono ? { probono: 'true' } : {}) } })
}

const list = useCursorList<Product>((cursor) =>
  call(() =>
    catalog.GET('/products', {
      params: {
        query: {
          type: type.value ?? undefined,
          department: department.value ?? undefined,
          project: project.value ?? undefined,
          inStock: inStock.value || undefined,
          probono: props.probono || undefined,
          cursor,
          limit: 24,
        },
      },
    }),
  ),
)
onMounted(list.reload)
watch(() => [type.value, department.value, project.value, inStock.value], () => void list.reload())
</script>

<template>
  <v-container max-width="1200" class="page">
    <div class="page-header">
      <div class="stack-sm">
        <h1 class="t-h1">{{ title }}</h1>
        <p class="t-body muted prose">{{ intro }}</p>
      </div>
    </div>
    <div class="layout">
      <aside v-if="mdAndUp" class="side" aria-label="Filters">
        <CatalogueFilters
          :reference="reference" :type="type" :department="department" :project="project" :in-stock="inStock"
          show-project show-stock @set="setFilter" @search="search" @clear="clear"
        />
      </aside>
      <v-navigation-drawer v-else v-model="drawer" temporary location="left" width="300" aria-label="Filters">
        <div class="drawer">
          <CatalogueFilters
            :reference="reference" :type="type" :department="department" :project="project" :in-stock="inStock"
            show-project show-stock @set="setFilter" @search="search" @clear="clear"
          />
        </div>
      </v-navigation-drawer>
      <ProductGrid :list="list" empty-title="Nothing matches these filters" @clear="clear">
        <template #toolbar>
          <v-btn v-if="!mdAndUp" variant="outlined" :prepend-icon="mdiFilterVariant" @click="drawer = true">
            Filters<template v-if="active"> ({{ active }})</template>
          </v-btn>
        </template>
      </ProductGrid>
    </div>
  </v-container>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: var(--sp-6);
  align-items: start;
}
@media (max-width: 959px) {
  .layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
.side {
  position: sticky;
  top: 80px;
}
.drawer {
  padding: var(--sp-4);
}
</style>
