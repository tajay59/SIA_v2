<script setup lang="ts">
/**
 * A-19 settings (admin): Fees (admin fee in CIMH quotes), Email lists (staff notified per event), Workflow
 * (quote validity, reminders, purge, cart inactivity), Reference (departments, projects). Every save is audited.
 */
import {
  type AccountSummary,
  ApiError,
  call,
  catalog,
  type EmailLists,
  type Fees,
  identity,
  type Project,
  useNotify,
  useReference,
  type WorkflowSettings,
} from '@cimh/web-app'
import { mdiDeleteOutline, mdiPlus } from '@mdi/js'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

definePage({ meta: { guard: 'admin', title: 'Settings' } })
const route = useRoute()
const router = useRouter()
const notify = useNotify()
const { reference, reload: reloadReference } = useReference()
const tab = computed({
  get: () => (typeof route.query.tab === 'string' ? route.query.tab : 'fees'),
  set: (t: string) => void router.replace({ query: { tab: t } }),
})
const busy = ref<string | null>(null)
const errors = ref<Record<string, string>>({})

async function run(key: string, fn: () => Promise<unknown>, ok: string) {
  busy.value = key
  errors.value = {}
  try {
    await fn()
    notify.toast(ok, 'success')
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) errors.value = e.fieldErrors()
    notify.report(e)
  } finally {
    busy.value = null
  }
}

// ---- fees
const fees = ref<{ name: string; fee: string }[]>([])
const feesValid = ref(false)
const money = (v: string) => /^\d{1,12}(\.\d{1,2})?$/.test(String(v ?? '').trim()) || 'An amount like 25 or 25.50'
const saveFees = () =>
  run(
    'fees',
    async () => {
      const body = { types: fees.value.map((f) => ({ name: f.name.trim(), fee: Number(f.fee).toFixed(2) })) }
      fees.value = (await call(() => catalog.PUT('/settings/fees', { body }))).types
    },
    'Fees saved',
  )

// ---- email lists
const LISTS: { key: keyof EmailLists; title: string; hint: string }[] = [
  { key: 'registration', title: 'New registrations', hint: 'Told when someone signs up and waits for approval' },
  { key: 'order', title: 'New requests', hint: 'Told when a customer submits a request' },
  { key: 'invoice', title: 'Invoices and agreements', hint: 'Told when a signed agreement or invoice arrives' },
  { key: 'cancellation', title: 'Cancellations', hint: 'Told when a request is cancelled or declined' },
  { key: 'lowStock', title: 'Low stock', hint: 'Told when an item drops below its alert level' },
]
const lists = reactive<Record<string, string[]>>({ registration: [], order: [], invoice: [], cancellation: [], lowStock: [] })
const staff = ref<AccountSummary[]>([])
const staffItems = computed(() =>
  staff.value.map((a) => ({ value: a.id, title: `${a.firstname} ${a.lastname}`, subtitle: a.email })),
)
const saveLists = () =>
  run(
    'lists',
    async () => {
      const body = Object.fromEntries(LISTS.map((l) => [l.key, lists[l.key]!.map((accountId) => ({ accountId }))])) as unknown as EmailLists
      const saved = await call(() => catalog.PUT('/settings/email-lists', { body }))
      for (const l of LISTS) lists[l.key] = saved[l.key].map((m) => m.accountId)
    },
    'Email lists saved',
  )

// ---- workflow
const workflow = ref<WorkflowSettings | null>(null)
const workflowValid = ref(false)
const whole = (min: number, max: number) => (v: unknown) =>
  (Number.isInteger(Number(v)) && Number(v) >= min && Number(v) <= max) || `A whole number from ${min} to ${max}`
const saveWorkflow = () =>
  run(
    'workflow',
    async () => {
      const w = workflow.value!
      const body = Object.fromEntries(Object.entries(w).map(([k, v]) => [k, Number(v)])) as WorkflowSettings
      workflow.value = await call(() => catalog.PUT('/settings/general', { body }))
    },
    'Workflow settings saved',
  )

// ---- reference
const departments = ref<string[]>([])
const saveDepartments = () =>
  run(
    'departments',
    async () => {
      await call(() => catalog.PUT('/reference/departments', { body: { values: departments.value.map((d) => d.trim()).filter(Boolean) } }))
      departments.value = (await reloadReference()).departments
    },
    'Departments saved',
  )
const projects = ref<Project[]>([])
const newProject = reactive({ code: '', name: '' })
async function loadProjects() {
  const all = await call(() => catalog.GET('/reference', { params: { query: { includeInactive: true } } }))
  projects.value = [...all.projects]
}
const addProject = () =>
  run(
    'project',
    async () => {
      const p = await call(() => catalog.POST('/reference/projects', { body: { code: newProject.code.trim(), name: newProject.name.trim(), active: true } }))
      projects.value = [...projects.value, p]
      Object.assign(newProject, { code: '', name: '' })
      await reloadReference()
    },
    'Project added',
  )
const updateProject = (p: Project, body: { name?: string; active?: boolean }) =>
  run(
    `p:${p.code}`,
    async () => {
      const saved = await call(() => catalog.PATCH('/reference/projects/{code}', { params: { path: { code: p.code } }, body }))
      projects.value = projects.value.map((x) => (x.code === saved.code ? saved : x))
      await reloadReference()
    },
    body.active === false ? 'Project deactivated: it no longer appears in the catalogue filters' : 'Project saved',
  )

onMounted(async () => {
  try {
    const [f, l, w, staffPage, adminPage] = await Promise.all([
      call(() => catalog.GET('/settings/fees')),
      call(() => catalog.GET('/settings/email-lists')),
      call(() => catalog.GET('/settings/general')),
      call(() => identity.GET('/admin/accounts', { params: { query: { role: 'staff', status: 'ACTIVE', limit: 100 } } })),
      call(() => identity.GET('/admin/accounts', { params: { query: { role: 'admin', status: 'ACTIVE', limit: 100 } } })),
    ])
    fees.value = f.types
    for (const def of LISTS) lists[def.key] = l[def.key].map((m) => m.accountId)
    workflow.value = w
    staff.value = [...adminPage.items, ...staffPage.items]
    departments.value = [...(reference.value ?? (await reloadReference())).departments]
    await loadProjects()
  } catch (e) {
    notify.report(e)
  }
})
</script>

<template>
  <div class="page settings">
    <v-tabs v-model="tab" color="primary">
      <v-tab value="fees">Fees</v-tab>
      <v-tab value="lists">Email lists</v-tab>
      <v-tab value="workflow">Workflow</v-tab>
      <v-tab value="reference">Reference</v-tab>
    </v-tabs>

    <v-window v-model="tab" class="pt-4">
      <v-window-item value="fees">
        <v-form v-model="feesValid" class="stack" @submit.prevent="saveFees">
          <p class="t-body muted prose">Fees added to CIMH-stock quotes, in BBD. The “admin” fee is added to every CIMH-stock line.</p>
          <div v-for="(f, i) in fees" :key="i" class="fee-row">
            <v-text-field v-model="f.name" label="Name" :rules="[(v: string) => !!v.trim() || 'Required']" hide-details="auto" />
            <v-text-field v-model="f.fee" label="Fee" prefix="BBD" inputmode="decimal" :rules="[money]" hide-details="auto" />
            <v-btn variant="text" :icon="mdiDeleteOutline" :aria-label="`Remove fee ${f.name || i + 1}`" @click="fees.splice(i, 1)" />
          </div>
          <div class="row">
            <v-btn variant="outlined" :prepend-icon="mdiPlus" @click="fees.push({ name: fees.length ? '' : 'admin', fee: '' })">Add fee</v-btn>
            <span class="spacer" />
            <v-btn type="submit" color="primary" :loading="busy === 'fees'" :disabled="!feesValid">Save fees</v-btn>
          </div>
        </v-form>
      </v-window-item>

      <v-window-item value="lists">
        <form class="stack" @submit.prevent="saveLists">
          <p class="t-body muted prose">Who gets the staff emails. Only active staff and administrators can be added.</p>
          <v-autocomplete
            v-for="l in LISTS"
            :key="l.key"
            v-model="lists[l.key]"
            :items="staffItems"
            :label="l.title"
            :hint="l.hint"
            persistent-hint
            multiple
            chips
            closable-chips
            :error-messages="Object.entries(errors).filter(([k]) => k.startsWith(l.key + '[')).map(([, v]) => v)"
          />
          <div class="row-end"><v-btn type="submit" color="primary" :loading="busy === 'lists'">Save email lists</v-btn></div>
        </form>
      </v-window-item>

      <v-window-item value="workflow">
        <v-form v-if="workflow" v-model="workflowValid" class="stack" @submit.prevent="saveWorkflow">
          <div class="grid-2">
            <v-text-field v-model.number="workflow.quoteValidityDays" type="number" label="Quotes are valid for" suffix="days" :rules="[whole(1, 365)]" />
            <v-text-field v-model.number="workflow.quoteReminderDays" type="number" label="Remind customers before a quote expires" suffix="days" :rules="[whole(0, 60)]" />
            <v-text-field v-model.number="workflow.approvalReminderHours" type="number" label="Remind admins of waiting sign-ups after" suffix="hours" :rules="[whole(1, 720)]" />
            <v-text-field v-model.number="workflow.purgeAfterDays" type="number" label="Delete rejected or expired accounts after" suffix="days" :rules="[whole(1, 3650)]" />
            <v-text-field v-model.number="workflow.cartInactivityDays" type="number" label="Empty inactive carts after" suffix="days" :rules="[whole(1, 3650)]" />
          </div>
          <div class="row-end"><v-btn type="submit" color="primary" :loading="busy === 'workflow'" :disabled="!workflowValid">Save workflow settings</v-btn></div>
        </v-form>
        <v-skeleton-loader v-else type="article" />
      </v-window-item>

      <v-window-item value="reference">
        <div class="stack">
          <form class="stack-sm" @submit.prevent="saveDepartments">
            <h2 class="t-h3">Departments</h2>
            <v-combobox v-model="departments" label="Departments" multiple chips closable-chips hint="Press Enter after each name. Products keep their department if it is removed here." persistent-hint />
            <div class="row-end"><v-btn type="submit" color="primary" :loading="busy === 'departments'">Save departments</v-btn></div>
          </form>
          <v-divider />
          <section class="stack-sm">
            <h2 class="t-h3">Projects</h2>
            <p class="t-body muted">Projects group Pro Bono items in the catalogue. Deactivated projects disappear from the filters.</p>
            <v-table density="compact">
              <thead><tr><th>Code</th><th>Name</th><th>Active</th></tr></thead>
              <tbody>
                <tr v-for="p in projects" :key="p.code">
                  <td class="t-mono">{{ p.code }}</td>
                  <td>
                    <v-text-field
                      :model-value="p.name"
                      density="compact"
                      hide-details
                      variant="plain"
                      :aria-label="`Name of project ${p.code}`"
                      @change="(e: Event) => updateProject(p, { name: (e.target as HTMLInputElement).value })"
                    />
                  </td>
                  <td>
                    <v-switch :model-value="p.active" color="primary" hide-details inset density="compact" :aria-label="`Project ${p.code} active`" :loading="busy === `p:${p.code}`" @update:model-value="(v: boolean | null) => updateProject(p, { active: !!v })" />
                  </td>
                </tr>
                <tr v-if="!projects.length"><td colspan="3" class="t-body muted">No projects yet.</td></tr>
              </tbody>
            </v-table>
            <form class="project-row" @submit.prevent="addProject">
              <v-text-field v-model="newProject.code" label="Code" hint="Letters, digits, - and _" persistent-hint :error-messages="errors.code" />
              <v-text-field v-model="newProject.name" label="Name" />
              <v-btn type="submit" variant="outlined" :prepend-icon="mdiPlus" :disabled="!newProject.code.trim() || !newProject.name.trim()" :loading="busy === 'project'">Add project</v-btn>
            </form>
          </section>
        </div>
      </v-window-item>
    </v-window>
  </div>
</template>

<style scoped>
.settings {
  max-width: 880px;
}
.fee-row {
  display: grid;
  grid-template-columns: 1fr 200px 40px;
  gap: var(--sp-3);
  align-items: start;
}
.project-row {
  display: grid;
  grid-template-columns: 180px 1fr max-content;
  gap: var(--sp-3);
  align-items: start;
}
@media (max-width: 600px) {
  .fee-row,
  .project-row {
    grid-template-columns: 1fr;
  }
}
</style>
