<script setup lang="ts">
/**
 * Inventory, the storeroom map (surface brief: web/sia/.impeccable/surfaces/src-pages-inventory-index-vue.md).
 * One scan field on top (shelf, unit or product code; or a product by name); below, one panel: the Places
 * tree (sites → locations → shelves) beside the record that is open. The URL holds what is open:
 *   ?code=<shelf|unit|product>  A-11 lookup        ?code=<SITE…|LOC…>  A-08 site / location (+ add under it)
 *   ?op=labels[&product=<id>]   A-12 unit labels   ?op=site             A-08 register a site
 * Older links (?op=lookup&code=…, ?op=location) still land here.
 */
import { codeKind, type ProductStaff, useNotify } from '@cimh/web-app'
import { mdiMapMarkerPlusOutline, mdiTagOutline } from '@mdi/js'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import InventoryLabels from '../../components/InventoryLabels.vue'
import InventoryLookup from '../../components/InventoryLookup.vue'
import InventoryPlace from '../../components/InventoryPlace.vue'
import PlacesTree from '../../components/PlacesTree.vue'
import ProductPicker from '../../components/ProductPicker.vue'
import ScanField from '../../components/ScanField.vue'
import { usePlaces } from '../../places'

definePage({ meta: { guard: 'staff', title: 'Locations' } })
const route = useRoute()
const router = useRouter()
const notify = useNotify()
const places = usePlaces()

const str = (v: unknown) => (typeof v === 'string' && v.trim() ? v.trim() : null)
const code = computed(() => str(route.query.code))
const op = computed(() => str(route.query.op))
const view = computed<'labels' | 'new-site' | 'site' | 'location' | 'lookup' | 'none'>(() => {
  if (op.value === 'labels') return 'labels'
  if (op.value === 'site') return 'new-site'
  if (!code.value) return 'none'
  const k = codeKind(code.value)
  return k === 'site' ? 'site' : k === 'location' ? 'location' : 'lookup'
})
const paneTitle = computed(
  () =>
    ({ labels: 'Unit labels', 'new-site': 'New site', site: 'Site', location: 'Location', lookup: 'Lookup', none: 'Start here' })[view.value],
)

// Where the open place, shelf or unit sits, so the tree can show it.
const shelfOf = ref<{ site?: string | null; location?: string | null } | null>(null)
watch(code, () => (shelfOf.value = null))
const siteParam = computed(() => str(route.query.site))
const where = computed(() => {
  if (view.value === 'site') return { site: code.value }
  if (view.value === 'location') return { site: siteParam.value, location: code.value }
  return view.value === 'lookup' ? shelfOf.value : null
})

function open(c: string) {
  void router.push({ query: { code: c } })
}
const picked = ref<ProductStaff | null>(null)
watch(picked, (p) => {
  if (p) {
    open(p.id)
    picked.value = null
  }
})

// Narrow screens: the tree sits under the record and starts folded while something is open.
// It follows the width too: widening to two columns opens it, narrowing folds it again.
const treeOpen = ref(true)
const display = useDisplay()
const narrowTree = computed(() => display.width.value < 900)
watch(
  [view, narrowTree],
  ([v, narrow]) => {
    treeOpen.value = !narrow || v === 'none'
  },
  { immediate: true },
)
const totals = computed(() => ({ sites: places.sites.value.length }))

onMounted(() => {
  if (places.state.value !== 'ready') places.load().catch((e) => notify.report(e, { retry: () => void places.load() }))
})
</script>

<template>
  <div class="inv">
    <div class="bar">
      <ScanField class="scan" label="Shelf, unit or product code" prominent :autofocus="view === 'none' || view === 'lookup'" @scan="open" />
      <ProductPicker v-model="picked" class="find" label="Find a product by name" />
      <div class="acts">
        <v-btn class="m3" variant="outlined" :active="false" :prepend-icon="mdiMapMarkerPlusOutline" :to="{ query: { op: 'site' } }">Register site</v-btn>
        <v-btn class="m3" variant="outlined" :active="false" :prepend-icon="mdiTagOutline" :to="{ query: { op: 'labels' } }">Create labels</v-btn>
      </div>
    </div>

    <div class="frame">
      <section class="tree-col" aria-labelledby="places-title">
        <div class="console-head">
          <h2 id="places-title" class="console-title">Places</h2>
          <span v-if="places.state.value === 'ready'" class="console-mono t-caption muted grow-r">{{ totals.sites }} sites</span>
          <v-btn
            class="m3 tree-toggle"
            size="small"
            variant="text"
            :aria-expanded="treeOpen"
            aria-controls="places-body"
            @click="treeOpen = !treeOpen"
          >
            {{ treeOpen ? 'Hide' : 'Show' }}
          </v-btn>
        </div>
        <div id="places-body" class="tree-body" :class="{ shut: !treeOpen }"><PlacesTree :current="code" :where="where" /></div>
      </section>

      <section class="record" :aria-label="paneTitle">
        <div class="body">
          <InventoryLabels v-if="view === 'labels'" :key="str(route.query.product) ?? 'new'" :product-id="str(route.query.product) ?? undefined" />
          <InventoryPlace v-else-if="view === 'new-site'" kind="new-site" />
          <InventoryPlace v-else-if="view === 'site' || view === 'location'" :key="code!" :kind="view" :code="code!" :site="siteParam" />
          <InventoryLookup v-else-if="view === 'lookup'" :key="code!" :code="code!" @place="(w) => (shelfOf = w)" />
          <div v-else class="start">
            <h2 class="t-h3">Find anything in the store</h2>
            <p class="t-body">Scan a shelf, unit or product label, or open a place in the tree.</p>
            <p class="t-caption muted">
              New stock: <router-link :to="{ query: { op: 'labels' } }">create its unit labels</router-link>, then put the units on a shelf with
              <router-link :to="{ path: '/pick', query: { op: 'stow' } }">Pick › Stow · Relocate</router-link>.
            </p>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.inv {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
  padding: var(--sp-4) var(--sp-6) var(--sp-6);
}
.bar {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) auto;
  gap: var(--sp-3);
  align-items: start;
}
.scan {
  grid-column: 1 / -1;
}
.acts {
  display: flex;
  gap: var(--sp-2);
  padding-top: 4px;
}
.frame {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
}
@media (min-width: 900px) {
  .frame {
    min-height: 420px;
  }
}
.tree-col {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: 1px solid rgb(var(--v-theme-seam));
}
.record {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}
.grow-r {
  margin-left: auto;
}
.tree-toggle {
  display: none;
}
.tree-body {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1 1 0;
}
.body {
  min-height: 0;
  overflow: auto;
}
.start {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
  padding: var(--sp-6) var(--sp-4);
  max-width: 560px;
}
@media (min-width: 1280px) {
  /* Wide screens: the page fits the window; the tree and the record scroll on their own. */
  .inv {
    height: calc(100dvh - 140px);
  }
  .frame {
    flex: 1 1 0;
    min-height: 0;
  }
  .tree-col :deep(.tree) {
    flex: 1 1 0;
  }
}
@media (max-width: 899px) {
  .frame {
    grid-template-columns: minmax(0, 1fr);
  }
  /* Phones and narrow windows: what is open first, the tree under it. */
  .record {
    order: -1;
    border-bottom: 1px solid rgb(var(--v-theme-seam));
  }
  .tree-col {
    border-right: 0;
  }
  .tree-toggle {
    display: inline-flex;
  }
  .tree-body {
    flex: none;
  }
  .tree-body.shut {
    display: none;
  }
}
@media (max-width: 599px) {
  .inv {
    padding: var(--sp-4);
  }
  .bar {
    grid-template-columns: minmax(0, 1fr);
  }
  .acts {
    justify-content: stretch;
  }
  .acts .v-btn {
    flex: 1;
  }
}
</style>
