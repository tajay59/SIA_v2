<script setup lang="ts">
/** A-20 audit log (admin), newest first. Filters: entity type/id, action, date range. */
import { type AuditEntry, call, identity, useCursorList } from '@cimh/web-app'
import { formatDateTime, statusLabel } from '@cimh/web-ui'
import { onMounted, reactive, watch } from 'vue'

definePage({ meta: { guard: 'admin', title: 'Audit log' } })

const f = reactive({ entityType: '', entityId: '', action: '', from: '', to: '' })
const iso = (d: string, end = false) => (d ? new Date(`${d}T${end ? '23:59:59' : '00:00:00'}`).toISOString() : undefined)
const list = useCursorList<AuditEntry>((cursor) =>
  call(() =>
    identity.GET('/audit', {
      params: {
        query: {
          entityType: f.entityType || undefined,
          entityId: f.entityId.trim() || undefined,
          action: f.action.trim() || undefined,
          from: iso(f.from),
          to: iso(f.to, true),
          cursor,
          limit: 50,
        },
      },
    }),
  ),
)
onMounted(list.reload)
let timer: ReturnType<typeof setTimeout> | undefined
watch(f, () => {
  clearTimeout(timer)
  timer = setTimeout(() => void list.reload(), 300)
})

const ENTITY_TYPES = [
  { value: 'account', title: 'Account' },
  { value: 'organisation', title: 'Organisation' },
]
const show = (v: unknown) => (v === null || v === undefined ? '—' : typeof v === 'string' ? statusLabel(v) : JSON.stringify(v))
const link = (e: AuditEntry) =>
  e.entity.type === 'account' ? `/admin/accounts/${e.entity.id}` : e.entity.type === 'organisation' ? '/admin/organisations' : null
const headers = [
  { title: 'When', key: 'at', sortable: false },
  { title: 'Who', key: 'actor', sortable: false },
  { title: 'Action', key: 'action', sortable: false },
  { title: 'Entity', key: 'entity', sortable: false },
  { title: 'Change', key: 'change', sortable: false },
]
</script>

<template>
  <div class="page">
    <div class="filters">
      <v-select v-model="f.entityType" :items="ENTITY_TYPES" label="Entity" clearable hide-details />
      <v-text-field v-model="f.entityId" label="Entity id" hide-details class="t-mono" />
      <v-text-field v-model="f.action" label="Action (e.g. account.approved)" hide-details />
      <v-text-field v-model="f.from" type="date" label="From" hide-details />
      <v-text-field v-model="f.to" type="date" label="To" hide-details />
    </div>
    <v-card>
      <v-data-table :headers="headers" :items="list.items.value" :loading="list.loading.value" item-value="id" :items-per-page="-1" hide-default-footer>
        <template #[`item.at`]="{ item }"><span class="tnum">{{ formatDateTime(item.at) }}</span></template>
        <template #[`item.actor`]="{ item }">{{ item.actor.name }} <span class="t-caption muted">({{ item.actor.role }})</span></template>
        <template #[`item.action`]="{ item }"><span class="t-mono">{{ item.action }}</span></template>
        <template #[`item.entity`]="{ item }">
          <router-link v-if="link(item)" :to="link(item)!" class="t-mono">{{ item.entity.type }} {{ item.entity.id }}</router-link>
          <span v-else class="t-mono">{{ item.entity.type }} {{ item.entity.id }}</span>
        </template>
        <template #[`item.change`]="{ item }">
          <span>{{ show(item.from) }} → {{ show(item.to) }}</span>
          <div v-if="item.reason" class="t-caption muted">“{{ item.reason }}”</div>
        </template>
        <template #no-data><p class="t-body pa-6">No entries match these filters.</p></template>
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
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: var(--sp-3);
  margin-bottom: var(--sp-4);
}
</style>
