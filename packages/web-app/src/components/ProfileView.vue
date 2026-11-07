<script setup lang="ts">
/**
 * S-19 / A-21 profile: personal details (If-Match), addresses (max 10), change email (code to the new
 * address), change password (other sessions are signed out), theme, log out.
 */
import { mdiDelete, mdiPencil, mdiPlus } from '@mdi/js'
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError, call, identity, ifMatch } from '../api'
import { countries, countryName } from '../countries'
import { useNotify } from '../notify'
import { useSession } from '../session'
import { useThemeMode } from '../theme-mode'
import type { ShippingAddress } from '../types'
import { country as countrySchema, email as emailSchema, name as nameSchema, password as passwordSchema, rule } from '../validation'
import AddressDialog from './AddressDialog.vue'
import PasswordField from './PasswordField.vue'
import StatusChip from './StatusChip.vue'
import VerifyForm from './VerifyForm.vue'

const props = defineProps<{ afterLogout: string; showAddresses?: boolean }>()
const session = useSession()
const notify = useNotify()
const router = useRouter()
const { dark } = useThemeMode()

const account = computed(() => session.account)
const details = reactive({ firstname: '', lastname: '', phone: '', department: '', country: '' })
const detailsValid = ref(false)
const saving = ref(false)
const errors = ref<Record<string, string>>({})

function fill() {
  const a = account.value
  if (!a) return
  Object.assign(details, {
    firstname: a.firstname,
    lastname: a.lastname,
    phone: a.phone ?? '',
    department: a.department ?? '',
    country: a.country ?? '',
  })
}
watch(account, fill, { immediate: true })

async function patch(body: Record<string, unknown>, okText: string): Promise<boolean> {
  const a = account.value
  if (!a) return false
  saving.value = true
  errors.value = {}
  try {
    const updated = await call(() =>
      identity.PATCH('/me', { params: { header: { 'If-Match': ifMatch(a.version) } }, body: body as never }),
    )
    session.set(updated)
    notify.toast(okText, 'success')
    return true
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) errors.value = e.fieldErrors()
    notify.report(e, { retry: () => void session.load(true) })
    return false
  } finally {
    saving.value = false
  }
}

function saveDetails() {
  void patch(
    {
      firstname: details.firstname.trim(),
      lastname: details.lastname.trim(),
      phone: details.phone.trim() || null,
      department: details.department.trim() || null,
      country: details.country || null,
    },
    'Profile saved',
  )
}

// ---- addresses
const addresses = computed<ShippingAddress[]>(() => (account.value?.addresses ?? []) as ShippingAddress[])
const addrOpen = ref(false)
const addrIndex = ref<number | null>(null)
function editAddress(i: number | null) {
  addrIndex.value = i
  addrOpen.value = true
}
function saveAddress(a: ShippingAddress) {
  const list = [...addresses.value]
  if (addrIndex.value === null) list.push(a)
  else list[addrIndex.value] = a
  void patch({ addresses: list }, 'Address saved')
}
function removeAddress(i: number) {
  void patch({ addresses: addresses.value.filter((_, j) => j !== i) }, 'Address removed')
}

// ---- email change
const emailOpen = ref(false)
const emailStep = ref<'request' | 'verify'>('request')
const newEmail = ref('')
const emailPassword = ref('')
const emailValid = ref(false)
const emailBusy = ref(false)
const emailError = ref<string | null>(null)
function openEmail() {
  emailStep.value = 'request'
  newEmail.value = ''
  emailPassword.value = ''
  emailError.value = null
  emailOpen.value = true
}
async function requestEmail() {
  emailBusy.value = true
  emailError.value = null
  try {
    await call(() => identity.POST('/me/email', { body: { newEmail: newEmail.value.trim(), password: emailPassword.value } }))
    emailStep.value = 'verify'
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) emailError.value = 'Your password is not correct.'
    else if (e instanceof ApiError && e.status === 422) emailError.value = e.message
    else notify.report(e)
  } finally {
    emailBusy.value = false
  }
}
async function emailVerified() {
  emailOpen.value = false
  await session.load(true)
  notify.toast('Email address changed', 'success')
}

// ---- password change
const pwOpen = ref(false)
const pw = reactive({ current: '', next: '', confirm: '' })
const pwValid = ref(false)
const pwBusy = ref(false)
const pwErrors = ref<Record<string, string>>({})
function openPassword() {
  Object.assign(pw, { current: '', next: '', confirm: '' })
  pwErrors.value = {}
  pwOpen.value = true
}
async function changePassword() {
  pwBusy.value = true
  pwErrors.value = {}
  try {
    await call(() => identity.POST('/me/password', { body: { currentPassword: pw.current, newPassword: pw.next } }))
    pwOpen.value = false
    notify.toast('Password changed. Your other sessions were signed out.', 'success')
  } catch (e) {
    if (e instanceof ApiError && e.status === 401 && e.code === 'INVALID_CREDENTIALS')
      pwErrors.value = { currentPassword: 'Your current password is not correct.' }
    else if (e instanceof ApiError && e.status === 422)
      pwErrors.value =
        e.code === 'PASSWORD_BREACHED'
          ? { newPassword: 'This password appears in known data breaches. Choose another one.' }
          : e.fieldErrors()
    else notify.report(e)
  } finally {
    pwBusy.value = false
  }
}

async function logout() {
  await session.logout()
  await router.push(props.afterLogout)
}

const organisation = computed(() => {
  const a = account.value
  if (!a) return ''
  if (a.organisationName) return a.organisationName
  if (a.organisationText) return `${a.organisationText} (waiting to be linked by an administrator)`
  return a.isCimh ? 'CIMH' : 'Not set'
})
</script>

<template>
  <div v-if="account" class="stack profile">
    <div class="page-header">
      <div class="stack-sm">
        <h1 class="t-h1">{{ session.displayName }}</h1>
        <div class="row t-body muted">
          <span>{{ account.email }}</span>
          <span aria-hidden="true">·</span>
          <span>{{ account.role === 'user' ? 'Customer' : account.role === 'staff' ? 'Staff' : 'Administrator' }}</span>
          <StatusChip :status="account.status" />
        </div>
      </div>
      <span class="spacer" />
      <v-btn variant="outlined" @click="logout">Log out</v-btn>
    </div>

    <v-card>
      <v-card-title class="t-h3">Personal details</v-card-title>
      <v-card-text>
        <v-form v-model="detailsValid" class="stack" @submit.prevent="saveDetails">
          <div class="grid-2">
            <v-text-field v-model="details.firstname" label="First name" autocomplete="given-name" :rules="[rule(nameSchema)]" :error-messages="errors.firstname" />
            <v-text-field v-model="details.lastname" label="Last name" autocomplete="family-name" :rules="[rule(nameSchema)]" :error-messages="errors.lastname" />
            <v-text-field v-model="details.phone" label="Phone (optional)" type="tel" autocomplete="tel" :error-messages="errors.phone" />
            <v-text-field v-model="details.department" label="Department (optional)" :error-messages="errors.department" />
            <v-autocomplete v-model="details.country" label="Country" :items="countries()" autocomplete="country" :rules="[rule(countrySchema)]" />
            <v-text-field :model-value="organisation" label="Organisation" readonly hint="Contact an administrator to change it" persistent-hint />
          </div>
          <div class="row-end">
            <v-btn type="submit" color="primary" :loading="saving" :disabled="!detailsValid">Save details</v-btn>
          </div>
        </v-form>
      </v-card-text>
    </v-card>

    <v-card v-if="showAddresses">
      <v-card-title class="row">
        <span class="t-h3">Shipping addresses</span>
        <span class="spacer" />
        <v-btn variant="outlined" size="small" :prepend-icon="mdiPlus" :disabled="addresses.length >= 10" @click="editAddress(null)">Add address</v-btn>
      </v-card-title>
      <v-card-text>
        <p v-if="!addresses.length" class="t-body muted">No saved addresses yet. You can also add one when you submit a request.</p>
        <v-list v-else lines="three" density="comfortable">
          <v-list-item v-for="(a, i) in addresses" :key="i">
            <v-list-item-title>{{ a.firstname }} {{ a.lastname }}<span v-if="a.organisation">, {{ a.organisation }}</span></v-list-item-title>
            <v-list-item-subtitle>
              {{ [a.line1, a.line2, a.city, a.parish, a.zip, countryName(a.country)].filter(Boolean).join(', ') }}
            </v-list-item-subtitle>
            <template #append>
              <v-btn variant="text" :icon="mdiPencil" :aria-label="`Edit address ${i + 1}`" @click="editAddress(i)" />
              <v-btn variant="text" :icon="mdiDelete" :aria-label="`Remove address ${i + 1}`" @click="removeAddress(i)" />
            </template>
          </v-list-item>
        </v-list>
        <p v-if="addresses.length >= 10" class="t-caption muted">You can save up to 10 addresses.</p>
      </v-card-text>
    </v-card>

    <v-card>
      <v-card-title class="t-h3">Sign-in</v-card-title>
      <v-card-text class="stack">
        <div class="row">
          <div class="stack-sm">
            <span class="t-label">Email</span>
            <span class="t-body">{{ account.email }}</span>
          </div>
          <span class="spacer" />
          <v-btn variant="outlined" @click="openEmail">Change email</v-btn>
        </div>
        <v-divider />
        <div class="row">
          <div class="stack-sm">
            <span class="t-label">Password</span>
            <span class="t-body muted">Changing it signs you out everywhere else.</span>
          </div>
          <span class="spacer" />
          <v-btn variant="outlined" @click="openPassword">Change password</v-btn>
        </div>
        <template v-if="session.isAdmin">
          <v-divider />
          <div class="stack-sm">
            <span class="t-label">Two-step verification</span>
            <span class="t-body">{{ account.mfaEnabled ? 'On: you sign in with a code from your authenticator app.' : 'Off' }}</span>
          </div>
        </template>
      </v-card-text>
    </v-card>

    <v-card>
      <v-card-title class="t-h3">Appearance</v-card-title>
      <v-card-text>
        <v-switch v-model="dark" label="Dark theme (this device)" color="primary" hide-details inset />
      </v-card-text>
    </v-card>

    <AddressDialog v-model="addrOpen" :address="addrIndex === null ? null : addresses[addrIndex]" @save="saveAddress" />

    <v-dialog v-model="emailOpen" max-width="480">
      <v-card>
        <v-card-title class="t-h3">Change email</v-card-title>
        <v-card-text>
          <v-form v-if="emailStep === 'request'" v-model="emailValid" class="stack" @submit.prevent="requestEmail">
            <v-alert v-if="emailError" type="error" variant="tonal" density="compact">{{ emailError }}</v-alert>
            <v-text-field v-model="newEmail" label="New email" type="email" autocomplete="email" :rules="[rule(emailSchema)]" />
            <PasswordField v-model="emailPassword" label="Current password" autocomplete="current-password" :rules="[(v: unknown) => !!v || 'Required']" />
            <div class="row-end">
              <v-btn variant="text" @click="emailOpen = false">Cancel</v-btn>
              <v-btn type="submit" color="primary" :loading="emailBusy" :disabled="!emailValid">Send code</v-btn>
            </div>
          </v-form>
          <VerifyForm v-else :email="newEmail.trim()" no-resend submit-label="Confirm new email" @verified="emailVerified" />
        </v-card-text>
      </v-card>
    </v-dialog>

    <v-dialog v-model="pwOpen" max-width="480">
      <v-card>
        <v-card-title class="t-h3">Change password</v-card-title>
        <v-card-text>
          <v-form v-model="pwValid" class="stack" @submit.prevent="changePassword">
            <PasswordField v-model="pw.current" label="Current password" name="current-password" autocomplete="current-password" :rules="[(v: unknown) => !!v || 'Required']" :error-messages="pwErrors.currentPassword" />
            <PasswordField v-model="pw.next" label="New password" name="new-password" autocomplete="new-password" strength :rules="[rule(passwordSchema)]" :error-messages="pwErrors.newPassword" />
            <PasswordField v-model="pw.confirm" label="Repeat new password" name="confirm-password" autocomplete="new-password" :rules="[(v: unknown) => v === pw.next || 'The passwords do not match']" />
            <div class="row-end">
              <v-btn variant="text" @click="pwOpen = false">Cancel</v-btn>
              <v-btn type="submit" color="primary" :loading="pwBusy" :disabled="!pwValid">Change password</v-btn>
            </div>
          </v-form>
        </v-card-text>
      </v-card>
    </v-dialog>
  </div>
  <v-skeleton-loader v-else type="article, article" />
</template>

<style scoped>
.profile {
  max-width: 880px;
}
</style>
