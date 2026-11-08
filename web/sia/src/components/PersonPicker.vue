<script setup lang="ts">
/** Pick an active account by name or email (issuing a unit to a person). identity GET /admin/accounts?q=. */
import { type AccountSummary, call, identity } from '@cimh/web-app'
import { ref, watch } from 'vue'

const model = defineModel<AccountSummary | null>({ default: null })
withDefaults(defineProps<{ label?: string }>(), { label: 'Person' })
const items = ref<AccountSummary[]>([])
const search = ref('')
const loading = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

watch(search, (q) => {
  clearTimeout(timer)
  const text = (q ?? '').trim()
  if (text.length < 2 || (model.value && text === title(model.value))) return
  timer = setTimeout(async () => {
    loading.value = true
    try {
      const page = await call(() => identity.GET('/admin/accounts', { params: { query: { q: text, status: 'ACTIVE', limit: 20 } } }))
      items.value = page.items
    } catch {
      items.value = []
    } finally {
      loading.value = false
    }
  }, 250)
})

function title(a: AccountSummary): string {
  return `${a.firstname} ${a.lastname}`.trim()
}
</script>

<template>
  <v-autocomplete
    v-model="model"
    v-model:search="search"
    :items="items"
    :item-title="title"
    item-value="id"
    return-object
    :label="label"
    :loading="loading"
    no-filter
    hide-no-data
    hint="Type at least 2 letters of the name or email"
    persistent-hint
  >
    <template #item="{ props: p, item }">
      <v-list-item v-bind="p" :subtitle="item.email" />
    </template>
  </v-autocomplete>
</template>
