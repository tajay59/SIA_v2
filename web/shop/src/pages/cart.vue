<script setup lang="ts">
/**
 * S-07 cart, S-08 submit and S-09 submitted ("Progress rule", impeccable 2026-11-16): a navy band carries the
 * request path (Cart → Invoice → Delivery → Sent) as four nodes on one rule that fills as the customer goes;
 * under it one question per screen. Request wording, not a webshop checkout: nothing is paid here, no prices
 * (quotes come later). Every quote is in BBD (owner, 2026-11-16: the currency question is gone; staff convert a
 * supplier's USD quote). A cart with both kinds becomes two requests.
 */
import { AddressDialog, call, identity, ifMatch, type OrderRequest, type ShippingAddress, useCart, useDraft, useNotify, useSession } from '@cimh/web-app'
import { mdiCartOutline, mdiCheck, mdiCheckCircleOutline, mdiClose, mdiMinus, mdiPlus } from '@mdi/js'
import { computed, nextTick, onMounted, ref, watch } from 'vue'

definePage({ meta: { guard: 'customer', title: 'Cart' } })
const cart = useCart()
const session = useSession()
const notify = useNotify()

const STEPS = [
  { n: 1, label: 'Cart' },
  { n: 2, label: 'Invoice' },
  { n: 3, label: 'Delivery' },
  { n: 4, label: 'Sent' },
] as const
const step = ref(1)
const dir = ref<'fwd' | 'back'>('fwd')
const heading = ref<HTMLElement | null>(null)
let moved = false
watch(step, (now, before) => {
  dir.value = now >= before ? 'fwd' : 'back'
  moved = true
})
// Each step change moves focus to the new question once its pane is in (out-in: it mounts after the old one
// leaves), so keyboard and screen-reader users land on it. The first load keeps the browser's focus.
function onEntered() {
  if (!moved) return
  window.scrollTo({ top: 0, behavior: 'instant' as ScrollBehavior })
  heading.value?.focus({ preventScroll: true })
}
function goTo(n: number) {
  if (n < step.value && step.value < 4) step.value = n
}

const loading = ref(true)
const busy = ref<string | null>(null)
onMounted(async () => {
  try {
    await cart.load()
  } catch (e) {
    notify.report(e)
  } finally {
    loading.value = false
  }
})

const lines = computed(() => cart.cart?.lines ?? [])
const paid = computed(() => lines.value.filter((l) => !l.product.probono))
const probono = computed(() => lines.value.filter((l) => l.product.probono))
const groups = computed(() =>
  [
    { key: 'paid', title: 'Items to be quoted', items: paid.value, free: false },
    { key: 'probono', title: 'Pro Bono items', items: probono.value, free: true },
  ].filter((g) => g.items.length),
)
const unavailable = computed(() => lines.value.some((l) => l.available === false))
const split = computed(() => paid.value.length > 0 && probono.value.length > 0)
const itemsWord = computed(() => `${cart.count} ${cart.count === 1 ? 'item' : 'items'}`)

async function setQty(productId: string, qty: number) {
  busy.value = productId
  try {
    await (qty < 1 ? cart.remove(productId) : cart.setQty(productId, qty))
  } catch (e) {
    notify.report(e)
  } finally {
    busy.value = null
  }
}
// A typed quantity: whole numbers only; 0 removes the line, anything else unreadable snaps back.
function typedQty(productId: string, current: number, el: HTMLInputElement) {
  const n = Number(el.value.trim())
  if (!Number.isInteger(n) || n < 0) {
    el.value = String(current)
    return
  }
  if (n !== current) void setQty(productId, n)
}

// ---- addresses
const saved = computed<ShippingAddress[]>(() => (session.account?.addresses ?? []) as ShippingAddress[])
const billTo = ref<ShippingAddress | null>(null)
const shipTo = ref<ShippingAddress | null>(null)
const sameAsBilling = ref(true)
const notes = ref('')
const dialogFor = ref<'bill' | 'ship' | null>(null)
const dialogOpen = computed({ get: () => dialogFor.value !== null, set: (v) => !v && (dialogFor.value = null) })
onMounted(() => {
  billTo.value = saved.value[0] ?? null
})
/** Two addresses are the same when every filled field matches (empty and missing count as equal). */
const KEYS = ['firstname', 'lastname', 'organisation', 'line1', 'line2', 'city', 'parish', 'zip', 'country', 'attention', 'email', 'tel'] as const
function same(a: ShippingAddress | null, b: ShippingAddress | null): boolean {
  if (!a || !b) return false
  const r = a as unknown as Record<string, unknown>
  const s = b as unknown as Record<string, unknown>
  return KEYS.every((k) => (r[k] ?? '') === (s[k] ?? ''))
}
/** Saved addresses, plus one in use that is not on the account (saving failed, or the list is full). */
const withExtra = (a: ShippingAddress | null) => (a && !saved.value.some((x) => same(x, a)) ? [...saved.value, a] : saved.value)
const billChoices = computed(() => withExtra(billTo.value))
const shipChoices = computed(() => withExtra(shipTo.value))

// Unsaved request (APD §2): kept if the session ends mid-way, restored after logging back in. Drafts saved
// before 2026-11-16 also carry `currency`; it is ignored.
interface Checkout {
  step: number
  billTo: ShippingAddress | null
  shipTo: ShippingAddress | null
  sameAsBilling: boolean
  notes: string
}
const draft = useDraft<Checkout>(
  () => (session.account && step.value < 4 ? `checkout:${session.account.id}` : null), // sent: nothing left to keep
  () => ({ step: Math.min(step.value, 3), billTo: billTo.value, shipTo: shipTo.value, sameAsBilling: sameAsBilling.value, notes: notes.value }),
  (v) => {
    step.value = v.step
    billTo.value = v.billTo
    shipTo.value = v.shipTo
    sameAsBilling.value = v.sameAsBilling
    notes.value = v.notes
  },
  () => ({ step: 1, billTo: saved.value[0] ?? null, shipTo: null, sameAsBilling: true, notes: '' }),
)

const who = (a: ShippingAddress) => [a.firstname, a.lastname].filter(Boolean).join(' ')
/** An address as envelope lines (the name is shown on its own above). */
const addrLines = (a: ShippingAddress) =>
  [a.organisation, a.line1, a.line2, [a.city, a.parish].filter(Boolean).join(', '), a.country].filter((x): x is string => !!x)
const where = (a: ShippingAddress) => [a.organisation, a.line1, a.line2, a.city, a.parish, a.country].filter(Boolean).join(', ')
/**
 * A new address is used at once and saved to the account (PATCH /me, If-Match) so it is offered next time and
 * on the profile. Already saved = just picked; a full list (10) or a failed save keeps it for this request only.
 */
const MAX_ADDRESSES = 10
async function onSaveAddress(a: ShippingAddress) {
  const forBill = dialogFor.value === 'bill'
  const pick = (x: ShippingAddress) => (forBill ? (billTo.value = x) : (shipTo.value = x))
  const fresh = clean(a)
  pick(fresh)
  const existing = saved.value.find((x) => same(x, fresh))
  if (existing) return void pick(existing)
  const acc = session.account
  if (!acc) return
  if (saved.value.length >= MAX_ADDRESSES) {
    notify.toast('Used for this request. Your account already holds 10 addresses; remove one in Account to save more.', 'info')
    return
  }
  try {
    const updated = await call(() =>
      identity.PATCH('/me', {
        params: { header: { 'If-Match': ifMatch(acc.version) } },
        body: { addresses: [...saved.value.map(clean), fresh] } as never,
      }),
    )
    session.set(updated)
    const stored = saved.value.find((x) => same(x, fresh))
    if (stored) pick(stored)
    notify.toast('Address saved to your account', 'success')
  } catch (e) {
    // Still used for this request; a stale version (412) reloads the account so the next try works.
    notify.report(e, { retry: () => void session.load(true) })
  }
}
const shippingAddress = computed(() => (sameAsBilling.value ? billTo.value : shipTo.value))

// ---- Continue and Send are never disabled: a press with something missing says what, next to it.
const need = ref<'line' | 'bill' | 'ship' | null>(null)
watch([unavailable, billTo, shippingAddress], () => (need.value = null))
function point(what: 'line' | 'bill' | 'ship', selector: string) {
  need.value = what
  void nextTick(() => {
    const el = document.querySelector<HTMLElement>(selector)
    el?.scrollIntoView({ block: 'center' })
    el?.focus({ preventScroll: true })
  })
}
function toInvoice() {
  if (unavailable.value) return point('line', '.line.gone button[aria-label^="Remove"]')
  step.value = 2
}
function toDelivery() {
  if (!billTo.value) return point('bill', '[data-need="bill"] input, [data-need="bill"] button')
  step.value = 3
}

// ---- send
const created = ref<OrderRequest[]>([])
const submitting = ref(false)
function clean(a: ShippingAddress): ShippingAddress {
  return Object.fromEntries(Object.entries(a).filter(([, v]) => v !== null && v !== '')) as unknown as ShippingAddress
}
async function submit() {
  if (submitting.value) return
  if (!billTo.value) {
    step.value = 2
    return point('bill', '[data-need="bill"] input, [data-need="bill"] button')
  }
  if (!shippingAddress.value) return point('ship', '[data-need="ship"] input, [data-need="ship"] button')
  submitting.value = true
  try {
    created.value = await cart.submit({
      shipTo: clean(shippingAddress.value),
      billTo: clean(billTo.value),
      ...(notes.value.trim() ? { notes: notes.value.trim() } : {}),
    })
    draft.clear()
    step.value = 4
  } catch (e) {
    notify.report(e)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="cart-page" :style="{ '--fill': (step - 1) / 3 }">
    <!-- The request path: one rule, four nodes; done steps are buttons back to them. -->
    <div class="band">
      <nav class="path-wrap" aria-label="Request steps">
        <ol class="path">
          <li
            v-for="s in STEPS"
            :key="s.n"
            class="node"
            :class="{ done: s.n < step || step === 4, current: s.n === step }"
            :aria-current="s.n === step ? 'step' : undefined"
          >
            <button v-if="s.n < step && step < 4" type="button" class="node-hit" :aria-label="`${s.label}, done: go back`" @click="goTo(s.n)">
              <span class="dot"><v-icon :icon="mdiCheck" size="18" /></span>
              <span class="node-label">{{ s.label }}</span>
            </button>
            <span v-else class="node-hit">
              <span class="dot">
                <v-icon v-if="s.n < step || step === 4" :icon="mdiCheck" size="18" />
                <template v-else>{{ s.n }}</template>
              </span>
              <span class="node-label">{{ s.label }}<span v-if="s.n > step" class="sr-only">, to do</span></span>
            </span>
          </li>
        </ol>
      </nav>
    </div>

    <Transition :name="`pane-${dir}`" mode="out-in" @after-enter="onEntered">
      <!-- 1. Cart -->
      <section v-if="step === 1" key="1" class="pane wide" aria-labelledby="q-title">
        <div class="q-head">
          <h1 id="q-title" ref="heading" tabindex="-1" class="q-title">Your cart</h1>
          <p class="q-line">Send it as a request. CIMH replies with a quote; nothing is paid here.</p>
        </div>

        <v-skeleton-loader v-if="loading" type="list-item-avatar-two-line@3" />
        <div v-else-if="!lines.length" class="empty">
          <v-icon :icon="mdiCartOutline" size="40" class="muted" />
          <h2 class="t-h3">Your cart is empty</h2>
          <p class="t-body muted">Add the items you need from the catalogue, then come back here to send the request.</p>
          <v-btn to="/catalogue" color="primary" class="m3">Browse the catalogue</v-btn>
        </div>
        <div v-else class="cart-grid">
          <div class="groups">
            <section v-for="g in groups" :key="g.key" class="group" :aria-labelledby="`g-${g.key}`">
              <h2 :id="`g-${g.key}`" class="group-title">
                {{ g.title }}
                <span v-if="g.free" class="probono-badge">Free</span>
              </h2>
              <ul class="lines">
                <li
                  v-for="l in g.items"
                  :key="l.productId"
                  class="line"
                  :class="{ 'no-thumb': !l.product.image, gone: l.available === false }"
                >
                  <div v-if="l.product.image" class="thumb"><img :src="l.product.image" alt="" loading="lazy" /></div>
                  <div class="info">
                    <router-link :to="`/catalogue/${l.productId}`" class="name">{{ l.product.name }}</router-link>
                    <p class="meta">{{ [l.product.make, l.product.modelname].filter(Boolean).join(' · ') }}</p>
                    <p v-if="l.available === false" class="gone-note">No longer available: remove it to continue</p>
                  </div>
                  <div class="qty" role="group" :aria-label="`Quantity of ${l.product.name}`">
                    <v-btn :icon="mdiMinus" size="small" variant="text" aria-label="Fewer" :disabled="busy === l.productId" @click="setQty(l.productId, l.qty - 1)" />
                    <input
                      :key="`${l.productId}-${l.qty}`"
                      class="qty-input tnum"
                      :value="l.qty"
                      inputmode="numeric"
                      pattern="[0-9]*"
                      maxlength="4"
                      :aria-label="`Quantity of ${l.product.name}`"
                      :disabled="busy === l.productId"
                      @keydown.enter.prevent="($event.target as HTMLInputElement).blur()"
                      @change="typedQty(l.productId, l.qty, $event.target as HTMLInputElement)"
                    />
                    <v-btn :icon="mdiPlus" size="small" variant="text" aria-label="More" :disabled="busy === l.productId" @click="setQty(l.productId, l.qty + 1)" />
                  </div>
                  <v-btn
                    class="remove"
                    :icon="mdiClose"
                    variant="text"
                    size="small"
                    :aria-label="`Remove ${l.product.name}`"
                    :disabled="busy === l.productId"
                    @click="setQty(l.productId, 0)"
                  />
                </li>
              </ul>
            </section>
          </div>

          <aside class="slip" aria-label="Your request">
            <p class="slip-count"><strong class="tnum">{{ itemsWord }}</strong></p>
            <p v-if="split" class="slip-line">Paid and Pro Bono items become two requests.</p>
            <p class="slip-line">Nothing is paid here. CIMH quotes the prices in Barbados dollars after you send the request.</p>
            <p v-if="unavailable" class="slip-line text-error" :role="need === 'line' ? 'alert' : undefined">
              Remove the item that is no longer available to continue.
            </p>
            <v-btn color="primary" variant="flat" class="m3" block size="large" @click="toInvoice">Continue to invoice</v-btn>
            <v-btn variant="text" class="m3" block to="/catalogue">Add more items</v-btn>
          </aside>
        </div>
      </section>

      <!-- 2. Invoice -->
      <section v-else-if="step === 2" key="2" class="pane" aria-labelledby="q-title">
        <div class="q-head">
          <h1 id="q-title" ref="heading" tabindex="-1" class="q-title">Who is the quote made out to?</h1>
          <p class="q-line">The quote, the agreement and the invoice name this organisation and address.</p>
        </div>
        <fieldset data-need="bill" class="choices">
          <legend class="sr-only">Invoice address</legend>
          <label v-for="(a, i) in billChoices" :key="i" class="choice" :class="{ on: same(billTo, a) }">
            <input v-model="billTo" type="radio" name="bill" :value="a" class="choice-input" />
            <span class="choice-mark" aria-hidden="true" />
            <span class="choice-text">
              <span class="choice-title">{{ a.organisation || who(a) }}</span>
              <span class="choice-sub">{{ a.organisation ? `${who(a)}, ` : '' }}{{ where(a) }}</span>
            </span>
          </label>
          <button type="button" class="choice add" @click="dialogFor = 'bill'">
            <v-icon :icon="mdiPlus" size="20" />Use a new address
          </button>
        </fieldset>
        <p v-if="!billTo" class="need" :class="need === 'bill' ? 'text-error' : 'muted'" :role="need === 'bill' ? 'alert' : undefined">
          {{ saved.length ? 'Choose an invoice address, or add a new one, to continue.' : 'Add an invoice address to continue.' }}
        </p>
        <div class="nav-row">
          <v-btn variant="text" class="m3" @click="step = 1">Back</v-btn>
          <v-btn color="primary" variant="flat" class="m3" size="large" @click="toDelivery">Continue to delivery</v-btn>
        </div>
      </section>

      <!-- 3. Delivery: the choice on the left, the whole request read back on the right (one place to check) -->
      <section v-else-if="step === 3" key="3" class="pane review" aria-labelledby="q-title">
        <div class="q-head">
          <h1 id="q-title" ref="heading" tabindex="-1" class="q-title">Where should it go?</h1>
          <p class="q-line">CIMH ships to this address. Supplier items come straight from the supplier.</p>
        </div>
        <div class="review-grid">
          <div class="review-main">
            <fieldset data-need="ship" class="choices">
              <legend class="sr-only">Delivery address</legend>
              <label class="choice" :class="{ on: sameAsBilling }">
                <input v-model="sameAsBilling" type="radio" name="ship-mode" :value="true" class="choice-input" />
                <span class="choice-mark" aria-hidden="true" />
                <span class="choice-text">
                  <span class="choice-title">The invoice address</span>
                  <span v-if="billTo" class="choice-sub">{{ billTo.organisation || who(billTo) }}, {{ [billTo.city, billTo.country].filter(Boolean).join(', ') }}</span>
                </span>
              </label>
              <label class="choice" :class="{ on: !sameAsBilling }">
                <input v-model="sameAsBilling" type="radio" name="ship-mode" :value="false" class="choice-input" />
                <span class="choice-mark" aria-hidden="true" />
                <span class="choice-text"><span class="choice-title">Another address</span></span>
              </label>
              <div v-if="!sameAsBilling" class="sub-choices">
                <label v-for="(a, i) in shipChoices" :key="i" class="choice" :class="{ on: same(shipTo, a) }">
                  <input v-model="shipTo" type="radio" name="ship" :value="a" class="choice-input" />
                  <span class="choice-mark" aria-hidden="true" />
                  <span class="choice-text">
                    <span class="choice-title">{{ a.organisation || who(a) }}</span>
                    <span class="choice-sub">{{ a.organisation ? `${who(a)}, ` : '' }}{{ where(a) }}</span>
                  </span>
                </label>
                <button type="button" class="choice add" @click="dialogFor = 'ship'">
                  <v-icon :icon="mdiPlus" size="20" />Use a new address
                </button>
                <p v-if="!shipTo" class="need" :class="need === 'ship' ? 'text-error' : 'muted'" :role="need === 'ship' ? 'alert' : undefined">
                  {{ saved.length ? 'Choose a delivery address, or add a new one, to send the request.' : 'Add a delivery address to send the request.' }}
                </p>
              </div>
            </fieldset>
            <v-textarea v-model="notes" label="Notes for CIMH (optional)" rows="3" counter="2000" maxlength="2000" auto-grow />
            <v-btn variant="text" class="m3 back" @click="step = 2">Back</v-btn>
          </div>

          <aside class="sheet" aria-labelledby="check-title">
            <header class="sheet-head">
              <h2 id="check-title" class="sheet-title">Check before you send</h2>
              <span class="sheet-count tnum">{{ itemsWord }}</span>
            </header>

            <section class="sheet-part" aria-label="Items">
              <div v-for="g in groups" :key="g.key" class="sheet-group">
                <p class="part-label">
                  {{ g.free ? 'Pro Bono' : 'To be quoted' }}
                  <span v-if="g.free" class="probono-badge">Free</span>
                </p>
                <ul class="sheet-items">
                  <li v-for="l in g.items" :key="l.productId">
                    <span class="it-name">{{ l.product.name }}</span>
                    <span class="it-qty tnum">× {{ l.qty }}</span>
                  </li>
                </ul>
              </div>
              <p v-if="split" class="sheet-note">Sent as two requests: one to be quoted, one Pro Bono.</p>
              <button type="button" class="change" @click="step = 1">Change items</button>
            </section>

            <section class="sheet-part addrs" aria-label="Addresses">
              <div v-if="billTo" class="addr">
                <p class="part-label">Invoice to</p>
                <address>
                  <strong>{{ who(billTo) }}</strong>
                  <span v-for="(x, i) in addrLines(billTo)" :key="i">{{ x }}</span>
                </address>
                <button type="button" class="change" @click="step = 2">Change</button>
              </div>
              <div class="addr">
                <p class="part-label">Deliver to</p>
                <p v-if="sameAsBilling" class="same">Same as the invoice address</p>
                <address v-else-if="shipTo">
                  <strong>{{ who(shipTo) }}</strong>
                  <span v-for="(x, i) in addrLines(shipTo)" :key="i">{{ x }}</span>
                </address>
                <p v-else class="same missing">Not chosen yet</p>
              </div>
            </section>

            <section v-if="cart.cart?.hasPaidLines || notes.trim()" class="sheet-part" aria-label="Other details">
              <dl class="sheet-facts">
                <div v-if="cart.cart?.hasPaidLines"><dt>Quote in</dt><dd>Barbados dollars (BBD)</dd></div>
                <div v-if="notes.trim()"><dt>Your note</dt><dd class="note">{{ notes.trim() }}</dd></div>
              </dl>
            </section>

            <footer class="sheet-foot">
              <p class="sheet-note">
                {{ cart.cart?.hasPaidLines ? 'Sending is not a commitment to pay: you decide when you have the quote.' : 'Staff review Pro Bono requests and email you the decision.' }}
              </p>
              <v-btn color="primary" variant="flat" class="m3" size="large" block :loading="submitting" @click="submit">Send request</v-btn>
            </footer>
          </aside>
        </div>
      </section>

      <!-- 4. Sent (S-09) -->
      <section v-else key="4" class="pane" aria-labelledby="q-title">
        <div class="q-head done-head">
          <v-icon :icon="mdiCheckCircleOutline" size="40" color="success" />
          <h1 id="q-title" ref="heading" tabindex="-1" class="q-title">{{ created.length > 1 ? 'Requests sent' : 'Request sent' }}</h1>
        </div>
        <ul class="sent">
          <li v-for="r in created" :key="r.id">
            <span class="sent-kind">{{ r.type === 'PROBONO' ? 'Pro Bono request' : 'Request' }}</span>
            <router-link :to="`/requests/${r.id}`" class="t-mono">{{ r.id }}</router-link>
          </li>
        </ul>
        <section class="check" aria-labelledby="next-title">
          <h2 id="next-title" class="check-title">What happens next</h2>
          <ul class="next">
            <li v-if="created.some((r) => r.type === 'PAID')">CIMH prepares a quote in Barbados dollars. We email you when it is ready to review.</li>
            <li v-if="created.some((r) => r.type === 'PROBONO')">Staff review the Pro Bono request and email you the decision.</li>
            <li>You can follow every step under Orders.</li>
          </ul>
        </section>
        <div class="nav-row">
          <v-btn to="/catalogue" variant="text" class="m3">Continue browsing</v-btn>
          <v-btn v-if="created.length" :to="`/requests/${created[0]!.id}`" color="primary" variant="flat" class="m3" size="large">View request</v-btn>
        </div>
      </section>
    </Transition>

    <AddressDialog v-model="dialogOpen" @save="onSaveAddress" />
  </div>
</template>

<style scoped>
/* ---- the band: deep navy field (same as the home masthead) with the logo-blue rule under it */
.band {
  background: #0a2e4a;
  color: #fff;
  border-bottom: 4px solid #0084c8;
  padding: var(--sp-8) var(--sp-4) var(--sp-6);
}
.path-wrap {
  max-width: 880px;
  margin: 0 auto;
}
.path {
  --dot: 36px;
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  position: relative;
}
/* One track from the first node's centre to the last; the fill is the same line scaled to the progress. */
.path::before,
.path::after {
  content: '';
  position: absolute;
  top: calc(var(--dot) / 2 - 1.5px);
  left: 12.5%;
  width: 75%;
  height: 3px;
  border-radius: 2px;
  background: rgb(255 255 255 / 0.22);
}
.path::after {
  background: #5cc2ff;
  transform-origin: left center;
  transform: scaleX(var(--fill));
  transition: transform 480ms cubic-bezier(0.16, 1, 0.3, 1);
}
.node {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: center;
}
.node-hit {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-2);
  min-width: 64px;
  padding: 0 var(--sp-1);
  background: none;
  border: 0;
  color: inherit;
  font: inherit;
  border-radius: 8px;
}
button.node-hit {
  cursor: pointer;
}
button.node-hit:focus-visible {
  outline: 2px solid #5cc2ff;
  outline-offset: 4px;
}
.dot {
  display: grid;
  place-items: center;
  width: var(--dot);
  height: var(--dot);
  border-radius: 50%;
  font-size: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  background: #0a2e4a;
  border: 3px solid rgb(255 255 255 / 0.35);
  color: rgb(255 255 255 / 0.85);
  transition: background-color 240ms ease-out, border-color 240ms ease-out, color 240ms ease-out, transform 240ms cubic-bezier(0.16, 1, 0.3, 1);
}
.node.current .dot {
  position: relative;
  border-color: #5cc2ff;
  color: #fff;
  box-shadow: 0 0 0 6px rgb(92 194 255 / 0.18);
}
/* The active step breathes: a sky ring swells out of the halo and fades, every 2.4 s (transform + opacity
   only). It waits for the rule to finish filling, so the eye follows the fill first, then lands here. */
.node.current .dot::after {
  content: '';
  position: absolute;
  inset: -9px;
  border-radius: 50%;
  border: 2px solid rgb(92 194 255 / 0.55);
  opacity: 0;
  pointer-events: none;
  animation: node-pulse 2400ms cubic-bezier(0.16, 1, 0.3, 1) 520ms infinite;
}
/* Sent: the request is finished, nothing is waiting, so the last node stays still. */
.node.done.current .dot::after {
  animation: none;
}
@keyframes node-pulse {
  0% {
    transform: scale(0.82);
    opacity: 0.9;
  }
  70%,
  100% {
    transform: scale(1.45);
    opacity: 0;
  }
}
.node.done .dot {
  background: #5cc2ff;
  border-color: #5cc2ff;
  color: #0a2e4a;
}
button.node-hit:hover .dot {
  transform: scale(1.08);
}
.node-label {
  font-size: 15px;
  line-height: 20px;
  font-weight: 600;
  color: rgb(255 255 255 / 0.78);
}
.node.current .node-label,
.node.done .node-label {
  color: #fff;
}
button.node-hit:hover .node-label {
  text-decoration: underline;
  text-underline-offset: 4px;
}

/* ---- one question per screen */
.pane {
  max-width: 760px;
  margin: 0 auto;
  padding: var(--sp-10, 40px) var(--sp-4) var(--sp-12);
  display: flex;
  flex-direction: column;
  gap: var(--sp-6);
}
.pane.wide {
  max-width: 1200px;
}
.q-head {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.q-title {
  font-size: clamp(28px, 4vw, 40px);
  line-height: 1.15;
  font-weight: 700;
  letter-spacing: -0.015em;
  text-wrap: balance;
  margin: 0;
}
.q-title:focus {
  outline: none;
}
.q-line {
  font-size: 17px;
  line-height: 26px;
  color: rgb(var(--v-theme-on-surface-variant));
  max-width: 62ch;
  margin: 0;
}

/* ---- step 1: lines + the request slip */
.cart-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: var(--sp-10, 40px);
  align-items: start;
}
.groups {
  display: flex;
  flex-direction: column;
  gap: var(--sp-8);
}
.group-title {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: 20px;
  line-height: 28px;
  font-weight: 700;
  margin: 0 0 var(--sp-2);
}
.lines {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.line {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr) auto auto;
  align-items: center;
  gap: var(--sp-4);
  padding: var(--sp-4) 0;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.line.no-thumb {
  grid-template-columns: minmax(0, 1fr) auto auto;
}
.thumb {
  width: 88px;
  height: 66px;
  border-radius: 8px;
  overflow: hidden;
  background: rgb(var(--v-theme-photo-ground));
}
.thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  mix-blend-mode: multiply;
}
.info {
  min-width: 0;
  overflow-wrap: anywhere;
}
.name {
  font-weight: 600;
  font-size: 16px;
  line-height: 22px;
  color: inherit;
  text-decoration: none;
}
.name:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.meta {
  margin: 2px 0 0;
  font-size: 14px;
  line-height: 20px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.gone-note {
  margin: var(--sp-1) 0 0;
  font-size: 14px;
  color: rgb(var(--v-theme-error));
}
.line.gone .name {
  text-decoration: line-through;
}
.qty {
  display: flex;
  align-items: center;
  gap: var(--sp-1);
  border: 1px solid rgb(var(--v-theme-field-outline));
  border-radius: 999px;
  padding: 0 2px;
}
.qty-input {
  width: 3.5ch;
  min-height: 32px;
  text-align: center;
  font: inherit;
  font-weight: 600;
  color: inherit;
  background: transparent;
  border: 0;
  border-radius: 4px;
}
.qty-input:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
}
.slip {
  position: sticky;
  top: 88px;
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding: var(--sp-6);
  border-radius: 12px;
  background: rgb(var(--v-theme-surface-variant));
}
.slip p {
  margin: 0;
}
.slip-count {
  font-size: 22px;
  line-height: 28px;
}
.slip-line {
  font-size: 15px;
  line-height: 22px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.slip .v-btn:first-of-type {
  margin-top: var(--sp-2);
}

/* ---- steps 2 and 3: address tiles */
.choices {
  border: 0;
  margin: 0;
  padding: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.choice {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  min-height: 72px;
  padding: var(--sp-4) var(--sp-5, 20px);
  border: 1px solid rgb(var(--v-theme-field-outline));
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 160ms ease-out, background-color 160ms ease-out;
}
.choice:hover {
  border-color: rgb(var(--v-theme-primary));
}
.choice.on {
  border: 2px solid rgb(var(--v-theme-primary));
  padding: calc(var(--sp-4) - 1px) calc(var(--sp-5, 20px) - 1px);
  background: rgba(var(--v-theme-primary), 0.06);
}
.choice-input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}
.choice:has(.choice-input:focus-visible),
.choice.add:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.choice-mark {
  flex: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 2px solid rgb(var(--v-theme-on-surface-variant));
  transition: border-width 160ms cubic-bezier(0.16, 1, 0.3, 1), border-color 160ms ease-out;
}
.choice.on .choice-mark {
  border: 7px solid rgb(var(--v-theme-primary));
}
.choice-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow-wrap: anywhere;
}
.choice-title {
  font-weight: 600;
  font-size: 16px;
  line-height: 22px;
}
.choice-sub {
  font-size: 14px;
  line-height: 20px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.choice.add {
  justify-content: flex-start;
  min-height: 56px;
  border-style: dashed;
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
  gap: var(--sp-2);
}
.need {
  margin: 0;
  font-size: 15px;
}

/* ---- check before you send / what happens next: a ruled list, not a card */
.check {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding-top: var(--sp-5, 20px);
}
.check-title {
  font-size: 20px;
  line-height: 28px;
  font-weight: 700;
  margin: 0 0 var(--sp-3);
}
.facts {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.facts > div {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: var(--sp-3);
  font-size: 15px;
  line-height: 22px;
}
.facts dt {
  color: rgb(var(--v-theme-on-surface-variant));
}
.facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.check-line {
  margin: var(--sp-3) 0 0;
  font-size: 15px;
  line-height: 22px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.nav-row {
  display: flex;
  gap: var(--sp-3);
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
}

/* ---- step 3: choice left, the request read back on a sheet right */
.pane.review {
  max-width: 1120px;
}
.review-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 420px);
  gap: var(--sp-10, 40px);
  align-items: start;
}
.review-main {
  display: flex;
  flex-direction: column;
  gap: var(--sp-6);
}
.sub-choices {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding-left: var(--sp-6);
  margin-top: var(--sp-1);
  border-left: 2px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.review-main .back {
  align-self: flex-start;
}
.sheet {
  position: sticky;
  top: 88px;
  border-radius: 12px;
  overflow: hidden;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  box-shadow: 0 8px 24px -12px rgb(10 46 74 / 0.28);
}
/* The sheet carries the band's navy so the read-back belongs to the request path above. */
.sheet-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: var(--sp-4) var(--sp-6);
  background: #0a2e4a;
  color: #fff;
  border-bottom: 3px solid #0084c8;
}
.sheet-title {
  font-size: 18px;
  line-height: 24px;
  font-weight: 700;
  margin: 0;
}
.sheet-count {
  font-size: 15px;
  font-weight: 600;
  color: #cfe9fb;
}
.sheet-part {
  padding: var(--sp-4) var(--sp-6);
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.part-label {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin: 0 0 var(--sp-1);
  font-size: 13px;
  line-height: 18px;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface-variant));
}
.sheet-items {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}
.sheet-items li {
  display: flex;
  justify-content: space-between;
  gap: var(--sp-3);
  font-size: 15px;
  line-height: 22px;
}
.it-name {
  min-width: 0;
  overflow-wrap: anywhere;
}
.it-qty {
  flex: none;
  font-weight: 600;
}
.addrs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-4);
}
.addr {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}
.addr address {
  font-style: normal;
  display: flex;
  flex-direction: column;
  font-size: 15px;
  line-height: 22px;
  overflow-wrap: anywhere;
}
.addr strong {
  font-weight: 600;
}
.same {
  margin: 0;
  font-size: 15px;
  line-height: 22px;
}
.same.missing {
  color: rgb(var(--v-theme-error));
}
.change {
  align-self: flex-start;
  margin-top: var(--sp-1);
  padding: 2px 0;
  background: none;
  border: 0;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
  text-decoration-thickness: 1px;
}
.change:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
  border-radius: 2px;
}
.sheet-facts {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.sheet-facts > div {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: var(--sp-3);
  font-size: 15px;
  line-height: 22px;
}
.sheet-facts dt {
  color: rgb(var(--v-theme-on-surface-variant));
}
.sheet-facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.sheet-facts .note {
  white-space: pre-line;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.sheet-foot {
  padding: var(--sp-4) var(--sp-6) var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.sheet-note {
  margin: 0;
  font-size: 14px;
  line-height: 20px;
  color: rgb(var(--v-theme-on-surface-variant));
}
@media (max-width: 959.98px) {
  .review-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--sp-6);
  }
  .sheet {
    position: static;
  }
}
@media (max-width: 599.98px) {
  .sheet-head,
  .sheet-part,
  .sheet-foot {
    padding-left: var(--sp-4);
    padding-right: var(--sp-4);
  }
  .addrs {
    grid-template-columns: minmax(0, 1fr);
  }
  /* Every step ends in its button on phones: keep it clear of the bottom bar and toasts. */
  .cart-page .pane {
    padding-bottom: 120px;
  }
  .sub-choices {
    padding-left: var(--sp-3);
  }
}

/* ---- empty + sent */
.empty {
  padding: var(--sp-10, 40px) 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--sp-3);
}
.empty p {
  max-width: 52ch;
  margin: 0;
}
.done-head {
  align-items: flex-start;
}
.sent {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.sent li {
  display: flex;
  gap: var(--sp-3);
  flex-wrap: wrap;
  font-size: 16px;
}
.sent a {
  overflow-wrap: anywhere;
}
.sent-kind {
  font-weight: 600;
}
.next {
  margin: 0;
  padding-left: 1.2em;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  font-size: 15px;
  line-height: 22px;
}
.muted {
  color: rgb(var(--v-theme-on-surface-variant));
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

/* ---- pane change: slides 16 px in the direction of travel */
.pane-fwd-enter-active,
.pane-back-enter-active {
  transition: opacity 220ms ease-out, transform 280ms cubic-bezier(0.16, 1, 0.3, 1);
}
.pane-fwd-leave-active,
.pane-back-leave-active {
  transition: opacity 100ms ease-in;
}
.pane-fwd-enter-from {
  opacity: 0;
  transform: translateX(16px);
}
.pane-back-enter-from {
  opacity: 0;
  transform: translateX(-16px);
}
.pane-fwd-leave-to,
.pane-back-leave-to {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .path::after,
  .dot {
    transition: none;
  }
  /* No pulse: the static halo alone marks the active step. */
  .node.current .dot::after {
    animation: none;
  }
  .pane-fwd-enter-from,
  .pane-back-enter-from {
    transform: none;
  }
}

/* ---- tablets and phones */
@media (max-width: 959.98px) {
  .cart-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--sp-6);
  }
  .slip {
    position: static;
  }
}
@media (max-width: 599.98px) {
  .band {
    padding: var(--sp-5, 20px) var(--sp-2) var(--sp-4);
  }
  .path {
    --dot: 30px;
  }
  .dot {
    font-size: 13px;
  }
  .node-hit {
    min-width: 0;
  }
  .node-label {
    font-size: 13px;
    line-height: 18px;
  }
  .pane {
    padding: var(--sp-6) var(--sp-4) var(--sp-10, 40px);
    gap: var(--sp-5, 20px);
  }
  .line {
    grid-template-columns: 56px minmax(0, 1fr) auto;
    grid-template-areas: 'thumb info remove' 'qty qty qty';
    row-gap: var(--sp-2);
    gap: var(--sp-3);
  }
  .line.no-thumb {
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas: 'info remove' 'qty qty';
  }
  .thumb {
    grid-area: thumb;
    width: 56px;
    height: 44px;
  }
  .info {
    grid-area: info;
  }
  .qty {
    grid-area: qty;
    justify-self: start;
  }
  .remove {
    grid-area: remove;
  }
  .facts > div {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }
  .nav-row > .v-btn:last-child {
    flex: 1 1 auto;
  }
}
</style>
