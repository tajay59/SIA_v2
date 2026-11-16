<script setup lang="ts">
/**
 * The only date input in SHOP/SIA (owner, 2026-11-12): Vuetify `v-date-input` with its date picker.
 * Model is a local calendar date string `YYYY-MM-DD` ('' = none), so callers keep their string state.
 */
import { mdiCalendar } from '@mdi/js'
import { computed } from 'vue'

const model = defineModel<string>({ default: '' })
defineOptions({ inheritAttrs: false })

const pad = (n: number) => String(n).padStart(2, '0')
const toStr = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
const toDate = (s: string) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s)
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null
}

const value = computed<Date | null>({
  get: () => toDate(model.value),
  set: (d) => (model.value = d instanceof Date && !isNaN(d.getTime()) ? toStr(d) : ''),
})
</script>

<template>
  <!-- role="group": Vuetify puts the picker menu's aria-controls on the field's wrapper div, which axe refuses on a role-less div. -->
  <v-date-input
    v-model="value"
    v-bind="$attrs"
    role="group"
    prepend-icon=""
    :prepend-inner-icon="mdiCalendar"
    :rules="($attrs.rules as any[] | undefined)?.map((r) => () => r(model))"
  />
</template>
