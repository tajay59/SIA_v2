<script setup lang="ts">
/** Confirm an action that needs a reason (cancel, decline, reject): 3–500 characters, as the API requires. */
import { computed, nextTick, ref, watch } from 'vue'

const open = defineModel<boolean>({ default: false })
/** `dismiss`: label of the button that closes without acting (default "Back"; e.g. "Keep request" next to "Cancel request"). */
const props = defineProps<{ title: string; text?: string; confirm: string; dismiss?: string; danger?: boolean; busy?: boolean }>()
const emit = defineEmits<{ submit: [reason: string] }>()
const reason = ref('')
/* Opened from a button by v-model (no activator), so Vuetify can't return focus: remember the opener, put the cursor in
   Reason on open, and give focus back to the opener on close (critique fix 5, 2026-11-19; focus fell to <body>). */
let opener: HTMLElement | null = null
const field = ref<{ focus: () => void } | null>(null)
watch(open, async (o) => {
  if (o) {
    reason.value = ''
    opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await nextTick()
    setTimeout(() => field.value?.focus(), 60)
  } else if (opener?.isConnected) {
    const el = opener
    opener = null
    setTimeout(() => el.focus(), 0)
  }
})
const valid = computed(() => reason.value.trim().length >= 3)
</script>

<template>
  <v-dialog v-model="open" max-width="520">
    <v-card :title="title">
      <v-card-text>
        <p v-if="text" class="t-body">{{ text }}</p>
        <v-textarea
          ref="field"
          v-model="reason"
          label="Reason"
          rows="3"
          auto-grow
          counter="500"
          maxlength="500"
          :hint="valid ? '' : 'At least 3 characters'"
          persistent-hint
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="open = false">{{ props.dismiss ?? 'Back' }}</v-btn>
        <v-btn :color="props.danger ? 'error' : 'primary'" variant="flat" :disabled="!valid" :loading="busy" @click="emit('submit', reason.trim())">
          {{ confirm }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
