<script setup lang="ts">
/**
 * Product card, same structure as the legacy InventoryCard: a tall photo tile with a chip in the top-right
 * corner (availability here; v2 never shows prices) and the Pro Bono badge, then the name, make/model and
 * "N per pack" under the tile.
 */
import { makeModel, primaryImage, type Product, ProductImage } from '@cimh/web-app'
import { mdiCheckCircleOutline, mdiClockOutline, mdiGiftOutline } from '@mdi/js'

defineProps<{ product: Product }>()
</script>

<template>
  <router-link :to="`/catalogue/${product.id}`" class="card" :aria-label="product.name">
    <div class="tile">
      <ProductImage :image="primaryImage(product)" :alt="product.name" small sizes="(max-width: 600px) 50vw, 240px" class="photo" />
      <span v-if="product.probono" class="probono"><v-icon :icon="mdiGiftOutline" size="14" />Pro Bono</span>
      <span class="stock" :class="{ in: product.inStock }">
        <v-icon :icon="product.inStock ? mdiCheckCircleOutline : mdiClockOutline" size="14" />
        {{ product.inStock ? 'In stock' : 'On request' }}
      </span>
    </div>
    <div class="info">
      <span class="name">{{ product.name }}</span>
      <div class="meta">
        <span class="t-caption muted model">{{ makeModel(product) }}</span>
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
  background: #fff;
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
.stock,
.probono {
  position: absolute;
  top: 10px;
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
  right: 10px;
  background: rgba(15, 26, 36, 0.06);
  color: #3b4754;
}
.stock.in {
  background: #e7f4ec;
  color: #1a7f37;
}
.probono {
  left: 10px;
  background: #f5c400;
  color: #0f1a24;
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
