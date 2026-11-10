<script setup lang="ts">
/** A-17 accounts list: filter by status, role and name/email prefix. Staff can read; admins act on detail. */
import { type AccountSummary, call, identity, StatusChip, useCursorList } from '@cimh/web-app'
import { formatDate } from '@cimh/web-ui'
import { mdiMagnify } from '@mdi/js'
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

definePage({ meta: { guard: 'staff', title: 'Accounts' } })

const route = useRoute()
const router = useRouter()
type Status = AccountSummary['status']
const status = ref<Status | null>((route.query.status as Status) || null)
const role = ref<AccountSummary['role'] | null>((route.query.role as AccountSummary['role']) || null)
const q = ref(typeof route.query.q === 'string' ? route.query.q : '')
const erasure = ref(route.query.erasure === '1')

const list = useCursorList<AccountSummary>((cursor) =>
  call(() =>
    identity.GET('/admin/accounts', {
      params: {
        query: {
          status: status.value ?? undefined,
          role: role.value ?? undefined,
          q: q.value.trim() || undefined,
          erasureRequested: erasure.value || undefined,
          cursor,
          limit: 50,
        },
      },
    }),
  ),
)
onMounted(list.reload)

let timer: ReturnType<typeof setTimeout> | undefined
watch([status, role, q, erasure], () => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    void router.replace({ query: { ...(status.value ? { status: status.value } : {}), ...(role.value ? { role: role.value } : {}), ...(q.value ? { q: q.value } : {}), ...(erasure.value ? { erasure: '1' } : {}) } })
    void list.reload()
  }, 250)
})

const STATUSES = ['PENDING_VERIFICATION', 'PENDING_APPROVAL', 'ACTIVE', 'SUSPENDED', 'REJECTED', 'EXPIRED'].map((v) => ({
  value: v,
  title: v.charAt(0) + v.slice(1).toLowerCase().replace(/_/g, ' '),
}))
const ROLES = [
  { value: 'user', title: 'Customer' },
  { value: 'staff', title: 'Staff' },
  { value: 'admin', title: 'Administrator' },
]
const roleTitle = (r: string) => ROLES.find((x) => x.value === r)?.title ?? r
const headers = [
  { title: 'Name', key: 'name', sortable: false },
  { title: 'Email', key: 'email', sortable: false },
  { title: 'Organisation', key: 'organisation', sortable: false },
  { title: 'Role', key: 'role', sortable: false },
  { title: 'Status', key: 'status', sortable: false },
  { title: 'Created', key: 'createdAt', sortable: false },
]
</script>

<template>
  <div class="page">
    <div class="filters">
      <v-text-field v-model="q" data-page-search :prepend-inner-icon="mdiMagnify" label="Name or email starts with" clearable hide-details @click:clear="q = ''" />
      <v-select v-model="status" :items="STATUSES" label="Status" clearable hide-details />
      <v-select v-model="role" :items="ROLES" label="Role" clearable hide-details />
      <v-checkbox v-model="erasure" label="Asked to be deleted" hide-details density="compact" />
    </div>
    <v-card>
      <v-data-table
        :headers="headers"
        :items="list.items.value"
        :loading="list.loading.value"
        item-value="id"
        :items-per-page="-1"
        hide-default-footer
        hover
        @click:row="(_e: unknown, row: { item: AccountSummary }) => router.push(`/admin/accounts/${row.item.id}`)"
      >
        <template #[`item.name`]="{ item }">
          <router-link :to="`/admin/accounts/${item.id}`">{{ item.firstname }} {{ item.lastname }}</router-link>
        </template>
        <template #[`item.organisation`]="{ item }">
          {{ item.organisationName ?? (item.organisationText ? `${item.organisationText} (unlinked)` : item.isCimh ? 'CIMH' : '—') }}
        </template>
        <template #[`item.role`]="{ item }">{{ roleTitle(item.role) }}</template>
        <template #[`item.status`]="{ item }">
          <div class="row"><StatusChip :status="item.status" /><v-chip v-if="item.erasureRequestedAt" size="small" color="error" variant="tonal">Delete requested</v-chip></div>
        </template>
        <template #[`item.createdAt`]="{ item }"><span class="tnum">{{ item.createdAt ? formatDate(item.createdAt) : '—' }}</span></template>
        <template #no-data><p class="t-body pa-6">No accounts match these filters.</p></template>
      </v-data-table>
      <div v-if="list.nextCursor.value" class="row-end pa-4">
        <v-btn variant="outlined" :loading="list.loading.value" @click="list.loadMore">Load more</v-btn>
      </div>
    </v-card>
  </div>
</template>

<style scoped>
.filters {
  display: grid;
  grid-template-columns: minmax(240px, 2fr) repeat(2, minmax(160px, 1fr)) max-content;
  align-items: center;
  gap: var(--sp-3);
  margin-bottom: var(--sp-4);
}
@media (max-width: 760px) {
  .filters {
    grid-template-columns: 1fr;
  }
}
</style>
