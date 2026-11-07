<script setup lang="ts">
/** S-06 search results: ranked by relevance (name, model number, keywords, make), with type/department filters. */
import { boolParam, call, catalog, type Product, type ProductType, useCursorList, useReference } from '@cimh/web-app'
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import CatalogueFilters from '../components/CatalogueFilters.vue'
import ProductGrid from '../components/ProductGrid.vue'

definePage({ meta: { guard: 'public', title: 'Search' } })
const route = useRoute()
const router = useRouter()
const { reference } = useReference()

const str = (v: unknown) => (typeof v === 'string' && v ? v : null)
const q = computed(() => (str(route.query.q) ?? '').trim())
const type = computed(() => str(route.query.type) as ProductType | null)
const department = computed(() => str(route.query.department))
const probono = computed(() => boolParam(route.query.probono))

function setFilter(key: string, value: string | boolean | null) {
  const query = { ...route.query }
  if (value === null || value === false || value === '') delete query[key]
  else query[key] = String(value)
  void router.replace({ query })
}
const clear = () => void router.replace({ query: { q: q.value } })
const search = (text: string) => text.length >= 2 && void router.replace({ query: { ...route.query, q: text } })

const list = useCursorList<Product>(async (cursor) => {
  if (q.value.length < 2) return { items: [], nextCursor: null }
  return call(() =>
    catalog.GET('/products/search', {
      params: {
        query: {
          q: q.value,
          type: type.value ?? undefined,
          department: department.value ?? undefined,
          probono: probono.value,
          cursor,
          limit: 24,
        },
      },
    }),
  )
})
onMounted(list.reload)
watch(() => [q.value, type.value, department.value, probono.value], () => void list.reload())
</script>

<template>
  <v-container max-width="1200" class="page">
    <div class="page-header">
      <h1 class="t-h1">
        <template v-if="q.length >= 2">Results for “{{ q }}”</template>
        <template v-else>Search the catalogue</template>
      </h1>
    </div>
    <div class="layout">
      <aside aria-label="Filters">
        <CatalogueFilters
          :key="q" :reference="reference" :type="type" :department="department" :query="q"
          @set="setFilter" @search="search" @clear="clear"
        />
        <v-switch
          class="mt-2" :model-value="probono === true" label="Pro Bono only" color="primary" hide-details inset
          @update:model-value="(v: boolean | null) => setFilter('probono', !!v)"
        />
      </aside>
      <p v-if="q.length < 2" class="t-body muted">Type at least two characters: a name, model number or keyword.</p>
      <ProductGrid
        v-else :list="list" empty-title="No products found"
        empty-text="Check the spelling, try a model number, or clear the filters." @clear="clear"
      />
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
</style>
