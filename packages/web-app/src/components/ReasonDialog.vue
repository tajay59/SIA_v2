<script setup lang="ts">
/** Confirm an action that needs a reason (cancel, decline, reject): 3–500 characters, as the API requires. */
import { computed, ref, watch } from 'vue'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ title: string; text?: string; confirm: string; danger?: boolean; busy?: boolean }>()
const emit = defineEmits<{ submit: [reason: string] }>()
const reason = ref('')
watch(open, (o) => o && (reason.value = ''))
const valid = computed(() => reason.value.trim().length >= 3)
</script>

<template>
  <v-dialog v-model="open" max-width="520">
    <v-card :title="title">
      <v-card-text>
        <p v-if="text" class="t-body">{{ text }}</p>
        <v-textarea
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
        <v-btn variant="text" @click="open = false">Back</v-btn>
        <v-btn :color="props.danger ? 'error' : 'primary'" variant="flat" :disabled="!valid" :loading="busy" @click="emit('submit', reason.trim())">
          {{ confirm }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
