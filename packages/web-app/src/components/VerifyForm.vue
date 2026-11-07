<script setup lang="ts">
/**
 * S-14 verify email: 6-digit code + resend with a cool-down (max 3 per hour on the server).
 * Also used for the email-change confirmation (same endpoint, the new address).
 */
import { onBeforeUnmount, ref } from 'vue'
import { ApiError, type AccountStatus, call, identity } from '../api'
import { useNotify } from '../notify'
import { useInitialFocus } from '../focus'
import { code as codeSchema, email as emailSchema, rule } from '../validation'

const props = defineProps<{ email?: string; editableEmail?: boolean; submitLabel?: string; noResend?: boolean }>()
const emit = defineEmits<{ verified: [status: AccountStatus, email: string] }>()
const notify = useNotify()

const address = ref(props.email ?? '')
const code = ref('')
const busy = ref(false)
const error = ref<string | null>(null)
const cooldown = ref(0)
const codeField = ref<{ focus: () => void } | null>(null)
useInitialFocus(codeField)
let timer: ReturnType<typeof setInterval> | undefined

function startCooldown(seconds = 60) {
  cooldown.value = seconds
  clearInterval(timer)
  timer = setInterval(() => {
    cooldown.value = Math.max(0, cooldown.value - 1)
    if (!cooldown.value) clearInterval(timer)
  }, 1000)
}
onBeforeUnmount(() => clearInterval(timer))

async function verify() {
  if (rule(codeSchema)(code.value) !== true) return
  error.value = null
  busy.value = true
  try {
    const res = await call(() => identity.POST('/auth/verify', { body: { email: address.value.trim(), code: code.value } }), {
      refresh: false,
    })
    emit('verified', res.status, address.value.trim())
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) {
      error.value =
        e.code === 'CODE_EXPIRED'
          ? 'This code has expired. Send a new one.'
          : e.code === 'CODE_INVALID'
            ? (e.detail ?? 'That code is not right. Check the email and try again.')
            : e.message
      code.value = ''
    } else notify.report(e)
  } finally {
    busy.value = false
  }
}

async function resend() {
  try {
    await call(() => identity.POST('/auth/verify/resend', { body: { email: address.value.trim() } }), { refresh: false })
    notify.toast('If the address is waiting for verification, a new code is on its way.', 'success')
    startCooldown()
  } catch (e) {
    if (e instanceof ApiError && e.status === 429) startCooldown(e.retryAfter ?? 300)
    notify.report(e)
  }
}
</script>

<template>
  <form class="stack" @submit.prevent="verify">
    <v-text-field
      v-if="editableEmail || !email"
      v-model="address"
      label="Email"
      type="email"
      autocomplete="email"
      :rules="[rule(emailSchema)]"
    />
    <p v-else class="t-body">
      We sent a 6-digit code to <strong>{{ email }}</strong>. It is valid for 15 minutes.
    </p>
    <v-otp-input
      ref="codeField"
      v-model="code"
      length="6"
      type="number"
      :error="!!error"
      aria-label="6-digit code"
      @finish="verify"
    />
    <v-alert v-if="error" type="error" variant="tonal" density="compact" role="alert">{{ error }}</v-alert>
    <v-btn type="submit" color="primary" size="large" block :loading="busy" :disabled="code.length !== 6">
      {{ submitLabel ?? 'Verify email' }}
    </v-btn>
    <div v-if="!noResend" class="row t-body">
      <span class="muted">No code?</span>
      <v-btn variant="text" density="compact" :disabled="cooldown > 0 || !address" @click="resend">
        {{ cooldown > 0 ? `Resend in ${cooldown} s` : 'Send a new code' }}
      </v-btn>
    </div>
  </form>
</template>
