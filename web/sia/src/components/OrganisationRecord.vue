<script setup lang="ts">
/**
 * One organisation beside the A-18 list (or alone on narrow screens): identity, facts, members, the edit form
 * (admins) and Merge, kept apart at the foot. `organisationId === null` = create a new organisation.
 */
import {
  type AccountSummary,
  ApiError,
  call,
  checkForm,
  countries,
  countryName,
  type FormLike,
  identity,
  ifMatch,
  type Organisation,
  StatusChip,
  useNotify,
  useSession,
} from '@cimh/web-app'
import { formatDate } from '@cimh/web-ui'
import { mdiCallMerge, mdiPlus } from '@mdi/js'
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import OrganisationPicker from './OrganisationPicker.vue'
import SaveState from './SaveState.vue'
import { ORG_TYPES, orgTypeTitle } from '../organisations'

const props = defineProps<{ organisationId: string | null }>()
const emit = defineEmits<{ saved: [o: Organisation, created: boolean]; merged: [id: string] }>()
const session = useSession()
const notify = useNotify()

const org = ref<Organisation | null>(null)
const missing = ref(false)
const members = ref<AccountSummary[]>([])
const moreMembers = ref(false)
const isNew = computed(() => props.organisationId === null)

const form = reactive({ name: '', country: 'BB', type: 'met_service' as Organisation['type'], emailDomains: [] as string[], aliases: [] as string[], active: true })
const formRef = ref<FormLike | null>(null)
const busy = ref(false)
const justSaved = ref(false)
let savedTimer: ReturnType<typeof setTimeout> | undefined
onBeforeUnmount(() => clearTimeout(savedTimer))
function fill(o: Organisation | null) {
  Object.assign(form, {
    name: o?.name ?? '',
    country: o?.country ?? 'BB',
    type: o?.type ?? 'met_service',
    emailDomains: [...(o?.emailDomains ?? [])],
    aliases: [...(o?.aliases ?? [])],
    active: o?.active ?? true,
  })
}
const dirty = computed(() => {
  const o = org.value
  if (!o) return !!form.name.trim()
  return (
    form.name !== o.name ||
    form.country !== o.country ||
    form.type !== o.type ||
    form.active !== (o.active ?? true) ||
    form.emailDomains.join() !== (o.emailDomains ?? []).join() ||
    form.aliases.join() !== (o.aliases ?? []).join()
  )
})

onMounted(async () => {
  if (isNew.value) return fill(null)
  try {
    const id = props.organisationId!
    const [o, m] = await Promise.all([
      call(() => identity.GET('/organisations/{organisationId}', { params: { path: { organisationId: id } } })),
      call(() => identity.GET('/admin/accounts', { params: { query: { organisationId: id, limit: 20 } } })).catch(() => null),
    ])
    org.value = o
    fill(o)
    members.value = m?.items ?? []
    moreMembers.value = !!m?.nextCursor
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) missing.value = true
    else notify.report(e)
  }
})

async function save() {
  if (busy.value) return
  // Never a disabled Create: a missing name is marked and gets the cursor.
  if (!(await checkForm(formRef.value))) return
  busy.value = true
  const body = { ...form, name: form.name.trim(), emailDomains: form.emailDomains.map((d) => d.trim().toLowerCase()).filter(Boolean) }
  try {
    const o = org.value
    const saved = o
      ? await call(() =>
          identity.PATCH('/organisations/{organisationId}', {
            params: { path: { organisationId: o.id }, header: { 'If-Match': ifMatch(o.version) } },
            body,
          }),
        )
      : await call(() => identity.POST('/organisations', { body }))
    org.value = saved
    fill(saved)
    justSaved.value = true
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => (justSaved.value = false), 1800)
    notify.toast(o ? 'Organisation saved' : 'Organisation created', 'success')
    emit('saved', saved, !o)
  } catch (e) {
    if (e instanceof ApiError && e.code === 'DUPLICATE') notify.toast('An organisation with this name already exists.', 'warning')
    else notify.report(e)
  } finally {
    busy.value = false
  }
}

const mergeTarget = ref<Organisation | null>(null)
const confirmOpen = ref(false)
async function merge() {
  const s = org.value
  const t = mergeTarget.value
  if (!s || !t) return
  busy.value = true
  try {
    await call(() => identity.POST('/organisations/{organisationId}/merge', { params: { path: { organisationId: s.id } }, body: { targetId: t.id } }))
    notify.toast(`${s.name} merged into ${t.name}`, 'success')
    confirmOpen.value = false
    emit('merged', s.id)
  } catch (e) {
    notify.report(e)
  } finally {
    busy.value = false
  }
}
const required = (v: string) => !!v.trim() || 'Required'
const maxLen = (v: string) => v.length <= 200 || 'At most 200 characters'
</script>

<template>
  <div class="or">
    <div v-if="missing" class="or-pad stack">
      <h2 class="t-h3">Organisation not found</h2>
      <p class="t-body muted">It may have been merged into another one.</p>
    </div>

    <div v-else-if="!isNew && !org" class="or-pad stack" aria-busy="true">
      <div class="console-skel" style="height: 28px; width: 55%" />
      <div class="console-skel" style="height: 16px; width: 35%" />
      <div class="console-skel" style="height: 120px" />
      <div class="console-skel" style="height: 200px" />
    </div>

    <article v-else :key="organisationId ?? 'new'" class="or-pad or-body">
      <header class="or-head">
        <h2 class="ident">{{ isNew ? 'New organisation' : org!.name }}</h2>
        <p v-if="org" class="sub">{{ orgTypeTitle(org.type) }} · {{ countryName(org.country) }}</p>
        <p v-else class="sub">Customers are linked to it when their sign-up is approved.</p>
        <div v-if="org" class="tags">
          <span v-if="org.mergedInto" class="tag">Merged</span>
          <span v-else-if="org.active === false" class="tag">Inactive</span>
          <span v-else class="tag">Active</span>
          <span v-if="org.aliases?.length" class="tag">{{ org.aliases.length }} other {{ org.aliases.length === 1 ? 'name' : 'names' }}</span>
        </div>
      </header>

      <dl v-if="org" class="facts">
        <dt>Members</dt>
        <dd class="console-mono">{{ Math.max(org.memberCount ?? 0, members.length) }}{{ moreMembers ? '+' : '' }}</dd>
        <dt>Email domains</dt>
        <dd class="console-mono">{{ (org.emailDomains ?? []).join(', ') || '—' }}</dd>
        <dt>Other names</dt>
        <dd>{{ (org.aliases ?? []).join(', ') || '—' }}</dd>
        <dt>Created</dt>
        <dd class="console-mono">{{ formatDate(org.createdAt) }}</dd>
        <dt>Id</dt>
        <dd class="console-mono id">{{ org.id }}</dd>
      </dl>

      <section v-if="org" class="group" aria-labelledby="or-members">
        <h3 id="or-members" class="console-title">Members</h3>
        <ul v-if="members.length" class="members">
          <li v-for="m in members" :key="m.id">
            <router-link :to="`/admin/accounts/${m.id}`" class="member">
              <span class="m-name">{{ `${m.firstname} ${m.lastname}`.trim() || m.email }}<span class="m-mail">{{ m.email }}</span></span>
              <StatusChip :status="m.status" />
            </router-link>
          </li>
        </ul>
        <p v-else class="t-body muted">No accounts are linked to it yet.</p>
        <p v-if="moreMembers" class="t-caption muted">Showing the first 20.</p>
      </section>

      <section v-if="session.isAdmin" class="group" aria-labelledby="or-edit">
        <h3 id="or-edit" class="console-title">{{ isNew ? 'Details' : 'Edit details' }}</h3>
        <v-form ref="formRef" class="stack" @submit.prevent="save">
          <v-text-field v-model="form.name" label="Name" :rules="[required, maxLen]" />
          <div class="grid-2">
            <v-autocomplete v-model="form.country" label="Country" :items="countries()" />
            <v-select v-model="form.type" label="Type" :items="ORG_TYPES" />
          </div>
          <v-combobox v-model="form.emailDomains" label="Email domains" multiple chips closable-chips hint="Press Enter after each, e.g. barbados.gov.bb" persistent-hint />
          <v-combobox v-model="form.aliases" label="Other names (aliases)" multiple chips closable-chips hint="Help match sign-ups that spell it differently" persistent-hint />
          <v-switch v-model="form.active" label="Active" color="primary" hide-details inset />
          <div class="save-bar">
            <SaveState :dirty="dirty" :saved="justSaved" :quiet="isNew" />
            <v-btn
              type="submit"
              class="m3"
              color="primary"
              variant="flat"
              :prepend-icon="isNew ? mdiPlus : undefined"
              :loading="busy"
              :disabled="!isNew && !dirty"
            >{{ isNew ? 'Create organisation' : 'Save changes' }}</v-btn>
          </div>
        </v-form>
      </section>

      <section v-if="session.isAdmin && org && !org.mergedInto" class="group merge" aria-labelledby="or-merge">
        <h3 id="or-merge" class="console-title">Merge a duplicate</h3>
        <p class="t-body muted measure">
          If {{ org.name }} is a duplicate, merge it into the right organisation: its members and request visibility move there and it becomes
          inactive. This can't be undone.
        </p>
        <div class="merge-row">
          <OrganisationPicker v-model="mergeTarget" label="Merge into" :exclude-id="org.id" />
          <v-btn class="m3 m3-danger" variant="outlined" :prepend-icon="mdiCallMerge" :disabled="!mergeTarget" @click="confirmOpen = true">Merge…</v-btn>
        </div>
      </section>
    </article>

    <v-dialog v-model="confirmOpen" max-width="480">
      <v-card>
        <v-card-title class="t-h3">Merge into {{ mergeTarget?.name }}?</v-card-title>
        <v-card-subtitle>{{ org?.name }}</v-card-subtitle>
        <v-divider />
        <v-card-text>
          <p class="t-body">
            {{ org?.memberCount ?? 0 }} {{ (org?.memberCount ?? 0) === 1 ? 'member moves' : 'members move' }} to {{ mergeTarget?.name }}, and
            {{ org?.name }} becomes inactive. This can't be undone.
          </p>
        </v-card-text>
        <v-card-actions class="row-end">
          <v-btn class="m3" variant="text" @click="confirmOpen = false">Back</v-btn>
          <v-btn class="m3" color="error" variant="flat" :loading="busy" @click="merge">Merge</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.or {
  font-size: 14px;
}
.or-pad {
  padding: var(--sp-4) var(--sp-6) var(--sp-6);
}
.or-body {
  display: flex;
  flex-direction: column;
  gap: var(--sp-6);
  animation: or-in 200ms var(--ease-out) both;
}
@keyframes or-in {
  from {
    opacity: 0;
    transform: translateX(8px);
  }
}
.or-head {
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
.sub {
  margin: 0;
  color: rgb(var(--v-theme-secondary));
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
  margin-top: var(--sp-2);
}
.tags:empty {
  display: none;
}
.tag {
  font-size: 13px;
  font-weight: 500;
  line-height: 26px;
  padding: 0 10px;
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 8px;
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
.group {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.members {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.member {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  min-height: 48px;
  padding: 6px 8px;
  color: inherit;
  text-decoration: none;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
  transition: background-color 120ms ease;
}
.member:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.m-name {
  display: flex;
  flex-direction: column;
  min-width: 0;
  font-weight: 500;
}
.m-mail {
  font-size: 12px;
  font-weight: 400;
  color: rgb(var(--v-theme-secondary));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.save-bar {
  position: sticky;
  bottom: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--sp-3);
  padding: var(--sp-3) 0;
  border-top: 1px solid rgb(var(--v-theme-seam));
  background: rgb(var(--v-theme-background));
}
.merge {
  padding-top: var(--sp-6);
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.measure {
  max-width: 62ch;
  margin: 0;
}
.merge-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) max-content;
  gap: var(--sp-3);
  align-items: start;
}
@media (max-width: 599.98px) {
  .or-pad {
    padding: var(--sp-4);
  }
  .merge-row {
    grid-template-columns: 1fr;
  }
}
@media (prefers-reduced-motion: reduce) {
  .or-body {
    animation: none;
  }
}
</style>
