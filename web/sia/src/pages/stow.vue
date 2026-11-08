<script setup lang="ts">
/**
 * A-09 stow (legacy SIA /stow: numbered steps, instructions on the left, the action on the right).
 *   1. Select shelf: scan its QR code (validated).
 *   2. Scan units: each scan stows one unit on that shelf; the list shows ✓ / ✗ with the reason.
 * Legacy step "product lookup" is gone: every v2 label already names its product.
 */
import { newScanKey, scan, scanError, type Shelf, unitWhere, ApiError, call, inventory } from '@cimh/web-app'
import { mdiArchiveOutline, mdiChevronRight, mdiMapMarkerOutline } from '@mdi/js'
import { ref } from 'vue'
import ScanField from '../components/ScanField.vue'
import ScanLog, { type ScanEntry } from '../components/ScanLog.vue'

definePage({ meta: { guard: 'staff', title: 'Stow' } })

const shelf = ref<Shelf | null>(null)
const shelfError = ref('')
const checking = ref(false)
const entries = ref<ScanEntry[]>([])
let seq = 0

async function chooseShelf(code: string) {
  checking.value = true
  shelfError.value = ''
  try {
    shelf.value = await call(() => inventory.GET('/shelves/{barcode}', { params: { path: { barcode: code } } }))
  } catch (e) {
    shelfError.value = e instanceof ApiError && e.status === 404 ? 'No shelf with this code. Scan the QR code on the shelf.' : scanError(e)
  } finally {
    checking.value = false
  }
}

function stow(code: string, key = newScanKey(), id = ++seq) {
  const s = shelf.value
  if (!s) return
  const entry: ScanEntry = { id, code, ok: null, text: 'Stowing…' }
  entries.value = [entry, ...entries.value.filter((e) => e.id !== id)]
  scan('/stow', { unit: code, shelf: s.barcode }, key)
    .then((u) => update(id, { ok: true, text: `${u.productName ?? u.product} · ${unitWhere(u)}` }))
    // The same key on retry: if the first attempt did reach the server, it is not applied twice.
    .catch((e) => update(id, { ok: false, text: scanError(e), retry: () => stow(code, key, id) }))
}
function update(id: number, patch: Partial<ScanEntry>) {
  entries.value = entries.value.map((e) => (e.id === id ? { ...e, ...patch, retry: patch.retry } : e))
}
const stowed = () => entries.value.filter((e) => e.ok).length
</script>

<template>
  <div class="page stack">
    <section class="step">
      <div class="instructions">
        <h2 class="t-h3">1. Select shelf</h2>
        <p class="t-body muted">Go to the shelf you are stowing to and scan its QR code.</p>
      </div>
      <div class="stack-sm">
        <ScanField v-if="!shelf" label="Shelf" :loading="checking" autofocus @scan="chooseShelf" />
        <v-alert v-if="shelfError" type="error" variant="tonal" density="compact">{{ shelfError }}</v-alert>
        <div v-if="shelf" class="chosen" role="status">
          <span class="t-caption muted">You have selected</span>
          <div class="where">
            <span class="place"><v-icon :icon="mdiMapMarkerOutline" />{{ shelf.locationName ?? shelf.location }}</span>
            <v-icon :icon="mdiChevronRight" />
            <span class="place"><v-icon :icon="mdiArchiveOutline" />Shelf {{ shelf.number }}</span>
          </div>
          <span class="t-caption muted">{{ shelf.siteName }}</span>
          <v-btn class="mt-2" size="small" variant="outlined" @click="(shelf = null), (entries = [])">Change shelf</v-btn>
        </div>
      </div>
    </section>

    <section v-if="shelf" class="step">
      <div class="instructions">
        <h2 class="t-h3">2. Scan units</h2>
        <p class="t-body muted">Scan the label on each unit as you place it. Keep scanning; each scan is saved on its own.</p>
        <p class="t-body"><strong class="tnum">{{ stowed() }}</strong> stowed on this shelf</p>
      </div>
      <div class="stack">
        <ScanField label="Unit" autofocus @scan="(c) => stow(c)" />
        <ScanLog :entries="entries" empty="Scan the first unit." />
      </div>
    </section>
  </div>
</template>

<style scoped>
.page {
  max-width: 1100px;
  margin: 0 auto;
  width: 100%;
}
.step {
  display: grid;
  grid-template-columns: minmax(200px, 1fr) minmax(0, 2fr);
  gap: var(--sp-6);
  align-items: start;
  padding-bottom: var(--sp-6);
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
@media (max-width: 959px) {
  .step {
    grid-template-columns: minmax(0, 1fr);
  }
}
.instructions {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.chosen {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--sp-1);
  padding: var(--sp-4);
  border-radius: 12px;
  border: 1px solid rgb(var(--v-theme-primary));
}
.where {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: 18px;
  font-weight: 600;
}
.place {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-1);
}
</style>
