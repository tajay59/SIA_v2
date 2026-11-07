<script setup lang="ts">
/** S-18: code + new password. Success revokes every session (J-11) and returns to login. */
import { ref } from 'vue'
import { ApiError, call, identity } from '../api'
import { useNotify } from '../notify'
import { code as codeSchema, email as emailSchema, password as passwordSchema, rule } from '../validation'
import PasswordField from './PasswordField.vue'

const props = defineProps<{ email?: string }>()
const emit = defineEmits<{ done: [email: string] }>()
const notify = useNotify()

const email = ref(props.email ?? '')
const code = ref('')
const newPassword = ref('')
const confirm = ref('')
const valid = ref(false)
const busy = ref(false)
const fieldErrors = ref<Record<string, string>>({})
const error = ref<string | null>(null)

async function submit() {
  busy.value = true
  error.value = null
  fieldErrors.value = {}
  try {
    await call(
      () =>
        identity.POST('/auth/password/reset', {
          body: { email: email.value.trim(), code: code.value, newPassword: newPassword.value },
        }),
      { refresh: false },
    )
    emit('done', email.value.trim())
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) {
      fieldErrors.value = e.fieldErrors()
      if (e.code === 'PASSWORD_BREACHED')
        fieldErrors.value.newPassword = 'This password appears in known data breaches. Choose another one.'
      else if (e.code === 'CODE_INVALID' || e.code === 'CODE_EXPIRED')
        error.value = e.code === 'CODE_EXPIRED' ? 'The code has expired. Request a new one.' : 'The code is not right.'
      else if (!Object.keys(fieldErrors.value).length) error.value = e.message
    } else notify.report(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <v-form v-model="valid" class="stack" @submit.prevent="submit">
    <v-alert v-if="error" type="error" variant="tonal" density="compact" role="alert">{{ error }}</v-alert>
    <v-text-field
      v-if="!props.email"
      v-model="email"
      label="Email"
      type="email"
      autocomplete="username"
      :rules="[rule(emailSchema)]"
    />
    <p v-else class="t-body">
      If <strong>{{ props.email }}</strong> has an account, we sent it a 6-digit code.
    </p>
    <v-text-field
      v-model="code"
      label="6-digit code"
      inputmode="numeric"
      autocomplete="one-time-code"
      maxlength="6"
      class="t-mono"
      :rules="[rule(codeSchema)]"
      :error-messages="fieldErrors.code"
    />
    <PasswordField
      v-model="newPassword"
      label="New password"
      name="new-password"
      autocomplete="new-password"
      strength
      :rules="[rule(passwordSchema)]"
      :error-messages="fieldErrors.newPassword"
    />
    <PasswordField
      v-model="confirm"
      label="Repeat new password"
      name="confirm-password"
      autocomplete="new-password"
      :rules="[(v: unknown) => v === newPassword || 'The passwords do not match']"
    />
    <v-btn type="submit" color="primary" size="large" block :loading="busy" :disabled="!valid">Change password</v-btn>
  </v-form>
</template>
