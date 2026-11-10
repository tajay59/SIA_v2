<script setup lang="ts">
/**
 * S-02 catalogue / S-04 Pro Bono, same structure as the legacy Inventory and NCI pages: a banner with the
 * page title and the search box (catalogue: gear line-art; Pro Bono: the primary colour), the type chips
 * (Pro Bono: project chips) under it, then the product grid. Searching shows ranked results on the same
 * page, as in legacy. State lives in the URL (?q, type, department, project, inStock) so it can be shared.
 * v2 differences: cursor paging ("Load more") instead of page numbers; no prices.
 */
import { boolParam, call, catalog, type Product, PRODUCT_TYPES, type ProductType, typeLabel, useCursorList, useReference } from '@cimh/web-app'
import { mdiClose, mdiFilterVariant, mdiMagnify } from '@mdi/js'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ProductGrid from './ProductGrid.vue'

const props = defineProps<{ probono?: boolean; title: string; intro: string }>()
const route = useRoute()
const router = useRouter()
const { reference } = useReference()

const str = (v: unknown) => (typeof v === 'string' && v ? v : null)
const q = computed(() => (str(route.query.q) ?? '').trim())
const type = computed(() => str(route.query.type) as ProductType | null)
const department = computed(() => str(route.query.department))
const project = computed(() => str(route.query.project))
const inStock = computed(() => boolParam(route.query.inStock) === true)
const searching = computed(() => q.value.length >= 2)

function setQuery(patch: Record<string, string | null>) {
  const query: Record<string, string> = {}
  for (const [k, v] of Object.entries({ ...route.query, ...patch })) if (typeof v === 'string' && v) query[k] = v
  void router.replace({ query })
}

// Search box: debounced into ?q (legacy searched as you typed).
const text = ref(q.value)
let timer: ReturnType<typeof setTimeout> | undefined
// A pending debounce must not fire after the page is left (router.replace would navigate back here).
onBeforeUnmount(() => clearTimeout(timer))
watch(text, (v) => {
  clearTimeout(timer)
  timer = setTimeout(() => setQuery({ q: v.trim().length >= 2 ? v.trim() : null }), 300)
})
watch(q, (v) => {
  if (v !== text.value.trim()) text.value = v
})

const chips = computed(() =>
  props.probono
    ? (reference.value?.projects ?? []).map((p) => ({ key: 'project', value: p.code, title: p.name }))
    : PRODUCT_TYPES.map((k) => ({ key: 'type', value: k as string, title: typeLabel(reference.value, k) })),
)
const chipKey = computed(() => (props.probono ? 'project' : 'type'))
const chipValue = computed(() => (props.probono ? project.value : type.value))
const extra = computed(() => [props.probono ? null : project.value, department.value, inStock.value || null].filter(Boolean).length)

const list = useCursorList<Product>((cursor) => {
  const common = {
    type: type.value ?? undefined,
    department: department.value ?? undefined,
    probono: props.probono || undefined,
    cursor,
    limit: 24,
  }
  return searching.value
    ? call(() => catalog.GET('/products/search', { params: { query: { ...common, q: q.value } } }))
    : call(() =>
        catalog.GET('/products', {
          params: { query: { ...common, project: project.value ?? undefined, inStock: inStock.value || undefined } },
        }),
      )
})
onMounted(list.reload)
watch(() => [q.value, type.value, department.value, project.value, inStock.value], () => void list.reload())
</script>

<template>
  <div>
    <section class="banner" :class="{ probono }">
      <div class="banner-inner">
        <div class="banner-text">
          <h1 class="banner-title">{{ title }}</h1>
          <p class="banner-intro">{{ intro }}</p>
        </div>
        <form class="search" role="search" @submit.prevent="setQuery({ q: text.trim() || null })">
          <v-text-field
            v-model="text"
            :prepend-inner-icon="mdiMagnify"
            :label="probono ? 'Search Pro Bono items' : 'Search the catalogue'"
            hide-details
            clearable
            variant="solo"
            flat
            rounded="lg"
            bg-color="surface"
            @click:clear="text = ''"
          />
        </form>
      </div>
    </section>

    <div class="toolbar">
      <div class="toolbar-inner">
        <v-chip-group
          :model-value="chipValue"
          selected-class="chip-on"
          class="chips"
          :aria-label="probono ? 'Project' : 'Type'"
          @update:model-value="(v: string | null) => setQuery({ [chipKey]: v ?? null })"
        >
          <v-chip :value="null" :class="{ 'chip-on': !chipValue }" variant="outlined" rounded="lg" @click="setQuery({ [chipKey]: null })">All</v-chip>
          <v-chip v-for="c in chips" :key="c.value" :value="c.value" variant="outlined" rounded="lg" filter>{{ c.title }}</v-chip>
        </v-chip-group>
        <v-menu :close-on-content-click="false" location="bottom end">
          <template #activator="{ props: act }">
            <v-btn v-bind="act" variant="outlined" :prepend-icon="mdiFilterVariant">
              Filters<template v-if="extra"> ({{ extra }})</template>
            </v-btn>
          </template>
          <v-card min-width="300" class="pa-4 stack">
            <v-select
              :model-value="department"
              :items="reference?.departments ?? []"
              label="Department"
              clearable
              hide-details
              @update:model-value="(v: string | null) => setQuery({ department: v })"
            />
            <v-select
              v-if="!probono"
              :model-value="project"
              :items="(reference?.projects ?? []).map((p) => ({ value: p.code, title: p.name }))"
              label="Project"
              clearable
              hide-details
              @update:model-value="(v: string | null) => setQuery({ project: v })"
            />
            <v-switch
              :model-value="inStock"
              :disabled="searching"
              label="In stock only"
              color="primary"
              hide-details
              inset
              @update:model-value="(v: boolean | null) => setQuery({ inStock: v ? 'true' : null })"
            />
            <v-btn v-if="extra" variant="text" :prepend-icon="mdiClose" @click="setQuery({ department: null, inStock: null, ...(probono ? {} : { project: null }) })">
              Clear filters
            </v-btn>
          </v-card>
        </v-menu>
      </div>
    </div>

    <v-container max-width="1200" class="results">
      <p v-if="searching" class="t-body muted mb-2">Results for “{{ q }}”, best matches first.</p>
      <ProductGrid
        :list="list"
        :empty-title="searching ? 'No products found' : 'Nothing matches these filters'"
        :empty-text="searching ? 'Check the spelling or try a model number.' : 'Try another type, or clear the filters.'"
        @clear="router.replace({ query: {} })"
      />
    </v-container>
  </div>
</template>

<style scoped>
.banner {
  background-color: rgb(var(--v-theme-surface));
  background-image: url('@cimh/web-app/assets/legacy/gears.webp');
  background-size: cover;
  background-position: center bottom;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.v-theme--cimhDark .banner:not(.probono) {
  background-blend-mode: multiply;
}
.banner.probono {
  background-image: none;
  background-color: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}
.banner-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--sp-10, 40px) var(--sp-4);
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 480px);
  gap: var(--sp-6);
  align-items: center;
}
@media (max-width: 959px) {
  .banner-inner {
    grid-template-columns: minmax(0, 1fr);
    padding: var(--sp-8) var(--sp-4) var(--sp-6);
  }
}
.banner-title {
  font-size: clamp(28px, 3.2vw, 40px);
  font-weight: 700;
  letter-spacing: -0.015em;
  margin: 0 0 var(--sp-2);
}
.banner-intro {
  margin: 0;
  max-width: 60ch;
}
.search :deep(.v-field) {
  box-shadow: 0 2px 10px rgba(15, 26, 36, 0.1);
}
.toolbar {
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgb(var(--v-theme-surface));
}
.toolbar-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--sp-2) var(--sp-4);
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}
.chips {
  flex: 1;
  min-width: 0;
}
.chips :deep(.chip-on) {
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
  border-color: rgb(var(--v-theme-primary));
}
.results {
  padding-top: var(--sp-6);
  padding-bottom: var(--sp-12, 48px);
}
</style>
