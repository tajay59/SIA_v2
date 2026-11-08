<script setup lang="ts">
/** Result area shared by catalogue, Pro Bono and search: count, skeletons, grid, empty state, "Load more". */
import type { Product, useCursorList } from '@cimh/web-app'
import ProductCard from './ProductCard.vue'

defineProps<{ list: ReturnType<typeof useCursorList<Product>>; emptyTitle: string; emptyText?: string }>()
const emit = defineEmits<{ clear: [] }>()
</script>

<template>
  <section class="results" aria-live="polite" :aria-busy="list.loading.value">
    <div class="row bar">
      <span class="t-body muted">
        <template v-if="list.loaded.value">{{ list.items.value.length }}{{ list.nextCursor.value ? '+' : '' }} items</template>
      </span>
      <span class="spacer" />
      <slot name="toolbar" />
    </div>
    <div v-if="!list.loaded.value && list.loading.value" class="grid">
      <v-skeleton-loader v-for="i in 8" :key="i" type="image, list-item-two-line" />
    </div>
    <div v-else-if="list.items.value.length" class="grid">
      <ProductCard v-for="p in list.items.value" :key="p.id" :product="p" />
    </div>
    <div v-else-if="list.loaded.value" class="empty stack-sm">
      <h2 class="t-h3">{{ emptyTitle }}</h2>
      <p class="t-body muted">{{ emptyText ?? 'Try another type or department, or clear the filters.' }}</p>
      <div><v-btn variant="outlined" @click="emit('clear')">Clear filters</v-btn></div>
    </div>
    <div v-if="list.nextCursor.value" class="row more">
      <v-btn variant="outlined" :loading="list.loading.value" @click="list.loadMore">Load more</v-btn>
    </div>
  </section>
</template>

<style scoped>
.bar {
  margin-bottom: var(--sp-3);
  min-height: 40px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--sp-8) var(--sp-5, 20px);
}
/* Phones: two columns, as the legacy grid wrapped. */
@media (max-width: 599.98px) {
  .grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--sp-6) var(--sp-3);
  }
}
.empty {
  padding: var(--sp-8) 0;
}
.more {
  justify-content: center;
  margin-top: var(--sp-6);
}
</style>
