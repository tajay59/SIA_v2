<script setup lang="ts">
/**
 * S-16 / A-21 login (APD §2): email + password, then a 6-digit code for admins with MFA.
 * Account-state errors route or explain: unverified → verify screen, awaiting approval → pending screen,
 * rejected/suspended/locked → message.
 */
import { computed, nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError, type Account } from '../api'
import { useNotify } from '../notify'
import { useSession } from '../session'
import { code as codeSchema, email as emailSchema, rule } from '../validation'
import { useInitialFocus } from '../focus'
import PasswordField from './PasswordField.vue'

const props = defineProps<{
  verifyPath: string
  forgotPath: string
  /** SHOP has an "awaiting approval" page; SIA shows the message inline. */
  pendingPath?: string
  initialEmail?: string
}>()
const emit = defineEmits<{ success: [account: Account] }>()

const session = useSession()
const notify = useNotify()
const router = useRouter()

const email = ref(props.initialEmail ?? '')
const password = ref('')
const totp = ref('')
const step = ref<'credentials' | 'mfa'>('credentials')
const busy = ref(false)
const formError = ref<string | null>(null)
const fieldErrors = ref<Record<string, string>>({})
const valid = ref(false)
const emailField = ref<{ focus: () => void } | null>(null)
const totpField = ref<{ focus: () => void } | null>(null)
useInitialFocus(emailField)

const MESSAGES: Record<string, string> = {
  ACCOUNT_PENDING_APPROVAL: 'Your email is verified. An administrator still has to approve your account; you will get an email.',
  ACCOUNT_REJECTED: 'This account request was not approved. Contact the CIMH stores team if you think this is a mistake.',
  ACCOUNT_SUSPENDED: 'This account is suspended. Contact the CIMH stores team.',
}

const title = computed(() => (step.value === 'mfa' ? 'Enter the code from your authenticator app' : null))

async function submit() {
  formError.value = null
  fieldErrors.value = {}
  busy.value = true
  try {
    const out = await session.login(email.value.trim(), password.value, step.value === 'mfa' ? totp.value : undefined)
    if (out.kind === 'ok') emit('success', out.account)
    else if (out.kind === 'mfa') {
      step.value = 'mfa'
      totp.value = ''
      void nextTick(() => totpField.value?.focus())
    } else if (out.code === 'ACCOUNT_PENDING_VERIFICATION') {
      await router.push({ path: props.verifyPath, query: { email: email.value.trim() } })
    } else if (out.code === 'ACCOUNT_PENDING_APPROVAL' && props.pendingPath) {
      await router.push(props.pendingPath)
    } else {
      formError.value = MESSAGES[out.code] ?? out.message
    }
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      if (step.value === 'mfa') fieldErrors.value = { totp: 'That code is not valid. Try the current one.' }
      else formError.value = 'Email or password is incorrect.'
    } else if (e instanceof ApiError && e.status === 422) {
      fieldErrors.value = e.fieldErrors()
      if (step.value === 'mfa' && !fieldErrors.value.totp) fieldErrors.value.totp = e.message
    } else {
      notify.report(e)
    }
  } finally {
    busy.value = false
  }
}

function back() {
  step.value = 'credentials'
  totp.value = ''
  fieldErrors.value = {}
}
</script>

<template>
  <v-form v-model="valid" class="stack" @submit.prevent="submit">
    <v-alert v-if="formError" type="error" variant="tonal" density="compact" role="alert">{{ formError }}</v-alert>

    <template v-if="step === 'credentials'">
      <v-text-field
        v-model="email"
        label="Email"
        type="email"
        ref="emailField"
        name="email"
        autocomplete="username"
        :rules="[rule(emailSchema)]"
        :error-messages="fieldErrors.email"
      />
      <PasswordField
        v-model="password"
        autocomplete="current-password"
        :rules="[(v: unknown) => !!v || 'Enter your password']"
        :error-messages="fieldErrors.password"
      />
      <div class="row">
        <router-link :to="{ path: forgotPath, query: email ? { email } : {} }" class="t-body">Forgot password?</router-link>
      </div>
    </template>

    <template v-else>
      <p class="t-body">{{ title }}</p>
      <v-otp-input
        ref="totpField"
        v-model="totp"
        length="6"
        type="number"
        :error="!!fieldErrors.totp"
        aria-label="6-digit code"
        @finish="submit"
      />
      <p v-if="fieldErrors.totp" class="t-caption" style="color: rgb(var(--v-theme-error))" role="alert">
        {{ fieldErrors.totp }}
      </p>
      <v-btn variant="text" class="align-self-start" @click="back">Use a different account</v-btn>
    </template>

    <v-btn
      type="submit"
      color="primary"
      size="large"
      block
      :loading="busy"
      :disabled="step === 'mfa' ? rule(codeSchema)(totp) !== true : !valid"
    >
      {{ step === 'mfa' ? 'Verify and log in' : 'Log in' }}
    </v-btn>
  </v-form>
</template>
