<script setup lang="ts">
/**
 * A-17 account record, shown beside the accounts list (`/admin/accounts?open=<id>`) and on its own page
 * (`/admin/accounts/<id>`). Header (name, email, status, role) → Next step well (the one decision this
 * account needs: approve/deny, an erasure request, a suspension) → facts in two groups → status history →
 * admin actions, destructive ones kept apart at the foot. Admin actions use If-Match; staff read only.
 */
import {
  type Account,
  ApiError,
  call,
  countryName,
  downloadJson,
  exportFilename,
  identity,
  ifMatch,
  reason as reasonSchema,
  type Role,
  rule,
  StatusChip,
  useNotify,
  useSession,
} from '@cimh/web-app'
import { formatDateTime } from '@cimh/web-ui'
import {
  mdiAccountCancelOutline,
  mdiAccountCheckOutline,
  mdiAccountClockOutline,
  mdiDeleteClockOutline,
  mdiDeleteForeverOutline,
  mdiDownloadOutline,
  mdiEmailCheckOutline,
  mdiShieldKeyOutline,
} from '@mdi/js'
import { computed, onMounted, ref, watch } from 'vue'
import DecisionDialog from './DecisionDialog.vue'

const props = defineProps<{ accountId: string; embedded?: boolean }>()
const emit = defineEmits<{ updated: [a: Account]; erased: [id: string] }>()
const session = useSession()
const notify = useNotify()
const account = ref<Account | null>(null)
const missing = ref(false)
const busy = ref(false)

async function load() {
  missing.value = false
  try {
    account.value = await call(() => identity.GET('/admin/accounts/{accountId}', { params: { path: { accountId: props.accountId } } }))
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) missing.value = true
    else notify.report(e, { retry: load })
  }
}
onMounted(load)
watch(account, (a) => a && emit('updated', a))

const ROLES = [
  { value: 'user', title: 'Customer' },
  { value: 'staff', title: 'Staff' },
  { value: 'admin', title: 'Administrator' },
]
const roleTitle = (r: string) => ROLES.find((x) => x.value === r)?.title ?? r
const isSelf = computed(() => account.value?.id === session.account?.id)
const name = computed(() => (account.value ? `${account.value.firstname} ${account.value.lastname}`.trim() : ''))

async function act(fn: (a: Account) => Promise<Account>, ok: string) {
  if (!account.value) return
  busy.value = true
  try {
    account.value = await fn(account.value)
    notify.toast(ok, 'success')
    return true
  } catch (e) {
    if (e instanceof ApiError && e.code === 'LAST_ADMIN') notify.toast('This is the last administrator; promote someone else first.', 'warning')
    else notify.report(e, { retry: load })
    if (e instanceof ApiError && e.status === 409) await load()
    return false
  } finally {
    busy.value = false
  }
}
const params = (a: Account) => ({ header: { 'If-Match': ifMatch(a.version) }, path: { accountId: a.id } })

// role
const roleOpen = ref(false)
const newRole = ref<Role>('user')
async function saveRole() {
  if (await act((a) => call(() => identity.PUT('/admin/accounts/{accountId}/role', { params: params(a), body: { role: newRole.value } })), 'Role changed'))
    roleOpen.value = false
}

// suspend / reactivate
const suspendOpen = ref(false)
const suspendReason = ref('')
const suspendValid = ref(false)
async function suspend() {
  if (await act((a) => call(() => identity.POST('/admin/accounts/{accountId}/suspend', { params: params(a), body: { reason: suspendReason.value.trim() } })), 'Account suspended; its sessions were signed out'))
    suspendOpen.value = false
}
function reactivate() {
  void act((a) => call(() => identity.POST('/admin/accounts/{accountId}/reactivate', { params: params(a) })), 'Account reactivated')
}

// lost authenticator (runbook OPERATIONS): another admin removes the MFA enrolment
const mfaOpen = ref(false)
const mfaReason = ref('')
const mfaValid = ref(false)
async function resetMfa() {
  if (await act((a) => call(() => identity.POST('/admin/accounts/{accountId}/mfa/reset', { params: params(a), body: { reason: mfaReason.value.trim() } })), 'Two-step verification reset; they were signed out and must set it up again'))
    mfaOpen.value = false
}

// pending → approve / deny
const decisionOpen = ref(false)
const decision = ref<'approve' | 'deny'>('approve')
function decide(d: 'approve' | 'deny') {
  decision.value = d
  decisionOpen.value = true
}

// personal data (TR-PRIV-1): export, erase
const exporting = ref(false)
async function exportData() {
  if (!account.value) return
  exporting.value = true
  try {
    const id = account.value.id
    const body = await call(() => identity.GET('/admin/accounts/{accountId}/export', { params: { path: { accountId: id } } }))
    downloadJson(body, exportFilename(`cimh-data-${id}`, body.generatedAt))
  } catch (e) {
    notify.report(e)
  } finally {
    exporting.value = false
  }
}
const eraseOpen = ref(false)
const eraseReason = ref('')
const eraseConfirm = ref('')
const eraseValid = ref(false)
function openErase() {
  eraseReason.value = account.value?.erasureRequestedAt ? 'Asked by the account holder' : ''
  eraseConfirm.value = ''
  eraseOpen.value = true
}
async function erase() {
  const a = account.value
  if (!a) return
  busy.value = true
  try {
    await call(() => identity.POST('/admin/accounts/{accountId}/erase', { params: params(a), body: { reason: eraseReason.value.trim() } }))
    eraseOpen.value = false
    notify.toast('Account erased', 'success')
    emit('erased', a.id)
  } catch (e) {
    if (e instanceof ApiError && e.code === 'LAST_ADMIN') notify.toast('This is the last administrator; promote someone else first.', 'warning')
    else notify.report(e, { retry: load })
    if (e instanceof ApiError && e.status === 409) await load()
  } finally {
    busy.value = false
  }
}

/** The one thing this account needs from an admin now, if anything. */
const step = computed(() => {
  const a = account.value
  if (!a) return null
  if (a.erasureRequestedAt)
    return { tone: 'warning', icon: mdiDeleteClockOutline, text: 'Asked to be deleted', sub: `The account holder asked to be deleted on ${formatDateTime(a.erasureRequestedAt)}. Export their data if they want a copy, then erase the account.` }
  if (a.status === 'PENDING_APPROVAL')
    return { tone: 'warning', icon: mdiAccountClockOutline, text: 'Waiting for approval', sub: 'Email verified. Link an organisation and approve, or deny with a reason (emailed to them).' }
  if (a.status === 'PENDING_VERIFICATION')
    return { tone: 'muted', icon: mdiEmailCheckOutline, text: 'Waiting for email verification', sub: 'Nothing to do yet; the link expires after 24 hours.' }
  if (a.status === 'SUSPENDED') return { tone: 'error', icon: mdiAccountCancelOutline, text: 'Suspended', sub: 'They cannot sign in until an administrator reactivates the account.' }
  if (a.role === 'admin' && !a.mfaEnabled)
    return { tone: 'muted', icon: mdiShieldKeyOutline, text: 'Two-step verification not set up', sub: 'They are asked to set it up at their next sign-in; admin pages stay locked until then.' }
  return null
})
const canAct = computed(() => session.isAdmin)
const history = computed(() => [...(account.value?.statusHistory ?? [])].reverse())
</script>

<template>
  <div class="ar" :class="{ embedded }">
    <div v-if="missing" class="ar-empty">
      <h1 class="t-h3">Account not found</h1>
      <p class="t-body muted">It may have been erased or purged.</p>
      <div class="row"><v-btn class="m3" variant="outlined" to="/admin/accounts">Back to accounts</v-btn></div>
    </div>

    <div v-else-if="!account" class="ar-skel" aria-busy="true">
      <div class="console-skel" style="height: 28px; width: 50%" />
      <div class="console-skel" style="height: 16px; width: 35%" />
      <div class="console-skel" style="height: 96px" />
      <div class="console-skel" style="height: 220px" />
    </div>

    <article v-else :key="account.id" class="ar-body">
      <header class="ar-head">
        <component :is="embedded ? 'h2' : 'h1'" class="ident">{{ name || account.email }}</component>
        <p class="email">{{ account.email }}</p>
        <div class="tags">
          <Transition name="land" mode="out-in"><StatusChip :key="account.status" :status="account.status" /></Transition>
          <Transition name="land" mode="out-in"><span :key="account.role" class="tag">{{ roleTitle(account.role) }}</span></Transition>
          <span v-if="account.isCimh" class="tag">CIMH</span>
          <span v-if="isSelf" class="tag">You</span>
        </div>
      </header>

      <Transition name="well">
      <section v-if="step" :key="step.text" class="well" :class="`tone-${step.tone}`" aria-label="Next step">
        <p class="step"><v-icon :icon="step.icon" size="20" />{{ step.text }}</p>
        <p class="t-body step-sub">{{ step.sub }}</p>
        <div v-if="canAct" class="well-acts">
          <template v-if="account.status === 'PENDING_APPROVAL'">
            <v-btn class="m3" color="primary" variant="flat" :prepend-icon="mdiAccountCheckOutline" @click="decide('approve')">Approve</v-btn>
            <v-btn class="m3 m3-danger" variant="outlined" @click="decide('deny')">Deny</v-btn>
          </template>
          <template v-else-if="account.erasureRequestedAt">
            <v-btn class="m3" variant="outlined" :prepend-icon="mdiDownloadOutline" :loading="exporting" @click="exportData">Export data</v-btn>
            <span class="well-gap" aria-hidden="true" />
            <v-btn class="m3 m3-danger" variant="outlined" :prepend-icon="mdiDeleteForeverOutline" :disabled="isSelf" @click="openErase">Erase permanently…</v-btn>
          </template>
          <v-btn v-else-if="account.status === 'SUSPENDED'" class="m3" color="primary" variant="flat" :loading="busy" @click="reactivate">Reactivate</v-btn>
        </div>
      </section>
      </Transition>

      <div class="groups">
        <section class="group" aria-labelledby="g-profile">
          <h3 id="g-profile" class="console-title">Profile</h3>
          <dl class="facts">
            <dt>Organisation</dt>
            <dd>
              {{ account.organisationName ?? (account.isCimh ? 'CIMH' : 'Not linked') }}
              <span v-if="account.organisationText" class="muted"> · given as “{{ account.organisationText }}”</span>
            </dd>
            <dt>Department</dt><dd>{{ account.department || '—' }}</dd>
            <dt>Country</dt><dd>{{ countryName(account.country) || '—' }}</dd>
            <dt>Phone</dt><dd class="console-mono">{{ account.phone || '—' }}</dd>
            <dt>Can request items</dt><dd>{{ account.isCimh ? 'No (CIMH account)' : 'Yes' }}</dd>
          </dl>
        </section>
        <section class="group" aria-labelledby="g-access">
          <h3 id="g-access" class="console-title">Sign-in and access</h3>
          <dl class="facts">
            <dt>Role</dt><dd>{{ roleTitle(account.role) }}</dd>
            <dt>Two-step verification</dt><dd>{{ account.mfaEnabled ? 'On' : 'Off' }}</dd>
            <dt>Created</dt><dd class="console-mono">{{ account.createdAt ? formatDateTime(account.createdAt) : '—' }}</dd>
            <dt>Verified</dt><dd class="console-mono">{{ account.verifiedAt ? formatDateTime(account.verifiedAt) : '—' }}</dd>
            <dt>Approved</dt><dd class="console-mono">{{ account.approvedAt ? formatDateTime(account.approvedAt) : '—' }}</dd>
            <dt>Id</dt><dd class="console-mono id">{{ account.id }}</dd>
          </dl>
        </section>
      </div>

      <section class="group" aria-labelledby="g-history">
        <h3 id="g-history" class="console-title">Status history</h3>
        <p v-if="!history.length" class="t-body muted">No changes recorded.</p>
        <TransitionGroup v-else tag="ol" name="entry" class="ledger">
          <li v-for="h in history" :key="`${h.at}-${h.to}`">
            <span class="when console-mono">{{ formatDateTime(h.at) }}</span>
            <span class="what">
              <StatusChip v-if="h.to" :status="h.to" />
              <span class="t-body">by {{ h.by.name }}<span v-if="h.reason" class="muted">: “{{ h.reason }}”</span></span>
            </span>
          </li>
        </TransitionGroup>
      </section>

      <footer v-if="canAct && (account.status === 'ACTIVE' || (account.role === 'admin' && account.mfaEnabled && !isSelf))" class="ar-foot">
        <div class="row">
          <v-btn v-if="account.status === 'ACTIVE'" class="m3" variant="outlined" :disabled="isSelf" @click="newRole = account.role; roleOpen = true">Change role</v-btn>
          <v-btn v-if="account.role === 'admin' && account.mfaEnabled && !isSelf" class="m3" variant="outlined" @click="mfaReason = ''; mfaOpen = true">
            Reset two-step verification
          </v-btn>
          <v-btn v-if="account.status === 'ACTIVE'" class="m3" variant="outlined" :disabled="isSelf" @click="suspendReason = ''; suspendOpen = true">Suspend…</v-btn>
        </div>
        <p v-if="isSelf" class="t-caption muted self-note">You can't change your own role, suspend or erase yourself.</p>
      </footer>

      <!-- Erase is the one action here that can't be undone: its own group, away from Suspend (reversible). -->
      <section v-if="canAct && !account.erasureRequestedAt" class="group pdata" aria-labelledby="g-pdata">
        <h3 id="g-pdata" class="console-title">Personal data</h3>
        <p class="t-body muted pdata-text">
          Export gives a copy of everything held about this person. Erasing removes their name, contact details and sign-in for good;
          do it only when the person has asked for it.
        </p>
        <div class="pdata-acts">
          <v-btn class="m3" variant="outlined" :prepend-icon="mdiDownloadOutline" :loading="exporting" @click="exportData">Export data</v-btn>
          <v-btn class="m3 m3-danger" variant="outlined" :prepend-icon="mdiDeleteForeverOutline" :disabled="isSelf" @click="openErase">Erase permanently…</v-btn>
        </div>
      </section>
    </article>

    <v-dialog v-model="roleOpen" max-width="420">
      <v-card :title="'Change role'" :subtitle="account?.email">
        <v-divider />
        <v-card-text><v-select v-model="newRole" :items="ROLES" label="Role" /></v-card-text>
        <v-card-actions class="row-end">
          <v-btn class="m3" variant="text" @click="roleOpen = false">Cancel</v-btn>
          <v-btn class="m3" color="primary" variant="flat" :loading="busy" :disabled="newRole === account?.role" @click="saveRole">Save</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="suspendOpen" max-width="480">
      <v-card title="Suspend account" :subtitle="account?.email">
        <v-divider />
        <v-card-text>
          <v-form v-model="suspendValid" @submit.prevent="suspend">
            <p class="t-body muted mb-4">The user is signed out everywhere and can't log in until reactivated.</p>
            <v-textarea v-model="suspendReason" label="Reason" rows="3" auto-grow counter="500" :rules="[rule(reasonSchema)]" />
          </v-form>
        </v-card-text>
        <v-card-actions class="row-end">
          <v-btn class="m3" variant="text" @click="suspendOpen = false">Cancel</v-btn>
          <v-btn class="m3" color="error" variant="flat" :loading="busy" :disabled="!suspendValid" @click="suspend">Suspend</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="mfaOpen" max-width="480">
      <v-card title="Reset two-step verification" :subtitle="account?.email">
        <v-divider />
        <v-card-text>
          <v-form v-model="mfaValid" @submit.prevent="resetMfa">
            <p class="t-body muted mb-4">For an administrator who lost their authenticator. They are signed out everywhere and must set up two-step verification again at their next sign-in. Check who is asking before you do this.</p>
            <v-textarea v-model="mfaReason" label="Reason" rows="3" auto-grow counter="500" :rules="[rule(reasonSchema)]" />
          </v-form>
        </v-card-text>
        <v-card-actions class="row-end">
          <v-btn class="m3" variant="text" @click="mfaOpen = false">Cancel</v-btn>
          <v-btn class="m3" color="error" variant="flat" :loading="busy" :disabled="!mfaValid" @click="resetMfa">Reset</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="eraseOpen" max-width="520">
      <v-card title="Erase account" :subtitle="account?.email">
        <v-divider />
        <v-card-text>
          <v-form v-model="eraseValid" class="stack" @submit.prevent="erase">
            <p class="t-body">
              Removes the name, contact details, addresses and sign-in of <strong>{{ account?.email }}</strong> and signs them out.
              Their requests stay as financial records with the name replaced by “[deleted]”. This cannot be undone.
            </p>
            <v-textarea v-model="eraseReason" label="Reason" rows="2" auto-grow counter="500" :rules="[rule(reasonSchema)]" />
            <v-text-field
              v-model="eraseConfirm"
              label="Type the email address to confirm"
              autocomplete="off"
              :rules="[(v: string) => v.trim().toLowerCase() === account?.email.toLowerCase() || 'Must match the account email']"
            />
          </v-form>
        </v-card-text>
        <v-card-actions class="row-end">
          <v-btn class="m3" variant="text" @click="eraseOpen = false">Cancel</v-btn>
          <v-btn class="m3" color="error" variant="flat" :loading="busy" :disabled="!eraseValid" @click="erase">Erase account</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <DecisionDialog v-if="account" v-model="decisionOpen" :accounts="[account]" :decision="decision" @done="load" />
  </div>
</template>

<style scoped>
.ar {
  font-size: 14px;
}
.ar:not(.embedded) {
  max-width: 960px;
  margin-inline: auto;
  padding: var(--sp-6);
}
.ar.embedded .ar-body,
.ar.embedded .ar-empty,
.ar.embedded .ar-skel {
  padding: var(--sp-4) var(--sp-6) var(--sp-6);
}
.ar-body {
  display: flex;
  flex-direction: column;
  gap: var(--sp-6);
  animation: ar-in 200ms var(--ease-out) both;
}
@keyframes ar-in {
  from {
    opacity: 0;
    transform: translateX(8px);
  }
}
.ar-skel,
.ar-empty {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.ar-head {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}
.ident {
  margin: 0;
  font-size: 20px;
  line-height: 26px;
  font-weight: 600;
  letter-spacing: -0.01em;
  overflow-wrap: anywhere;
}
.ar:not(.embedded) .ident {
  font-size: 28px;
  line-height: 36px;
  letter-spacing: -0.3px;
}
.email {
  margin: 0;
  color: rgb(var(--v-theme-secondary));
  overflow-wrap: anywhere;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-2);
  margin-top: var(--sp-2);
}
.tag {
  font-size: 13px;
  font-weight: 500;
  line-height: 26px;
  padding: 0 10px;
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 8px;
}
.well {
  padding: 12px 16px 16px;
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface-variant));
}
.step {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin: 0;
  font-size: 16px;
  line-height: 22px;
  font-weight: 600;
}
.tone-warning .step {
  color: rgb(var(--v-theme-warning));
}
.tone-error .step {
  color: rgb(var(--v-theme-error));
}
.tone-muted .step {
  color: rgb(var(--v-theme-secondary));
}
.step-sub {
  margin: var(--sp-1) 0 0 28px;
  max-width: 62ch;
}
.well-acts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
  margin: var(--sp-3) 0 0 28px;
}
.groups {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--sp-6);
}
.group {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.facts {
  display: grid;
  grid-template-columns: minmax(120px, max-content) 1fr;
  margin: 0;
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.facts dt,
.facts dd {
  margin: 0;
  padding: 8px 0;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.facts dt {
  padding-right: var(--sp-4);
  font-size: 13px;
  color: rgb(var(--v-theme-secondary));
}
.facts dd {
  overflow-wrap: anywhere;
}
.facts .console-mono {
  font-size: 13px;
}
.facts .id {
  font-size: 12px;
}
.ledger {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.ledger li {
  display: grid;
  grid-template-columns: 150px 1fr;
  gap: var(--sp-4);
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.when {
  font-size: 12px;
  color: rgb(var(--v-theme-secondary));
}
.what {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-2);
}
.ar-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-3);
  padding-top: var(--sp-4);
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.well-gap {
  flex: 1 1 var(--sp-6);
}
.pdata {
  padding-top: var(--sp-4);
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.pdata-text {
  max-width: 65ch;
  margin: 0;
}
.pdata-acts {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: var(--sp-3);
}
.self-note {
  flex-basis: 100%;
  margin: 0;
}
@media (max-width: 599.98px) {
  .ar:not(.embedded) {
    padding: var(--sp-4);
  }
  .ledger li {
    grid-template-columns: 1fr;
    gap: 4px;
  }
  .step-sub,
  .well-acts {
    margin-left: 0;
  }
}
/* A decision landing: the new status chip / role arrives with a short ring, the Next step well hands over
   (old one lifts away, the next settles in), and the new history entry drops in on an action wash. */
.land-enter-active {
  animation: ar-land 420ms var(--ease-out) both;
}
.land-leave-active {
  transition: opacity 100ms ease-in, transform 100ms ease-in;
}
.land-leave-to {
  opacity: 0;
  transform: scale(0.94);
}
@keyframes ar-land {
  from {
    opacity: 0;
    transform: scale(0.9);
    box-shadow: 0 0 0 0 rgba(var(--v-theme-primary), 0.5);
  }
  60% {
    opacity: 1;
    transform: scale(1);
    box-shadow: 0 0 0 6px rgba(var(--v-theme-primary), 0);
  }
}
.well-enter-active {
  transition: opacity 240ms var(--ease-out) 80ms, transform 240ms var(--ease-out) 80ms;
}
.well-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.well-leave-active {
  position: absolute;
  left: 0;
  right: 0;
  transition: opacity 140ms ease-in, transform 140ms ease-in;
}
.well-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
.ar-body {
  position: relative;
}
.ar.embedded .well-leave-active {
  left: var(--sp-6);
  right: var(--sp-6);
}
.entry-enter-active {
  animation: ar-entry 900ms var(--ease-out) both;
}
@keyframes ar-entry {
  from {
    opacity: 0;
    transform: translateY(-8px);
    background: rgba(var(--v-theme-primary), 0.18);
  }
  25% {
    opacity: 1;
    transform: none;
  }
  to {
    background: transparent;
  }
}
.entry-move {
  transition: transform 280ms var(--ease-out);
}
@keyframes ar-entry-reduced {
  from {
    background: rgba(var(--v-theme-primary), 0.18);
  }
}
@media (prefers-reduced-motion: reduce) {
  .ar-body,
  .land-enter-active {
    animation: none;
  }
  .well-enter-from,
  .well-leave-to {
    transform: none;
  }
  .entry-enter-active {
    animation: ar-entry-reduced 900ms ease both;
  }
  .entry-move {
    transition: none;
  }
}
</style>
