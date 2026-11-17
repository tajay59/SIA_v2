<script setup lang="ts">
/**
 * S-19 Your account ("Account checklist", impeccable 2026-11-16; brief web/shop/.impeccable/surfaces/src-pages-account-vue.md).
 * The navy band says who you are and where the account stands: email verified, approved by CIMH (CIMH accounts
 * need no approval), organisation linked by an administrator, saved addresses (customers), and an erasure
 * request when there is one. Below, one ruled row per section, read first: its current values and one action.
 * Personal details and Addresses open in place (one at a time); email, password and erasure keep their dialogs
 * (they need a password or a code). Logic: web-app `useProfile` (shared with SIA /profile).
 */
import {
  AddressDialog,
  countries,
  countryName,
  MAX_ADDRESSES,
  PasswordField,

  useProfile,
  useThemeMode,
  VerifyForm,
} from '@cimh/web-app'
import { formatDate } from '@cimh/web-ui'
import { country as countrySchema, email as emailSchema, name as nameSchema, password as passwordSchema, rule } from '@cimh/web-app'
import { mdiCheck, mdiClockOutline, mdiDeleteOutline, mdiPencilOutline, mdiPlus } from '@mdi/js'
import { computed, nextTick, ref, watch } from 'vue'

definePage({ meta: { guard: 'auth', title: 'Your account' } })

const p = useProfile('/')
const {
  session,
  account,
  details,
  detailsForm,
  detailsDirty,
  saving,
  errors,
  fill,
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
  roleLabel,
} = p
const { dark } = useThemeMode()
const customer = computed(() => session.isCustomer)
const STATUS_WORDS: Record<string, string> = { ACTIVE: 'Active', PENDING_APPROVAL: 'Waiting for approval', PENDING_VERIFICATION: 'Email not verified', SUSPENDED: 'Suspended', REJECTED: 'Not approved', EXPIRED: 'Expired' }
const statusWord = computed(() => STATUS_WORDS[account.value?.status ?? ''] ?? account.value?.status)

/** Where the account stands, as checks on the band. `state`: done, wait (on CIMH), todo (on you), info. */
type Check = { key: string; state: 'done' | 'wait' | 'todo'; title: string; note?: string }
const checks = computed<Check[]>(() => {
  const a = account.value
  if (!a) return []
  const out: Check[] = [
    { key: 'verified', state: a.verifiedAt || a.status === 'ACTIVE' ? 'done' : 'todo', title: 'Email verified', note: a.verifiedAt ? formatDate(a.verifiedAt) : undefined },
    a.isCimh
      ? { key: 'approved', state: 'done', title: 'CIMH account', note: 'No approval needed' }
      : a.status === 'ACTIVE' || a.approvedAt
        ? { key: 'approved', state: 'done', title: 'Approved by CIMH', note: a.approvedAt ? formatDate(a.approvedAt) : undefined }
        : { key: 'approved', state: 'wait', title: 'Waiting for approval', note: 'CIMH emails you' },
  ]
  if (!a.isCimh)
    out.push(
      a.organisationId
        ? { key: 'org', state: 'done', title: 'Organisation linked', note: a.organisationName ?? undefined }
        : { key: 'org', state: 'wait', title: 'Organisation not linked yet', note: 'An administrator links it' },
    )
  if (customer.value)
    out.push(
      addresses.value.length
        ? { key: 'addr', state: 'done', title: `${addresses.value.length} saved ${addresses.value.length === 1 ? 'address' : 'addresses'}` }
        : { key: 'addr', state: 'todo', title: 'No saved address', note: 'Add one below or in the cart' },
    )
  return out
})

// One section open in place at a time.
const open = ref<null | 'details' | 'addresses'>(null)
const rowEl = ref<Record<string, HTMLElement | null>>({})
async function toggle(which: 'details' | 'addresses') {
  if (open.value === 'details') fill() // closing or switching drops unsaved typing (the form shows saved values)
  open.value = open.value === which ? null : which
  await nextTick()
  if (open.value) rowEl.value[open.value]?.querySelector<HTMLElement>('input, button.add')?.focus({ preventScroll: false })
}
function cancelDetails() {
  fill()
  open.value = null
}
/** A saved change lights its row's value once (what changed, where). */
const flash = ref<string | null>(null)
let flashTimer: ReturnType<typeof setTimeout> | undefined
function acknowledge(which: string) {
  flash.value = null
  clearTimeout(flashTimer)
  requestAnimationFrame(() => {
    flash.value = which
    flashTimer = setTimeout(() => (flash.value = null), 1200)
  })
}
watch(
  () => JSON.stringify(addresses.value),
  (now, before) => {
    if (before !== undefined && now !== before) acknowledge('addresses')
  },
)

async function submitDetails() {
  if (await p.saveDetails()) {
    open.value = null
    acknowledge('details')
  }
}

const oneLine = (a: (typeof addresses.value)[number]) =>
  [a.organisation, a.line1, a.line2, a.city, a.parish, a.zip, countryName(a.country)].filter(Boolean).join(', ')
const detailsLine = computed(() => {
  const a = account.value
  if (!a) return ''
  return [a.phone, a.department, a.country ? countryName(a.country) : null].filter(Boolean).join(' · ') || 'No phone, department or country yet'
})
</script>

<template>
  <div v-if="account" class="account-page">
    <div class="band">
      <div class="band-in">
        <div class="who">
          <h1 class="band-title">Your account</h1>
          <p class="band-line">
            {{ session.displayName }} · {{ account.email }}<template v-if="organisation"> · {{ organisation }}</template>
          </p>
          <p class="band-line role">{{ roleLabel }} · {{ statusWord }}</p>
        </div>
        <v-btn variant="outlined" class="out" @click="logout">Log out</v-btn>
      </div>
      <ul class="checks band-in" aria-label="Where your account stands">
        <li v-for="(c, n) in checks" :key="c.key" class="check" :class="c.state" :style="{ '--i': n }">
          <span class="mark" aria-hidden="true">
            <v-icon :icon="c.state === 'done' ? mdiCheck : c.state === 'wait' ? mdiClockOutline : mdiPlus" size="14" />
          </span>
          <span class="check-text">
            <span class="check-title">
              <span class="sr-only">{{ c.state === 'done' ? 'Done: ' : c.state === 'wait' ? 'Waiting for CIMH: ' : 'To do: ' }}</span>{{ c.title }}
            </span>
            <span v-if="c.note" class="check-note">{{ c.note }}</span>
          </span>
        </li>
        <li v-if="account.erasureRequestedAt" class="check stop" :style="{ '--i': checks.length }">
          <span class="mark" aria-hidden="true"><v-icon :icon="mdiClockOutline" size="14" /></span>
          <span class="check-text">
            <span class="check-title">Deletion requested</span>
            <span class="check-note">{{ formatDate(account.erasureRequestedAt) }} · an administrator erases it</span>
          </span>
        </li>
      </ul>
    </div>

    <div class="rows">
      <!-- Personal details: read, then edit in place -->
      <section :ref="(el) => (rowEl.details = el as HTMLElement)" class="acct-row" :class="{ open: open === 'details' }" aria-labelledby="r-details">
        <div class="row-head">
          <div class="row-name">
            <h2 id="r-details">Personal details</h2>
            <p>Name, phone, department, country</p>
          </div>
          <div class="row-value" :class="{ flash: flash === 'details' }">
            <p class="val-main">{{ session.displayName }}</p>
            <p class="val-sub">{{ detailsLine }}</p>
          </div>
          <v-btn
            variant="outlined"
            :prepend-icon="open === 'details' ? undefined : mdiPencilOutline"
            :aria-expanded="open === 'details'"
            aria-controls="details-form"
            @click="toggle('details')"
          >
            {{ open === 'details' ? 'Close' : 'Edit' }}
          </v-btn>
        </div>
        <div v-if="open === 'details'" id="details-form" class="row-body">
          <v-form ref="detailsForm" @submit.prevent="submitDetails">
            <div class="grid">
              <v-text-field v-model="details.firstname" label="First name" autocomplete="given-name" :rules="[rule(nameSchema)]" :error-messages="errors.firstname" />
              <v-text-field v-model="details.lastname" label="Last name" autocomplete="family-name" :rules="[rule(nameSchema)]" :error-messages="errors.lastname" />
              <v-text-field v-model="details.phone" label="Phone (optional)" type="tel" autocomplete="tel" :error-messages="errors.phone" />
              <v-text-field v-model="details.department" label="Department (optional)" :error-messages="errors.department" />
              <v-autocomplete v-model="details.country" label="Country" :items="countries()" autocomplete="country" :rules="[rule(countrySchema)]" />
              <v-text-field :model-value="organisation" label="Organisation" readonly hint="An administrator changes it" persistent-hint />
            </div>
            <div class="row-actions">
              <v-btn variant="text" @click="cancelDetails">Cancel</v-btn>
              <v-btn type="submit" color="primary" variant="flat" :loading="saving" :disabled="!detailsDirty">Save details</v-btn>
            </div>
          </v-form>
        </div>
      </section>

      <!-- Addresses (customers) -->
      <section v-if="customer" :ref="(el) => (rowEl.addresses = el as HTMLElement)" class="acct-row" :class="{ open: open === 'addresses' }" aria-labelledby="r-addr">
        <div class="row-head">
          <div class="row-name">
            <h2 id="r-addr">Addresses</h2>
            <p>Invoice and delivery, up to {{ MAX_ADDRESSES }}</p>
          </div>
          <div class="row-value" :class="{ flash: flash === 'addresses' }">
            <template v-if="addresses.length">
              <p class="val-main">{{ addresses[0]!.firstname }} {{ addresses[0]!.lastname }}<template v-if="addresses[0]!.organisation">, {{ addresses[0]!.organisation }}</template></p>
              <p class="val-sub">
                {{ oneLine(addresses[0]!) }}<template v-if="addresses.length > 1"> · and {{ addresses.length - 1 }} more</template>
              </p>
            </template>
            <p v-else class="val-sub">None saved yet. Addresses you add in the cart are saved here too.</p>
          </div>
          <v-btn variant="outlined" :aria-expanded="open === 'addresses'" aria-controls="addr-list" @click="toggle('addresses')">
            {{ open === 'addresses' ? 'Close' : 'Manage' }}
          </v-btn>
        </div>
        <div v-if="open === 'addresses'" id="addr-list" class="row-body">
          <TransitionGroup tag="ul" name="tile" class="tiles">
            <li v-for="(a, i) in addresses" :key="i" class="tile">
              <p class="tile-name">{{ a.firstname }} {{ a.lastname }}</p>
              <p class="tile-addr">
                <template v-if="a.organisation">{{ a.organisation }}<br /></template>
                {{ a.line1 }}<template v-if="a.line2">, {{ a.line2 }}</template><br />
                {{ [a.city, a.parish, a.zip].filter(Boolean).join(' ') }}<br />
                {{ countryName(a.country) }}
              </p>
              <div class="tile-acts">
                <v-btn variant="text" size="small" :prepend-icon="mdiPencilOutline" :aria-label="`Edit address ${i + 1}`" @click="editAddress(i)">Edit</v-btn>
                <v-btn variant="text" size="small" color="error" :prepend-icon="mdiDeleteOutline" :aria-label="`Remove address ${i + 1}`" @click="removing = i">Remove</v-btn>
              </div>
            </li>
            <li v-if="addresses.length < MAX_ADDRESSES" class="tile add-tile">
              <button type="button" class="add" @click="editAddress(null)"><v-icon :icon="mdiPlus" size="20" />Add an address</button>
            </li>
          </TransitionGroup>
          <p v-if="addresses.length >= MAX_ADDRESSES" class="note">You can save up to {{ MAX_ADDRESSES }} addresses. Remove one to add another.</p>
        </div>
      </section>

      <!-- Sign-in -->
      <section class="acct-row" aria-labelledby="r-sign">
        <div class="row-head">
          <div class="row-name">
            <h2 id="r-sign">Sign-in</h2>
            <p>Email and password</p>
          </div>
          <div class="row-value">
            <p class="val-main">{{ account.email }}</p>
            <p class="val-sub">Changing the password signs you out everywhere else.</p>
          </div>
          <div class="row-btns">
            <v-btn variant="outlined" @click="openEmail">Change email</v-btn>
            <v-btn variant="outlined" @click="openPassword">Change password</v-btn>
          </div>
        </div>
      </section>

      <!-- Appearance -->
      <section class="acct-row" aria-labelledby="r-look">
        <div class="row-head">
          <div class="row-name">
            <h2 id="r-look">Appearance</h2>
            <p>Saved on this device</p>
          </div>
          <div class="row-value">
            <p class="val-main">{{ dark ? 'Dark theme' : 'Light theme' }}</p>
          </div>
          <v-switch v-model="dark" label="Dark theme" color="primary" hide-details inset class="look" />
        </div>
      </section>

      <!-- Your data -->
      <section class="acct-row" aria-labelledby="r-data">
        <div class="row-head">
          <div class="row-name">
            <h2 id="r-data">Your data</h2>
            <p>Download it, or ask to delete the account</p>
          </div>
          <div class="row-value">
            <p class="val-main">Your profile, addresses and account history as a JSON file</p>
            <p v-if="account.erasureRequestedAt" class="val-sub">
              You asked for deletion on {{ formatDate(account.erasureRequestedAt) }}. An administrator will erase your account.
            </p>
            <p v-else class="val-sub">Deleting: an administrator erases your personal data. Orders stay on record as financial documents, with your name removed.</p>
          </div>
          <div class="row-btns">
            <v-btn variant="outlined" :loading="exporting" @click="downloadMyData">Download</v-btn>
            <v-btn v-if="!account.erasureRequestedAt" variant="outlined" color="error" @click="openErase">Ask to delete</v-btn>
          </div>
        </div>
      </section>
    </div>

    <!-- Dialogs: unchanged flows from the profile (password or code needed, or irreversible). -->
    <v-dialog :model-value="removing !== null" max-width="480" @update:model-value="(v: boolean) => !v && (removing = null)">
      <v-card v-if="removing !== null && addresses[removing]">
        <v-card-title class="t-h3">Remove this address?</v-card-title>
        <v-card-text class="stack">
          <p class="t-body"><strong>{{ addresses[removing]!.firstname }} {{ addresses[removing]!.lastname }}</strong><br />{{ oneLine(addresses[removing]!) }}</p>
          <p class="t-body muted">It leaves your saved list. Orders you already sent keep the address they were sent with.</p>
        </v-card-text>
        <v-card-actions class="row-end">
          <v-btn variant="text" @click="removing = null">Keep address</v-btn>
          <v-btn color="error" variant="flat" :loading="saving" @click="removeAddress">Remove</v-btn>
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
              <v-btn variant="text" @click="emailOpen = false">Cancel</v-btn>
              <v-btn type="submit" color="primary" :loading="emailBusy">Send code</v-btn>
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
          <v-form ref="pwForm" class="stack" @submit.prevent="changePassword">
            <PasswordField v-model="pw.current" label="Current password" name="current-password" autocomplete="current-password" :rules="[(v: unknown) => !!v || 'Required']" :error-messages="pwErrors.currentPassword" />
            <PasswordField v-model="pw.next" label="New password" name="new-password" autocomplete="new-password" strength :rules="[rule(passwordSchema)]" :error-messages="pwErrors.newPassword" />
            <PasswordField v-model="pw.confirm" label="Repeat new password" name="confirm-password" autocomplete="new-password" :rules="[(v: unknown) => v === pw.next || 'The passwords do not match']" />
            <div class="row-end">
              <v-btn variant="text" @click="pwOpen = false">Cancel</v-btn>
              <v-btn type="submit" color="primary" :loading="pwBusy">Change password</v-btn>
            </div>
          </v-form>
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
              <v-btn variant="text" @click="eraseOpen = false">Cancel</v-btn>
              <v-btn type="submit" color="error" :loading="eraseBusy">Ask to delete</v-btn>
            </div>
          </v-form>
        </v-card-text>
      </v-card>
    </v-dialog>
  </div>
  <v-container v-else max-width="1040"><v-skeleton-loader type="heading, paragraph, list-item-two-line@4" /></v-container>
</template>

<style scoped>
/* ---- band: the SHOP navy field with the logo-blue rule; the checklist sits on it */
.band {
  background: #0a2e4a;
  color: #fff;
  border-bottom: 4px solid #0084c8;
  padding: var(--sp-8) 0 var(--sp-6);
}
.band-in {
  max-width: 1040px;
  margin: 0 auto;
  padding: 0 var(--sp-6);
}
.band-in:first-child {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-6);
}
.who {
  min-width: 0;
}
.band-title {
  margin: 0;
  font-size: clamp(28px, 2vw + 16px, 36px);
  line-height: 1.15;
  font-weight: 700;
  letter-spacing: -0.015em;
}
.band-line {
  margin: var(--sp-2) 0 0;
  font-size: 15px;
  line-height: 22px;
  color: #c4d5e3;
  overflow-wrap: anywhere;
}
.band-line.role {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-top: var(--sp-1);
}
.out {
  flex: none;
  color: #fff !important;
  border-color: rgb(255 255 255 / 0.5) !important;
}
.checks {
  list-style: none;
  margin-top: var(--sp-6) !important;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--sp-4) var(--sp-6);
  padding-top: var(--sp-4) !important;
  border-top: 1px solid rgb(255 255 255 / 0.16);
}
.check {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
}
.mark {
  flex: none;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  margin-top: -1px;
}
.check.done .mark {
  background: #5cc2ff;
  color: #0a2e4a;
}
.check.wait .mark {
  border: 2px solid #f5c400;
  color: #f5c400;
}
.check.todo .mark {
  border: 2px dashed rgb(255 255 255 / 0.6);
  color: #fff;
}
.check.stop .mark {
  border: 2px solid #ff8a80;
  color: #ff8a80;
}
.check-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.check-title {
  font-size: 15px;
  line-height: 22px;
  font-weight: 600;
}
.check-note {
  font-size: 13px;
  line-height: 18px;
  color: #b8cbdb;
  overflow-wrap: anywhere;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

/* ---- rows: read first (name · current value · one action), the open one unfolds below its head */
.rows {
  max-width: 1040px;
  margin: 0 auto;
  padding: var(--sp-4) var(--sp-6) var(--sp-12);
}
.acct-row {
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  scroll-margin-top: 80px;
}
.row-head {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr) auto;
  gap: var(--sp-4) var(--sp-8);
  align-items: center;
  padding: var(--sp-6) 0;
}
.row-name h2 {
  margin: 0;
  font-size: 18px;
  line-height: 24px;
  font-weight: 700;
}
.row-name p,
.val-sub {
  margin: 2px 0 0;
  font-size: 14px;
  line-height: 20px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  text-wrap: pretty;
}
.val-main {
  margin: 0;
  font-size: 15px;
  line-height: 22px;
  overflow-wrap: anywhere;
}
.row-value {
  min-width: 0;
  max-width: 62ch;
}
.row-btns {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
  justify-content: flex-end;
}
.look {
  flex: none;
}
.acct-row.open .row-head {
  padding-bottom: var(--sp-4);
}
.row-body {
  padding: 0 0 var(--sp-6) calc(240px + var(--sp-8));
  animation: unfold 260ms cubic-bezier(0.16, 1, 0.3, 1);
}
@keyframes unfold {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }
}
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sp-3) var(--sp-4);
}
.row-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
  margin-top: var(--sp-4);
}
.tiles {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--sp-3);
}
.tile {
  display: flex;
  flex-direction: column;
  padding: var(--sp-4);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
}
.tile-name {
  margin: 0;
  font-weight: 600;
}
.tile-addr {
  margin: var(--sp-1) 0 var(--sp-3);
  font-size: 14px;
  line-height: 20px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  flex: 1;
  overflow-wrap: anywhere;
}
.tile-acts {
  display: flex;
  gap: var(--sp-1);
  margin-left: calc(-1 * var(--sp-2));
}
.add-tile {
  border-style: dashed;
  padding: 0;
}
.add {
  flex: 1;
  min-height: 140px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
  background: none;
  border: 0;
  border-radius: 12px;
  font: inherit;
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
}
.add:hover {
  background: rgba(var(--v-theme-primary), 0.06);
}
.add:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.note {
  margin: var(--sp-3) 0 0;
  font-size: 14px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

/* ---- narrower screens: rows stack (name, value, actions); the body loses its indent */
@media (max-width: 839.98px) {
  .row-head {
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas: 'name act' 'value value';
    align-items: start;
  }
  .row-name {
    grid-area: name;
  }
  .row-value {
    grid-area: value;
  }
  .row-head > :last-child {
    grid-area: act;
  }
  .row-body {
    padding-left: 0;
  }
}
@media (max-width: 599.98px) {
  .band {
    padding-top: var(--sp-6);
  }
  .band-in {
    padding: 0 var(--sp-4);
  }
  .band-in:first-child {
    flex-direction: column;
  }
  .rows {
    padding: var(--sp-2) var(--sp-4) 120px;
  }
  .row-head {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas: 'name' 'value' 'act';
  }
  .row-btns {
    justify-content: flex-start;
  }
  .grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (prefers-reduced-motion: reduce) {
  .row-body {
    animation: none;
  }
}
</style>
