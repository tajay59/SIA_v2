<script setup lang="ts">
/** Product card (DESIGN_BRIEF §9): 4:3 photo on white, name (2 lines), make · model, availability, Pro Bono. No price. */
import { makeModel, primaryImage, type Product, ProductBadges, ProductImage } from '@cimh/web-app'

defineProps<{ product: Product }>()
</script>

<template>
  <router-link :to="`/catalogue/${product.id}`" class="card">
    <ProductImage :image="primaryImage(product)" :alt="product.name" small />
    <div class="body">
      <h3 class="name">{{ product.name }}</h3>
      <p v-if="makeModel(product)" class="t-caption muted meta">{{ makeModel(product) }}</p>
      <ProductBadges :product="product" />
    </div>
  </router-link>
</template>

<style scoped>
.card {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding: var(--sp-3);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
  color: inherit;
  text-decoration: none;
  transition: box-shadow 160ms ease-out;
}
.card:hover {
  box-shadow: 0 1px 3px rgba(15, 26, 36, 0.12);
}
.card:hover :deep(img) {
  transform: scale(1.02);
}
@media (max-width: 599.98px) {
  .card {
    padding: var(--sp-2);
    gap: var(--sp-2);
  }
  .name {
    font-size: 14px;
  }
}
.card:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.body {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.name {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.35;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.meta {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
