<script setup lang="ts">
/** A-13 stock levels: products at or below their low-stock alert first; any product's stock via Lookup. */
import { call, inventory, type ProductStaff, type ProductStock, useCursorList } from '@cimh/web-app'
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import ProductPicker from '../../components/ProductPicker.vue'

definePage({ meta: { guard: 'staff', title: 'Stock levels' } })
const router = useRouter()
const low = useCursorList<ProductStock>((cursor) => call(() => inventory.GET('/stock/low', { params: { query: { cursor, limit: 50 } } })))
onMounted(low.reload)

const picked = ref<ProductStaff | null>(null)
watch(picked, (p) => p && router.push({ path: '/inventory', query: { op: 'lookup', code: p.id } }))
</script>

<template>
  <div class="page stack">
    <div class="finder"><ProductPicker v-model="picked" label="Stock of any product" /></div>

    <section class="stack-sm">
      <h2 class="t-h3">Low stock</h2>
      <p class="t-body muted">Products whose available units are at or below their alert level. Staff on the low-stock email list are told when a product drops this far.</p>
      <v-skeleton-loader v-if="!low.loaded.value && low.loading.value" type="table-row@4" />
      <p v-else-if="low.loaded.value && !low.items.value.length" class="t-body">Nothing is low on stock.</p>
      <v-table v-else density="comfortable">
        <thead>
          <tr>
            <th>Product</th>
            <th class="text-right">Available</th>
            <th class="text-right">Alert at</th>
            <th class="text-right">Reserved</th>
            <th class="text-right">Issued</th>
            <th class="text-right">Picked</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in low.items.value" :key="s.productId">
            <td><router-link :to="`/products/${s.productId}?tab=stock`">{{ s.productName ?? s.productId }}</router-link></td>
            <td class="text-right tnum"><strong :class="{ out: s.available === 0 }">{{ s.available }}</strong></td>
            <td class="text-right tnum">{{ s.threshold }}</td>
            <td class="text-right tnum">{{ s.reserved }}</td>
            <td class="text-right tnum">{{ s.assigned ?? 0 }}</td>
            <td class="text-right tnum">{{ s.picked }}</td>
          </tr>
        </tbody>
      </v-table>
      <v-btn v-if="low.nextCursor.value" variant="text" :loading="low.loading.value" @click="low.loadMore">Load more</v-btn>
    </section>
  </div>
</template>

<style scoped>
.page {
  max-width: 1100px;
  margin: 0 auto;
  width: 100%;
}
.finder {
  max-width: 480px;
}
.out {
  color: rgb(var(--v-theme-error));
}
</style>
