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
      :hint="props.strength ? 'At least 12 characters. A short sentence works well.' : undefined"
      persistent-hint
    >
      <!-- A real button (Vuetify's append-inner-icon is an <i> named "Password appended action", with no state).
           One fixed name + aria-pressed; mousedown.prevent keeps the caret in the field. -->
      <template #append-inner>
        <button
          type="button"
          class="pw-toggle"
          aria-label="Show password"
          :aria-pressed="show"
          :title="show ? 'Hide password' : 'Show password'"
          @mousedown.prevent
          @click="show = !show"
        >
          <v-icon :icon="show ? mdiEyeOff : mdiEye" />
        </button>
      </template>
    </v-text-field>
    <div v-if="props.strength && model" class="meter" aria-live="polite">
      <!-- The words beside it say the same; a nameless progressbar is an axe "serious" finding. -->
      <v-progress-linear :model-value="meter.score * 25" :color="meterColor" height="4" rounded aria-hidden="true" />
      <span class="t-caption muted">Strength: {{ meter.label }}</span>
    </div>
  </div>
</template>

<style scoped>
.pw-toggle {
  display: inline-grid;
  place-items: center;
  width: 40px;
  height: 40px;
  margin-inline-end: -8px;
  border: 0;
  border-radius: 999px;
  background: none;
  color: inherit;
  opacity: var(--v-medium-emphasis-opacity);
  cursor: pointer;
  transition: opacity 120ms ease, background-color 120ms ease;
}
.pw-toggle:hover,
.pw-toggle[aria-pressed='true'] {
  opacity: 1;
}
.pw-toggle:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}
.pw-toggle:focus-visible {
  opacity: 1;
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.meter {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
}
</style>
