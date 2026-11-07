<script setup lang="ts">
/**
 * A-16 approve / deny one or several pending accounts (J-08).
 * Approve: link an organisation (suggested from the email domain or the organisation text; or create one)
 * and pick a role. Deny: a reason (emailed to the user). Several accounts → POST bulk-decision (207).
 */
import {
  type AccountSummary,
  ApiError,
  call,
  countries,
  identity,
  ifMatch,
  type Organisation,
  reason as reasonSchema,
  type Role,
  rule,
  useNotify,
} from '@cimh/web-app'
import { computed, reactive, ref, watch } from 'vue'
import OrganisationPicker from './OrganisationPicker.vue'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ accounts: AccountSummary[]; decision: 'approve' | 'deny' }>()
const emit = defineEmits<{ done: [okIds: string[]] }>()
const notify = useNotify()

const org = ref<Organisation | null>(null)
const suggested = ref<Organisation | null>(null)
const createNew = ref(false)
const newOrg = reactive({ name: '', country: 'BB', type: 'met_service' as Organisation['type'], domain: '' })
const role = ref<Role>('user')
const reason = ref('')
const valid = ref(false)
const busy = ref(false)
const failures = ref<{ name: string; message: string }[]>([])

const single = computed(() => (props.accounts.length === 1 ? props.accounts[0] : null))
const domain = (email: string) => email.split('@')[1]?.toLowerCase() ?? ''
const ORG_TYPES = [
  { value: 'met_service', title: 'Meteorological service' },
  { value: 'hydro_service', title: 'Hydrological service' },
  { value: 'government', title: 'Government' },
  { value: 'academic', title: 'Academic' },
  { value: 'other', title: 'Other' },
]
const ROLES = [
  { value: 'user', title: 'Customer' },
  { value: 'staff', title: 'Staff' },
  { value: 'admin', title: 'Administrator' },
]

async function suggest(a: AccountSummary) {
  suggested.value = null
  try {
    const byDomain = await call(() => identity.GET('/organisations', { params: { query: { emailDomain: domain(a.email), limit: 1 } } }))
    let match = byDomain.items[0]
    if (!match && a.organisationText) {
      const byName = await call(() => identity.GET('/organisations', { params: { query: { q: a.organisationText ?? '', limit: 1 } } }))
      match = byName.items[0]
    }
    suggested.value = match ?? null
    org.value = match ?? null
    createNew.value = !match
  } catch (e) {
    notify.report(e)
  }
}

watch(open, (o) => {
  if (!o) return
  failures.value = []
  reason.value = ''
  role.value = 'user'
  org.value = null
  const first = props.accounts[0]
  Object.assign(newOrg, { name: first?.organisationText ?? '', country: 'BB', type: 'met_service', domain: first ? domain(first.email) : '' })
  createNew.value = false
  if (props.decision === 'approve' && single.value) void suggest(single.value)
})

async function version(id: string): Promise<number> {
  return (await call(() => identity.GET('/admin/accounts/{accountId}', { params: { path: { accountId: id } } }))).version
}

async function organisationId(): Promise<string> {
  if (!createNew.value && org.value) return org.value.id
  const created = await call(() =>
    identity.POST('/organisations', {
      body: {
        name: newOrg.name.trim(),
        country: newOrg.country,
        type: newOrg.type,
        emailDomains: newOrg.domain.trim() ? [newOrg.domain.trim().toLowerCase()] : [],
      },
    }),
  )
  notify.toast(`Organisation “${created.name}” created`, 'success')
  return created.id
}

async function submit() {
  busy.value = true
  failures.value = []
  try {
    const orgId = props.decision === 'approve' ? await organisationId() : undefined
    if (single.value) {
      const a = single.value
      const v = await version(a.id)
      const headers = { header: { 'If-Match': ifMatch(v) }, path: { accountId: a.id } }
      if (props.decision === 'approve')
        await call(() => identity.POST('/admin/accounts/{accountId}/approve', { params: headers, body: { organisationId: orgId!, role: role.value } }))
      else await call(() => identity.POST('/admin/accounts/{accountId}/deny', { params: headers, body: { reason: reason.value.trim() } }))
      notify.toast(`${a.firstname} ${a.lastname} ${props.decision === 'approve' ? 'approved' : 'denied'}`, 'success')
      emit('done', [a.id])
      open.value = false
      return
    }
    const versions = await Promise.all(props.accounts.map((a) => version(a.id)))
    const res = await call(() =>
      identity.POST('/admin/accounts/bulk-decision', {
        body: {
          decisions: props.accounts.map((a, i) => ({
            accountId: a.id,
            version: versions[i]!,
            decision: props.decision,
            ...(props.decision === 'approve' ? { organisationId: orgId, role: role.value } : { reason: reason.value.trim() }),
          })),
        },
      }),
    )
    const ok = res.results.filter((r) => r.ok).map((r) => r.accountId)
    failures.value = res.results
      .filter((r) => !r.ok)
      .map((r) => {
        const a = props.accounts.find((x) => x.id === r.accountId)
        return { name: a ? `${a.firstname} ${a.lastname}` : r.accountId, message: r.error?.detail ?? r.error?.title ?? 'Failed' }
      })
    notify.toast(`${ok.length} ${props.decision === 'approve' ? 'approved' : 'denied'}${failures.value.length ? `, ${failures.value.length} failed` : ''}`, failures.value.length ? 'warning' : 'success')
    emit('done', ok)
    if (!failures.value.length) open.value = false
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) notify.toast('One of these accounts was changed by someone else. The list has been reloaded.', 'warning')
    else notify.report(e)
    if (e instanceof ApiError && e.status === 409) emit('done', [])
  } finally {
    busy.value = false
  }
}

const title = computed(() => {
  const n = props.accounts.length
  const who = single.value ? `${single.value.firstname} ${single.value.lastname}` : `${n} accounts`
  return `${props.decision === 'approve' ? 'Approve' : 'Deny'} ${who}`
})
</script>

<template>
  <v-dialog v-model="open" max-width="560" scrollable>
    <v-card>
      <v-card-title class="t-h3">{{ title }}</v-card-title>
      <v-card-text>
        <v-form v-model="valid" class="stack" @submit.prevent="submit">
          <template v-if="decision === 'approve'">
            <p v-if="single" class="t-body muted">
              Organisation given: <strong>{{ single.organisationText || '—' }}</strong> · email domain
              <span class="t-mono">{{ domain(single.email) }}</span>
            </p>
            <v-alert v-if="single && suggested && !createNew" type="info" variant="tonal" density="compact">
              Suggested match: <strong>{{ suggested.name }}</strong>
            </v-alert>
            <v-radio-group v-model="createNew" inline hide-details>
              <v-radio :value="false" label="Existing organisation" />
              <v-radio :value="true" label="Create a new one" />
            </v-radio-group>
            <OrganisationPicker
              v-if="!createNew"
              v-model="org"
              :initial-query="single?.organisationText ?? ''"
              :rules="[(v: unknown) => !!v || 'Choose an organisation']"
            />
            <template v-else>
              <v-text-field v-model="newOrg.name" label="Organisation name" :rules="[(v: string) => !!v.trim() || 'Required']" />
              <div class="grid-2">
                <v-autocomplete v-model="newOrg.country" label="Country" :items="countries()" />
                <v-select v-model="newOrg.type" label="Type" :items="ORG_TYPES" />
              </div>
              <v-text-field v-model="newOrg.domain" label="Email domain (optional)" hint="Used to suggest this organisation for future sign-ups" persistent-hint />
            </template>
            <v-select v-model="role" label="Role" :items="ROLES" />
          </template>
          <template v-else>
            <p class="t-body muted">The reason is included in the email to {{ single ? 'the user' : 'each user' }}.</p>
            <v-textarea v-model="reason" label="Reason" rows="3" auto-grow counter="500" :rules="[rule(reasonSchema)]" />
          </template>
          <v-alert v-if="failures.length" type="warning" variant="tonal" density="compact">
            <div v-for="f in failures" :key="f.name">{{ f.name }}: {{ f.message }}</div>
          </v-alert>
        </v-form>
      </v-card-text>
      <v-card-actions class="row-end">
        <v-btn variant="text" @click="open = false">Cancel</v-btn>
        <v-btn :color="decision === 'approve' ? 'primary' : 'error'" :loading="busy" :disabled="!valid" @click="submit">
          {{ decision === 'approve' ? 'Approve' : 'Deny' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
