<script setup lang="ts">
/** A-18 organisations: search, create/edit (admin), merge a duplicate into another (admin). Staff read. */
import {
  ApiError,
  call,
  countries,
  countryName,
  identity,
  ifMatch,
  type Organisation,
  useCursorList,
  useNotify,
  useSession,
} from '@cimh/web-app'
import { mdiMagnify, mdiPlus } from '@mdi/js'
import { onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import OrganisationPicker from '../../components/OrganisationPicker.vue'

definePage({ meta: { guard: 'staff', title: 'Organisations' } })

const session = useSession()
const notify = useNotify()
const q = ref('')
const list = useCursorList<Organisation>((cursor) =>
  call(() => identity.GET('/organisations', { params: { query: { q: q.value.trim() || undefined, cursor, limit: 50 } } })),
)
onMounted(list.reload)
let timer: ReturnType<typeof setTimeout> | undefined
// A pending debounce must not fire after the page is left (router.replace would navigate back here).
onBeforeUnmount(() => clearTimeout(timer))
watch(q, () => {
  clearTimeout(timer)
  timer = setTimeout(() => void list.reload(), 250)
})

const TYPES = [
  { value: 'met_service', title: 'Meteorological service' },
  { value: 'hydro_service', title: 'Hydrological service' },
  { value: 'government', title: 'Government' },
  { value: 'academic', title: 'Academic' },
  { value: 'other', title: 'Other' },
]
const typeTitle = (t?: string | null) => TYPES.find((x) => x.value === t)?.title ?? '—'

// create / edit
const editOpen = ref(false)
const editing = ref<Organisation | null>(null)
const form = reactive({ name: '', country: 'BB', type: 'met_service' as Organisation['type'], emailDomains: [] as string[], aliases: [] as string[], active: true })
const formValid = ref(false)
const busy = ref(false)
function openEdit(o: Organisation | null) {
  editing.value = o
  Object.assign(form, {
    name: o?.name ?? '',
    country: o?.country ?? 'BB',
    type: o?.type ?? 'met_service',
    emailDomains: [...(o?.emailDomains ?? [])],
    aliases: [...(o?.aliases ?? [])],
    active: o?.active ?? true,
  })
  editOpen.value = true
}
async function save() {
  busy.value = true
  const body = { ...form, name: form.name.trim(), emailDomains: form.emailDomains.map((d) => d.trim().toLowerCase()).filter(Boolean) }
  try {
    const o = editing.value
    if (o)
      await call(() =>
        identity.PATCH('/organisations/{organisationId}', {
          params: { path: { organisationId: o.id }, header: { 'If-Match': ifMatch(o.version) } },
          body,
        }),
      )
    else await call(() => identity.POST('/organisations', { body }))
    notify.toast(o ? 'Organisation saved' : 'Organisation created', 'success')
    editOpen.value = false
    void list.reload()
  } catch (e) {
    if (e instanceof ApiError && e.code === 'DUPLICATE') notify.toast('An organisation with this name already exists.', 'warning')
    else notify.report(e, { retry: list.reload })
  } finally {
    busy.value = false
  }
}

// merge
const mergeOpen = ref(false)
const source = ref<Organisation | null>(null)
const mergeTarget = ref<Organisation | null>(null)
function openMerge(o: Organisation) {
  source.value = o
  mergeTarget.value = null
  mergeOpen.value = true
}
async function merge() {
  const s = source.value
  const t = mergeTarget.value
  if (!s || !t) return
  busy.value = true
  try {
    await call(() => identity.POST('/organisations/{organisationId}/merge', { params: { path: { organisationId: s.id } }, body: { targetId: t.id } }))
    notify.toast(`${s.name} merged into ${t.name}`, 'success')
    mergeOpen.value = false
    void list.reload()
  } catch (e) {
    notify.report(e)
  } finally {
    busy.value = false
  }
}

const headers = [
  { title: 'Name', key: 'name', sortable: false },
  { title: 'Type', key: 'type', sortable: false },
  { title: 'Country', key: 'country', sortable: false },
  { title: 'Email domains', key: 'emailDomains', sortable: false },
  { title: 'Members', key: 'memberCount', sortable: false, align: 'end' as const },
  { title: '', key: 'actions', sortable: false, align: 'end' as const },
]
</script>

<template>
  <div class="page">
    <div class="page-header">
      <v-text-field v-model="q" :prepend-inner-icon="mdiMagnify" label="Search organisations" clearable hide-details class="search" @click:clear="q = ''" />
      <span class="spacer" />
      <v-btn v-if="session.isAdmin" color="primary" :prepend-icon="mdiPlus" @click="openEdit(null)">New organisation</v-btn>
    </div>
    <v-card>
      <v-data-table :headers="headers" :items="list.items.value" :loading="list.loading.value" item-value="id" :items-per-page="-1" hide-default-footer>
        <template #[`item.name`]="{ item }">
          <div class="stack-sm py-2">
            <span class="t-body">{{ item.name }} <v-chip v-if="item.active === false" size="x-small" class="ml-1">Inactive</v-chip></span>
            <span v-if="item.aliases?.length" class="t-caption muted">Also: {{ item.aliases.join(', ') }}</span>
          </div>
        </template>
        <template #[`item.type`]="{ item }">{{ typeTitle(item.type) }}</template>
        <template #[`item.country`]="{ item }">{{ countryName(item.country) }}</template>
        <template #[`item.emailDomains`]="{ item }"><span class="t-mono">{{ (item.emailDomains ?? []).join(', ') || '—' }}</span></template>
        <template #[`item.memberCount`]="{ item }"><span class="tnum">{{ item.memberCount ?? 0 }}</span></template>
        <template #[`item.actions`]="{ item }">
          <div v-if="session.isAdmin" class="row-end">
            <v-btn size="small" variant="text" @click="openEdit(item)">Edit</v-btn>
            <v-btn size="small" variant="text" @click="openMerge(item)">Merge…</v-btn>
          </div>
        </template>
        <template #no-data><p class="t-body pa-6">No organisations found.</p></template>
      </v-data-table>
      <div v-if="list.nextCursor.value" class="row-end pa-4">
        <v-btn variant="outlined" :loading="list.loading.value" @click="list.loadMore">Load more</v-btn>
      </div>
    </v-card>

    <v-dialog v-model="editOpen" max-width="560" scrollable>
      <v-card>
        <v-card-title class="t-h3">{{ editing ? 'Edit organisation' : 'New organisation' }}</v-card-title>
        <v-card-text>
          <v-form v-model="formValid" class="stack" @submit.prevent="save">
            <v-text-field v-model="form.name" label="Name" :rules="[(v: string) => !!v.trim() || 'Required', (v: string) => v.length <= 200 || 'At most 200 characters']" />
            <div class="grid-2">
              <v-autocomplete v-model="form.country" label="Country" :items="countries()" />
              <v-select v-model="form.type" label="Type" :items="TYPES" />
            </div>
            <v-combobox v-model="form.emailDomains" label="Email domains" multiple chips closable-chips hint="Press Enter after each, e.g. barbados.gov.bb" persistent-hint />
            <v-combobox v-model="form.aliases" label="Other names (aliases)" multiple chips closable-chips hint="Help match sign-ups that spell it differently" persistent-hint />
            <v-switch v-model="form.active" label="Active" color="primary" hide-details inset />
          </v-form>
        </v-card-text>
        <v-card-actions class="row-end">
          <v-btn variant="text" @click="editOpen = false">Cancel</v-btn>
          <v-btn color="primary" :loading="busy" :disabled="!formValid" @click="save">Save</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="mergeOpen" max-width="520">
      <v-card>
        <v-card-title class="t-h3">Merge {{ source?.name }}</v-card-title>
        <v-card-text class="stack">
          <p class="t-body muted">Members and request visibility move to the organisation you choose. {{ source?.name }} becomes inactive. This can't be undone.</p>
          <OrganisationPicker v-model="mergeTarget" label="Merge into" :exclude-id="source?.id" />
        </v-card-text>
        <v-card-actions class="row-end">
          <v-btn variant="text" @click="mergeOpen = false">Cancel</v-btn>
          <v-btn color="error" :loading="busy" :disabled="!mergeTarget" @click="merge">Merge</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.search {
  max-width: 420px;
}
</style>
