<script setup lang="ts">
/**
 * Availability chip ("In stock" success / "On request" neutral) and the Pro Bono badge (yellow with ink text
 * only, DESIGN_BRIEF §3). Never a price.
 */
import { mdiCheckCircleOutline, mdiClockOutline, mdiGiftOutline } from '@mdi/js'
import type { Product } from '../catalog'

defineProps<{ product: Product; showLimit?: boolean }>()
</script>

<template>
  <div class="badges">
    <v-chip
      size="small"
      label
      variant="tonal"
      :color="product.inStock ? 'success' : undefined"
      :prepend-icon="product.inStock ? mdiCheckCircleOutline : mdiClockOutline"
    >
      {{ product.inStock ? 'In stock' : 'On request' }}
    </v-chip>
    <span v-if="product.probono" class="probono">
      <v-icon :icon="mdiGiftOutline" size="14" />
      Pro Bono<template v-if="showLimit && product.probonoMaxPerRequest"> · max {{ product.probonoMaxPerRequest }} per request</template>
    </span>
  </div>
</template>

<style scoped>
.badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.probono {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 24px;
  padding: 0 8px;
  border-radius: 4px;
  background: #f5c400;
  color: #0f1a24; /* ink on yellow only (contrast-checked in the Design Brief) */
  font-size: 12px;
  font-weight: 600;
}
</style>
