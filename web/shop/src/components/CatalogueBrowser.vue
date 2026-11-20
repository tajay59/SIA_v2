<script setup lang="ts">
/**
 * S-02 catalogue / S-04 Pro Bono ("Search desk", impeccable 2026-11-16; brief web/shop/.impeccable/surfaces/
 * src-components-cataloguebrowser-vue.md). A navy counter band: title, one wide search over make, model and model
 * number, and the family index along its bottom edge (catalogue: Meteorological / Radar, the only types SHOP
 * shows; Pro Bono: projects) with In stock and Filters at the right. Results: same-height cards; while
 * searching, matched text is marked. State lives in the URL (?q, type, department, project, inStock).
 * Cursor paging ("Load more"); no prices.
 */
import { boolParam, call, catalog, type Product, type ProductType, SHOP_TYPES, typeLabel, useCursorList, useReference } from '@cimh/web-app'
import { mdiClose, mdiFilterVariant, mdiMagnify } from '@mdi/js'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
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

// Search box: debounced into ?q (searches as you type).
const text = ref(q.value)
let timer: ReturnType<typeof setTimeout> | undefined
// A pending debounce must not fire after the page is left (router.replace would navigate back here).
onBeforeUnmount(() => clearTimeout(timer))
watch(text, (v) => {
  clearTimeout(timer)
  timer = setTimeout(() => setQuery({ q: (v ?? '').trim().length >= 2 ? (v ?? '').trim() : null }), 300)
})
watch(q, (v) => {
  if (v !== (text.value ?? '').trim()) text.value = v
})

// Family index: catalogue = the SHOP types; Pro Bono = projects.
const tabs = computed(() => [
  { value: null as string | null, title: 'All' },
  ...(props.probono
    ? (reference.value?.projects ?? []).map((p) => ({ value: p.code as string | null, title: p.name }))
    : SHOP_TYPES.map((k) => ({ value: k as string | null, title: typeLabel(reference.value, k) }))),
])
const tabKey = computed(() => (props.probono ? 'project' : 'type'))
const tabValue = computed(() => (props.probono ? project.value : type.value))
const extra = computed(() => [props.probono ? null : project.value, department.value].filter(Boolean).length)

// The index ink slides to the chosen tab (signature interaction; transform only).
const indexEl = ref<HTMLElement | null>(null)
const ink = ref({ x: 0, w: 0, ready: false })
function placeInk() {
  const on = indexEl.value?.querySelector<HTMLElement>('[aria-pressed="true"]')
  if (!on) return
  ink.value = { x: on.offsetLeft, w: on.offsetWidth, ready: true }
}
watch([tabValue, tabs], () => void nextTick(placeInk))
let ro: ResizeObserver | undefined
onMounted(() => {
  void nextTick(placeInk)
  if (indexEl.value && 'ResizeObserver' in window) {
    ro = new ResizeObserver(placeInk)
    ro.observe(indexEl.value)
  }
})
onBeforeUnmount(() => ro?.disconnect())

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

const filtered = computed(() => !!(tabValue.value || extra.value || inStock.value))
</script>

<template>
  <div>
    <section class="desk" :class="{ probono }" aria-labelledby="desk-title">
      <div class="desk-inner">
        <div class="desk-head">
          <span v-if="probono" class="probono-badge">Pro Bono</span>
          <h1 id="desk-title" class="desk-title">{{ title }}</h1>
          <p class="desk-intro">{{ intro }}</p>
        </div>
        <form class="search" role="search" @submit.prevent="setQuery({ q: (text ?? '').trim() || null })">
          <v-text-field
            v-model="text"
            :prepend-inner-icon="mdiMagnify"
            :label="probono ? 'Search Pro Bono items' : 'Search the catalogue'"
            placeholder="Make, model or model number"
            persistent-placeholder
            hide-details
            clearable
            class="search-field"
            @click:clear="text = ''"
          />
        </form>
        <div class="index-row">
          <div ref="indexEl" class="index" role="group" :aria-label="probono ? 'Project' : 'Type'">
            <button
              v-for="t in tabs"
              :key="t.value ?? 'all'"
              type="button"
              class="tab"
              :aria-pressed="tabValue === t.value"
              @click="setQuery({ [tabKey]: t.value })"
            >
              {{ t.title }}
            </button>
            <span class="ink" :class="{ ready: ink.ready }" :style="{ transform: `translateX(${ink.x}px)`, width: `${ink.w}px` }" aria-hidden="true" />
          </div>
          <div class="index-tools">
            <v-switch
              :model-value="inStock"
              :disabled="searching"
              label="In stock only"
              color="white"
              hide-details
              inset
              density="compact"
              class="stock-switch"
              @update:model-value="(v: boolean | null) => setQuery({ inStock: v ? 'true' : null })"
            />
            <v-menu :close-on-content-click="false" location="bottom end">
              <template #activator="{ props: act }">
                <v-btn v-bind="act" variant="outlined" color="white" :prepend-icon="mdiFilterVariant">
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
                <v-btn v-if="extra" variant="text" :prepend-icon="mdiClose" @click="setQuery({ department: null, ...(probono ? {} : { project: null }) })">
                  Clear filters
                </v-btn>
              </v-card>
            </v-menu>
          </div>
        </div>
      </div>
    </section>

    <div class="results">
      <p v-if="searching" class="search-note">Results for “{{ q }}”, best matches first.</p>
      <ProductGrid
        :list="list"
        :highlight="searching ? q : ''"
        :empty-title="searching ? 'No products found' : 'Nothing matches these filters'"
        :empty-text="searching ? 'Check the spelling, or try the model number on the instrument’s label.' : 'Try the other family, or clear the filters.'"
        :clear-label="searching ? 'Clear search' : 'Clear filters'"
        @clear="searching ? setQuery({ q: null }) : router.replace({ query: {} })"
      >
        <template v-if="filtered && !searching" #toolbar>
          <v-btn variant="text" size="small" :prepend-icon="mdiClose" @click="router.replace({ query: {} })">Clear all</v-btn>
        </template>
      </ProductGrid>
    </div>
  </div>
</template>

<style scoped>
/* The counter band: the same deep CIMH navy as the home masthead, gear line-art inverted and faint. */
.desk {
  --field: #0a2e4a;
  position: relative;
  isolation: isolate;
  overflow: hidden;
  background: var(--field);
  color: #fff;
  border-bottom: 4px solid #0084c8;
}
.desk.probono {
  border-bottom-color: rgb(var(--v-theme-accent-probono));
}
.desk::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: -1;
  background: url('@cimh/web-app/assets/legacy/gears.webp') center bottom / cover no-repeat;
  filter: invert(1);
  mix-blend-mode: screen;
  opacity: 0.18;
}
.desk-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--sp-10, 40px) var(--sp-4) 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-6);
}
.desk-head {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: var(--sp-2) var(--sp-3);
}
.desk-head > :not(.probono-badge) {
  grid-column: 1 / -1;
}
.desk-head .probono-badge {
  justify-self: start;
}
.desk-title {
  font-size: clamp(28px, 3vw, 38px);
  line-height: 1.15;
  font-weight: 700;
  letter-spacing: -0.015em;
  margin: 0;
}
.desk-intro {
  flex-basis: 100%;
  margin: 0;
  max-width: 70ch;
  font-size: 16px;
  line-height: 24px;
  color: rgba(255, 255, 255, 0.84);
}
/* The search is the counter: wide, white, tall. */
.search-field :deep(.v-field) {
  min-height: 60px;
  font-size: 18px;
  background: #fff;
  color: #0f1a24;
  box-shadow: 0 8px 24px -10px rgba(0, 0, 0, 0.5);
}
.search-field :deep(.v-field::after) {
  border-color: transparent;
}
.search-field :deep(.v-field--focused::after) {
  border-color: #0084c8;
}
.search-field :deep(.v-label),
.search-field :deep(input::placeholder) {
  color: #4b5866;
  opacity: 1;
}
.search-field :deep(.v-icon) {
  color: #0f1a24;
  opacity: 0.8;
}
.index-row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--sp-3) var(--sp-6);
  flex-wrap: wrap;
}
.index {
  position: relative;
  display: flex;
  gap: var(--sp-1);
  overflow-x: auto;
  scrollbar-width: none;
  max-width: 100%;
}
.tab {
  flex: none;
  min-height: 48px;
  padding: 0 var(--sp-4);
  font: inherit;
  font-size: 15px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.78);
  background: none;
  border: 0;
  border-radius: 8px 8px 0 0;
  cursor: pointer;
  transition: color 150ms ease-out, background-color 150ms ease-out;
}
.tab:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.08);
}
.tab[aria-pressed='true'] {
  color: #fff;
}
.tab:focus-visible {
  outline: 2px solid #fff;
  outline-offset: -2px;
}
.ink {
  position: absolute;
  left: 0;
  bottom: 0;
  height: 4px;
  border-radius: 4px 4px 0 0;
  background: #fff;
  opacity: 0;
}
.ink.ready {
  opacity: 1;
  transition: transform 300ms cubic-bezier(0.16, 1, 0.3, 1), width 300ms cubic-bezier(0.16, 1, 0.3, 1);
}
.probono .ink {
  background: rgb(var(--v-theme-accent-probono));
}
.index-tools {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding-bottom: var(--sp-2);
}
.stock-switch {
  flex: none;
}
.stock-switch :deep(.v-label) {
  color: #fff;
  opacity: 1;
}
.desk :deep(.v-btn:focus-visible) {
  outline: 2px solid #fff;
  outline-offset: 2px;
}
.results {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--sp-6) var(--sp-4) var(--sp-12, 48px);
}
.search-note {
  margin: 0 0 var(--sp-2);
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
@media (max-width: 599.98px) {
  .desk-inner {
    padding-top: var(--sp-6);
    gap: var(--sp-4);
  }
  .index-row {
    flex-direction: column;
    align-items: stretch;
  }
  .index-tools {
    justify-content: space-between;
  }
}
@media (prefers-reduced-motion: reduce) {
  .ink.ready,
  .tab {
    transition: none;
  }
}
</style>
