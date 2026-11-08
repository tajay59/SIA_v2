<script setup lang="ts">
/** A-15 movement history, newest first. Filters: unit, person, operation, date range (America/Barbados days). */
import { type AccountSummary, call, type HistoryEntry, inventory, type Operation, OPERATION_LABELS, useAccountNames, useCursorList } from '@cimh/web-app'
import { formatDateTime } from '@cimh/web-ui'
import { onMounted, ref, watch } from 'vue'
import PersonPicker from '../../components/PersonPicker.vue'

definePage({ meta: { guard: 'staff', title: 'Movement history' } })
const { name } = useAccountNames()

const unit = ref('')
const person = ref<AccountSummary | null>(null)
const operation = ref<Operation | null>(null)
const from = ref('')
const to = ref('')
const opItems = (Object.keys(OPERATION_LABELS) as Operation[]).map((k) => ({ value: k, title: OPERATION_LABELS[k] }))

// Day boundaries in Barbados time (UTC-4, no DST).
const dayStart = (d: string) => (d ? `${d}T00:00:00-04:00` : undefined)
const dayEnd = (d: string) => (d ? `${d}T23:59:59-04:00` : undefined)

const list = useCursorList((cursor) =>
  call(() =>
    inventory.GET('/history', {
      params: {
        query: {
          unit: unit.value.trim() || undefined,
          user: person.value?.id,
          operation: operation.value ?? undefined,
          from: dayStart(from.value),
          to: dayEnd(to.value),
          cursor,
          limit: 50,
        },
      },
    }),
  ),
)
onMounted(list.reload)

function details(h: HistoryEntry): string[] {
  const out: string[] = []
  if (h.accountId) out.push(`${h.operation === 'assign' ? 'to' : 'from'} ${name(h.accountId)}`)
  if (h.orderId) out.push(`request ${h.orderId}`)
  if (h.reason) out.push(h.reason)
  return out
}
watch([person, operation, from, to], () => void list.reload())

</script>

<template>
  <div class="page stack">
    <form class="filters" @submit.prevent="list.reload">
      <v-text-field v-model="unit" label="Unit code" hide-details clearable @click:clear="(unit = ''), list.reload()" />
      <PersonPicker v-model="person" label="Scanned by" clearable hide-details />
      <v-select v-model="operation" :items="opItems" label="Operation" hide-details clearable />
      <v-text-field v-model="from" type="date" label="From" hide-details />
      <v-text-field v-model="to" type="date" label="To" hide-details />
      <v-btn type="submit" variant="tonal">Apply</v-btn>
    </form>

    <v-skeleton-loader v-if="!list.loaded.value && list.loading.value" type="table-row@6" />
    <p v-else-if="list.loaded.value && !list.items.value.length" class="t-body">No movements match.</p>
    <v-table v-else density="compact">
      <thead><tr><th>When</th><th>What</th><th>Unit</th><th>By</th><th>Details</th></tr></thead>
      <tbody>
        <tr v-for="(h, i) in list.items.value" :key="`${h.unit}-${h.date}-${i}`">
          <td class="tnum t-caption">{{ formatDateTime(h.date) }}</td>
          <td>{{ OPERATION_LABELS[h.operation] }}</td>
          <td class="t-mono"><router-link :to="{ path: '/inventory', query: { op: 'lookup', code: h.unit } }">{{ h.unit }}</router-link></td>
          <td>{{ name(h.user) }}</td>
          <td class="t-caption">
            <span v-for="(d, j) in details(h)" :key="j"><template v-if="j"> · </template>{{ d }}</span>
            <template v-if="h.shelf">
              <template v-if="details(h).length"> · </template>
              <router-link :to="{ path: '/inventory', query: { op: 'lookup', code: h.shelf } }">{{ h.operation === 'pick' ? 'from shelf' : 'shelf' }}</router-link>
            </template>
          </td>
        </tr>
      </tbody>
    </v-table>
    <v-btn v-if="list.nextCursor.value" variant="text" :loading="list.loading.value" @click="list.loadMore">Load more</v-btn>
  </div>
</template>

<style scoped>
.page {
  max-width: 1300px;
  margin: 0 auto;
  width: 100%;
}
.filters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--sp-3);
  align-items: center;
}
</style>
