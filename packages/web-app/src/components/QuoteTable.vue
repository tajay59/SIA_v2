<script setup lang="ts">
/**
 * The quote as the customer signs it ("view and sign", owner 2026-11-17; DESIGN_BRIEF "quote"): one row per line
 * with where it comes from (CIMH stock, or the supplier that ships it directly), its unit price and total; then
 * the items, the estimated shipping per source, the admin fee (once per request) and the total: "Total to sign" while
 * the quote waits, "Agreed total" once signed, "Quoted total" on a request that ended (one name per state, as S-12
 * and the agreement PDF say it).
 * Nothing to choose: staff fixed the source of every line when they sent the quote.
 * Narrow containers (< 600 px, e.g. phones) get one card per line instead of the table.
 */
import { formatDate, formatMoney } from '@cimh/web-ui'
import { computed } from 'vue'
import { type OrderRequest, type PricedLine, pricedQuote } from '../orders'

const props = defineProps<{ request: OrderRequest; staff?: boolean }>()

const cur = computed(() => props.request.currency ?? 'BBD')
const q = computed(() => pricedQuote(props.request))
const money = (v: string | null | undefined) => (v ? formatMoney(v, cur.value) : '—')
const from = (x: PricedLine) =>
  x.source === 'CIMH' ? 'CIMH stock' : x.source === 'SUPPLIER' ? `${x.supplier ?? 'Supplier'}, ships to you directly` : '—'
/** "120.00 USD at 2.0 BBD per USD" for a supplier price staff converted from the supplier's USD quote. */
const sourceNote = (x: PricedLine) =>
  x.converted ? `Supplier quote: ${formatMoney(x.converted.unitPrice, x.converted.currency)} each at ${x.converted.rate} BBD per USD` : ''
const expires = computed(() => props.request.quoteExpiresAt)
const SIGNED = new Set(['ACCEPTED', 'PURCHASING', 'SHIPPED', 'DELIVERED'])
const totalLabel = computed(() =>
  SIGNED.has(props.request.status) ? 'Agreed total' : props.request.status === 'QUOTED' || props.request.status === 'QUOTING' ? 'Total to sign' : 'Quoted total',
)
</script>

<template>
  <div class="quote">
    <!-- Narrow: one card per line -->
    <ol class="cards" aria-label="Quoted items">
      <li v-for="x in q.rows" :key="x.line.lineId" class="card">
        <div class="card-head">
          <span class="t-label">{{ x.line.product.name }}</span>
          <strong class="tnum">{{ money(x.total) }}</strong>
        </div>
        <div class="card-sub t-caption muted tnum">
          <span>{{ from(x) }}</span>
          <span>{{ x.line.qty }} × {{ money(x.unitPrice) }}</span>
        </div>
        <span v-if="sourceNote(x)" class="t-caption muted tnum">{{ sourceNote(x) }}</span>
      </li>
    </ol>
    <dl class="card-foot">
      <div>
        <dt>Items</dt>
        <dd class="tnum">{{ money(q.items) }}</dd>
      </div>
      <div v-for="s in q.shipping" :key="s.source + s.label">
        <dt>Estimated shipping, {{ s.label }}</dt>
        <dd class="tnum">{{ money(s.amount) }}</dd>
      </div>
      <div v-if="q.fee">
        <dt>Admin fee</dt>
        <dd class="tnum">{{ money(q.fee) }}</dd>
      </div>
      <div class="total">
        <dt>{{ totalLabel }}</dt>
        <dd class="tnum">{{ money(q.total) }}</dd>
      </div>
    </dl>

    <!-- Wide: one table -->
    <v-table density="comfortable" class="wide">
      <thead>
        <tr>
          <th>Item</th>
          <th>From</th>
          <th class="num">Qty</th>
          <th class="num">Each</th>
          <th class="num">Total</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="x in q.rows" :key="x.line.lineId">
          <td><span class="t-label">{{ x.line.product.name }}</span></td>
          <td>
            <span :class="['from', x.source === 'CIMH' ? 'cimh' : 'supplier']">{{ from(x) }}</span>
            <span v-if="sourceNote(x)" class="t-caption muted d-block tnum">{{ sourceNote(x) }}</span>
          </td>
          <td class="num tnum">{{ x.line.qty }}</td>
          <td class="num tnum">{{ money(x.unitPrice) }}</td>
          <td class="num tnum price">{{ money(x.total) }}</td>
        </tr>
      </tbody>
      <tfoot>
        <tr>
          <td colspan="4">Items</td>
          <td class="num tnum">{{ money(q.items) }}</td>
        </tr>
        <tr v-for="s in q.shipping" :key="s.source + s.label">
          <td colspan="4">Estimated shipping, {{ s.label }}</td>
          <td class="num tnum">{{ money(s.amount) }}</td>
        </tr>
        <tr v-if="q.fee">
          <td colspan="4">Admin fee (once per request)</td>
          <td class="num tnum">{{ money(q.fee) }}</td>
        </tr>
        <tr class="total">
          <td colspan="4">{{ totalLabel }}</td>
          <td class="num tnum">{{ money(q.total) }}</td>
        </tr>
      </tfoot>
    </v-table>
    <p class="t-caption muted meta">
      Quote version {{ q.version }}<template v-if="expires"> · valid until {{ formatDate(expires) }}</template>
      <template v-if="request.cimhQuote?.exchangeRate"> · exchange rate {{ request.cimhQuote.exchangeRate }} BBD per USD</template>
      <template v-if="!staff"> · shipping amounts are estimates; the total is what CIMH invoices</template>
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
    gap: var(--sp-2);
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
  gap: 2px;
  padding: var(--sp-3);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}
.card-head,
.card-sub {
  display: flex;
  justify-content: space-between;
  gap: var(--sp-2);
  overflow-wrap: anywhere;
}
.card-foot {
  margin: 0;
}
.card-foot > div {
  display: flex;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: 2px 0;
}
.card-foot dd {
  margin: 0;
  text-align: right;
  white-space: nowrap; /* "BBD 20.00" never breaks after the currency */
}
.card-foot .total {
  font-weight: 600;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding-top: var(--sp-2);
  margin-top: var(--sp-1);
}
.num {
  text-align: right;
  white-space: nowrap; /* amounts stay on one line ("BBD 150.00"); Item and From wrap instead (owner 2026-11-24) */
}
.total td {
  font-weight: 600;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.price {
  font-weight: 600;
}
.from {
  display: inline-block;
  font-size: 13px;
}
.meta {
  margin-top: var(--sp-2);
}
</style>
