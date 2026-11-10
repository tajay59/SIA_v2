<script setup lang="ts">
/**
 * A-07 product: tabs Details (edit, If-Match), Images, Stock, History (admins: audit entries).
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
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ProductForm from '../../components/ProductForm.vue'
import ProductImagesPanel from '../../components/ProductImagesPanel.vue'

definePage({ meta: { guard: 'staff', title: 'Product', ownHeading: true } })
const route = useRoute('/products/[id]')
const router = useRouter()
const session = useSession()
const notify = useNotify()
const { reference } = useReference()

const product = ref<ProductStaff | null>(null)
const missing = ref(false)
const saving = ref(false)
const errors = ref<Record<string, string>>({})
const tab = computed({
  get: () => (typeof route.query.tab === 'string' ? route.query.tab : 'details'),
  set: (t: string) => void router.replace({ query: { ...route.query, tab: t } }),
})

async function load() {
  try {
    product.value = (await call(() =>
      catalog.GET('/products/{productId}', { params: { path: { productId: route.params.id } } }),
    )) as ProductStaff
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) missing.value = true
    else notify.report(e, { retry: load })
  }
}
watch(() => route.params.id, load, { immediate: true })

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

// Serials and make/model on one line (legacy description card), skipping what is missing.
const identLine = computed(() => {
  const p = product.value
  if (!p) return ''
  const serials = [p.sn, p.sn1].filter(Boolean).join(', ')
  const model = [p.make, p.modelname, p.modelnumber].filter(Boolean).join(' ')
  return [serials, model].filter(Boolean).join(' · ')
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

// Stock (A-07 Stock tab): counts and units per shelf, from inventory-svc.
const stock = ref<ProductStock | null>(null)
watch(
  () => [tab.value, product.value?.id],
  async () => {
    if (tab.value !== 'stock' || !product.value) return
    try {
      stock.value = await call(() => inventory.GET('/products/{productId}/stock', { params: { path: { productId: product.value!.id } } }))
    } catch (e) {
      notify.report(e)
    }
  },
  { immediate: true },
)

// History (admins): audit entries recorded for this product (cost changes, deactivation…).
const history = ref<AuditEntry[] | null>(null)
watch(
  () => [tab.value, product.value?.id],
  async () => {
    if (tab.value !== 'history' || !product.value || !session.isAdmin) return
    try {
      const page = await call(() =>
        identity.GET('/audit', { params: { query: { entityType: 'product', entityId: product.value!.id, limit: 100 } } }),
      )
      history.value = page.items
    } catch (e) {
      notify.report(e)
    }
  },
  { immediate: true },
)
</script>

<template>
  <div class="page">
    <div v-if="missing" class="stack">
      <h1 class="t-h2">Product not found</h1>
      <div><v-btn to="/products" variant="outlined">Back to products</v-btn></div>
    </div>
    <v-skeleton-loader v-else-if="!product" type="article, table" />
    <div v-else class="stack">
      <v-breadcrumbs :items="[{ title: 'Products', to: '/products' }, { title: product.name, disabled: true }]" class="pa-0" />
      <!-- Same structure as the legacy SIA product page: photos and description left, info card right. -->
      <div class="overview">
        <section class="ov-left">
          <div class="stack-sm">
            <h1 class="t-h2">{{ product.name }}</h1>
            <div class="row t-body muted">
              <span>{{ typeLabel(reference, product.type) }}</span>
              <ProductBadges :product="product" show-limit />
              <v-chip v-if="!product.active" size="small" label color="error" variant="tonal">Inactive</v-chip>
              <v-chip v-else-if="!product.sellable" size="small" label>Hidden from customers</v-chip>
            </div>
          </div>
          <div class="ov-photos">
            <ProductImage :image="shownImage" :alt="product.name" sizes="(max-width: 960px) 100vw, 640px" />
            <div v-if="product.images.length > 1" class="ov-thumbs" role="group" aria-label="Photos">
              <button
                v-for="(img, i) in product.images"
                :key="img.fileId"
                type="button"
                class="ov-thumb"
                :class="{ on: shownImage?.fileId === img.fileId }"
                :aria-label="`Photo ${i + 1} of ${product.images.length}`"
                :aria-pressed="shownImage?.fileId === img.fileId"
                @click="shown = img.fileId"
              >
                <ProductImage :image="img" alt="" small sizes="72px" />
              </button>
            </div>
          </div>
          <div class="ov-section">
            <h2 class="cap">Description</h2>
            <v-card class="pa-5 stack-sm">
              <p v-if="identLine" class="t-caption muted t-mono">{{ identLine }}</p>
              <p class="t-body">{{ product.description || 'No description yet.' }}</p>
              <p v-if="product.details" class="t-body muted details">{{ product.details }}</p>
            </v-card>
          </div>
        </section>
        <aside class="ov-right">
          <h2 class="cap">Info</h2>
          <v-card class="pa-5">
            <dl class="facts">
              <dt>In stock</dt><dd class="tnum"><strong>{{ product.stockCount ?? 'not counted yet' }}</strong></dd>
              <dt>Low-stock alert at</dt><dd class="tnum">{{ product.threshold }}</dd>
              <dt>Cost</dt><dd class="tnum">{{ product.cost ? `${product.cost} BBD` : '—' }}</dd>
              <dt>Units per pack</dt><dd class="tnum">{{ product.unitquantity ?? 1 }}</dd>
              <dt>Department</dt><dd>{{ product.department }}</dd>
              <dt>Shown to customers</dt><dd>{{ product.active && product.sellable ? 'Yes' : 'No' }}</dd>
              <dt>Id</dt><dd class="t-mono">{{ product.id }}</dd>
            </dl>
            <v-btn class="mt-4" block variant="tonal" :to="{ path: '/inventory', query: { op: 'labels', product: product.id } }">Create labels</v-btn>
            <v-btn v-if="product.active" class="mt-4" block variant="outlined" color="error" @click="deactivateOpen = true">Deactivate</v-btn>
          </v-card>
        </aside>
      </div>

      <v-tabs v-model="tab" color="primary">
        <v-tab value="details">Details</v-tab>
        <v-tab value="images">Images ({{ product.images.length }})</v-tab>
        <v-tab value="stock">Stock</v-tab>
        <v-tab v-if="session.isAdmin" value="history">History</v-tab>
      </v-tabs>

      <v-window v-model="tab">
        <v-window-item value="details">
          <ProductForm :product="product" :saving="saving" :errors="errors" :draft-key="`product:${product.id}:v${product.version}`" class="pt-4" @save="save" />
        </v-window-item>
        <v-window-item value="images">
          <div class="pt-4"><ProductImagesPanel :product="product" @updated="(p) => (product = p)" /></div>
        </v-window-item>
        <v-window-item value="stock">
          <div class="pt-4 stack-sm">
            <v-skeleton-loader v-if="!stock" type="table-row@3" />
            <template v-else>
              <p class="t-body tnum">
                <strong>{{ stock.available }}</strong> available · {{ stock.reserved }} reserved · {{ stock.assigned ?? 0 }} issued ·
                {{ stock.picked }} picked
              </p>
              <p v-if="!stock.byLocation.length" class="t-body muted">Nothing of this product is on a shelf.</p>
              <v-table v-else density="compact">
                <thead><tr><th>Site</th><th>Location</th><th>Shelf</th><th class="text-right">Units</th></tr></thead>
                <tbody>
                  <tr v-for="b in stock.byLocation" :key="b.shelf">
                    <td>{{ b.siteName ?? b.site }}</td>
                    <td>{{ b.locationName ?? b.location }}</td>
                    <td><router-link :to="{ path: '/inventory', query: { op: 'lookup', code: b.shelf } }">Shelf {{ b.shelfNumber ?? '?' }}</router-link></td>
                    <td class="text-right tnum">{{ b.count }}</td>
                  </tr>
                </tbody>
              </v-table>
            </template>
          </div>
        </v-window-item>
        <v-window-item v-if="session.isAdmin" value="history">
          <div class="pt-4">
            <v-skeleton-loader v-if="history === null" type="list-item-two-line@3" />
            <p v-else-if="!history.length" class="t-body muted">No recorded changes yet. Cost changes and deactivation are recorded here.</p>
            <v-list v-else lines="two" density="compact">
              <v-list-item v-for="h in history" :key="h.id" :title="h.action.replace('product.', '').replace('_', ' ')">
                <template #subtitle>
                  <span class="tnum">{{ formatDateTime(h.at) }}</span> · {{ h.actor.name }}
                  <template v-if="h.from !== undefined || h.to !== undefined"> · {{ h.from ?? '—' }} → {{ h.to ?? '—' }}</template>
                </template>
              </v-list-item>
            </v-list>
          </div>
        </v-window-item>
      </v-window>
    </div>

    <v-dialog v-model="deactivateOpen" max-width="480">
      <v-card>
        <v-card-title class="t-h3">Deactivate this product?</v-card-title>
        <v-card-text>
          <p class="t-body">Customers will no longer see it. Existing requests keep their copy of the product, and staff can still find it with “Include inactive”.</p>
        </v-card-text>
        <v-card-actions class="row-end">
          <v-btn variant="text" @click="deactivateOpen = false">Cancel</v-btn>
          <v-btn color="error" :loading="saving" @click="deactivate">Deactivate</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.overview {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr);
  gap: var(--sp-6);
  align-items: start;
}
@media (max-width: 959px) {
  .overview {
    grid-template-columns: minmax(0, 1fr);
  }
}
.ov-left {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.ov-photos {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  max-width: 640px;
}
.ov-thumbs {
  display: flex;
  gap: var(--sp-2);
  flex-wrap: wrap;
}
.ov-thumb {
  width: 72px;
  padding: 2px;
  border: 2px solid transparent;
  border-radius: 8px;
  background: none;
  cursor: pointer;
}
.ov-thumb.on {
  border-color: rgb(var(--v-theme-primary));
}
.cap {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  opacity: 0.72;
  margin: 0 0 var(--sp-2);
}
.ov-right {
  position: sticky;
  top: 80px;
}
@media (max-width: 959px) {
  .ov-right {
    position: static; /* one column: no sticky card under scrolling content */
  }
}
.details {
  white-space: pre-line;
}
.facts {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: var(--sp-2) var(--sp-4);
  margin: 0;
  font-size: 14px;
}
.facts dt {
  opacity: 0.72;
}
.facts dd {
  margin: 0;
  word-break: break-word;
}
</style>
