<script setup lang="ts">
/**
 * Scan input. Handheld scanners type the code and press Enter (keyboard wedge), so Enter = one scan:
 * the trimmed value is emitted, the field clears and keeps focus for the next scan.
 */
import { mdiBarcodeScan } from '@mdi/js'
import { nextTick, onMounted, ref } from 'vue'

const props = withDefaults(
  defineProps<{ label: string; hint?: string; loading?: boolean; autofocus?: boolean; keep?: boolean }>(),
  { hint: 'Scan the code, or type it and press Enter', loading: false, autofocus: false, keep: false },
)
const emit = defineEmits<{ scan: [code: string] }>()
const value = ref('')
const field = ref<{ focus: () => void } | null>(null)

function submit() {
  const code = value.value.trim()
  if (!code || props.loading) return
  emit('scan', code)
  if (!props.keep) value.value = ''
  void nextTick(() => field.value?.focus())
}

defineExpose({ focus: () => field.value?.focus(), clear: () => (value.value = '') })
onMounted(() => {
  if (props.autofocus) field.value?.focus()
})
</script>

<template>
  <form class="scan" @submit.prevent="submit">
    <v-text-field
      ref="field"
      v-model="value"
      :label="label"
      :hint="hint"
      persistent-hint
      :prepend-inner-icon="mdiBarcodeScan"
      :loading="loading"
      autocomplete="off"
      autocapitalize="off"
      spellcheck="false"
      @keydown.enter.prevent="submit"
    >
      <template #append-inner>
        <v-btn type="submit" variant="tonal" size="small" :disabled="!value.trim() || loading">Enter</v-btn>
      </template>
    </v-text-field>
  </form>
</template>

<style scoped>
/* Codes in the mono face (DESIGN_BRIEF), on the input only: on the whole field it shifts the label. */
.scan :deep(input) {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}
</style>
