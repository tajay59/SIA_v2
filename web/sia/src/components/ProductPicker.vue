<script setup lang="ts">
/** Find a product by name, model, keyword or serial (catalog search, staff view). */
import { call, catalog, type ProductStaff } from '@cimh/web-app'
import { ref, watch } from 'vue'

const model = defineModel<ProductStaff | null>({ default: null })
withDefaults(defineProps<{ label?: string }>(), { label: 'Product' })
const items = ref<ProductStaff[]>(model.value ? [model.value] : [])
const search = ref('')
const loading = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

watch(model, (p) => {
  if (p && !items.value.some((i) => i.id === p.id)) items.value = [p, ...items.value]
})
watch(search, (q) => {
  clearTimeout(timer)
  const text = (q ?? '').trim()
  if (text.length < 2 || text === model.value?.name) return
  timer = setTimeout(async () => {
    loading.value = true
    try {
      const page = await call(() => catalog.GET('/products/search', { params: { query: { q: text, limit: 20 } } }))
      items.value = page.items as ProductStaff[]
    } catch {
      items.value = []
    } finally {
      loading.value = false
    }
  }, 250)
})
</script>

<template>
  <v-autocomplete
    v-model="model"
    v-model:search="search"
    :items="items"
    item-title="name"
    item-value="id"
    return-object
    :label="label"
    :loading="loading"
    no-filter
    hide-no-data
    hint="Name, model number, keyword or serial"
    persistent-hint
  >
    <template #item="{ props: p, item }">
      <v-list-item v-bind="p" :subtitle="[item.make, item.modelnumber].filter(Boolean).join(' · ') || item.id" />
    </template>
  </v-autocomplete>
</template>
