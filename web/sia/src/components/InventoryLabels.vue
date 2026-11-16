<script setup lang="ts">
/**
 * A-12 labels, the record beside the Places tree on /inventory (`?op=labels[&product=]`).
 * Product, quantity, optional serials → unit records + QR labels to print, or the legacy CSV
 * (`barcode,CODE`), or the PDF document-svc makes (`fileId`; null when that failed: labels still work,
 * print them from this page instead).
 */
import { ApiError, call, catalog, downloadText, fileUrl, inventory, labelsCsv, type ProductStaff, useNotify } from '@cimh/web-app'
import { mdiArrowRight, mdiDownload, mdiFilePdfBox } from '@mdi/js'
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
const made = ref<{ product: ProductStaff; barcodes: string[]; fileId: string | null } | null>(null)

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
    made.value = { product: p, barcodes: res.barcodes, fileId: res.fileId ?? null }
    notify.toast(`${res.barcodes.length} unit${res.barcodes.length === 1 ? '' : 's'} created. Print the labels, then stow the units.`, 'success')
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) errors.value = e.fieldErrors()
    notify.report(e)
  } finally {
    busy.value = false
  }
}

function again() {
  made.value = null
  quantity.value = 1
  serialsText.value = ''
}
function csv() {
  if (made.value) downloadText(labelsCsv(made.value.barcodes), `labels-${made.value.product.id}.csv`, 'text/csv')
}
</script>

<template>
  <div class="labels">
    <header class="pad">
      <h2 class="t-h3">Create unit labels</h2>
      <p class="t-body muted">Each physical unit gets its own record and QR label. Serials are optional: one per line, one per unit.</p>
    </header>

    <form v-if="!made" class="pad form" @submit.prevent="create">
      <ProductPicker v-model="product" />
      <div class="pair">
        <v-text-field v-model.number="quantity" type="number" label="Number of units" min="1" max="500" :error-messages="errors.quantity" />
        <v-textarea
          v-model="serialsText"
          label="Serials (optional)"
          rows="1"
          auto-grow
          :error-messages="serialProblem || errors.serials"
        />
      </div>
      <div class="actions">
        <v-btn class="m3" type="submit" color="primary" :loading="busy" :disabled="!product || quantity < 1 || quantity > 500 || !!serialProblem">
          Create labels
        </v-btn>
      </div>
    </form>

    <template v-else>
      <div class="console-head sub">
        <h3 class="console-title">Print and stow</h3>
        <span class="console-mono t-caption muted">{{ made.barcodes.length }} units</span>
      </div>
      <div class="pad done">
        <p class="t-body">
          {{ made.barcodes.length }} labels for <router-link :to="`/products/${made.product.id}`">{{ made.product.name }}</router-link>. Stick one on
          each unit, then stow them.
        </p>
        <p v-if="!made.fileId" class="t-caption muted">The PDF could not be made this time. Print from this page or use the CSV.</p>
        <LabelSheet
          :heading="`Labels for ${made.product.name}`"
          :items="made.barcodes.map((b) => ({ value: b, title: (b.split('_').pop() ?? b).toUpperCase(), subtitle: made!.product.name }))"
        >
          <template #actions>
            <v-btn
              v-if="made.fileId"
              class="m3"
              :href="fileUrl(made.fileId)"
              target="_blank"
              rel="noopener"
              :prepend-icon="mdiFilePdfBox"
              color="primary"
              variant="flat"
            >
              Download PDF
            </v-btn>
            <v-btn class="m3" :prepend-icon="mdiDownload" variant="outlined" @click="csv">Download CSV</v-btn>
            <v-btn class="m3" variant="text" :append-icon="mdiArrowRight" :to="{ path: '/pick', query: { op: 'stow' } }">Go to Stow</v-btn>
            <v-btn class="m3" variant="text" @click="again">More labels</v-btn>
          </template>
        </LabelSheet>
      </div>
    </template>
  </div>
</template>

<style scoped>
.labels {
  animation: console-swap-in 220ms var(--ease-out);
}
.pad {
  padding: var(--sp-4);
}
header.pad {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}
.form {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  max-width: 640px;
  padding-top: 0;
}
.pair {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: var(--sp-3);
}
.actions {
  display: flex;
  justify-content: flex-end;
}
.sub {
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.done {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
@media (max-width: 599px) {
  .pair {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
