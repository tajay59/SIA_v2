<script setup lang="ts">
/** S-17: always moves on to the reset screen, whether or not the address exists (no enumeration). */
import { ref } from 'vue'
import { ApiError, call, identity } from '../api'
import { useNotify } from '../notify'
import { email as emailSchema, rule } from '../validation'

const props = defineProps<{ initialEmail?: string }>()
const emit = defineEmits<{ sent: [email: string] }>()
const notify = useNotify()
const email = ref(props.initialEmail ?? '')
const valid = ref(false)
const busy = ref(false)

async function submit() {
  busy.value = true
  try {
    await call(() => identity.POST('/auth/password/forgot', { body: { email: email.value.trim() } }), { refresh: false })
    emit('sent', email.value.trim())
  } catch (e) {
    // Only rate limiting or an outage can stop this step; everything else looks like success.
    if (e instanceof ApiError && (e.status === 429 || e.isNetwork)) notify.report(e)
    else emit('sent', email.value.trim())
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <v-form v-model="valid" class="stack" @submit.prevent="submit">
    <v-text-field
      v-model="email"
      label="Email"
      type="email"
      autocomplete="email"
      autofocus
      :rules="[rule(emailSchema)]"
    />
    <v-btn type="submit" color="primary" size="large" block :loading="busy" :disabled="!valid">Send reset code</v-btn>
  </v-form>
</template>
