<script setup lang="ts">
/**
 * Scan input. Handheld scanners type the code and press Enter (keyboard wedge), so Enter = one scan:
 * the trimmed value is emitted, the field clears and keeps focus for the next scan.
 */
import { markRaw, nextTick, onMounted, ref } from 'vue'
import QrScan from '../icons/QrScan.vue'

const scanIcon = markRaw(QrScan)

const props = withDefaults(
  defineProps<{
    label: string
    hint?: string
    placeholder?: string
    loading?: boolean
    autofocus?: boolean
    keep?: boolean
    prominent?: boolean
    /** The label names the input for assistive tech only; the placeholder carries the visible words. */
    hideLabel?: boolean
  }>(),
  { hint: 'Scan the code, or type it and press Enter', placeholder: undefined, loading: false, autofocus: false, keep: false, prominent: false, hideLabel: false },
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
  <form class="scan" :class="{ prominent }" @submit.prevent="submit">
    <v-text-field
      ref="field"
      v-model="value"
      :label="hideLabel ? undefined : label"
      :aria-label="hideLabel ? label : undefined"
      :hint="hint"
      :placeholder="placeholder"
      :persistent-placeholder="!!placeholder"
      :color="prominent ? 'primary' : undefined"

      :persistent-hint="!!hint"
      :prepend-inner-icon="scanIcon"
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
/* The placeholder is words, not a code: the interface face. */
.scan :deep(input::placeholder) {
  font-family: 'Inter Variable', Inter, system-ui, sans-serif;
}
</style>
<style scoped>
/* The page's main target: a 2 px primary ring in place of the 1 px resting edge every field has (base.css). */
.scan.prominent :deep(.v-field) {
  box-shadow: 0 0 0 2px rgb(var(--v-theme-primary));
}
.scan.prominent :deep(.v-field)::after {
  content: none;
}
.scan.prominent :deep(input) {
  font-size: 1.0625rem;
  min-height: 60px;
}
</style>
