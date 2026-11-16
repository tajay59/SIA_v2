<script setup lang="ts">
/**
 * A-19 settings (admin), one console frame: a section index (Fees · Email lists · Workflow · Reference,
 * `?tab=`) beside the open section. Each section is a ledger of settings with a sticky save bar that says whether
 * anything is unsaved. Every save is audited. One save model everywhere: edits wait for the section's Save
 * (only adding a project acts at once); leaving the page with unsaved sections asks first.
 */
import {
  type AccountSummary,
  ApiError,
  call,
  catalog,
  checkForm,
  type EmailLists,
  type FormLike,
  identity,
  type Project,
  useNotify,
  useReference,
  useSession,
  type WorkflowSettings,
} from '@cimh/web-app'
import { formatDate } from '@cimh/web-ui'
import {
  mdiAccountMultipleOutline,
  mdiAlertOutline,
  mdiCheck,
  mdiCashMultiple,
  mdiDeleteOutline,
  mdiPlus,
  mdiShapeOutline,
  mdiTimerCogOutline,
} from '@mdi/js'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import SaveState from '../../components/SaveState.vue'
import { revealInStrip } from '../../strip'

definePage({ meta: { guard: 'admin', title: 'Settings', ownHeading: true } })
const route = useRoute()
const router = useRouter()
const notify = useNotify()
const session = useSession()
const { reference, reload: reloadReference } = useReference()

const SECTIONS = [
  { value: 'fees', title: 'Fees', desc: 'Added to CIMH-stock quotes', icon: mdiCashMultiple },
  { value: 'lists', title: 'Email lists', desc: 'Staff told about each event', icon: mdiAccountMultipleOutline },
  { value: 'workflow', title: 'Workflow', desc: 'Validity, reminders, clean-up', icon: mdiTimerCogOutline },
  { value: 'reference', title: 'Reference', desc: 'Departments and projects', icon: mdiShapeOutline },
] as const
const tab = computed({
  get: () => (SECTIONS.some((s) => s.value === route.query.tab) ? (route.query.tab as string) : 'fees'),
  set: (t: string) => void router.replace({ query: { tab: t } }),
})
const current = computed(() => SECTIONS.find((s) => s.value === tab.value)!)

// One marker glides to the open section (down the index on wide screens, along the strip on narrow ones).
const indexList = ref<HTMLElement | null>(null)
const marker = reactive({ x: 0, y: 0, w: 0, h: 0, ready: false, placed: false })
function placeMarker() {
  const el = indexList.value?.querySelector<HTMLElement>('.sec.on')
  if (!el) return
  // Narrow screens: the index is a sideways strip; keep the open section on screen.
  revealInStrip(indexList.value!, el)
  Object.assign(marker, { x: el.offsetLeft, y: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight, ready: true })
  // The first placement is instant; later ones move.
  if (!marker.placed) requestAnimationFrame(() => (marker.placed = true))
}
watch(tab, () => void nextTick(placeMarker))
onMounted(() => {
  void nextTick(placeMarker)
  window.addEventListener('resize', placeMarker)
})
onBeforeUnmount(() => window.removeEventListener('resize', placeMarker))

/** "Saved" flashes with a check for a moment after a save; otherwise the bar states the plain status. */
const justSaved = ref<string | null>(null)
let savedTimer: ReturnType<typeof setTimeout> | undefined
onBeforeUnmount(() => clearTimeout(savedTimer))
function flashSaved(key: string) {
  justSaved.value = key
  clearTimeout(savedTimer)
  savedTimer = setTimeout(() => (justSaved.value = null), 1800)
}
const loaded = ref(false)
const busy = ref<string | null>(null)
const errors = ref<Record<string, string>>({})

async function run(key: string, fn: () => Promise<unknown>, ok: string) {
  busy.value = key
  errors.value = {}
  try {
    await fn()
    flashSaved(key)
    notify.toast(ok, 'success')
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) errors.value = e.fieldErrors()
    notify.report(e)
  } finally {
    busy.value = null
  }
}
const snap = (v: unknown) => JSON.stringify(v)

// ---- fees
const fees = ref<{ name: string; fee: string }[]>([])
const feesSaved = ref('[]')
const feesDirty = computed(() => snap(fees.value) !== feesSaved.value)
const feesForm = ref<FormLike | null>(null)
const money = (v: string) => /^\d{1,12}(\.\d{1,2})?$/.test(String(v ?? '').trim()) || 'An amount like 25 or 25.50'
const feesTotal = computed(() => fees.value.reduce((t, f) => t + (Number(f.fee) || 0), 0).toFixed(2))
const saveFees = async () =>
  !busy.value &&
  (await checkForm(feesForm.value)) &&
  run(
    'fees',
    async () => {
      const body = { types: fees.value.map((f) => ({ name: f.name.trim(), fee: Number(f.fee).toFixed(2) })) }
      fees.value = (await call(() => catalog.PUT('/settings/fees', { body }))).types
      feesSaved.value = snap(fees.value)
    },
    'Fees saved',
  )

// ---- email lists
const LISTS: { key: keyof EmailLists; title: string; hint: string }[] = [
  { key: 'registration', title: 'New registrations', hint: 'Someone signs up and waits for approval, or asks to be deleted' },
  { key: 'order', title: 'New requests', hint: 'A customer submits a request' },
  { key: 'invoice', title: 'Invoices and agreements', hint: 'A signed agreement or an invoice arrives' },
  { key: 'cancellation', title: 'Cancellations', hint: 'A request is cancelled or declined' },
  { key: 'lowStock', title: 'Low stock', hint: 'A product drops to its alert level' },
]
const lists = reactive<Record<string, string[]>>({ registration: [], order: [], invoice: [], cancellation: [], lowStock: [] })
const listsSaved = ref('')
const listsDirty = computed(() => snap(lists) !== listsSaved.value)
const staff = ref<AccountSummary[]>([])
const staffItems = computed(() => staff.value.map((a) => ({ value: a.id, title: `${a.firstname} ${a.lastname}`, subtitle: a.email })))
const emptyLists = computed(() => LISTS.filter((l) => !lists[l.key]!.length).length)
const saveLists = () =>
  run(
    'lists',
    async () => {
      const body = Object.fromEntries(LISTS.map((l) => [l.key, lists[l.key]!.map((accountId) => ({ accountId }))])) as unknown as EmailLists
      const saved = await call(() => catalog.PUT('/settings/email-lists', { body }))
      for (const l of LISTS) lists[l.key] = saved[l.key].map((m) => m.accountId)
      listsSaved.value = snap(lists)
    },
    'Email lists saved',
  )

// ---- workflow
const workflow = ref<WorkflowSettings | null>(null)
const workflowSaved = ref('')
const workflowDirty = computed(() => !!workflow.value && snap(workflow.value) !== workflowSaved.value)
const workflowForm = ref<FormLike | null>(null)
const whole = (min: number, max: number) => (v: unknown) =>
  (Number.isInteger(Number(v)) && Number(v) >= min && Number(v) <= max) || `A whole number from ${min} to ${max}`
type WKey = keyof WorkflowSettings
const WORKFLOW: { group: string; rows: { key: WKey; label: string; hint: string; unit: string; min: number; max: number }[] }[] = [
  {
    group: 'Quotes',
    rows: [
      { key: 'quoteValidityDays', label: 'Quotes are valid for', hint: 'After this the customer can no longer accept; the request is cancelled.', unit: 'days', min: 1, max: 365 },
      { key: 'quoteReminderDays', label: 'Remind the customer before a quote expires', hint: 'One email, this many days before the expiry date. 0 sends none.', unit: 'days', min: 0, max: 60 },
    ],
  },
  {
    group: 'Accounts',
    rows: [
      { key: 'approvalReminderHours', label: 'Remind admins of waiting sign-ups after', hint: 'Sent to the New registrations list.', unit: 'hours', min: 1, max: 720 },
      { key: 'purgeAfterDays', label: 'Delete rejected or expired accounts after', hint: 'Personal data is removed; audit entries are anonymised.', unit: 'days', min: 1, max: 3650 },
    ],
  },
  {
    group: 'Carts',
    rows: [{ key: 'cartInactivityDays', label: 'Empty inactive carts after', hint: 'Counted from the last change to the cart.', unit: 'days', min: 1, max: 3650 }],
  },
]
const quoteExample = computed(() => {
  const d = Number(workflow.value?.quoteValidityDays)
  return Number.isInteger(d) && d > 0 ? formatDate(new Date(Date.now() + d * 864e5).toISOString()) : null
})
const saveWorkflow = async () =>
  !busy.value &&
  (await checkForm(workflowForm.value)) &&
  run(
    'workflow',
    async () => {
      const body = Object.fromEntries(Object.entries(workflow.value!).map(([k, v]) => [k, Number(v)])) as WorkflowSettings
      workflow.value = await call(() => catalog.PUT('/settings/general', { body }))
      workflowSaved.value = snap(workflow.value)
    },
    'Workflow settings saved',
  )

// ---- reference
const departments = ref<string[]>([])
const departmentsSaved = ref('[]')
const departmentsDirty = computed(() => snap(departments.value) !== departmentsSaved.value)
const projects = ref<Project[]>([])
// Project names and Active switches are staged here and saved with the section (no save-on-blur).
const projectEdits = reactive<Record<string, { name: string; active: boolean }>>({})
watch(
  projects,
  (list) => {
    for (const p of list) projectEdits[p.code] ??= { name: p.name, active: !!p.active }
  },
  { flush: 'sync' },
)
const changedProjects = computed(() =>
  projects.value.filter((p) => {
    const e = projectEdits[p.code]
    return !!e && (e.name.trim() !== p.name || e.active !== !!p.active)
  }),
)
const referenceDirty = computed(() => departmentsDirty.value || changedProjects.value.length > 0)
const referenceForm = ref<FormLike | null>(null)
const saveReference = async () =>
  !busy.value &&
  (await checkForm(referenceForm.value)) &&
  run(
    'reference',
    async () => {
      if (departmentsDirty.value) {
        await call(() => catalog.PUT('/reference/departments', { body: { values: departments.value.map((d) => d.trim()).filter(Boolean) } }))
        departments.value = [...(await reloadReference()).departments]
        departmentsSaved.value = snap(departments.value)
      }
      // One project at a time: if one is refused, those before it are saved and the rest stay marked unsaved.
      for (const p of [...changedProjects.value]) {
        const e = projectEdits[p.code]!
        const body = { ...(e.name.trim() !== p.name ? { name: e.name.trim() } : {}), ...(e.active !== !!p.active ? { active: e.active } : {}) }
        const saved = await call(() => catalog.PATCH('/reference/projects/{code}', { params: { path: { code: p.code } }, body }))
        projects.value = projects.value.map((x) => (x.code === saved.code ? saved : x))
        projectEdits[saved.code] = { name: saved.name, active: !!saved.active }
      }
      await reloadReference()
    },
    'Reference saved',
  )
const newProject = reactive({ code: '', name: '' })
async function loadProjects() {
  const all = await call(() => catalog.GET('/reference', { params: { query: { includeInactive: true } } }))
  projects.value = [...all.projects]
}
const addProject = () => {
  if (busy.value) return
  // Add is never disabled: a missing code or name is marked.
  const missing: Record<string, string> = {}
  if (!newProject.code.trim()) missing.code = 'Enter a code'
  if (!newProject.name.trim()) missing.projectName = 'Enter a name'
  if (Object.keys(missing).length) {
    errors.value = missing
    document.getElementById(missing.code ? 'np-code' : 'np-name')?.focus()
    return
  }
  return run(
    'project',
    async () => {
      const p = await call(() => catalog.POST('/reference/projects', { body: { code: newProject.code.trim(), name: newProject.name.trim(), active: true } }))
      projects.value = [...projects.value, p]
      Object.assign(newProject, { code: '', name: '' })
      await reloadReference()
    },
    'Project added',
  )
}

const dirtyOf: Record<string, () => boolean> = {
  fees: () => feesDirty.value,
  lists: () => listsDirty.value,
  workflow: () => workflowDirty.value,
  reference: () => referenceDirty.value,
}

// Leaving with unsaved sections asks first (sections keep their edits while you move between them here).
const unsaved = computed(() => SECTIONS.filter((s) => dirtyOf[s.value]!()))
const leaveOpen = ref(false)
let answer: ((leave: boolean) => void) | null = null
function decideLeave(leave: boolean) {
  leaveOpen.value = false
  answer?.(leave)
  answer = null
}
watch(leaveOpen, (open) => !open && answer && decideLeave(false)) // Esc or a click outside = stay
onBeforeRouteLeave(() => {
  // Signed out or session ended: nothing can be saved any more, don't hold the redirect.
  if (!unsaved.value.length || !session.isLoggedIn) return true
  leaveOpen.value = true
  return new Promise<boolean>((resolve) => (answer = resolve))
})
const beforeUnload = (e: BeforeUnloadEvent) => {
  if (unsaved.value.length) e.preventDefault()
}
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))

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
    feesSaved.value = snap(fees.value)
    for (const def of LISTS) lists[def.key] = l[def.key].map((m) => m.accountId)
    listsSaved.value = snap(lists)
    workflow.value = w
    workflowSaved.value = snap(w)
    staff.value = [...adminPage.items, ...staffPage.items]
    departments.value = [...(reference.value ?? (await reloadReference())).departments]
    departmentsSaved.value = snap(departments.value)
    await loadProjects()
    loaded.value = true
  } catch (e) {
    notify.report(e)
  }
})
</script>

<template>
  <div class="settings">
    <h1 class="t-h1">Settings</h1>

    <div class="frame">
      <nav class="index" aria-label="Settings sections">
        <div class="console-head"><h2 class="console-title">Sections</h2></div>
        <ul ref="indexList">
          <li v-if="marker.ready" class="marker" role="presentation" :class="{ moves: marker.placed }" aria-hidden="true" :style="{ transform: `translate(${marker.x}px, ${marker.y}px)`, width: `${marker.w}px`, height: `${marker.h}px` }" />
          <li v-for="s in SECTIONS" :key="s.value">
            <a
              :href="`/admin/settings?tab=${s.value}`"
              class="sec"
              :class="{ on: tab === s.value }"
              :aria-current="tab === s.value ? 'page' : undefined"
              @click.prevent="tab = s.value"
            >
              <v-icon :icon="s.icon" size="20" />
              <span class="sec-text">
                <span class="sec-title">{{ s.title }}<Transition name="dot"><span v-if="dirtyOf[s.value]!()" class="dot" title="Unsaved changes"><span class="sr-only">(unsaved changes)</span></span></Transition></span>
                <span class="sec-desc">{{ s.desc }}</span>
              </span>
            </a>
          </li>
        </ul>
      </nav>

      <section class="pane" :aria-labelledby="`h-${tab}`">
        <div class="console-head">
          <h2 :id="`h-${tab}`" class="console-title">{{ current.title }}</h2>
        </div>

        <div v-if="!loaded" class="body" aria-busy="true">
          <div v-for="n in 4" :key="n" class="console-skel sk" />
        </div>

        <Transition v-else name="pane" mode="out-in">
          <!-- Fees -->
          <v-form v-if="tab === 'fees'" key="fees" ref="feesForm" class="body" @submit.prevent="saveFees">
            <p class="lede">Fees added once to every request quoted from CIMH stock, in BBD. Supplier lines carry no fee.</p>
            <div class="ledger">
              <div class="l-head fee-grid" aria-hidden="true"><span>Name</span><span>Amount</span><span /></div>
              <TransitionGroup tag="div" name="lrow">
                <div v-for="(f, i) in fees" :key="i" class="l-row fee-grid">
                  <v-text-field v-model="f.name" label="Name" :rules="[(v: string) => !!v.trim() || 'Required']" hide-details="auto" />
                  <v-text-field v-model="f.fee" label="Amount" prefix="BBD" inputmode="decimal" class="amount" :rules="[money]" hide-details="auto" />
                  <v-btn variant="text" :icon="mdiDeleteOutline" :aria-label="`Remove fee ${f.name || i + 1}`" @click="fees.splice(i, 1)" />
                </div>
              </TransitionGroup>
              <p v-if="!fees.length" class="l-empty t-body muted">No fees: CIMH-stock quotes are priced at catalogue cost only.</p>
              <div class="l-foot fee-grid">
                <v-btn class="m3" variant="text" :prepend-icon="mdiPlus" @click="fees.push({ name: fees.length ? '' : 'admin', fee: '' })">Add fee</v-btn>
                <span v-if="fees.length" class="total"><span class="muted">Per request</span> <span class="console-mono">BBD {{ feesTotal }}</span></span>
              </div>
            </div>
            <div class="save-bar">
              <SaveState :dirty="feesDirty" :saved="justSaved === 'fees'" />
              <v-btn type="submit" class="m3" color="primary" variant="flat" :loading="busy === 'fees'" :disabled="!feesDirty">Save fees</v-btn>
            </div>
          </v-form>

          <!-- Email lists -->
          <form v-else-if="tab === 'lists'" key="lists" class="body" @submit.prevent="saveLists">
            <p class="lede">Who gets the staff emails. Only active staff and administrators can be added.</p>
            <p v-if="emptyLists" class="warn"><v-icon :icon="mdiAlertOutline" size="18" />{{ emptyLists }} {{ emptyLists === 1 ? 'list has' : 'lists have' }} nobody on it: those emails are not sent.</p>
            <div class="ledger">
              <div v-for="l in LISTS" :key="l.key" class="l-row set-grid">
                <div class="set-label">
                  <span class="set-title">{{ l.title }}</span>
                  <span class="set-hint">{{ l.hint }}</span>
                  <span class="set-count console-mono" :class="{ none: !lists[l.key]!.length }">
                    <template v-if="lists[l.key]!.length">{{ lists[l.key]!.length }} {{ lists[l.key]!.length === 1 ? 'person' : 'people' }}</template>
                    <template v-else><v-icon :icon="mdiAlertOutline" size="14" />Nobody</template>
                  </span>
                </div>
                <v-autocomplete
                  v-model="lists[l.key]"
                  :items="staffItems"
                  :label="l.title"
                  multiple
                  chips
                  closable-chips
                  hide-details="auto"
                  :error-messages="Object.entries(errors).filter(([k]) => k.startsWith(l.key + '[')).map(([, v]) => v)"
                />
              </div>
            </div>
            <div class="save-bar">
              <SaveState :dirty="listsDirty" :saved="justSaved === 'lists'" />
              <v-btn type="submit" class="m3" color="primary" variant="flat" :loading="busy === 'lists'" :disabled="!listsDirty">Save email lists</v-btn>
            </div>
          </form>

          <!-- Workflow -->
          <v-form v-else-if="tab === 'workflow' && workflow" key="workflow" ref="workflowForm" class="body" @submit.prevent="saveWorkflow">
            <p class="lede">Time limits the services apply on their own. Changes apply to what happens next, not to dates already set.</p>
            <section v-for="g in WORKFLOW" :key="g.group" class="ledger" :aria-label="g.group">
              <h3 class="l-group">{{ g.group }}</h3>
              <div v-for="r in g.rows" :key="r.key" class="l-row set-grid">
                <label class="set-label" :for="`wf-${r.key}`">
                  <span class="set-title">{{ r.label }}</span>
                  <span class="set-hint">
                    {{ r.hint }}
                    <template v-if="r.key === 'quoteValidityDays' && quoteExample"> A quote sent today runs until {{ quoteExample }}.</template>
                  </span>
                </label>
                <v-text-field
                  :id="`wf-${r.key}`"
                  v-model.number="workflow[r.key]"
                  type="number"
                  :suffix="r.unit"
                  class="num"
                  :rules="[whole(r.min, r.max)]"
                  hide-details="auto"
                />
              </div>
            </section>
            <div class="save-bar">
              <SaveState :dirty="workflowDirty" :saved="justSaved === 'workflow'" />
              <v-btn type="submit" class="m3" color="primary" variant="flat" :loading="busy === 'workflow'" :disabled="!workflowDirty">Save workflow settings</v-btn>
            </div>
          </v-form>

          <!-- Reference -->
          <v-form v-else-if="tab === 'reference'" key="reference" ref="referenceForm" class="body" @submit.prevent="saveReference">
            <section class="ledger" aria-label="Departments">
              <h3 class="l-group">Departments</h3>
              <div class="l-row set-grid">
                <div class="set-label">
                  <span class="set-title">Departments products can belong to</span>
                  <span class="set-hint">Press Enter after each name. Products keep their department if it is removed here.</span>
                </div>
                <v-combobox v-model="departments" label="Departments" multiple chips closable-chips hide-details />
              </div>
            </section>

            <section class="ledger" aria-labelledby="h-projects">
              <h3 id="h-projects" class="l-group">Projects</h3>
              <p class="lede">Projects group Pro Bono items in the catalogue. A deactivated project disappears from the filters. Changes to names and Active are saved with Save reference.</p>
              <div class="l-head proj-grid" aria-hidden="true"><span>Code</span><span>Name</span><span>Active</span></div>
              <TransitionGroup tag="div" name="lrow">
                <div v-for="p in projects" :key="p.code" class="l-row proj-grid" :class="{ off: !projectEdits[p.code]!.active }">
                  <span class="console-mono code">{{ p.code }}</span>
                  <v-text-field
                    v-model="projectEdits[p.code]!.name"
                    hide-details="auto"
                    maxlength="200"
                    :aria-label="`Name of project ${p.code}`"
                    :rules="[(v: string) => !!String(v ?? '').trim() || 'Enter a name']"
                  />
                  <v-switch
                    v-model="projectEdits[p.code]!.active"
                    color="primary"
                    hide-details
                    inset
                    density="compact"
                    :aria-label="`Project ${p.code} active`"
                  />
                </div>
              </TransitionGroup>
              <p v-if="!projects.length" class="l-empty t-body muted">No projects yet.</p>
              <!-- Not a nested form: Enter in these two fields adds the project (it is created at once). -->
              <div class="l-row proj-grid add" role="group" aria-label="Add a project">
                <v-text-field id="np-code" v-model="newProject.code" label="New code" hint="Letters, digits, - and _" persistent-hint class="mono-in" :error-messages="errors.code" @keydown.enter.prevent="addProject" />
                <v-text-field id="np-name" v-model="newProject.name" label="Name" :error-messages="errors.projectName ?? errors.name" @keydown.enter.prevent="addProject" />
                <v-btn class="m3" variant="outlined" :prepend-icon="mdiPlus" :loading="busy === 'project'" @click="addProject">Add project</v-btn>
              </div>
            </section>
            <div class="save-bar">
              <SaveState :dirty="referenceDirty" :saved="justSaved === 'reference'" />
              <v-btn type="submit" class="m3" color="primary" variant="flat" :loading="busy === 'reference'" :disabled="!referenceDirty">Save reference</v-btn>
            </div>
          </v-form>
        </Transition>
      </section>
    </div>

    <v-dialog v-model="leaveOpen" max-width="480">
      <v-card>
        <v-card-title class="t-h3">Leave without saving?</v-card-title>
        <v-divider />
        <v-card-text>
          <p class="t-body">
            {{ unsaved.length === 1 ? 'This section has' : 'These sections have' }} changes that are not saved:
            <strong>{{ unsaved.map((s) => s.title).join(', ') }}</strong>. If you leave now they are lost.
          </p>
        </v-card-text>
        <v-card-actions class="row-end">
          <v-btn class="m3" variant="text" @click="decideLeave(true)">Leave without saving</v-btn>
          <v-btn class="m3" color="primary" variant="flat" @click="decideLeave(false)">Keep editing</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.settings {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  max-width: 1200px;
  margin-inline: auto;
  padding: var(--sp-4) var(--sp-6) var(--sp-6);
  font-size: 14px;
}
.frame {
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr);
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
}
.index {
  border-right: 1px solid rgb(var(--v-theme-seam));
}
.index ul {
  position: relative;
  list-style: none;
  margin: 0;
  padding: var(--sp-2) 0;
}
.sec {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
  padding: 10px var(--sp-4);
  color: inherit;
  text-decoration: none;
  transition: background-color 120ms ease;
}
.sec .v-icon {
  margin-top: 1px;
  color: rgb(var(--v-theme-secondary));
}
.sec:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.sec.on {
  background: rgb(var(--v-theme-surface-variant));
}
.marker {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
  box-shadow: inset -2px 0 rgb(var(--v-theme-primary));
}
.marker.moves {
  transition: transform 300ms var(--ease-out), width 300ms var(--ease-out), height 300ms var(--ease-out);
}
.sec {
  position: relative;
}
.sec.on .v-icon {
  color: rgb(var(--v-theme-primary));
}
.sec.on .sec-title {
  font-weight: 600;
}
.sec:focus-visible {
  outline-offset: -2px;
}
.sec-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.sec-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  line-height: 20px;
}
.sec-desc {
  font-size: 12px;
  line-height: 16px;
  color: rgb(var(--v-theme-secondary));
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: rgb(var(--v-theme-primary));
}
.pane {
  min-width: 0;
}
.body {
  display: flex;
  flex-direction: column;
  gap: var(--sp-6);
  padding: var(--sp-4) var(--sp-6) 0;
}
.sk {
  height: 48px;
  border-radius: 4px;
}
.body > .sk:last-child {
  margin-bottom: var(--sp-6);
}
.lede {
  margin: 0;
  max-width: 68ch;
  color: rgb(var(--v-theme-secondary));
}
.warn {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin: 0;
  font-weight: 500;
  color: rgb(var(--v-theme-warning));
}
.ledger {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.l-group {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 22px;
}
.l-head {
  font-size: 12px;
  font-weight: 500;
  color: rgb(var(--v-theme-secondary));
  padding-bottom: 4px;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.l-row {
  padding: var(--sp-3) 0;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.l-head + div > .l-row:first-child,
.l-group + .l-row,
.lede + .l-head {
  border-top: 0;
}
.l-group + .l-row {
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.l-row.off .code {
  color: rgb(var(--v-theme-secondary));
  text-decoration: line-through;
}
.l-empty {
  margin: 0;
  padding: var(--sp-3) 0;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.l-foot {
  align-items: center;
  padding-top: var(--sp-1);
}
.l-foot.end {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-3);
}
.fee-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 220px 40px;
  gap: var(--sp-3);
  align-items: start;
}
.l-foot.fee-grid {
  grid-template-columns: max-content minmax(0, 1fr);
}
.total {
  justify-self: end;
  padding-right: 52px;
  font-size: 13px;
}
.amount :deep(input) {
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  font-variant-numeric: tabular-nums;
}
.set-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
  gap: var(--sp-6);
  align-items: start;
}
.set-label {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.set-title {
  font-weight: 500;
  line-height: 20px;
}
.set-hint {
  font-size: 13px;
  line-height: 18px;
  color: rgb(var(--v-theme-secondary));
  max-width: 52ch;
}
.set-count {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  font-size: 12px;
  color: rgb(var(--v-theme-secondary));
}
.set-count.none {
  color: rgb(var(--v-theme-warning));
}
.num {
  max-width: 200px;
}
.num :deep(input) {
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  font-variant-numeric: tabular-nums;
}
.proj-grid {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr) max-content;
  gap: var(--sp-3);
  align-items: center;
}
.proj-grid.add {
  align-items: start;
  border-bottom: 0;
}
.code {
  font-size: 13px;
}
.mono-in :deep(input) {
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
}
.save-bar {
  position: sticky;
  bottom: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--sp-3);
  margin: 0 calc(-1 * var(--sp-6));
  padding: var(--sp-3) var(--sp-6);
  border-top: 1px solid rgb(var(--v-theme-seam));
  background: rgb(var(--v-theme-surface));
}
.body > div:last-child:not(.save-bar),
.body > section:last-child {
  margin-bottom: var(--sp-6);
}
.dot-enter-active {
  animation: dot-pop 260ms var(--ease-out) both;
}
.dot-leave-active {
  transition: opacity 160ms ease-in, transform 160ms ease-in;
}
.dot-leave-to {
  opacity: 0;
  transform: scale(0.4);
}
@keyframes dot-pop {
  from {
    opacity: 0;
    transform: scale(0.2);
  }
  60% {
    transform: scale(1.3);
  }
}
.pane-enter-active {
  transition: opacity 200ms var(--ease-out), transform 200ms var(--ease-out);
}
.pane-enter-from {
  opacity: 0;
  transform: translateX(8px);
}
.pane-leave-active {
  transition: opacity 100ms ease-in;
}
.pane-leave-to {
  opacity: 0;
}
.lrow-enter-active {
  transition: opacity 200ms var(--ease-out), transform 200ms var(--ease-out);
}
.lrow-enter-from,
.lrow-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
.lrow-leave-active {
  transition: opacity 120ms ease-in, transform 120ms ease-in;
}
@media (max-width: 899.98px) {
  .frame {
    grid-template-columns: minmax(0, 1fr);
  }
  .index {
    border-right: 0;
    border-bottom: 1px solid rgb(var(--v-theme-seam));
  }
  .index .console-head {
    display: none;
  }
  .index ul {
    display: flex;
    overflow-x: auto;
    padding: 0;
    scrollbar-width: none;
  }
  .sec {
    padding: 10px var(--sp-4);
    white-space: nowrap;
  }
  .marker {
    box-shadow: inset 0 -2px rgb(var(--v-theme-primary));
  }
  .sec-desc {
    display: none;
  }
  .set-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--sp-2);
  }
}
@media (max-width: 599.98px) {
  .settings {
    padding: var(--sp-3) var(--sp-4) var(--sp-6);
  }
  .body {
    padding: var(--sp-4) var(--sp-4) 0;
  }
  .save-bar {
    margin: 0 calc(-1 * var(--sp-4));
    padding: var(--sp-3) var(--sp-4);
  }
  .fee-grid {
    grid-template-columns: minmax(0, 1fr) 40px;
  }
  .fee-grid .amount {
    grid-column: 1;
  }
  .fee-grid > .v-btn {
    grid-row: 1;
    grid-column: 2;
  }
  .l-head.fee-grid {
    display: none;
  }
  .total {
    padding-right: 0;
  }
  .proj-grid {
    grid-template-columns: minmax(0, 1fr) max-content;
  }
  .proj-grid > .code {
    grid-column: 1 / -1;
  }
  .l-head.proj-grid {
    display: none;
  }
  .proj-grid.add > .v-btn {
    grid-column: 1 / -1;
    justify-self: start;
  }
}
@media (prefers-reduced-motion: reduce) {
  .marker.moves {
    transition: none;
  }
  .dot-enter-active {
    animation: none;
  }
  .dot-leave-to,
  .pane-enter-from,
  .lrow-enter-from,
  .lrow-leave-to {
    transform: none;
  }
}
</style>
