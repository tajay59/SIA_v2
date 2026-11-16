<script setup lang="ts">
/**
 * Quote comparison (DESIGN_BRIEF "quote comparison"): one row per line, the supplier option and the CIMH-stock
 * option side by side, the admin fee and the expiry. With `v-model` (S-12 step 1) each line that has both
 * options gets a choice and the total follows the choices; lines with one option use it.
 * Narrow containers (< 600 px, e.g. phones) get one card per line with full-width option tiles instead of
 * the table, whose price columns wrapped one character per line at 360 px.
 */
import { formatDate, formatMoney } from '@cimh/web-ui'
import { mdiCheck } from '@mdi/js'
import { computed } from 'vue'
import { addCents, type LineChoice, type OrderRequest, quoteRows } from '../orders'

// `picked` (read-only, S-11 after the customer chose): marks the chosen option per line and shows the agreement total.
const props = defineProps<{ request: OrderRequest; choosable?: boolean; staff?: boolean; picked?: Record<string, LineChoice> }>()
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

/** Read-only: the option the customer chose for each line (a line offered one way uses that way). */
const marks = computed<Record<string, LineChoice | null>>(() => {
  const out: Record<string, LineChoice | null> = {}
  if (props.choosable || !props.picked) return out
  for (const { line, cimh, supplier } of table.value.rows)
    out[line.lineId] = cimh && supplier ? (props.picked[line.lineId] ?? null) : cimh ? 'CIMH' : supplier ? 'SUPPLIER' : null
  return out
})
const cell = (lineId: string, c: LineChoice) => {
  const m = marks.value[lineId]
  return m ? (m === c ? 'on' : 'off') : undefined
}
const agreed = computed(() => (!props.choosable && props.picked ? (props.request.agreement?.total ?? null) : null))

function pick(lineId: string, c: LineChoice) {
  choices.value = { ...choices.value, [lineId]: c }
}
</script>

<template>
  <div class="quote">
    <!-- Narrow: one card per line -->
    <ol class="cards" :aria-label="choosable ? 'Choose an option for each item' : 'Quoted items'">
      <li v-for="{ line, supplier, cimh } in table.rows" :key="line.lineId" class="card">
        <div class="card-head">
          <span class="t-label">{{ line.product.name }}</span>
          <span class="t-caption muted tnum">Qty {{ line.qty }}</span>
        </div>
        <span v-if="staff && supplier?.supplier" class="t-caption muted">{{ supplier.supplier }}</span>
        <v-radio-group
          v-if="choosable && supplier && cimh"
          :model-value="choices[line.lineId]"
          hide-details
          class="tiles"
          :aria-label="`Option for ${line.product.name}`"
          @update:model-value="(v: unknown) => pick(line.lineId, v as LineChoice)"
        >
          <v-radio value="SUPPLIER" class="tile" :class="{ on: choices[line.lineId] === 'SUPPLIER' }">
            <template #label>
              <span class="opt"><span>{{ staff ? 'Supplier' : 'Supplier (ordered for you)' }}</span>
                <strong class="tnum">{{ money(supplier.total) }}</strong>
                <span class="t-caption muted tnum">{{ money(supplier.unitPrice) }} each</span></span>
            </template>
          </v-radio>
          <v-radio value="CIMH" class="tile" :class="{ on: choices[line.lineId] === 'CIMH' }">
            <template #label>
              <span class="opt"><span>From CIMH stock</span>
                <strong class="tnum">{{ money(cimh.total) }}</strong>
                <span class="t-caption muted tnum">{{ money(cimh.unitPrice) }} each</span></span>
            </template>
          </v-radio>
        </v-radio-group>
        <dl v-else class="opts">
          <div :class="cell(line.lineId, 'SUPPLIER')">
            <dt>
              {{ staff ? 'Supplier' : 'Supplier (ordered for you)' }}
              <span v-if="marks[line.lineId] === 'SUPPLIER'" class="chosen"><v-icon :icon="mdiCheck" size="14" />Chosen</span>
            </dt>
            <dd v-if="supplier" class="tnum"><span class="price">{{ money(supplier.total) }}</span> <span class="t-caption muted">({{ money(supplier.unitPrice) }} each)</span></dd>
            <dd v-else class="muted">Not offered</dd>
          </div>
          <div :class="cell(line.lineId, 'CIMH')">
            <dt>
              From CIMH stock
              <span v-if="marks[line.lineId] === 'CIMH'" class="chosen"><v-icon :icon="mdiCheck" size="14" />Chosen</span>
            </dt>
            <dd v-if="cimh" class="tnum"><span class="price">{{ money(cimh.total) }}</span> <span class="t-caption muted">({{ money(cimh.unitPrice) }} each)</span></dd>
            <dd v-else class="muted">Not in stock</dd>
          </div>
        </dl>
      </li>
    </ol>
    <dl class="card-foot">
      <div v-if="request.adminFee && request.adminFee !== '0.00'">
        <dt>Admin fee</dt>
        <dd class="tnum">{{ money(request.adminFee) }}</dd>
      </div>
      <div v-if="choosable" class="total">
        <dt>Total for your choices</dt>
        <dd class="tnum">{{ complete ? money(total) : 'Choose every item' }}</dd>
      </div>
      <div v-else-if="agreed" class="total">
        <dt>Agreement total</dt>
        <dd class="tnum">{{ money(agreed) }}</dd>
      </div>
    </dl>

    <!-- Wide: comparison table -->
    <v-table density="comfortable" class="wide">
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
          <td class="num" :class="cell(line.lineId, 'SUPPLIER')">
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
              <span v-else class="tnum price">{{ money(supplier.total) }}</span>
              <span class="t-caption muted d-block tnum">{{ money(supplier.unitPrice) }} each</span>
              <span v-if="marks[line.lineId] === 'SUPPLIER'" class="chosen"><v-icon :icon="mdiCheck" size="14" />Chosen</span>
            </template>
            <span v-else class="muted">Not offered</span>
          </td>
          <td class="num" :class="cell(line.lineId, 'CIMH')">
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
              <span v-else class="tnum price">{{ money(cimh.total) }}</span>
              <span class="t-caption muted d-block tnum">{{ money(cimh.unitPrice) }} each</span>
              <span v-if="marks[line.lineId] === 'CIMH'" class="chosen"><v-icon :icon="mdiCheck" size="14" />Chosen</span>
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
        <tr v-else-if="agreed" class="total">
          <td colspan="3">Agreement total</td>
          <td class="num tnum">{{ money(agreed) }}</td>
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
.quote {
  container-type: inline-size;
}
.cards,
.card-foot {
  display: none;
}
@container (max-width: 599px) {
  .wide {
    display: none;
  }
  .cards {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
    list-style: none;
    padding: 0;
    margin: 0;
  }
  .card-foot {
    display: block;
    margin: var(--sp-3) 0 0;
  }
}
.card {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-3);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}
.card-head {
  display: flex;
  justify-content: space-between;
  gap: var(--sp-2);
  overflow-wrap: anywhere;
}
.tiles :deep(.v-selection-control-group) {
  gap: var(--sp-2);
}
.tile {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  padding: var(--sp-1) var(--sp-2) var(--sp-1) 0;
}
.tile.on {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: inset 0 0 0 1px rgb(var(--v-theme-primary));
}
.tile :deep(.v-label) {
  opacity: 1;
  width: 100%;
}
.opt {
  display: flex;
  flex-direction: column;
  padding: var(--sp-1) 0;
}
.opts,
.card-foot {
  margin: 0;
}
.opts > div,
.card-foot > div {
  display: flex;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: 2px 0;
}
.opts dd,
.card-foot dd {
  margin: 0;
  text-align: right;
}
.card-foot .total {
  font-weight: 600;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding-top: var(--sp-2);
  margin-top: var(--sp-1);
}
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
/* Read-only after choosing: the chosen option carries the weight and a "Chosen" mark; the other steps back. */
.on .price {
  font-weight: 600;
}
.off,
.off .price {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.off .price {
  text-decoration: line-through;
}
.chosen {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
  white-space: nowrap;
}
td .chosen {
  display: flex;
  justify-content: flex-end;
}
.meta {
  margin-top: var(--sp-2);
}
</style>
