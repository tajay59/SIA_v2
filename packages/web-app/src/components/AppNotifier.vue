<script setup lang="ts">
/** Toast stack + "service unavailable" banner (APD §2). Mount once, inside v-app. */
import { mdiAlertCircleOutline, mdiCheckCircleOutline, mdiClose, mdiInformationOutline } from '@mdi/js'
import { storeToRefs } from 'pinia'
import { useNotify } from '../notify'

const notify = useNotify()
const { toasts, unavailable } = storeToRefs(notify)
const icon = { success: mdiCheckCircleOutline, info: mdiInformationOutline, warning: mdiAlertCircleOutline, error: mdiAlertCircleOutline }

function retry() {
  const r = unavailable.value?.retry
  unavailable.value = null
  r?.()
}
</script>

<template>
  <v-alert
    v-if="unavailable"
    type="warning"
    variant="tonal"
    rounded="0"
    class="unavailable"
    role="alert"
    density="compact"
  >
    <div class="row">
      <span>The service is unavailable right now. Nothing was saved.</span>
      <span class="spacer" />
      <v-btn variant="outlined" size="small" @click="retry">Try again</v-btn>
      <v-btn variant="text" size="small" :icon="mdiClose" aria-label="Dismiss" @click="unavailable = null" />
    </div>
  </v-alert>

  <div class="toasts" aria-live="polite">
    <v-snackbar
      v-for="t in toasts"
      :key="t.id"
      :model-value="true"
      :timeout="t.timeout"
      :color="t.tone"
      location="bottom"
      @update:model-value="(v: boolean) => !v && notify.dismiss(t.id)"
    >
      <div class="row">
        <v-icon :icon="icon[t.tone]" size="20" />
        <span>{{ t.text }}</span>
      </div>
      <template #actions>
        <v-btn v-if="t.action" variant="text" @click="t.action.run(); notify.dismiss(t.id)">{{ t.action.label }}</v-btn>
        <v-btn variant="text" :icon="mdiClose" aria-label="Dismiss" @click="notify.dismiss(t.id)" />
      </template>
    </v-snackbar>
  </div>
</template>

<style scoped>
.unavailable {
  position: sticky;
  top: 0;
  z-index: 1010;
}
</style>
