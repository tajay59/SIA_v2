<script setup lang="ts">
/** A-06 new product -> A-07 Images tab (J-10). */
import { ApiError, call, catalog, type ProductInput, removeDraft, useNotify } from '@cimh/web-app'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import ProductForm from '../../components/ProductForm.vue'

definePage({ meta: { guard: 'staff', title: 'New product' } })
const router = useRouter()
const notify = useNotify()
const saving = ref(false)
const errors = ref<Record<string, string>>({})
const DRAFT = 'product:new'

async function save(body: Record<string, unknown>) {
  saving.value = true
  errors.value = {}
  try {
    const p = await call(() => catalog.POST('/products', { body: body as unknown as ProductInput }))
    removeDraft(DRAFT)
    notify.toast(`${p.name} created. Add photos next.`, 'success')
    await router.push({ path: `/products/${p.id}`, query: { tab: 'images' } })
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) errors.value = e.fieldErrors()
    if (e instanceof ApiError && e.code === 'PRODUCT_EXISTS') errors.value = { id: 'A product with this barcode already exists' }
    else notify.report(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="page">
    <v-breadcrumbs :items="[{ title: 'Products', to: '/products' }, { title: 'New product', disabled: true }]" class="pa-0 mb-4" />
    <ProductForm :saving="saving" :errors="errors" :draft-key="DRAFT" @save="save">
      <template #actions><v-btn variant="text" to="/products" @click="removeDraft(DRAFT)">Cancel</v-btn></template>
    </ProductForm>
  </div>
</template>
