<script setup lang="ts">
/** A-16 pending accounts, oldest first (J-08). Single or bulk approve/deny (up to 100). */
import { type AccountSummary, call, identity, useCursorList } from '@cimh/web-app'
import { formatAge, formatDate } from '@cimh/web-ui'
import { mdiAccountCheckOutline } from '@mdi/js'
import { computed, onMounted, ref } from 'vue'
import DecisionDialog from '../../components/DecisionDialog.vue'

definePage({ meta: { guard: 'admin', title: 'Pending accounts' } })

const list = useCursorList<AccountSummary>((cursor) =>
  call(() => identity.GET('/admin/accounts', { params: { query: { status: 'PENDING_APPROVAL', cursor, limit: 50 } } })),
)
onMounted(list.reload)

const selected = ref<string[]>([])
const dialog = ref(false)
const decision = ref<'approve' | 'deny'>('approve')
const target = ref<AccountSummary[]>([])
const chosen = computed(() => list.items.value.filter((a) => selected.value.includes(a.id)))

function decide(d: 'approve' | 'deny', accounts: AccountSummary[]) {
  decision.value = d
  target.value = accounts
  dialog.value = true
}

function done(okIds: string[]) {
  selected.value = selected.value.filter((id) => !okIds.includes(id))
  void list.reload()
}

const headers = [
  { title: 'Name', key: 'name', sortable: false },
  { title: 'Email', key: 'email', sortable: false },
  { title: 'Organisation given', key: 'organisationText', sortable: false },
  { title: 'Waiting', key: 'createdAt', sortable: false },
  { title: '', key: 'actions', sortable: false, align: 'end' as const },
]
</script>

<template>
  <div class="page">
    <div class="page-header">
      <p class="t-body muted prose">
        Check each organisation and email domain, then approve (linking an organisation) or deny with a reason.
      </p>
      <span class="spacer" />
      <template v-if="selected.length">
        <span class="t-label">{{ selected.length }} selected</span>
        <v-btn color="primary" @click="decide('approve', chosen)">Approve selected</v-btn>
        <v-btn variant="outlined" color="error" @click="decide('deny', chosen)">Deny selected</v-btn>
      </template>
    </div>

    <v-card>
      <v-data-table
        v-model="selected"
        :headers="headers"
        :items="list.items.value"
        :loading="list.loading.value"
        item-value="id"
        show-select
        :items-per-page="-1"
        hide-default-footer
      >
        <template #[`item.name`]="{ item }">
          <router-link :to="`/admin/accounts/${item.id}`">{{ item.firstname }} {{ item.lastname }}</router-link>
        </template>
        <template #[`item.organisationText`]="{ item }">{{ item.organisationText || '—' }}</template>
        <template #[`item.createdAt`]="{ item }">
          <span :title="item.createdAt ? formatDate(item.createdAt) : ''">{{ item.createdAt ? formatAge(item.createdAt) : '—' }}</span>
        </template>
        <template #[`item.actions`]="{ item }">
          <div class="row-end">
            <v-btn size="small" color="primary" variant="tonal" @click="decide('approve', [item])">Approve</v-btn>
            <v-btn size="small" variant="text" color="error" @click="decide('deny', [item])">Deny</v-btn>
          </div>
        </template>
        <template #no-data>
          <div class="empty">
            <v-icon :icon="mdiAccountCheckOutline" size="36" class="muted" />
            <p class="t-body">No accounts are waiting for approval.</p>
          </div>
        </template>
      </v-data-table>
      <div v-if="list.nextCursor.value" class="row-end pa-4">
        <v-btn variant="outlined" :loading="list.loading.value" @click="list.loadMore">Load more</v-btn>
      </div>
    </v-card>

    <DecisionDialog v-model="dialog" :accounts="target" :decision="decision" @done="done" />
  </div>
</template>

<style scoped>
.empty {
  padding: var(--sp-8);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-2);
}
</style>
