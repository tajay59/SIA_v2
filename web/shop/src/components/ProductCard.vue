<script setup lang="ts">
/**
 * Product card: a tall photo tile with a chip in the top-right corner (availability; v2 never shows prices)
 * and the Pro Bono badge, then the name, make/model and "N per pack" under the tile. Many products have no
 * photo: those get a shorter "nameplate" tile with the make, model and model number in readable text.
 */
import { makeModel, primaryImage, type Product, ProductImage } from '@cimh/web-app'
import { mdiCheckCircleOutline, mdiClockOutline, mdiGiftOutline } from '@mdi/js'

defineProps<{ product: Product }>()
</script>

<template>
  <router-link :to="`/catalogue/${product.id}`" class="card" :aria-label="product.name">
    <div class="tile" :class="{ plate: !primaryImage(product) }">
      <ProductImage v-if="primaryImage(product)" :image="primaryImage(product)" :alt="product.name" small sizes="(max-width: 600px) 50vw, 240px" class="photo" />
      <!-- No photo yet: the tile reads like the part's nameplate (make, model, model number), not an empty frame. -->
      <div v-else class="plate-text">
        <span v-if="product.make" class="plate-make">{{ product.make }}</span>
        <span class="plate-model">{{ product.modelname || product.modelnumber || product.name }}</span>
        <span v-if="product.modelname && product.modelnumber" class="plate-number t-mono">{{ product.modelnumber }}</span>
        <span class="plate-note">No photo yet</span>
      </div>
      <!-- One wrapping row: two absolutely placed badges collided on 2-column phone tiles. -->
      <div class="badges">
        <span v-if="product.probono" class="probono"><v-icon :icon="mdiGiftOutline" size="14" />Pro Bono</span>
        <span class="stock" :class="{ in: product.inStock }">
          <v-icon :icon="product.inStock ? mdiCheckCircleOutline : mdiClockOutline" size="14" />
          {{ product.inStock ? 'In stock' : 'On request' }}
        </span>
      </div>
    </div>
    <div class="info">
      <span v-if="primaryImage(product) || product.modelname || product.modelnumber" class="name">{{ product.name }}</span>
      <div class="meta">
        <span v-if="primaryImage(product)" class="t-caption muted model">{{ makeModel(product) }}</span>
        <span v-if="product.unitquantity && product.unitquantity > 1" class="pack">{{ product.unitquantity }} per pack</span>
      </div>
    </div>
  </router-link>
</template>

<style scoped>
.card {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  color: inherit;
  text-decoration: none;
  min-width: 0;
}
.tile {
  position: relative;
  aspect-ratio: 5 / 6;
  border-radius: 12px;
  overflow: hidden;
  background: rgb(var(--v-theme-photo-ground));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  transition:
    box-shadow 160ms ease-out,
    transform 160ms ease-out;
}
.tile :deep(.frame) {
  height: 100%;
  aspect-ratio: auto;
  border-radius: 0;
  padding: 12%;
}
.tile.plate {
  aspect-ratio: auto;
  background: rgb(var(--v-theme-surface-variant));
}
.plate-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 132px;
  padding: 44px var(--sp-3) var(--sp-3); /* clears the badge row */
  overflow-wrap: anywhere;
}
.plate-make {
  font-size: 12px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.plate-model {
  font-size: 17px;
  line-height: 1.25;
  font-weight: 600;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.plate-number {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.plate-note {
  margin-top: auto;
  padding-top: var(--sp-2);
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.card:hover .tile {
  box-shadow: 0 6px 18px rgba(15, 26, 36, 0.12);
  transform: translateY(-2px);
}
.card:focus-visible {
  outline: none;
}
.card:focus-visible .tile {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.badges {
  position: absolute;
  top: 8px;
  left: 8px;
  right: 8px;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 4px;
  pointer-events: none;
}
.stock,
.probono {
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 24px;
  padding: 0 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
}
.stock {
  margin-left: auto;
  background: rgba(15, 26, 36, 0.06);
  color: #3b4754;
}
.stock.in {
  background: #e7f4ec;
  color: #116329; /* 6.4:1 on the badge (#1a7f37 was 4.4:1, below AA for 12px text) */
}
/* On the tinted nameplate (dark in the dark theme) the neutral badge needs its own solid surface. */
.plate .stock:not(.in) {
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
}
.probono {
  background: rgb(var(--v-theme-accent-probono));
  color: var(--probono-ink);
}
.info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 2px;
}
.name {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card:hover .name {
  color: rgb(var(--v-theme-primary));
}
.meta {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  min-width: 0;
}
.model {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.pack {
  font-size: 12px;
  font-weight: 700;
  color: rgb(var(--v-theme-primary));
  white-space: nowrap;
}
@media (max-width: 599.98px) {
  .name {
    font-size: 14px;
  }
  .stock,
  .probono {
    top: 6px;
    height: 22px;
    font-size: 11px;
  }
  .stock {
    right: 6px;
  }
  .probono {
    left: 6px;
  }
}
</style>
