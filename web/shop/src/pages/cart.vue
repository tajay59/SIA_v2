<script setup lang="ts">
/**
 * S-07 cart, S-08 submit and S-09 submitted, in the legacy SHOP Cart structure: one stepper
 * Cart → Billing → Shipping → Confirmation. Step 1 lists paid items, then "Pro Bono items" as a separate
 * group, with a summary card on the right. v2 rules: no prices (quotes come later); a cart with both kinds
 * becomes two requests; currency is asked only when there are paid items.
 */
import {
  AddressDialog,
  type Currency,
  type OrderRequest,
  type ShippingAddress,
  useCart,
  useDraft,
  useNotify,
  useSession,
} from '@cimh/web-app'
import {
  mdiAccountCreditCardOutline,
  mdiCartOutline,
  mdiCheckCircleOutline,
  mdiCloseCircleOutline,
  mdiMinus,
  mdiPlus,
  mdiSendCheckOutline,
  mdiTruckOutline,
} from '@mdi/js'
import { computed, onMounted, ref } from 'vue'
import { useDisplay } from 'vuetify'

definePage({ meta: { guard: 'customer', title: 'Cart' } })
const cart = useCart()
const session = useSession()
const notify = useNotify()
const { mdAndUp } = useDisplay()

const step = ref(1)
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
const unavailable = computed(() => lines.value.some((l) => l.available === false))

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

// ---- billing and shipping
const saved = computed<ShippingAddress[]>(() => (session.account?.addresses ?? []) as ShippingAddress[])
const currency = ref<Currency | null>(null)
const billTo = ref<ShippingAddress | null>(null)
const shipTo = ref<ShippingAddress | null>(null)
const sameAsBilling = ref(true)
const notes = ref('')
const dialogFor = ref<'bill' | 'ship' | null>(null)
const dialogOpen = computed({ get: () => dialogFor.value !== null, set: (v) => !v && (dialogFor.value = null) })
onMounted(() => {
  billTo.value = saved.value[0] ?? null
})

// Unsaved checkout (APD §2): kept if the session ends mid-way, restored after logging back in.
interface Checkout {
  step: number
  currency: Currency | null
  billTo: ShippingAddress | null
  shipTo: ShippingAddress | null
  sameAsBilling: boolean
  notes: string
}
const draft = useDraft<Checkout>(
  () => (session.account && step.value < 4 ? `checkout:${session.account.id}` : null), // sent: nothing left to keep
  () => ({ step: Math.min(step.value, 3), currency: currency.value, billTo: billTo.value, shipTo: shipTo.value,
    sameAsBilling: sameAsBilling.value, notes: notes.value }), // prettier-ignore
  (v) => {
    step.value = v.step
    currency.value = v.currency
    billTo.value = v.billTo
    shipTo.value = v.shipTo
    sameAsBilling.value = v.sameAsBilling
    notes.value = v.notes
  },
  () => ({ step: 1, currency: null, billTo: saved.value[0] ?? null, shipTo: null, sameAsBilling: true, notes: '' }),
)

function addressLine(a: ShippingAddress): string {
  return [a.organisation, a.line1, a.line2, a.city, a.parish, a.country].filter(Boolean).join(', ')
}
function onSaveAddress(a: ShippingAddress) {
  if (dialogFor.value === 'bill') billTo.value = a
  else shipTo.value = a
}

const billingDone = computed(() => !!billTo.value && (!cart.cart?.hasPaidLines || !!currency.value))
const shippingAddress = computed(() => (sameAsBilling.value ? billTo.value : shipTo.value))

// ---- submit
const created = ref<OrderRequest[]>([])
const submitting = ref(false)
function clean(a: ShippingAddress): ShippingAddress {
  return Object.fromEntries(Object.entries(a).filter(([, v]) => v !== null && v !== '')) as unknown as ShippingAddress
}
async function submit() {
  if (!shippingAddress.value || !billTo.value) return
  submitting.value = true
  try {
    created.value = await cart.submit({
      ...(cart.cart?.hasPaidLines && currency.value ? { currency: currency.value } : {}),
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
  <v-container class="page" max-width="1200">
    <!-- aria-label on each step: in mobile mode Vuetify hides the titles, which left the step buttons nameless. -->
    <v-stepper v-model="step" alt-label flat class="stepper" :mobile="!mdAndUp">
      <v-stepper-header>
        <v-stepper-item :value="1" title="Cart" aria-label="Cart" :complete="step > 1" :icon="mdiCartOutline" />
        <v-divider />
        <v-stepper-item :value="2" title="Billing" aria-label="Billing" :complete="step > 2" :icon="mdiAccountCreditCardOutline" />
        <v-stepper-item :value="3" title="Shipping" aria-label="Shipping" :complete="step > 3" :icon="mdiTruckOutline" />
        <v-divider />
        <v-stepper-item :value="4" title="Confirmation" aria-label="Confirmation" :complete="step === 4" :icon="mdiSendCheckOutline" />
      </v-stepper-header>

      <v-stepper-window>
        <!-- 1. Cart -->
        <v-stepper-window-item :value="1">
          <v-skeleton-loader v-if="loading" type="list-item-avatar-two-line@3" />
          <div v-else-if="!lines.length" class="empty">
            <v-icon :icon="mdiCartOutline" size="40" class="muted" />
            <h2 class="t-h3">Your cart is empty</h2>
            <p class="t-body muted">Browse the catalogue and add the items you need.</p>
            <v-btn to="/catalogue" color="primary">Browse the catalogue</v-btn>
          </div>
          <div v-else class="cart-grid">
            <div class="lines">
              <template v-for="group in [{ title: '', items: paid }, { title: 'Pro Bono items', items: probono }]" :key="group.title">
                <h2 v-if="group.title && group.items.length" class="t-h3 group-title">{{ group.title }}</h2>
                <v-sheet
                  v-for="l in group.items"
                  :key="l.productId"
                  border
                  rounded="lg"
                  class="line"
                  :class="{ probono: l.product.probono }"
                >
                  <v-img :src="l.product.image ?? undefined" :alt="l.product.name" class="thumb" cover />
                  <div class="info">
                    <router-link :to="`/catalogue/${l.productId}`" class="t-label name">{{ l.product.name }}</router-link>
                    <p class="t-caption muted">{{ [l.product.make, l.product.modelname].filter(Boolean).join(' · ') }}</p>
                    <p v-if="l.available === false" class="t-caption text-error">No longer available: remove it to continue</p>
                  </div>
                  <div class="stepper-qty" role="group" :aria-label="`Quantity of ${l.product.name}`">
                    <v-btn :icon="mdiMinus" size="small" variant="text" aria-label="Fewer" :disabled="busy === l.productId" @click="setQty(l.productId, l.qty - 1)" />
                    <span class="tnum">{{ l.qty }}</span>
                    <v-btn :icon="mdiPlus" size="small" variant="text" aria-label="More" :disabled="busy === l.productId" @click="setQty(l.productId, l.qty + 1)" />
                  </div>
                  <v-btn
                    :icon="mdiCloseCircleOutline"
                    variant="text"
                    size="small"
                    :aria-label="`Remove ${l.product.name}`"
                    :disabled="busy === l.productId"
                    @click="setQty(l.productId, 0)"
                  />
                </v-sheet>
              </template>
            </div>
            <v-card border flat class="summary">
              <v-card-subtitle>Details</v-card-subtitle>
              <v-card-text class="t-body">
                <p><strong class="tnum">{{ cart.count }}</strong> items</p>
                <p v-if="paid.length && probono.length" class="t-caption muted note">
                  Paid and Pro Bono items become two requests.
                </p>
                <p class="t-caption muted">Prices are quoted after you send the request.</p>
              </v-card-text>
              <v-card-actions class="actions">
                <v-btn color="primary" variant="flat" block :disabled="unavailable" @click="step = 2">Proceed to checkout</v-btn>
                <v-btn variant="outlined" block to="/catalogue">Continue shopping</v-btn>
              </v-card-actions>
            </v-card>
          </div>
        </v-stepper-window-item>

        <!-- 2. Billing -->
        <v-stepper-window-item :value="2">
          <section class="form">
            <div v-if="cart.cart?.hasPaidLines">
              <h2 class="t-h3">Currency</h2>
              <p class="t-caption muted">The quote for the paid items will be in this currency.</p>
              <v-radio-group v-model="currency" inline hide-details>
                <v-radio label="BBD (Barbados dollar)" value="BBD" />
                <v-radio label="USD (US dollar)" value="USD" />
              </v-radio-group>
            </div>
            <div>
              <h2 class="t-h3">Billing address</h2>
              <v-radio-group v-if="saved.length" v-model="billTo" hide-details>
                <v-radio v-for="(a, i) in saved" :key="i" :value="a" :label="`${a.firstname} ${a.lastname}, ${addressLine(a)}`" />
              </v-radio-group>
              <p v-if="billTo && !saved.includes(billTo)" class="t-body">{{ billTo.firstname }} {{ billTo.lastname }}, {{ addressLine(billTo) }}</p>
              <v-btn variant="text" color="primary" @click="dialogFor = 'bill'">Use a new address</v-btn>
            </div>
            <div class="nav-row">
              <v-btn variant="text" @click="step = 1">Back</v-btn>
              <v-btn color="primary" :disabled="!billingDone" @click="step = 3">Continue</v-btn>
            </div>
          </section>
        </v-stepper-window-item>

        <!-- 3. Shipping -->
        <v-stepper-window-item :value="3">
          <section class="form">
            <div>
              <h2 class="t-h3">Shipping address</h2>
              <v-checkbox v-model="sameAsBilling" label="Same as billing address" hide-details />
              <template v-if="!sameAsBilling">
                <v-radio-group v-if="saved.length" v-model="shipTo" hide-details>
                  <v-radio v-for="(a, i) in saved" :key="i" :value="a" :label="`${a.firstname} ${a.lastname}, ${addressLine(a)}`" />
                </v-radio-group>
                <p v-if="shipTo && !saved.includes(shipTo)" class="t-body">{{ shipTo.firstname }} {{ shipTo.lastname }}, {{ addressLine(shipTo) }}</p>
                <v-btn variant="text" color="primary" @click="dialogFor = 'ship'">Use a new address</v-btn>
              </template>
            </div>
            <v-textarea v-model="notes" label="Notes for CIMH (optional)" rows="3" counter="2000" maxlength="2000" auto-grow />
            <v-card border flat>
              <v-card-subtitle>Review</v-card-subtitle>
              <v-card-text class="t-body review">
                <p>{{ cart.count }} items{{ paid.length && probono.length ? ' · sent as two requests (paid and Pro Bono)' : '' }}</p>
                <p v-if="cart.cart?.hasPaidLines">Quote currency: <strong>{{ currency }}</strong></p>
                <p v-if="shippingAddress">Ship to: {{ shippingAddress.firstname }} {{ shippingAddress.lastname }}, {{ addressLine(shippingAddress) }}</p>
              </v-card-text>
            </v-card>
            <div class="nav-row">
              <v-btn variant="text" @click="step = 2">Back</v-btn>
              <v-btn color="primary" :disabled="!shippingAddress" :loading="submitting" @click="submit">Submit request</v-btn>
            </div>
          </section>
        </v-stepper-window-item>

        <!-- 4. Confirmation (S-09) -->
        <v-stepper-window-item :value="4">
          <section class="done">
            <v-icon :icon="mdiCheckCircleOutline" size="48" color="success" />
            <h2 class="t-h2">{{ created.length > 1 ? 'Requests sent' : 'Request sent' }}</h2>
            <p v-for="r in created" :key="r.id" class="t-body">
              {{ r.type === 'PROBONO' ? 'Pro Bono request' : 'Request' }}
              <router-link :to="`/requests/${r.id}`" class="t-mono">{{ r.id }}</router-link>
            </p>
            <div class="next prose">
              <h3 class="t-h3">What happens next</h3>
              <ul class="t-body">
                <li v-if="created.some((r) => r.type === 'PAID')">CIMH prepares a quote. We email you when it is ready to review.</li>
                <li v-if="created.some((r) => r.type === 'PROBONO')">Staff review the Pro Bono request and email you the decision.</li>
                <li>You can follow every step under My requests.</li>
              </ul>
            </div>
            <div class="nav-row">
              <v-btn v-if="created.length" :to="`/requests/${created[0]!.id}`" color="primary">View request</v-btn>
              <v-btn to="/catalogue" variant="outlined">Continue browsing</v-btn>
            </div>
          </section>
        </v-stepper-window-item>
      </v-stepper-window>
    </v-stepper>

    <AddressDialog v-model="dialogOpen" @save="onSaveAddress" />
  </v-container>
</template>

<style scoped>
.stepper {
  background: transparent;
}
.empty,
.done {
  padding: var(--sp-12) var(--sp-6);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-3);
  text-align: center;
}
.cart-grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(260px, 1fr);
  gap: var(--sp-6);
  align-items: start;
}
@media (max-width: 959px) {
  .cart-grid {
    grid-template-columns: 1fr;
  }
}
.lines {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.group-title {
  margin-top: var(--sp-4);
}
.line {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr) auto auto;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-2);
}
.line.probono {
  border-left: 4px solid #f5c400;
}
.thumb {
  width: 96px;
  height: 72px;
  border-radius: 8px;
  overflow: hidden;
}
.name {
  color: inherit;
  text-decoration: none;
}
.name:hover {
  text-decoration: underline;
}
.stepper-qty {
  display: flex;
  align-items: center;
  gap: var(--sp-1);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}
.summary .actions {
  flex-direction: column;
  gap: var(--sp-2);
}
.form {
  max-width: 720px;
  display: flex;
  flex-direction: column;
  gap: var(--sp-6);
  margin: 0 auto;
}
.nav-row {
  display: flex;
  gap: var(--sp-3);
  justify-content: flex-end;
  flex-wrap: wrap;
}
.done .nav-row {
  justify-content: center;
}
.next {
  text-align: left;
}
.review p + p {
  margin-top: var(--sp-1);
}
.note {
  margin: var(--sp-2) 0;
}
</style>
