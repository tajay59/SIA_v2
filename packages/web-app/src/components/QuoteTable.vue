<script setup lang="ts">
/**
 * Quote comparison (DESIGN_BRIEF "quote comparison"): one row per line, the supplier option and the CIMH-stock
 * option side by side, the admin fee and the expiry. With `v-model` (S-12 step 1) each line that has both
 * options gets a choice and the total follows the choices; lines with one option use it.
 */
import { formatDate, formatMoney } from '@cimh/web-ui'
import { computed } from 'vue'
import { addCents, type LineChoice, type OrderRequest, quoteRows } from '../orders'

const props = defineProps<{ request: OrderRequest; choosable?: boolean; staff?: boolean }>()
const choices = defineModel<Record<string, LineChoice>>({ default: () => ({}) })

const cur = computed(() => props.request.currency ?? 'BBD')
const table = computed(() => quoteRows(props.request))
const money = (v: string | null | undefined) => (v ? formatMoney(v, cur.value) : '—')

function chosen(lineId: string, hasCimh: boolean, hasSupplier: boolean): LineChoice | null {
  if (hasCimh && hasSupplier) return choices.value[lineId] ?? null
  return hasCimh ? 'CIMH' : hasSupplier ? 'SUPPLIER' : null
}
const total = computed(() => {
  const parts = table.value.rows.map(({ line, cimh, supplier }) => {
    const c = chosen(line.lineId, !!cimh, !!supplier)
    return c === 'CIMH' ? cimh?.total : c === 'SUPPLIER' ? supplier?.total : null
  })
  return addCents(...parts, props.request.adminFee)
})
const complete = computed(() =>
  table.value.rows.every(({ line, cimh, supplier }) => chosen(line.lineId, !!cimh, !!supplier) !== null),
)
const expires = computed(() => props.request.quoteExpiresAt)
defineExpose({ total, complete })

function pick(lineId: string, c: LineChoice) {
  choices.value = { ...choices.value, [lineId]: c }
}
</script>

<template>
  <div class="quote">
    <v-table density="comfortable">
      <thead>
        <tr>
          <th>Item</th>
          <th class="num">Qty</th>
          <th class="num">Supplier{{ staff ? '' : ' (ordered for you)' }}</th>
          <th class="num">From CIMH stock</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="{ line, supplier, cimh } in table.rows" :key="line.lineId">
          <td>
            <span class="t-label">{{ line.product.name }}</span>
            <span v-if="staff && supplier?.supplier" class="t-caption muted d-block">{{ supplier.supplier }}</span>
          </td>
          <td class="num tnum">{{ line.qty }}</td>
          <td class="num">
            <template v-if="supplier">
              <v-radio-group
                v-if="choosable && cimh"
                :model-value="choices[line.lineId]"
                hide-details
                density="compact"
                class="choice"
                :aria-label="`Option for ${line.product.name}`"
                @update:model-value="pick(line.lineId, 'SUPPLIER')"
              >
                <v-radio value="SUPPLIER" :label="money(supplier.total)" />
              </v-radio-group>
              <span v-else class="tnum">{{ money(supplier.total) }}</span>
              <span class="t-caption muted d-block tnum">{{ money(supplier.unitPrice) }} each</span>
            </template>
            <span v-else class="muted">Not offered</span>
          </td>
          <td class="num">
            <template v-if="cimh">
              <v-radio-group
                v-if="choosable && supplier"
                :model-value="choices[line.lineId]"
                hide-details
                density="compact"
                class="choice"
                @update:model-value="pick(line.lineId, 'CIMH')"
              >
                <v-radio value="CIMH" :label="money(cimh.total)" />
              </v-radio-group>
              <span v-else class="tnum">{{ money(cimh.total) }}</span>
              <span class="t-caption muted d-block tnum">{{ money(cimh.unitPrice) }} each</span>
            </template>
            <span v-else class="muted">Not in stock</span>
          </td>
        </tr>
      </tbody>
      <tfoot>
        <tr v-if="request.adminFee && request.adminFee !== '0.00'">
          <td colspan="3">Admin fee</td>
          <td class="num tnum">{{ money(request.adminFee) }}</td>
        </tr>
        <tr v-if="choosable" class="total">
          <td colspan="3">Total for your choices</td>
          <td class="num tnum">{{ complete ? money(total) : 'Choose every item' }}</td>
        </tr>
      </tfoot>
    </v-table>
    <p class="t-caption muted meta">
      Quote version {{ table.version }}<template v-if="expires"> · valid until {{ formatDate(expires) }}</template>
      <template v-if="request.cimhQuote?.exchangeRate"> · exchange rate {{ request.cimhQuote.exchangeRate }} BBD per USD</template>
    </p>
  </div>
</template>

<style scoped>
.num {
  text-align: right;
}
.choice {
  display: inline-flex;
  justify-content: flex-end;
}
.total td {
  font-weight: 600;
}
.meta {
  margin-top: var(--sp-2);
}
</style>
