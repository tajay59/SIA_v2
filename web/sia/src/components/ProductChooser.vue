<script setup lang="ts">
/**
 * Choose one product: a button (or the chosen product with Change) that opens a search dialog.
 * Search = catalog `/products/search` (name, model number, keyword or serial, ≥ 2 characters); with no search the
 * dialog lists the first active products so there is something to pick at once. Announcements (A-22) use it.
 */
import { call, catalog, makeModel, primaryImage, ProductImage, type ProductStaff } from '@cimh/web-app'
import { mdiClose, mdiMagnify } from '@mdi/js'
import { computed, nextTick, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'

const model = defineModel<ProductStaff | null>({ default: null })
const props = withDefaults(defineProps<{ label?: string; error?: boolean }>(), { label: 'Product', error: false })

const { xs } = useDisplay()
const open = ref(false)
const q = ref('')
const items = ref<ProductStaff[]>([])
const loading = ref(false)
const failed = ref(false)
const searchRef = ref<{ focus: () => void } | null>(null)
const triggerRef = ref<{ $el: HTMLElement } | null>(null)
let timer: ReturnType<typeof setTimeout> | undefined
let seq = 0

const text = computed(() => q.value.trim())
const tooShort = computed(() => text.value.length === 1)

async function load() {
  const mine = ++seq
  loading.value = true
  failed.value = false
  try {
    const page = text.value.length >= 2
      ? await call(() => catalog.GET('/products/search', { params: { query: { q: text.value, limit: 30 } } }))
      : await call(() => catalog.GET('/products', { params: { query: { limit: 30 } } }))
    if (mine === seq) items.value = page.items as ProductStaff[]
  } catch {
    if (mine === seq) {
      items.value = []
      failed.value = true
    }
  } finally {
    if (mine === seq) loading.value = false
  }
}

watch(q, () => {
  clearTimeout(timer)
  if (tooShort.value) return
  timer = setTimeout(load, 250)
})

function show() {
  q.value = ''
  open.value = true
  load()
}
function choose(p: ProductStaff) {
  model.value = p
  open.value = false
}
function clear() {
  model.value = null
}
// Focus the search once the dialog is in; give it back to the button that opened it.
watch(open, async (v) => {
  if (v) return
  clearTimeout(timer)
  await nextTick()
  triggerRef.value?.$el?.focus?.()
})
function onEntered() {
  searchRef.value?.focus()
}
// Enter in the search moves into the results (the first one), arrows then walk the list.
function toResults() {
  const first = document.querySelector<HTMLElement>('.pc-results .v-list-item')
  first?.focus()
}

// Products customers can open on SHOP: sellable, active, and MET/RAD or Pro Bono (catalog-svc PUBLIC_FILTER).
function onShop(p: ProductStaff) {
  return p.sellable && p.active !== false && (p.type === 'MET' || p.type === 'RAD' || !!p.probono)
}
</script>

<template>
  <div class="pc" :class="{ error: props.error }">
    <div v-if="model" class="chosen">
      <div class="thumb"><ProductImage :image="primaryImage(model)" alt="" small sizes="48px" /></div>
      <div class="ident">
        <p class="pc-cap">{{ label }}</p>
        <p class="name">{{ model.name }}</p>
        <p class="sub mono">{{ makeModel(model) || model.id }}</p>
      </div>
      <span class="acts">
        <v-btn ref="triggerRef" class="m3" variant="tonal" size="small" @click="show">Change…</v-btn>
        <v-btn :icon="mdiClose" variant="text" size="small" :aria-label="`Remove ${model.name}`" @click="clear" />
      </span>
    </div>
    <v-btn v-else ref="triggerRef" class="m3 pick" variant="tonal" :prepend-icon="mdiMagnify" @click="show">
      Choose a product…
    </v-btn>
  </div>

  <v-dialog v-model="open" max-width="640" :fullscreen="xs" scrollable aria-labelledby="pc-title" @after-enter="onEntered">
    <v-card :rounded="xs ? 0 : 'lg'" class="pc-card">
      <header class="dlg-head solo">
        <div class="dlg-who">
          <h2 id="pc-title" class="dlg-title">Choose a product</h2>
          <p class="dlg-sub">Search by name, model number, keyword or serial.</p>
        </div>
      </header>
      <div class="pc-search">
        <v-text-field
          ref="searchRef"
          v-model="q"
          :prepend-inner-icon="mdiMagnify"
          label="Search products"
          name="productSearch"
          autocomplete="off"
          clearable
          :loading="loading"
          hide-details
          @keydown.enter.prevent="toResults"
          @keydown.down.prevent="toResults"
        />
      </div>
      <v-card-text class="pc-body">
        <p class="pc-state" aria-live="polite">
          <template v-if="tooShort">Type one more character to search.</template>
          <template v-else-if="failed">Couldn’t load products. <a href="#" @click.prevent="load">Try again</a></template>
          <template v-else-if="!loading && !items.length">{{ text ? `No product matches “${text}”.` : 'No products yet.' }}</template>
          <template v-else-if="!loading">{{ text ? `${items.length}${items.length === 30 ? '+' : ''} matching` : 'Active products' }}</template>
        </p>
        <v-list v-if="items.length" class="pc-results" :class="{ dim: loading }" density="comfortable" aria-label="Products">
          <v-list-item
            v-for="p in items"
            :key="p.id"
            :active="model?.id === p.id"
            color="primary"
            rounded="lg"
            @click="choose(p)"
          >
            <template #prepend>
              <div class="thumb"><ProductImage :image="primaryImage(p)" alt="" small sizes="48px" /></div>
            </template>
            <v-list-item-title class="name">{{ p.name }}</v-list-item-title>
            <v-list-item-subtitle class="mono">{{ makeModel(p) || p.id }}</v-list-item-subtitle>
            <template #append>
              <span v-if="!onShop(p)" class="tag">SIA only</span>
            </template>
          </v-list-item>
        </v-list>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="open = false">Cancel</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.pc {
  container-type: inline-size;
  min-width: 0;
}
.acts {
  flex: none;
  display: flex;
  align-items: center;
  gap: 4px;
}
/* Narrow (phones): name and model get the whole line; Change and remove go under them. */
@container (max-width: 400px) {
  .chosen {
    flex-wrap: wrap;
    row-gap: 8px;
    padding: 8px 8px 8px 13px;
    border-radius: 20px;
  }
  .ident {
    flex-basis: calc(100% - 53px);
  }
  .acts {
    flex-basis: 100%;
    justify-content: flex-end;
  }
}
.pick {
  width: 100%;
  justify-content: flex-start;
}
.chosen {
  display: flex;
  align-items: center;
  gap: 13px;
  min-height: 56px;
  padding: 4px 4px 4px 8px;
  border: 1px solid rgb(var(--v-theme-field-outline));
  border-radius: 28px;
  background: rgb(var(--v-theme-surface-variant));
}
.pc.error .chosen,
.pc.error .pick {
  box-shadow: 0 0 0 2px rgb(var(--v-theme-error));
}
.thumb {
  flex: none;
  width: 48px;
}
.thumb :deep(.frame) {
  width: 48px;
  border-radius: 8px;
  overflow: hidden;
}
.chosen .thumb :deep(.frame) {
  width: 40px;
  border-radius: 20px;
}
.chosen .thumb {
  width: 40px;
}
.ident {
  flex: 1;
  min-width: 0;
}
.ident p {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pc-cap {
  font-size: 12px;
  line-height: 16px;
  color: rgb(var(--v-theme-secondary));
}
.name {
  font-size: 14px;
  line-height: 20px;
  font-weight: 600;
}
.sub {
  font-size: 12px;
  line-height: 16px;
  color: rgb(var(--v-theme-secondary));
}
.mono {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}
.pc-card {
  min-height: min(560px, 100dvh);
}
.pc-search {
  flex: none;
  padding: 13px 21px 8px;
}
.pc-body {
  padding-top: 0 !important;
}
.pc-state {
  margin: 0 0 8px;
  min-height: 21px;
  font-size: 11px;
  line-height: 1.618;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dlg-muted);
}
.pc-results {
  padding: 0;
  background: transparent;
  transition: opacity 0.15s ease;
}
.pc-results.dim {
  opacity: 0.55;
}
.pc-results :deep(.v-list-item) {
  padding-block: 8px;
}
.pc-results :deep(.v-list-item__prepend) {
  margin-inline-end: 13px;
}
.pc-results :deep(.v-list-item__spacer) {
  display: none;
}
.tag {
  margin-inline-start: 13px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--dlg-muted);
  white-space: nowrap;
}
@media (max-width: 599.98px) {
  .pc-search {
    padding-inline: 13px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .pc-results {
    transition: none;
  }
}
</style>
