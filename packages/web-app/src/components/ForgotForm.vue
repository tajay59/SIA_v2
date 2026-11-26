<script setup lang="ts">
/**
 * S-17: always moves on to the reset screen, whether or not the address exists (no enumeration).
 * Only two answers stop here: a rate limit (said on the form, in minutes) and an outage (the shared banner,
 * whose Try again sends the request again).
 */
import { ref } from 'vue'
import { ApiError, call, identity } from '../api'
import { tryAgainIn, useNotify } from '../notify'
import { useInitialFocus } from '../focus'
import { checkForm, type FormLike } from '../form'
import { email as emailSchema, rule } from '../validation'

const props = defineProps<{ initialEmail?: string }>()
const emit = defineEmits<{ sent: [email: string] }>()
const notify = useNotify()
const email = ref(props.initialEmail ?? '')
const formRef = ref<FormLike | null>(null)
const busy = ref(false)
const formError = ref<string | null>(null)
const field = ref<{ focus: () => void } | null>(null)
useInitialFocus(field)

async function submit() {
  if (busy.value) return
  formError.value = null
  if (!(await checkForm(formRef.value))) return
  busy.value = true
  try {
    await call(() => identity.POST('/auth/password/forgot', { body: { email: email.value.trim() } }), { refresh: false })
    emit('sent', email.value.trim())
  } catch (e) {
    // Only rate limiting or an outage can stop this step; everything else looks like success.
    if (e instanceof ApiError && e.status === 429) formError.value = `Too many attempts. ${tryAgainIn(e.retryAfter)}`
    else if (e instanceof ApiError && e.isNetwork) notify.report(e, { retry: () => void submit(), detail: 'No code was sent.' })
    else emit('sent', email.value.trim())
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <v-form ref="formRef" class="stack" @submit.prevent="submit">
    <v-alert v-if="formError" type="error" variant="tonal" density="compact" role="alert">{{ formError }}</v-alert>
    <v-text-field
      v-model="email"
      label="Email"
      type="email"
      ref="field"
      name="email"
      autocomplete="username"
      :rules="[rule(emailSchema)]"
    />
    <v-btn type="submit" color="primary" size="large" class="m3" block :loading="busy">Send reset code</v-btn>
  </v-form>
</template>
