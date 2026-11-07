<script setup lang="ts">
/**
 * A-17 account detail: details, organisation, status history. Admin actions with If-Match: change role,
 * suspend (reason; revokes sessions), reactivate; pending accounts → approve/deny. Staff read only.
 */
import {
  type Account,
  ApiError,
  call,
  countryName,
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
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import DecisionDialog from '../../../components/DecisionDialog.vue'

definePage({ meta: { guard: 'staff', title: 'Account' } })

const route = useRoute('/admin/accounts/[id]')
const session = useSession()
const notify = useNotify()
const account = ref<Account | null>(null)
const missing = ref(false)
const busy = ref(false)

async function load() {
  try {
    account.value = await call(() => identity.GET('/admin/accounts/{accountId}', { params: { path: { accountId: route.params.id } } }))
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) missing.value = true
    else notify.report(e, { retry: load })
  }
}
onMounted(load)

const ROLES = [
  { value: 'user', title: 'Customer' },
  { value: 'staff', title: 'Staff' },
  { value: 'admin', title: 'Administrator' },
]
const roleTitle = (r: string) => ROLES.find((x) => x.value === r)?.title ?? r
const isSelf = computed(() => account.value?.id === session.account?.id)

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

// pending → approve / deny
const decisionOpen = ref(false)
const decision = ref<'approve' | 'deny'>('approve')
</script>

<template>
  <div class="page">
    <div v-if="missing" class="stack">
      <h1 class="t-h2">Account not found</h1>
      <div class="row"><v-btn to="/admin/accounts" variant="outlined">Back to accounts</v-btn></div>
    </div>
    <v-skeleton-loader v-else-if="!account" type="article, table" />
    <div v-else class="stack detail">
      <div class="page-header">
        <div class="stack-sm">
          <h1 class="t-h2">{{ account.firstname }} {{ account.lastname }}</h1>
          <div class="row t-body muted">
            <span>{{ account.email }}</span>
            <StatusChip :status="account.status" />
          </div>
        </div>
        <span class="spacer" />
        <template v-if="session.isAdmin">
          <template v-if="account.status === 'PENDING_APPROVAL'">
            <v-btn color="primary" @click="decision = 'approve'; decisionOpen = true">Approve</v-btn>
            <v-btn variant="outlined" color="error" @click="decision = 'deny'; decisionOpen = true">Deny</v-btn>
          </template>
          <v-btn v-if="account.status === 'ACTIVE'" variant="outlined" :disabled="isSelf" @click="newRole = account.role; roleOpen = true">Change role</v-btn>
          <v-btn v-if="account.status === 'ACTIVE'" variant="outlined" color="error" :disabled="isSelf" @click="suspendReason = ''; suspendOpen = true">Suspend</v-btn>
          <v-btn v-if="account.status === 'SUSPENDED'" color="primary" :loading="busy" @click="reactivate">Reactivate</v-btn>
        </template>
      </div>

      <div class="cards">
        <v-card>
          <v-card-title class="t-h3">Details</v-card-title>
          <v-card-text>
            <dl class="facts">
              <dt>Role</dt><dd>{{ roleTitle(account.role) }}</dd>
              <dt>Organisation</dt>
              <dd>
                {{ account.organisationName ?? '—' }}
                <span v-if="account.organisationText" class="muted"> (given: {{ account.organisationText }})</span>
              </dd>
              <dt>CIMH account</dt><dd>{{ account.isCimh ? 'Yes (cannot request items)' : 'No' }}</dd>
              <dt>Department</dt><dd>{{ account.department || '—' }}</dd>
              <dt>Country</dt><dd>{{ countryName(account.country) || '—' }}</dd>
              <dt>Phone</dt><dd>{{ account.phone || '—' }}</dd>
              <dt>Two-step verification</dt><dd>{{ account.mfaEnabled ? 'On' : 'Off' }}</dd>
              <dt>Created</dt><dd class="tnum">{{ account.createdAt ? formatDateTime(account.createdAt) : '—' }}</dd>
              <dt>Verified</dt><dd class="tnum">{{ account.verifiedAt ? formatDateTime(account.verifiedAt) : '—' }}</dd>
              <dt>Approved</dt><dd class="tnum">{{ account.approvedAt ? formatDateTime(account.approvedAt) : '—' }}</dd>
              <dt>Id</dt><dd class="t-mono">{{ account.id }}</dd>
            </dl>
          </v-card-text>
        </v-card>

        <v-card>
          <v-card-title class="t-h3">Status history</v-card-title>
          <v-card-text>
            <p v-if="!account.statusHistory?.length" class="t-body muted">No changes recorded.</p>
            <v-timeline v-else side="end" density="compact" truncate-line="both">
              <v-timeline-item v-for="(h, i) in [...account.statusHistory].reverse()" :key="i" size="x-small" dot-color="primary">
                <div class="stack-sm">
                  <div class="row"><StatusChip :status="h.to" /><span class="t-caption muted tnum">{{ formatDateTime(h.at) }}</span></div>
                  <span class="t-body">by {{ h.by.name }}<span v-if="h.reason">: “{{ h.reason }}”</span></span>
                </div>
              </v-timeline-item>
            </v-timeline>
          </v-card-text>
        </v-card>
      </div>
    </div>

    <v-dialog v-model="roleOpen" max-width="420">
      <v-card>
        <v-card-title class="t-h3">Change role</v-card-title>
        <v-card-text><v-select v-model="newRole" :items="ROLES" label="Role" /></v-card-text>
        <v-card-actions class="row-end">
          <v-btn variant="text" @click="roleOpen = false">Cancel</v-btn>
          <v-btn color="primary" :loading="busy" :disabled="newRole === account?.role" @click="saveRole">Save</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="suspendOpen" max-width="480">
      <v-card>
        <v-card-title class="t-h3">Suspend account</v-card-title>
        <v-card-text>
          <v-form v-model="suspendValid" @submit.prevent="suspend">
            <p class="t-body muted mb-4">The user is signed out everywhere and can't log in until reactivated.</p>
            <v-textarea v-model="suspendReason" label="Reason" rows="3" auto-grow counter="500" :rules="[rule(reasonSchema)]" />
          </v-form>
        </v-card-text>
        <v-card-actions class="row-end">
          <v-btn variant="text" @click="suspendOpen = false">Cancel</v-btn>
          <v-btn color="error" :loading="busy" :disabled="!suspendValid" @click="suspend">Suspend</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <DecisionDialog v-if="account" v-model="decisionOpen" :accounts="[account]" :decision="decision" @done="load" />
  </div>
</template>

<style scoped>
.detail {
  max-width: 1100px;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: var(--sp-4);
  align-items: start;
}
.facts {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: var(--sp-2) var(--sp-6);
  margin: 0;
}
.facts dt {
  font-size: 13px;
  font-weight: 500;
  opacity: 0.72;
}
.facts dd {
  margin: 0;
  font-size: 14px;
  word-break: break-word;
}
</style>
