<script setup lang="ts">
import { mdiEye, mdiEyeOff } from '@mdi/js'
import { computed, ref } from 'vue'
import { passwordStrength, type Rule } from '../validation'

const model = defineModel<string>({ default: '' })
const props = defineProps<{
  label?: string
  autocomplete: 'current-password' | 'new-password'
  rules?: Rule[]
  errorMessages?: string | string[]
  strength?: boolean
  name?: string
}>()
const show = ref(false)
const meter = computed(() => passwordStrength(model.value))
const meterColor = computed(() => ['error', 'error', 'warning', 'success', 'success'][meter.value.score])
</script>

<template>
  <div>
    <v-text-field
      v-model="model"
      :label="label ?? 'Password'"
      :type="show ? 'text' : 'password'"
      :autocomplete="autocomplete"
      :name="name ?? 'password'"
      :rules="rules"
      :error-messages="errorMessages"
      :append-inner-icon="show ? mdiEyeOff : mdiEye"
      :hint="props.strength ? 'At least 12 characters. A short sentence works well.' : undefined"
      persistent-hint
      @click:append-inner="show = !show"
    />
    <div v-if="props.strength && model" class="meter" aria-live="polite">
      <v-progress-linear :model-value="meter.score * 25" :color="meterColor" height="4" rounded />
      <span class="t-caption muted">Strength: {{ meter.label }}</span>
    </div>
  </div>
</template>

<style scoped>
.meter {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
}
</style>
