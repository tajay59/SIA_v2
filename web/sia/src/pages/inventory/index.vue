<script setup lang="ts">
/**
 * Inventory (legacy SIA /inventory): one row of operation buttons, the chosen panel below.
 *   Labels   (A-12; legacy "Product": products themselves are created under Products)
 *   Location (A-08: register sites, locations, shelves; tree with shelf QR codes)
 *   Lookup   (A-11: shelf, unit or product)
 * The choice and its inputs live in the URL: ?op=labels&product=…, ?op=lookup&code=….
 */
import { mdiMagnify, mdiMapMarkerOutline, mdiQrcode } from '@mdi/js'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import InventoryLabels from '../../components/InventoryLabels.vue'
import InventoryLookup from '../../components/InventoryLookup.vue'
import InventoryPlaces from '../../components/InventoryPlaces.vue'

definePage({ meta: { guard: 'staff', title: 'Inventory' } })
const route = useRoute()
const router = useRouter()

const OPS = [
  { key: 'labels', title: 'Labels', icon: mdiQrcode, text: 'Create unit labels for a product' },
  { key: 'location', title: 'Location', icon: mdiMapMarkerOutline, text: 'Sites, locations and shelves' },
  { key: 'lookup', title: 'Lookup', icon: mdiMagnify, text: 'What is on a shelf, where a unit or product is' },
] as const
type Op = (typeof OPS)[number]['key']

const op = computed<Op | null>(() => {
  const v = route.query.op
  return OPS.some((o) => o.key === v) ? (v as Op) : null
})
const str = (v: unknown) => (typeof v === 'string' && v ? v : undefined)
const code = computed({
  get: () => str(route.query.code) ?? null,
  set: (c: string | null) => void router.replace({ query: { op: 'lookup', ...(c ? { code: c } : {}) } }),
})

function choose(key: Op) {
  void router.replace({ query: op.value === key ? {} : { op: key } })
}
</script>

<template>
  <div class="page stack">
    <div class="ops" role="group" aria-label="Inventory operations">
      <button
        v-for="o in OPS"
        :key="o.key"
        type="button"
        class="op"
        :class="{ on: op === o.key, dim: op && op !== o.key }"
        :aria-pressed="op === o.key"
        @click="choose(o.key)"
      >
        <v-icon :icon="o.icon" size="28" />
        <span class="t-h3">{{ o.title }}</span>
        <span class="t-caption muted">{{ o.text }}</span>
      </button>
    </div>

    <InventoryLabels v-if="op === 'labels'" :key="str(route.query.product)" :product-id="str(route.query.product)" />
    <InventoryPlaces v-else-if="op === 'location'" @shelf="(b) => (code = b)" />
    <InventoryLookup v-else-if="op === 'lookup'" v-model:code="code" />
    <p v-else class="t-body muted">Choose an operation.</p>
  </div>
</template>

<style scoped>
.page {
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
}
.ops {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--sp-4);
}
.op {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--sp-1);
  padding: var(--sp-4);
  border-radius: 12px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgb(var(--v-theme-surface));
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, opacity 0.15s;
}
.op:hover,
.op:focus-visible {
  border-color: rgb(var(--v-theme-primary));
}
.op.on {
  border: 2px solid rgb(var(--v-theme-primary));
  padding: calc(var(--sp-4) - 1px);
}
.op.on .v-icon {
  color: rgb(var(--v-theme-primary));
}
/* Dim the other operations by their icon only: fading the text broke AA contrast. */
.op.dim .v-icon {
  opacity: 0.6;
}
</style>
