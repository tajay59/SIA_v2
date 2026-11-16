<script setup lang="ts">
/** Result area shared by catalogue, Pro Bono and search: count, skeletons, same-height grid, empty state, "Load more". */
import type { Product, useCursorList } from '@cimh/web-app'
import { ref } from 'vue'
import ProductCard from './ProductCard.vue'

const props = withDefaults(
  defineProps<{ list: ReturnType<typeof useCursorList<Product>>; emptyTitle: string; emptyText?: string; clearLabel?: string; highlight?: string }>(),
  { highlight: '' },
)
const emit = defineEmits<{ clear: [] }>()
// Load more appends below (no dimming); any other load replaces the results, so the old ones dim meanwhile.
const appending = ref(false)
async function more() {
  appending.value = true
  try {
    await props.list.loadMore()
  } finally {
    appending.value = false
  }
}
</script>

<template>
  <section class="grid-area" aria-live="polite" :aria-busy="list.loading.value">
    <div class="bar">
      <span class="count">
        <template v-if="list.loaded.value">{{ list.items.value.length }}{{ list.nextCursor.value ? '+' : '' }} items</template>
      </span>
      <slot name="toolbar" />
    </div>
    <div v-if="!list.loaded.value && list.loading.value" class="grid">
      <v-skeleton-loader v-for="i in 10" :key="i" type="image, list-item-two-line" />
    </div>
    <ul v-else-if="list.items.value.length" class="grid" :class="{ refreshing: list.loading.value && !appending }">
      <li v-for="(p, i) in list.items.value" :key="p.id" :style="{ '--i': Math.min(i % 24, 8) }"><ProductCard :product="p" :highlight="highlight" /></li>
    </ul>
    <div v-else-if="list.loaded.value" class="empty stack-sm">
      <h2 class="t-h3">{{ emptyTitle }}</h2>
      <p class="t-body muted">{{ emptyText ?? 'Try another family or department, or clear the filters.' }}</p>
      <div><v-btn variant="outlined" @click="emit('clear')">{{ clearLabel ?? 'Clear filters' }}</v-btn></div>
    </div>
    <div v-if="list.nextCursor.value" class="more">
      <v-btn variant="outlined" :loading="list.loading.value" @click="more">Load more</v-btn>
    </div>
  </section>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  min-height: 40px;
  margin-bottom: var(--sp-3);
}
.count {
  font-size: 14px;
  font-variant-numeric: tabular-nums;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(208px, 1fr));
  gap: var(--sp-6) var(--sp-4);
}
.grid > li {
  display: flex;
  min-width: 0;
}
@media (max-width: 599.98px) {
  .grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--sp-4) var(--sp-3);
  }
}
.empty {
  padding: var(--sp-8) 0;
}
.more {
  display: flex;
  justify-content: center;
  margin-top: var(--sp-8);
}
</style>
<style scoped>
/* Motion: results that are being replaced dim (the request is in flight); new cards rise in, staggered by their
   place in the batch (capped at 8 × 40 ms); Load more animates only the cards it adds. */
.grid {
  transition: opacity 150ms ease-out;
}
.grid.refreshing {
  opacity: 0.45;
}
.grid > li {
  animation: card-in 360ms cubic-bezier(0.16, 1, 0.3, 1) backwards;
  animation-delay: calc(var(--i, 0) * 40ms);
}
@keyframes card-in {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
}
@media (prefers-reduced-motion: reduce) {
  .grid > li {
    animation-name: card-fade;
    animation-delay: 0ms;
  }
}
@keyframes card-fade {
  from {
    opacity: 0;
  }
}
</style>
