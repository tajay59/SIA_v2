<script setup lang="ts">
/** Search organisations as you type (GET /organisations?q=); emits the chosen organisation. */
import { call, identity, type Organisation, useNotify } from '@cimh/web-app'
import { computed, ref, watch } from 'vue'

const model = defineModel<Organisation | null>({ default: null })
/** `busy`: the caller is looking something up for this field (DecisionDialog's suggestion): show the progress bar. */
const props = defineProps<{ label?: string; initialQuery?: string; excludeId?: string; rules?: ((v: unknown) => true | string)[]; busy?: boolean }>()
const notify = useNotify()
const search = ref(props.initialQuery ?? '')
const items = ref<Organisation[]>([])
const loading = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
// The chosen organisation is always an option: a suggestion set from outside (DecisionDialog) is not in the last
// search's results, so the open menu said "No organisation found" under the chosen name.
const options = computed(() =>
  model.value && !items.value.some((o) => o.id === model.value!.id) ? [model.value, ...items.value] : items.value,
)

async function run(q: string) {
  loading.value = true
  try {
    const res = await call(() => identity.GET('/organisations', { params: { query: { q: q || undefined, limit: 20 } } }))
    items.value = res.items.filter((o) => o.id !== props.excludeId && !o.mergedInto)
  } catch (e) {
    notify.report(e)
  } finally {
    loading.value = false
  }
}

watch(
  search,
  (q) => {
    clearTimeout(timer)
    if (model.value && q === model.value.name) return
    timer = setTimeout(() => void run(q?.trim() ?? ''), 250)
  },
  { immediate: true },
)
</script>

<template>
  <v-autocomplete
    v-model="model"
    v-model:search="search"
    :items="options"
    item-title="name"
    item-value="id"
    return-object
    no-filter
    clearable
    :loading="loading || busy"
    :label="label ?? 'Organisation'"
    :rules="rules"
    no-data-text="No organisation found"
  >
    <template #item="{ props: itemProps, item }">
      <v-list-item v-bind="itemProps" :subtitle="[item.country, (item.emailDomains ?? []).join(', ')].filter(Boolean).join(' · ')" />
    </template>
  </v-autocomplete>
</template>
