<script setup lang="ts">
/** Status chip (DESIGN_BRIEF status mapping): colour + icon + text, never colour alone. */
import { mdiAlertCircleOutline, mdiCheckCircleOutline, mdiCircleOutline, mdiCloseCircleOutline, mdiClockOutline } from '@mdi/js'
import { statusLabel, statusTone, TONE_COLOR } from '@cimh/web-ui'
import { computed } from 'vue'

const props = defineProps<{ status: string }>()
const tone = computed(() => statusTone(props.status))
const ICONS = {
  neutral: mdiCircleOutline,
  info: mdiClockOutline,
  warning: mdiAlertCircleOutline,
  success: mdiCheckCircleOutline,
  error: mdiCloseCircleOutline,
} as const
</script>

<template>
  <v-chip :color="TONE_COLOR[tone]" variant="tonal" :prepend-icon="ICONS[tone]" label>
    {{ statusLabel(status) }}
  </v-chip>
</template>
