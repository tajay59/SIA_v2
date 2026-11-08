<script setup lang="ts">
/** A-14 who has what: units issued to people (grouped by person), with Return. Filter by one person. */
import { type AccountSummary, call, inventory, newScanKey, scan, scanError, type Unit, useAccountNames, useCursorList, useNotify } from '@cimh/web-app'
import { formatDateTime } from '@cimh/web-ui'
import { onMounted, ref, watch } from 'vue'
import PersonPicker from '../../components/PersonPicker.vue'

definePage({ meta: { guard: 'staff', title: 'Who has what' } })
const notify = useNotify()
const { name } = useAccountNames()
const person = ref<AccountSummary | null>(null)
const returning = ref<string | null>(null)

const list = useCursorList<Unit>((cursor) =>
  call(() => inventory.GET('/assignments', { params: { query: { accountId: person.value?.id, cursor, limit: 50 } } })),
)
onMounted(list.reload)
watch(person, () => void list.reload())

async function giveBack(u: Unit) {
  returning.value = u.barcode
  try {
    await scan('/unassign', { unit: u.barcode }, newScanKey())
    list.items.value = list.items.value.filter((x) => x.barcode !== u.barcode)
    notify.toast(`${u.productName ?? u.barcode} returned. Stow it on a shelf.`, 'success')
  } catch (e) {
    notify.toast(scanError(e), 'error')
  } finally {
    returning.value = null
  }
}
</script>

<template>
  <div class="page stack">
    <div class="finder"><PersonPicker v-model="person" label="Only this person" clearable hide-details /></div>
    <v-skeleton-loader v-if="!list.loaded.value && list.loading.value" type="table-row@4" />
    <p v-else-if="list.loaded.value && !list.items.value.length" class="t-body">No units are issued{{ person ? ` to ${person.firstname}` : '' }}.</p>
    <v-table v-else density="comfortable">
      <thead><tr><th>Person</th><th>Product</th><th>Unit</th><th>Serial</th><th>Stowed last</th><th /></tr></thead>
      <tbody>
        <tr v-for="u in list.items.value" :key="u.barcode">
          <td>{{ name(u.assignedTo) }}</td>
          <td><router-link :to="`/products/${u.product}`">{{ u.productName ?? u.product }}</router-link></td>
          <td class="t-mono">{{ u.barcode }}</td>
          <td class="t-mono">{{ u.serial ?? '' }}</td>
          <td class="t-caption">{{ u.stowDate ? formatDateTime(u.stowDate) : '' }}</td>
          <td class="text-right"><v-btn size="small" variant="text" :loading="returning === u.barcode" @click="giveBack(u)">Return</v-btn></td>
        </tr>
      </tbody>
    </v-table>
    <v-btn v-if="list.nextCursor.value" variant="text" :loading="list.loading.value" @click="list.loadMore">Load more</v-btn>
  </div>
</template>

<style scoped>
.page {
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
}
.finder {
  max-width: 420px;
}
</style>
