<script setup lang="ts">
/**
 * Admin MFA setup (TR-AUTH-9, Must): scan the QR code or type the key, confirm with a first code.
 * Admins without MFA can use nothing else (API 403 MFA_REQUIRED). After confirming, the current token
 * still says "no MFA", so the admin logs in again with a code.
 */
import { mdiCheck, mdiContentCopy } from '@mdi/js'
import QRCode from 'qrcode'
import { computed, onMounted, ref } from 'vue'
import { ApiError, call, identity } from '../api'
import { useNotify } from '../notify'

const emit = defineEmits<{ enabled: [] }>()
const notify = useNotify()
const uri = ref<string | null>(null)
const qr = ref<string | null>(null)
const code = ref('')
const busy = ref(false)
const error = ref<string | null>(null)

const secret = computed(() => {
  if (!uri.value) return ''
  const s = new URL(uri.value).searchParams.get('secret') ?? ''
  return s.replace(/(.{4})/g, '$1 ').trim()
})

async function start() {
  error.value = null
  try {
    const res = await call(() => identity.POST('/auth/mfa/setup', {}))
    uri.value = res.otpauthUri
    qr.value = await QRCode.toDataURL(res.otpauthUri, { margin: 1, width: 200, errorCorrectionLevel: 'M' })
  } catch (e) {
    if (e instanceof ApiError && e.code === 'MFA_ALREADY_ENABLED') emit('enabled')
    else notify.report(e, { retry: start })
  }
}
onMounted(start)

const copied = ref(false)
async function copyKey() {
  try {
    await navigator.clipboard.writeText(secret.value.replace(/ /g, ''))
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch {
    /* clipboard blocked: the key stays selectable (user-select: all) */
  }
}

async function confirm() {
  if (busy.value || !uri.value) return
  if (code.value.length !== 6) {
    error.value = 'Enter the 6-digit code your authenticator app shows.'
    return
  }
  busy.value = true
  error.value = null
  try {
    await call(() => identity.POST('/auth/mfa/confirm', { body: { totp: code.value } }))
    emit('enabled')
  } catch (e) {
    if (e instanceof ApiError && (e.status === 422 || e.status === 401)) {
      error.value = 'That code is not valid. Wait for the next one and try again.'
      code.value = ''
    } else notify.report(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="stack">
    <ol class="t-body steps">
      <li>Open an authenticator app (for example Microsoft Authenticator, Google Authenticator or 1Password).</li>
      <li>Scan this code, or enter the key by hand.</li>
      <li>Type the 6-digit code the app shows.</li>
    </ol>
    <div class="qr-row">
      <v-skeleton-loader v-if="!qr" type="image" width="200" height="200" />
      <img v-else :src="qr" width="200" height="200" alt="QR code for your authenticator app" class="qr" />
      <div v-if="secret" class="stack-sm">
        <span class="t-label">Key</span>
        <code class="t-mono key">{{ secret }}</code>
        <v-btn variant="tonal" size="small" class="m3 copy" :prepend-icon="copied ? mdiCheck : mdiContentCopy" @click="copyKey">
          {{ copied ? 'Copied' : 'Copy key' }}
        </v-btn>
      </div>
    </div>
    <form class="stack" @submit.prevent="confirm">
      <v-otp-input v-model="code" length="6" type="number" :error="!!error" aria-label="6-digit code" @finish="confirm" />
      <v-alert v-if="error" type="error" variant="tonal" density="compact" role="alert">{{ error }}</v-alert>
      <v-btn type="submit" color="primary" size="large" class="m3" block :loading="busy || !uri">
        Turn on two-step verification
      </v-btn>
    </form>
  </div>
</template>

<style scoped>
.steps {
  margin: 0;
  padding-left: 20px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.qr-row {
  display: flex;
  gap: var(--sp-6);
  align-items: center;
  flex-wrap: wrap;
}
.qr {
  border-radius: 8px;
  background: #fff;
  padding: 8px;
}
.copy {
  align-self: flex-start;
}
.key {
  word-break: break-all;
  user-select: all;
}
</style>
