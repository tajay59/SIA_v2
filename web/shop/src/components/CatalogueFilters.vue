<script setup lang="ts">
/** Filter panel for S-02 / S-04 / S-06: search box, type, department, project, in stock. */
import { PRODUCT_TYPES, type Reference, typeLabel } from '@cimh/web-app'
import { mdiMagnify } from '@mdi/js'
import { computed, ref } from 'vue'

const props = defineProps<{
  reference: Reference | null
  type: string | null
  department: string | null
  project?: string | null
  inStock?: boolean
  query?: string
  showProject?: boolean
  showStock?: boolean
}>()
const emit = defineEmits<{ set: [key: string, value: string | boolean | null]; search: [q: string]; clear: [] }>()

const q = ref(props.query ?? '')
const types = computed(() => PRODUCT_TYPES.map((k) => ({ value: k, title: typeLabel(props.reference, k) })))
const projects = computed(() => (props.reference?.projects ?? []).map((p) => ({ value: p.code, title: p.name })))
const active = computed(() => !!(props.type || props.department || props.project || props.inStock))
</script>

<template>
  <div class="filters">
    <form role="search" @submit.prevent="emit('search', q.trim())">
      <v-text-field v-model="q" label="Search the catalogue" :prepend-inner-icon="mdiMagnify" hide-details density="comfortable" />
    </form>
    <fieldset class="stack-sm">
      <legend class="t-label">Type</legend>
      <v-chip-group :model-value="type" column selected-class="text-primary" @update:model-value="(v: string | null) => emit('set', 'type', v ?? null)">
        <v-chip v-for="t in types" :key="t.value" :value="t.value" filter size="small" variant="outlined">{{ t.title }}</v-chip>
      </v-chip-group>
    </fieldset>
    <v-select
      :model-value="department"
      :items="reference?.departments ?? []"
      label="Department"
      clearable
      hide-details
      density="comfortable"
      @update:model-value="(v: string | null) => emit('set', 'department', v)"
    />
    <v-select
      v-if="showProject"
      :model-value="project"
      :items="projects"
      label="Project"
      clearable
      hide-details
      density="comfortable"
      @update:model-value="(v: string | null) => emit('set', 'project', v)"
    />
    <v-switch
      v-if="showStock"
      :model-value="inStock"
      label="In stock only"
      color="primary"
      hide-details
      inset
      @update:model-value="(v: boolean | null) => emit('set', 'inStock', !!v)"
    />
    <div v-if="active"><v-btn variant="text" @click="emit('clear')">Clear filters</v-btn></div>
  </div>
</template>

<style scoped>
.filters {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
fieldset {
  border: 0;
  padding: 0;
  margin: 0;
}
</style>
