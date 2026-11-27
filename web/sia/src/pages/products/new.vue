<script setup lang="ts">
/** A-06 new product -> A-07 Images tab (J-10). */
import { ApiError, call, catalog, type ProductInput, removeDraft, useNotify } from '@cimh/web-app'
import { mdiArrowLeft } from '@mdi/js'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import PhotoStager, { type StagedPhoto } from '../../components/PhotoStager.vue'
import ProductForm from '../../components/ProductForm.vue'

definePage({ meta: { guard: 'staff', title: 'New product', ownHeading: true } })
const router = useRouter()
const notify = useNotify()
const saving = ref(false)
const errors = ref<Record<string, string>>({})
const DRAFT = 'product:new'
const photos = ref<StagedPhoto[]>([])
const removeBackground = ref(false)

/** Upload the chosen photos (primary first); returns how many are now processing. */
async function uploadPhotos(productId: string): Promise<number> {
  if (!photos.value.length) return 0
  const form = new FormData()
  for (const p of photos.value) form.append('files', p.file)
  form.append('removeBackground', String(removeBackground.value))
  try {
    const res = await call(() =>
      catalog.POST('/products/{productId}/images', {
        params: { path: { productId } },
        body: form as never,
        bodySerializer: (b: unknown) => b as FormData,
      }),
    )
    return res.jobIds.length
  } catch (e) {
    // The product exists either way: say so, and let staff retry from the Images tab.
    notify.toast('The product was created, but its photos could not be uploaded. Add them again on the Images tab.', 'warning')
    if (!(e instanceof ApiError && e.status === 413)) notify.report(e)
    return 0
  }
}

async function save(body: Record<string, unknown>) {
  saving.value = true
  errors.value = {}
  try {
    const p = await call(() => catalog.POST('/products', { body: body as unknown as ProductInput }))
    removeDraft(DRAFT)
    const processing = await uploadPhotos(p.id)
    notify.toast(processing ? `${p.name} created. ${processing} photo${processing === 1 ? ' is' : 's are'} processing.` : `${p.name} created. Add photos next.`, 'success')
    await router.push({ path: `/products/${p.id}`, query: { tab: 'images', ...(processing ? { processing: String(processing) } : {}) } })
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
  <div class="np">
    <header class="head">
      <div class="title-row">
        <h1 class="t-h1">New product</h1>
        <router-link to="/products" class="back t-label"><v-icon :icon="mdiArrowLeft" size="18" />Inventory</router-link>
      </div>
      <p class="t-body muted">Name, type, department, the Pro Bono choice and the alert level are required. Photos are optional; labels and stock come after the product exists.</p>
    </header>
    <ProductForm style="--form-ground: rgb(var(--v-theme-background))" :saving="saving" :errors="errors" :draft-key="DRAFT" with-photos @save="save">
      <template #photos><PhotoStager v-model="photos" v-model:remove-background="removeBackground" /></template>
      <template #actions><v-btn class="m3" variant="text" to="/products" @click="removeDraft(DRAFT)">Cancel</v-btn></template>
    </ProductForm>
  </div>
</template>

<style scoped>
.np {
  padding: var(--sp-4) var(--sp-6) var(--sp-12);
}
.back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: rgb(var(--v-theme-secondary));
  text-decoration: none;
}
.back:hover {
  color: rgb(var(--v-theme-primary));
}
.head {
  margin: 0 0 var(--sp-6) 224px;
}
.title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
}
.head p {
  margin: var(--sp-1) 0 0;
}
@media (max-width: 1099.98px) {
  .head {
    margin-left: 0;
  }
}
@media (max-width: 599.98px) {
  .np {
    padding: var(--sp-3) var(--sp-4) var(--sp-8);
  }
}
</style>
