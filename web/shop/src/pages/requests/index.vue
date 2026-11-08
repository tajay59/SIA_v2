<script setup lang="ts">
/**
 * S-10 My requests, in the legacy SHOP Orders ("Transaction History") structure: page title, a row of filter
 * chips with the year selector beside them, then one list of requests (icon, id, date, ship-to organisation,
 * status). v2: chips switch Mine / My organisation; a status filter; an "action needed" badge (quote ready,
 * agreement to sign); "Load more" paging.
 */
import { call, customerActionNeeded, orders, type RequestStatus, type RequestSummary, StatusChip, useCursorList } from '@cimh/web-app'
import { formatDate } from '@cimh/web-ui'
import { mdiClipboardTextOutline, mdiGiftOutline, mdiPackageVariant } from '@mdi/js'
import { ref, watch } from 'vue'

definePage({ meta: { guard: 'customer', title: 'My requests' } })

const scope = ref<'mine' | 'organisation'>('mine')
const thisYear = new Date().getFullYear()
const years = Array.from({ length: thisYear - 2019 }, (_, i) => thisYear - i)
const year = ref<number | null>(null)
const STATUS_GROUPS: { title: string; value: RequestStatus[] | null }[] = [
  { title: 'All statuses', value: null },
  { title: 'Needs my action', value: ['QUOTED', 'AWAITING_AGREEMENT'] },
  { title: 'In progress', value: ['SUBMITTED', 'QUOTING', 'ACCEPTED', 'PURCHASING', 'APPROVED', 'PICKING', 'SHIPPED'] },
  { title: 'Delivered', value: ['DELIVERED'] },
  { title: 'Closed', value: ['CANCELLED', 'REJECTED', 'DECLINED'] },
]
const status = ref<RequestStatus[] | null>(null)

const list = useCursorList<RequestSummary>(async (cursor) => {
  const query: Record<string, unknown> = { scope: scope.value, limit: 25, sort: 'newest' }
  if (cursor) query.cursor = cursor
  if (year.value) query.year = year.value
  if (status.value) query.status = status.value.join(',')
  return (await call(() => orders.GET('/requests', { params: { query: query as any } }))) as {
    items: RequestSummary[]
    nextCursor: string | null
  }
})
watch([scope, year, status], () => void list.reload(), { immediate: true })
</script>

<template>
  <v-container class="page" max-width="1200">
    <div class="page-header"><h1 class="t-h1">My requests</h1></div>
    <v-divider />

    <div class="filters">
      <v-chip-group v-model="scope" mandatory selected-class="text-primary" aria-label="Whose requests">
        <v-chip value="mine" variant="outlined" filter>Mine</v-chip>
        <v-chip value="organisation" variant="outlined" filter>My organisation</v-chip>
      </v-chip-group>
      <v-select v-model="status" :items="STATUS_GROUPS" label="Status" density="compact" hide-details class="filter" />
      <v-select v-model="year" :items="[{ title: 'Any year', value: null }, ...years.map((y) => ({ title: String(y), value: y }))]"
                label="Year" density="compact" hide-details class="filter year" />
    </div>

    <v-skeleton-loader v-if="list.loading.value && !list.loaded.value" type="list-item-avatar-three-line@4" />
    <v-card v-else-if="list.loaded.value && !list.items.value.length" class="empty" flat border>
      <v-icon :icon="mdiClipboardTextOutline" size="40" class="muted" />
      <h2 class="t-h3">No requests found</h2>
      <p class="t-body muted">Add items from the catalogue to your cart, then send them as a request.</p>
      <v-btn to="/catalogue" color="primary">Browse the catalogue</v-btn>
    </v-card>
    <v-list v-else lines="three" rounded="lg" border class="list">
      <v-list-subheader>Requests</v-list-subheader>
      <template v-for="(r, i) in list.items.value" :key="r.id">
        <v-divider v-if="i" />
        <v-list-item :to="`/requests/${r.id}`">
          <template #prepend>
            <v-avatar :color="r.type === 'PROBONO' ? 'warning' : 'surface-variant'">
              <v-icon :icon="r.type === 'PROBONO' ? mdiGiftOutline : mdiPackageVariant" />
            </v-avatar>
          </template>
          <v-list-item-title class="t-mono">{{ r.id }}</v-list-item-title>
          <v-list-item-subtitle>
            {{ formatDate(r.submittedAt) }} · {{ r.lineCount }} {{ r.lineCount === 1 ? 'item' : 'items' }}
            <template v-if="scope === 'organisation'"> · {{ r.customerName }}</template>
            <template v-if="r.type === 'PROBONO'"> · Pro Bono</template>
          </v-list-item-subtitle>
          <template #append>
            <div class="right">
              <StatusChip :status="r.status" />
              <v-chip v-if="customerActionNeeded(r)" color="primary" variant="flat" size="small" label>
                {{ customerActionNeeded(r) }}
              </v-chip>
            </div>
          </template>
        </v-list-item>
      </template>
    </v-list>
    <div v-if="list.nextCursor.value" class="more">
      <v-btn variant="outlined" :loading="list.loading.value" @click="list.loadMore">Load more</v-btn>
    </div>
  </v-container>
</template>

<style scoped>
.filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-3);
  margin: var(--sp-4) 0;
}
.filter {
  max-width: 220px;
}
.filter.year {
  max-width: 150px;
}
.empty {
  padding: var(--sp-12) var(--sp-6);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-3);
  text-align: center;
}
.right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--sp-1);
}
.more {
  display: flex;
  justify-content: center;
  margin: var(--sp-4) 0;
}
</style>
