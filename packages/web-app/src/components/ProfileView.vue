<script setup lang="ts">
/**
 * S-19 / A-21 profile: personal details (If-Match), addresses (max 10), change email (code to the new
 * address), change password (other sessions are signed out), theme, log out.
 * Sections are ProfileSection: cards in SHOP, Graphite Console panels in SIA. Buttons carry `m3` (pill in SIA,
 * no rule in SHOP).
 */
import { mdiDelete, mdiPencil, mdiPlus } from '@mdi/js'
import { formatDate } from '@cimh/web-ui'
import { useAppName } from '../bootstrap'
import { countries, countryName } from '../countries'
import { useProfile } from '../profile'
import { useThemeMode } from '../theme-mode'
import { country as countrySchema, email as emailSchema, name as nameSchema, password as passwordSchema, rule } from '../validation'
import AddressDialog from './AddressDialog.vue'
import PasswordField from './PasswordField.vue'
import ProfileSection from './ProfileSection.vue'
import StatusChip from './StatusChip.vue'
import VerifyForm from './VerifyForm.vue'

const props = defineProps<{ afterLogout: string; showAddresses?: boolean }>()
const { dark } = useThemeMode()
const sia = useAppName() === 'sia'
const {
  session,
  account,
  details,
  detailsForm,
  saving,
  errors,
  saveDetails,
  addresses,
  addrOpen,
  addrIndex,
  editAddress,
  saveAddress,
  removing,
  removeAddress,
  emailOpen,
  emailStep,
  newEmail,
  emailPassword,
  emailForm,
  emailBusy,
  emailError,
  openEmail,
  requestEmail,
  emailVerified,
  pwOpen,
  pw,
  pwForm,
  pwBusy,
  pwErrors,
  openPassword,
  changePassword,
  exporting,
  downloadMyData,
  eraseOpen,
  erasePassword,
  eraseForm,
  eraseBusy,
  eraseError,
  openErase,
  requestErasure,
  logout,
  organisation,
} = useProfile(props.afterLogout)
</script>

<template>
  <div v-if="account" class="stack profile" :class="{ sia }">
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
      <v-btn variant="outlined" class="m3" @click="logout">Log out</v-btn>
    </div>

    <ProfileSection title="Personal details">
        <v-form ref="detailsForm" class="stack" @submit.prevent="saveDetails">
          <div class="grid-2">
            <v-text-field v-model="details.firstname" label="First name" autocomplete="given-name" :rules="[rule(nameSchema)]" :error-messages="errors.firstname" />
            <v-text-field v-model="details.lastname" label="Last name" autocomplete="family-name" :rules="[rule(nameSchema)]" :error-messages="errors.lastname" />
            <v-text-field v-model="details.phone" label="Phone (optional)" type="tel" autocomplete="tel" :error-messages="errors.phone" />
            <v-text-field v-model="details.department" label="Department (optional)" :error-messages="errors.department" />
            <v-autocomplete v-model="details.country" label="Country" :items="countries()" autocomplete="country" :rules="[rule(countrySchema)]" />
            <v-text-field :model-value="organisation" label="Organisation" readonly hint="Contact an administrator to change it" persistent-hint />
          </div>
          <div class="row-end">
            <v-btn type="submit" color="primary" class="m3" :loading="saving">Save details</v-btn>
          </div>
        </v-form>
    </ProfileSection>

    <ProfileSection v-if="showAddresses" title="Shipping addresses">
      <template #action>
        <v-btn variant="outlined" size="small" :prepend-icon="mdiPlus" :disabled="addresses.length >= 10" @click="editAddress(null)">Add address</v-btn>
      </template>
        <p v-if="!addresses.length" class="t-body muted">No saved addresses yet. You can also add one when you submit a request.</p>
        <v-list v-else lines="three" density="comfortable">
          <v-list-item v-for="(a, i) in addresses" :key="i">
            <v-list-item-title>{{ a.firstname }} {{ a.lastname }}<span v-if="a.organisation">, {{ a.organisation }}</span></v-list-item-title>
            <v-list-item-subtitle>
              {{ [a.line1, a.line2, a.city, a.parish, a.zip, countryName(a.country)].filter(Boolean).join(', ') }}
            </v-list-item-subtitle>
            <template #append>
              <v-btn variant="text" :icon="mdiPencil" :aria-label="`Edit address ${i + 1}`" @click="editAddress(i)" />
              <v-btn variant="text" :icon="mdiDelete" :aria-label="`Remove address ${i + 1}`" @click="removing = i" />
            </template>
          </v-list-item>
        </v-list>
        <p v-if="addresses.length >= 10" class="t-caption muted">You can save up to 10 addresses.</p>
    </ProfileSection>

    <ProfileSection title="Sign-in">
      <div class="stack">
        <div class="row">
          <div class="stack-sm">
            <span class="t-label">Email</span>
            <span class="t-body">{{ account.email }}</span>
          </div>
          <span class="spacer" />
          <v-btn variant="outlined" class="m3" @click="openEmail">Change email</v-btn>
        </div>
        <v-divider />
        <div class="row">
          <div class="stack-sm">
            <span class="t-label">Password</span>
            <span class="t-body muted">Changing it signs you out everywhere else.</span>
          </div>
          <span class="spacer" />
          <v-btn variant="outlined" class="m3" @click="openPassword">Change password</v-btn>
        </div>
        <template v-if="session.isAdmin">
          <v-divider />
          <div class="stack-sm">
            <span class="t-label">Two-step verification</span>
            <span class="t-body">{{ account.mfaEnabled ? 'On: you sign in with a code from your authenticator app.' : 'Off' }}</span>
          </div>
        </template>
      </div>
    </ProfileSection>

    <ProfileSection title="Appearance">
      <v-switch v-model="dark" label="Dark theme (this device)" color="primary" hide-details inset />
    </ProfileSection>

    <ProfileSection title="Your data">
      <div class="stack">
        <div class="row">
          <div class="stack-sm">
            <span class="t-label">Download your data</span>
            <span class="t-body muted">Your profile, addresses and account history as a JSON file.</span>
          </div>
          <span class="spacer" />
          <v-btn variant="outlined" class="m3" :loading="exporting" @click="downloadMyData">Download</v-btn>
        </div>
        <v-divider />
        <div class="row">
          <div class="stack-sm">
            <span class="t-label">Delete your account</span>
            <span v-if="account.erasureRequestedAt" class="t-body">
              You asked for this on {{ formatDate(account.erasureRequestedAt) }}. An administrator will erase your account.
            </span>
            <span v-else class="t-body muted">
              An administrator erases your personal data. Requests stay on record as financial documents, with your name removed.
            </span>
          </div>
          <span class="spacer" />
          <v-btn v-if="!account.erasureRequestedAt" variant="outlined" color="error" class="m3 m3-danger" @click="openErase">Ask to delete</v-btn>
        </div>
      </div>
    </ProfileSection>

    <v-dialog :model-value="removing !== null" max-width="480" @update:model-value="(v: boolean) => !v && (removing = null)">
      <v-card v-if="removing !== null && addresses[removing]">
        <v-card-title class="t-h3">Remove this address?</v-card-title>
        <v-divider />
        <v-card-text class="stack">
          <p class="t-body">
            <strong>{{ addresses[removing]!.firstname }} {{ addresses[removing]!.lastname }}</strong><br />
            {{ [addresses[removing]!.organisation, addresses[removing]!.line1, addresses[removing]!.line2, addresses[removing]!.city, addresses[removing]!.parish, addresses[removing]!.zip, countryName(addresses[removing]!.country)].filter(Boolean).join(', ') }}
          </p>
          <p class="t-body muted">It leaves your saved list. Requests you already sent keep the address they were sent with.</p>
        </v-card-text>
        <v-card-actions class="row-end">
          <v-btn class="m3" variant="text" @click="removing = null">Keep address</v-btn>
          <v-btn class="m3" color="error" variant="flat" :loading="saving" @click="removeAddress">Remove</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <AddressDialog v-model="addrOpen" :address="addrIndex === null ? null : addresses[addrIndex]" @save="saveAddress" />

    <v-dialog v-model="emailOpen" max-width="480">
      <v-card>
        <v-card-title class="t-h3">Change email</v-card-title>
        <v-card-text>
          <v-form v-if="emailStep === 'request'" ref="emailForm" class="stack" @submit.prevent="requestEmail">
            <v-alert v-if="emailError" type="error" variant="tonal" density="compact">{{ emailError }}</v-alert>
            <v-text-field v-model="newEmail" label="New email" type="email" autocomplete="email" :rules="[rule(emailSchema)]" />
            <PasswordField v-model="emailPassword" label="Current password" autocomplete="current-password" :rules="[(v: unknown) => !!v || 'Required']" />
            <div class="row-end">
              <v-btn variant="text" class="m3" @click="emailOpen = false">Cancel</v-btn>
              <v-btn type="submit" color="primary" class="m3" :loading="emailBusy">Send code</v-btn>
            </div>
          </v-form>
          <VerifyForm v-else :email="newEmail.trim()" no-resend submit-label="Confirm new email" @verified="emailVerified" />
        </v-card-text>
      </v-card>
    </v-dialog>

    <v-dialog v-model="eraseOpen" max-width="480">
      <v-card>
        <v-card-title class="t-h3">Delete your account?</v-card-title>
        <v-card-text>
          <v-form ref="eraseForm" class="stack" @submit.prevent="requestErasure">
            <p class="t-body">
              An administrator will erase your name, contact details and addresses, and you will be signed out. This cannot be
              undone. Download your data first if you want a copy.
            </p>
            <v-alert v-if="eraseError" type="error" variant="tonal" density="compact">{{ eraseError }}</v-alert>
            <PasswordField v-model="erasePassword" label="Your password" name="erase-password" autocomplete="current-password" :rules="[(v: unknown) => !!v || 'Required']" />
            <div class="row-end">
              <v-btn variant="text" class="m3" @click="eraseOpen = false">Cancel</v-btn>
              <v-btn type="submit" color="error" class="m3" :loading="eraseBusy">Ask to delete</v-btn>
            </div>
          </v-form>
        </v-card-text>
      </v-card>
    </v-dialog>

    <v-dialog v-model="pwOpen" max-width="480">
      <v-card>
        <v-card-title class="t-h3">Change password</v-card-title>
        <v-card-text>
          <v-form ref="pwForm" class="stack" @submit.prevent="changePassword">
            <PasswordField v-model="pw.current" label="Current password" name="current-password" autocomplete="current-password" :rules="[(v: unknown) => !!v || 'Required']" :error-messages="pwErrors.currentPassword" />
            <PasswordField v-model="pw.next" label="New password" name="new-password" autocomplete="new-password" strength :rules="[rule(passwordSchema)]" :error-messages="pwErrors.newPassword" />
            <PasswordField v-model="pw.confirm" label="Repeat new password" name="confirm-password" autocomplete="new-password" :rules="[(v: unknown) => v === pw.next || 'The passwords do not match']" />
            <div class="row-end">
              <v-btn variant="text" class="m3" @click="pwOpen = false">Cancel</v-btn>
              <v-btn type="submit" color="primary" class="m3" :loading="pwBusy">Change password</v-btn>
            </div>
          </v-form>
        </v-card-text>
      </v-card>
    </v-dialog>
  </div>
  <v-skeleton-loader v-else type="article, article" />
</template>

<style scoped>
/* SIA: width and centring come from the page frame (console.css), as every page (owner 2026-11-26); 24 px from the
   title block to the first section, as every page (8 + the stack's 16). */
.profile.sia > .page-header {
  margin-bottom: var(--sp-2);
}
</style>
