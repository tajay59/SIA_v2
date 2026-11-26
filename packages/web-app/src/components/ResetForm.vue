<script setup lang="ts">
/**
 * S-18: code + new password. Success revokes every session (J-11) and returns to login.
 * The code uses the same six boxes as S-14 and the MFA step; it does not submit when the sixth digit
 * lands, because the password fields come after it.
 * Audit 2026-11-26: every answer about the code is said under the boxes (marked, emptied, cursor back in the first
 * box); a refused password keeps the code (identity checks the password first); an outage banner's Try again sends
 * again; an address from the link that the server refuses brings the Email field back.
 */
import { nextTick, ref, useId, watch } from 'vue'
import { ApiError, call, identity } from '../api'
import { useNotify } from '../notify'
import { useInitialFocus } from '../focus'
import { checkForm, type FormLike } from '../form'
import { code as codeSchema, email as emailSchema, password as passwordSchema, rule } from '../validation'
import PasswordField from './PasswordField.vue'

const props = defineProps<{ email?: string }>()
const emit = defineEmits<{ done: [email: string] }>()
const notify = useNotify()

/** What each refusal of the code means for the person, and whether they need a new one. */
const CODE_ANSWERS: Record<string, { text: string; newCode: boolean }> = {
  CODE_INVALID: { text: 'That code is not right. Check the email and try again.', newCode: false },
  CODE_EXPIRED: { text: 'This code has expired.', newCode: true },
  CODE_ATTEMPTS_EXCEEDED: { text: 'Too many wrong codes. This one no longer works.', newCode: true },
}

const email = ref(props.email ?? '')
/** The address comes from the link (S-17 → S-18); the field shows only without one, or when the server refuses it. */
const emailShown = ref(!props.email)
const code = ref('')
const newPassword = ref('')
const confirm = ref('')
const formRef = ref<FormLike | null>(null)
const busy = ref(false)
const fieldErrors = ref<Record<string, string>>({})
const needsNewCode = ref(false)
const error = ref<string | null>(null)
const codeField = ref<{ focus: () => void } | null>(null)
const emailField = ref<{ focus: () => void } | null>(null)
const codeMessageId = useId()
useInitialFocus(props.email ? codeField : emailField)

// A server message belongs to what was sent: it goes once that field changes.
watch(code, () => {
  if (fieldErrors.value.code && code.value) {
    delete fieldErrors.value.code
    needsNewCode.value = false
  }
})
watch(newPassword, () => delete fieldErrors.value.newPassword)
watch(email, () => delete fieldErrors.value.email)

function focusByName(name: string) {
  void nextTick(() => document.querySelector<HTMLInputElement>(`input[name="${name}"]`)?.focus())
}

function refuseCode(text: string, newCode = false) {
  fieldErrors.value = { ...fieldErrors.value, code: text }
  needsNewCode.value = newCode
  code.value = ''
  void nextTick(() => codeField.value?.focus())
}

async function submit() {
  if (busy.value) return
  error.value = null
  fieldErrors.value = {}
  needsNewCode.value = false
  // Never a disabled button: the code and every field are checked and marked on a press.
  const codeOk = rule(codeSchema)(code.value) === true
  const fieldsOk = await checkForm(formRef.value)
  if (!codeOk) {
    fieldErrors.value = { code: 'Enter the 6-digit code from the email.' }
    codeField.value?.focus()
  }
  if (!codeOk || !fieldsOk) return
  busy.value = true
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
      const answer = CODE_ANSWERS[e.code ?? '']
      if (answer) return refuseCode(answer.text, answer.newCode)
      if (e.code === 'PASSWORD_BREACHED') {
        fieldErrors.value = { newPassword: 'This password appears in known data breaches. Choose another one.' }
        return focusByName('new-password')
      }
      // Field names as identity reports them; the password check calls it `password`.
      const fe = e.fieldErrors()
      const known: Record<string, string> = {}
      const passwordMessage = fe.newPassword ?? fe.password
      if (fe.code) known.code = fe.code
      if (passwordMessage) known.newPassword = passwordMessage
      if (fe.email) known.email = 'Enter a valid email address'
      fieldErrors.value = known
      if (known.email) {
        emailShown.value = true // the address came from the link: show it so it can be put right
        return focusByName('email')
      }
      if (known.code) return refuseCode(known.code)
      if (known.newPassword) return focusByName('new-password')
      error.value = e.message // nothing on screen to mark: say it on the form
    } else if (e instanceof ApiError && e.isNetwork) {
      notify.report(e, { retry: () => void submit(), detail: 'Your password was not changed.' })
    } else notify.report(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <v-form ref="formRef" class="stack" @submit.prevent="submit">
    <v-alert v-if="error" type="error" variant="tonal" density="compact" role="alert">{{ error }}</v-alert>
    <template v-if="emailShown">
      <p class="t-body">Enter your email and the 6-digit code we sent to it. Codes are valid for 15 minutes.</p>
      <v-text-field
        ref="emailField"
        v-model="email"
        label="Email"
        type="email"
        name="email"
        autocomplete="username"
        :rules="[rule(emailSchema)]"
        :error-messages="fieldErrors.email"
      />
    </template>
    <template v-else>
      <p class="t-body">
        If <strong>{{ props.email }}</strong> has an account, we sent it a 6-digit code. It is valid for 15 minutes.
      </p>
      <!-- Password managers save the new password against this account (the address is not typed on this page). -->
      <input type="email" name="email" autocomplete="username" :value="email" hidden readonly />
    </template>
    <div class="stack-sm">
      <span class="t-label" aria-hidden="true">6-digit code</span>
      <v-otp-input
        ref="codeField"
        v-model="code"
        length="6"
        type="number"
        autocomplete="one-time-code"
        :error="!!fieldErrors.code"
        aria-label="6-digit code"
        :aria-describedby="fieldErrors.code ? codeMessageId : undefined"
      />
      <p v-if="fieldErrors.code" :id="codeMessageId" class="t-caption code-message" role="alert">
        {{ fieldErrors.code }}
        <router-link
          v-if="needsNewCode"
          :to="{ path: '/forgot-password', query: email.trim() ? { email: email.trim() } : {} }"
        >
          Send a new code
        </router-link>
      </p>
    </div>
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
    <v-btn type="submit" color="primary" size="large" class="m3" block :loading="busy">
      Change password
    </v-btn>
  </v-form>
</template>

<style scoped>
.code-message {
  color: rgb(var(--v-theme-error));
  margin: 0;
}
.code-message a {
  color: inherit;
  font-weight: 600;
  margin-inline-start: 4px;
}
</style>
