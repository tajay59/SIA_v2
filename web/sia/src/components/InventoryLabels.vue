<script setup lang="ts">
/**
 * A-12 labels (legacy Inventory → "Product" panel; products themselves are created under Products).
 * Product, quantity, optional serials → unit records + QR labels to print, or the legacy CSV
 * (`barcode,CODE`). The server-made PDF arrives with document-svc (P6).
 */
import { ApiError, call, catalog, downloadText, inventory, labelsCsv, type ProductStaff, useNotify } from '@cimh/web-app'
import { mdiDownload } from '@mdi/js'
import { computed, onMounted, ref } from 'vue'
import LabelSheet from './LabelSheet.vue'
import ProductPicker from './ProductPicker.vue'

const props = defineProps<{ productId?: string }>()
const notify = useNotify()
const product = ref<ProductStaff | null>(null)
const quantity = ref(1)
const serialsText = ref('')
const busy = ref(false)
const errors = ref<Record<string, string>>({})
const made = ref<{ product: ProductStaff; barcodes: string[] } | null>(null)

const serials = computed(() =>
  serialsText.value
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean),
)
const serialProblem = computed(() =>
  serials.value.length && serials.value.length !== quantity.value
    ? `Give one serial per unit (${serials.value.length} for ${quantity.value}), or none`
    : '',
)

onMounted(async () => {
  if (!props.productId) return
  try {
    product.value = (await call(() =>
      catalog.GET('/products/{productId}', { params: { path: { productId: props.productId! } } }),
    )) as ProductStaff
  } catch (e) {
    notify.report(e)
  }
})

async function create() {
  const p = product.value
  if (!p || serialProblem.value) return
  busy.value = true
  errors.value = {}
  try {
    const body = { productId: p.id, quantity: quantity.value, ...(serials.value.length ? { serials: serials.value } : {}) }
    const res = await call(() => inventory.POST('/labels', { body }))
    made.value = { product: p, barcodes: res.barcodes }
    notify.toast(`${res.barcodes.length} unit${res.barcodes.length === 1 ? '' : 's'} created. Print the labels, then stow the units.`, 'success')
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) errors.value = e.fieldErrors()
    notify.report(e)
  } finally {
    busy.value = false
  }
}

function csv() {
  if (made.value) downloadText(labelsCsv(made.value.barcodes), `labels-${made.value.product.id}.csv`, 'text/csv')
}
</script>

<template>
  <div class="stack">
    <div class="steps">
      <div class="instructions">
        <h2 class="t-h3">1. Product and quantity</h2>
        <p class="t-body muted">Each physical unit gets its own label. Serials are optional: one per line, one per unit.</p>
      </div>
      <form class="stack-sm" @submit.prevent="create">
        <ProductPicker v-model="product" />
        <v-text-field
          v-model.number="quantity"
          type="number"
          label="Number of units"
          min="1"
          max="500"
          :error-messages="errors.quantity"
        />
        <v-textarea
          v-model="serialsText"
          label="Serials (optional)"
          rows="3"
          auto-grow
          :error-messages="serialProblem || errors.serials"
        />
        <div class="row-end">
          <v-btn type="submit" color="primary" :loading="busy" :disabled="!product || quantity < 1 || quantity > 500 || !!serialProblem">
            Create labels
          </v-btn>
        </div>
      </form>
    </div>

    <div v-if="made" class="steps">
      <div class="instructions">
        <h2 class="t-h3">2. Print</h2>
        <p class="t-body muted">{{ made.barcodes.length }} labels for {{ made.product.name }}. Stick one on each unit, then stow them.</p>
      </div>
      <LabelSheet
        :heading="`Labels for ${made.product.name}`"
        :items="made.barcodes.map((b) => ({ value: b, title: (b.split('_').pop() ?? b).toUpperCase(), subtitle: made!.product.name }))"
      >
        <template #actions>
          <v-btn :prepend-icon="mdiDownload" variant="outlined" @click="csv">Download CSV</v-btn>
          <v-btn variant="text" to="/stow">Go to Stow</v-btn>
        </template>
      </LabelSheet>
    </div>
  </div>
</template>

<style scoped>
.steps {
  display: grid;
  grid-template-columns: minmax(200px, 1fr) minmax(0, 2fr);
  gap: var(--sp-6);
  align-items: start;
}
@media (max-width: 959px) {
  .steps {
    grid-template-columns: minmax(0, 1fr);
  }
}
.instructions {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
</style>
