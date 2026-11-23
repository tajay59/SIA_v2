<script setup lang="ts">
/**
 * Outstanding payments at sign-in (owner, 2026-11-23; redesigned as a statement, impeccable): when a customer signs
 * in with delivered paid requests that have no proof of payment yet, a statement opens. Navy head (the SHOP band
 * with its logo-blue rule): what is owed in total and over how many requests. Below, a ruled ledger: what was
 * requested, short ref + delivery date, the amount aligned right (or "On the invoice" when none is on record, never
 * a false 0.00); a row opens the request. Foot: Continue · Go to orders (→ the list filtered on Payment required).
 * Once per account per tab session (sessionStorage), so moving around the store does not repeat it.
 */
import { call, orders, type RequestSummary, requestTitle, shortRef, useSession } from '@cimh/web-app'
import { formatDate, formatMoney } from '@cimh/web-ui'
import { mdiChevronRight } from '@mdi/js'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'

const session = useSession()
const router = useRouter()
const { xs } = useDisplay()
const open = ref(false)
const due = ref<RequestSummary[]>([])
const more = ref(false)

const key = (id: string) => `cimh.payments-shown.${id}`
function seen(id: string): boolean {
  try {
    return sessionStorage.getItem(key(id)) === '1'
  } catch {
    return false
  }
}
function markSeen(id: string) {
  try {
    sessionStorage.setItem(key(id), '1')
  } catch {
    /* private window: it may show again */
  }
}

async function check(accountId: string) {
  try {
    const query = { scope: 'mine', payment: 'due', limit: 20, sort: 'newest' }
    const page = (await call(() => orders.GET('/requests', { params: { query: query as any } }))) as {
      items: RequestSummary[]
      nextCursor: string | null
    }
    markSeen(accountId)
    if (!page.items.length || session.account?.id !== accountId) return
    due.value = page.items
    more.value = !!page.nextCursor
    open.value = true
  } catch {
    /* not an account that can list requests yet (pending approval, say): nothing to show */
  }
}

watch(
  () => (session.isCustomer ? session.account?.id : null),
  (id) => {
    if (!id) {
      open.value = false
      return
    }
    if (!seen(id)) void check(id)
  },
  { immediate: true },
)

const currency = (r: RequestSummary) => r.currency ?? 'BBD'
const amount = (r: RequestSummary) => (r.amountDue ? formatMoney(r.amountDue, currency(r)) : null)
/** The total of the amounts on record, per currency (legacy requests may be USD). */
const totals = computed(() => {
  const sums = new Map<ReturnType<typeof currency>, number>()
  for (const r of due.value) if (r.amountDue) sums.set(currency(r), (sums.get(currency(r)) ?? 0) + Math.round(Number(r.amountDue) * 100))
  return [...sums].map(([c, cents]) => formatMoney((cents / 100).toFixed(2), c))
})
const unpriced = computed(() => due.value.filter((r) => !r.amountDue).length)
const count = computed(() => `${due.value.length}${more.value ? '+' : ''}`)
const countWords = computed(() => (due.value.length === 1 && !more.value ? '1 delivered request' : `${count.value} delivered requests`))

function goToOrders() {
  open.value = false
  void router.push({ path: '/requests', query: { status: 'payment' } })
}
function openOne(id: string) {
  open.value = false
  void router.push(`/requests/${id}`)
}
</script>

<template>
  <v-dialog v-model="open" max-width="600" :fullscreen="xs" scrollable aria-labelledby="pay-title">
    <v-card class="statement" rounded="lg">
      <header class="head">
        <h2 id="pay-title" class="head-title">Payment due</h2>
        <p class="head-sum">
          <span v-if="totals.length" class="head-total">{{ totals.join(' + ') }}</span>
          <span class="head-of">
            on {{ countWords }}<template v-if="unpriced && totals.length">, {{ unpriced }} priced on the invoice</template>
          </span>
        </p>
      </header>

      <v-card-text class="body">
        <p class="lead">
          Pay each invoice, then open the request and send CIMH the proof of payment: a bank receipt or transfer
          confirmation.
        </p>
        <ul class="ledger" aria-label="Requests waiting for payment">
          <li v-for="r in due" :key="r.id">
            <button type="button" class="entry" @click="openOne(r.id)">
              <span class="entry-main">
                <span class="entry-title">{{ requestTitle(r.firstItemName, r.lineCount, r.type) }}</span>
                <span class="entry-meta">
                  <span class="t-mono">{{ shortRef(r.id) }}</span>
                  <span v-if="r.updatedAt" class="nowrap"> · delivered {{ formatDate(r.updatedAt) }}</span>
                </span>
              </span>
              <span v-if="amount(r)" class="entry-amount">{{ amount(r) }}</span>
              <span v-else class="entry-amount unknown">On the invoice</span>
              <v-icon :icon="mdiChevronRight" size="18" class="entry-go" aria-hidden="true" />
            </button>
          </li>
        </ul>
        <p v-if="more" class="more">More are listed on the Orders page.</p>
      </v-card-text>

      <footer class="foot">
        <v-btn variant="text" @click="open = false">Continue</v-btn>
        <v-btn color="primary" variant="flat" @click="goToOrders">Go to orders</v-btn>
      </footer>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.statement {
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
/* The SHOP band: navy field, logo-blue rule (masthead, cart, Orders). Same in both themes. */
.head {
  flex: none;
  background: #0a2e4a;
  color: #fff;
  border-bottom: 4px solid #0084c8;
  padding: var(--sp-6) var(--sp-6) var(--sp-5, 20px);
}
.head-title {
  margin: 0;
  font-size: 15px;
  line-height: 20px;
  font-weight: 600;
  color: rgb(255 255 255 / 0.78);
}
.head-sum {
  margin: var(--sp-2) 0 0;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--sp-1) var(--sp-3);
}
.head-total {
  font-size: clamp(28px, 4vw + 12px, 36px);
  line-height: 1.1;
  font-weight: 700;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.head-of {
  font-size: 15px;
  line-height: 22px;
  color: rgb(255 255 255 / 0.86);
}
.head-sum:not(:has(.head-total)) .head-of {
  font-size: 20px;
  line-height: 28px;
  font-weight: 600;
  color: #fff;
}

.body {
  padding: var(--sp-5, 20px) var(--sp-6) var(--sp-2) !important;
}
.lead {
  margin: 0 0 var(--sp-4);
  max-width: 60ch;
  font-size: 15px;
  line-height: 22px;
}
.ledger {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.ledger li {
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.entry {
  width: 100%;
  min-height: 56px;
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-1) var(--sp-3) var(--sp-2);
  background: none;
  border: 0;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background-color 140ms ease-out;
}
.entry:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.entry:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.entry-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.entry-title {
  font-size: 15px;
  line-height: 22px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.entry-meta {
  font-size: 13px;
  line-height: 18px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.nowrap {
  white-space: nowrap;
}
.entry-amount {
  flex: none;
  font-size: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.entry-amount.unknown {
  font-size: 13px;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.entry-go {
  flex: none;
  opacity: 0.5;
  transition: transform 160ms ease-out, opacity 160ms ease-out;
}
.entry:hover .entry-go,
.entry:focus-visible .entry-go {
  opacity: 1;
  transform: translateX(2px);
}
.more {
  margin: var(--sp-3) 0 0;
  font-size: 14px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.foot {
  flex: none;
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
  padding: var(--sp-4) var(--sp-6) var(--sp-5, 20px);
}
@media (max-width: 599.98px) {
  .head,
  .foot {
    padding-inline: var(--sp-4);
  }
  .body {
    padding-inline: var(--sp-4) !important;
  }
  .foot {
    flex-direction: column-reverse;
    align-items: stretch;
  }
}
@media (prefers-reduced-motion: reduce) {
  .entry,
  .entry-go {
    transition: none;
  }
}
</style>
