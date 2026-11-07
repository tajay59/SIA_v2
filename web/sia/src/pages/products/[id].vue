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
  type ProductPatch,
  type ProductStaff,
  ProductBadges,
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

definePage({ meta: { guard: 'staff', title: 'Product' } })
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
    product.value = (await call(() =>
      catalog.PATCH('/products/{productId}', {
        params: { path: { productId: p.id }, header: { 'If-Match': ifMatch(p.version) } },
        body: body as ProductPatch,
      }),
    )) as ProductStaff
    notify.toast('Product saved', 'success')
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) errors.value = e.fieldErrors()
    notify.report(e, { retry: load })
  } finally {
    saving.value = false
  }
}

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
      <div class="page-header">
        <div class="stack-sm">
          <h1 class="t-h2">{{ product.name }}</h1>
          <div class="row t-body muted">
            <span class="t-mono">{{ product.id }}</span>
            <span>{{ typeLabel(reference, product.type) }}</span>
            <ProductBadges :product="product" show-limit />
            <v-chip v-if="!product.active" size="small" label color="error" variant="tonal">Inactive</v-chip>
            <v-chip v-else-if="!product.sellable" size="small" label>Hidden from customers</v-chip>
          </div>
        </div>
        <span class="spacer" />
        <v-btn v-if="product.active" variant="outlined" color="error" @click="deactivateOpen = true">Deactivate</v-btn>
      </div>

      <v-tabs v-model="tab" color="primary">
        <v-tab value="details">Details</v-tab>
        <v-tab value="images">Images ({{ product.images.length }})</v-tab>
        <v-tab value="stock">Stock</v-tab>
        <v-tab v-if="session.isAdmin" value="history">History</v-tab>
      </v-tabs>

      <v-window v-model="tab">
        <v-window-item value="details">
          <ProductForm :product="product" :saving="saving" :errors="errors" class="pt-4" @save="save" />
        </v-window-item>
        <v-window-item value="images">
          <div class="pt-4"><ProductImagesPanel :product="product" @updated="(p) => (product = p)" /></div>
        </v-window-item>
        <v-window-item value="stock">
          <div class="pt-4 stack-sm">
            <p class="t-body">
              Available units: <strong class="tnum">{{ product.stockCount ?? 'not counted yet' }}</strong>
              · low-stock alert at <span class="tnum">{{ product.threshold }}</span>
            </p>
            <p class="t-body muted">Stock by site, location and shelf, and label printing, come with the inventory service.</p>
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
