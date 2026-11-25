<script setup lang="ts">
/**
 * Record or correct one shipment (A-03, J-06 / J-07). A request ships in parcels: CIMH stock (picked here) and
 * each supplier's direct shipment. Graphite Console dialog, same anatomy as Verify and purchase: a washed head band
 * (what, which request with its full id + copy, where it goes), three seamed step panels whose washed heads say where
 * each step stands (1 Parcel: where it comes from + its lines; 2 Carrier: carrier + tracking, or who delivered it by
 * hand; 3 Date and cost: ship date, shipping cost (required, owner 2026-11-24; CIMH's records only), note), and a
 * footer with the customer email switch beside the action. Record is never disabled for missing input: a press marks
 * what is missing and moves the cursor there (checkForm). Editing keeps source and lines (shown, not changed).
 * Emits the request body; the parent sends it and closes on success.
 */
import {
  CARRIERS,
  type Carrier,
  carrierLabel,
  checkForm,
  countryName,
  DateField,
  type OpenSource,
  openSources,
  type OrderRequest,
  type Shipment,
  type ShipmentInput,
  type ShipmentPatch,
  ShortRef,
} from '@cimh/web-app'
import { computed, markRaw, reactive, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import IDone from '~icons/material-symbols/check-circle-rounded'
import IPending from '~icons/material-symbols/radio-button-unchecked'
import IStock from '~icons/material-symbols/inventory-2-rounded'
import IDirect from '~icons/material-symbols/local-shipping-rounded'
import IFlight from '~icons/material-symbols/flight-rounded'
import IPackage from '~icons/material-symbols/package-2-rounded'
import IHand from '~icons/material-symbols/front-hand-rounded'
import IMore from '~icons/material-symbols/more-horiz'
import { BTN } from '../request-queue'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ request: OrderRequest; shipment?: Shipment | null; busy?: boolean }>()
const emit = defineEmits<{ submit: [body: ShipmentInput]; update: [id: string, body: ShipmentPatch] }>()
const { xs } = useDisplay()

const ICON = {
  FEDEX: markRaw(IFlight),
  DHL: markRaw(IDirect),
  UPS: markRaw(IPackage),
  HAND: markRaw(IHand),
  OTHER: markRaw(IMore),
} satisfies Record<Carrier, unknown>
const COST = /^\d{1,12}(\.\d{1,2})?$/
const localToday = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const formRef = ref()
const editing = computed(() => !!props.shipment)
const sources = computed<OpenSource[]>(() => openSources(props.request))
const sourceKey = ref('')
const picked = ref<string[]>([])
const form = reactive({
  carrier: 'DHL' as Carrier,
  carrierName: '',
  tracking: '',
  trackingLink: '',
  note: '',
  cost: '',
  date: localToday(),
  notifyCustomer: true,
})

const source = computed(() => sources.value.find((s) => s.key === sourceKey.value) ?? null)
// A line that comes from CIMH stock ships only once every unit is picked.
const short = (ln: OpenSource['lines'][number]) => source.value?.source === 'CIMH' && (ln.picked?.length ?? 0) < ln.qty

function pickSource(key: string) {
  sourceKey.value = key
  picked.value = (source.value?.lines ?? []).filter((l) => !short(l)).map((l) => l.lineId)
  formRef.value?.resetValidation?.()
}

watch(open, (v) => {
  if (!v) return
  formRef.value?.resetValidation?.()
  const s = props.shipment
  if (s) {
    Object.assign(form, {
      carrier: s.carrier,
      carrierName: s.carrierName ?? '',
      tracking: s.tracking ?? '',
      trackingLink: s.trackingLink ?? '',
      note: s.note ?? '',
      cost: s.cost ?? '',
      date: s.date ?? localToday(),
      notifyCustomer: false,
    })
    return
  }
  // Every new parcel starts blank (the last one's tracking, cost or note must never carry over); carrier stays as a guess.
  Object.assign(form, { carrierName: '', tracking: '', trackingLink: '', note: '', cost: '', date: localToday(), notifyCustomer: true })
  if (form.carrier === 'HAND' || form.carrier === 'OTHER') form.carrier = 'DHL'
  // Start on a source that can ship now (supplier parcels, or CIMH stock once picked).
  const ready = sources.value.find((x) => x.source === 'SUPPLIER' || x.lines.every((l) => (l.picked?.length ?? 0) >= l.qty))
  pickSource((ready ?? sources.value[0])?.key ?? '')
})

const hand = computed(() => form.carrier === 'HAND')
const other = computed(() => form.carrier === 'OTHER')
const carrierName = computed(() => (other.value ? form.carrierName.trim() || 'Other carrier' : carrierLabel({ carrier: form.carrier })))
const trackingHint = computed(() => (other.value ? 'As printed on the waybill' : `Typed from the ${carrierName.value} waybill`))

// Head band facts.
const who = computed(() => props.request.organisationName || props.request.customerName)
const shipTo = computed(() => {
  const a = props.request.shipTo
  if (!a) return null
  return [a.city, countryName(a.country) || a.country].filter(Boolean).join(', ')
})
const fixedSource = computed(() => {
  const s = props.shipment
  if (!s) return null
  return s.source === 'SUPPLIER' ? s.supplier || 'Supplier' : 'CIMH stock'
})
const parcelLines = computed(() =>
  editing.value ? props.request.lines.filter((l) => props.shipment!.lineIds.includes(l.lineId)) : (source.value?.lines ?? []),
)
const tickedQty = computed(() => parcelLines.value.filter((l) => editing.value || picked.value.includes(l.lineId)).reduce((n, l) => n + l.qty, 0))
const itemWord = (n: number) => (n === 1 ? 'item' : 'items')

// Step states, said in the head of each panel.
const parcelDone = computed(() => editing.value || picked.value.length > 0)
const carrierDone = computed(() => {
  if (other.value && (!form.carrierName.trim() || !/^https:\/\/\S+$/.test(form.trackingLink.trim()))) return false
  return hand.value || !!form.tracking.trim()
})
const costDone = computed(() => !!form.date && COST.test(form.cost.trim()))

// Rules (checkForm marks them all on a press and focuses the first).
const required = (what: string) => (v: string) => !!v?.trim() || what
const linesRule = () => {
  if (editing.value) return true
  if (!source.value) return 'Nothing is left to ship on this request'
  if (picked.value.length) return true
  return source.value.lines.every(short) ? 'Pick every unit of these items first' : 'Tick the items in this parcel'
}
const linkRule = (v: string) => /^https:\/\/\S+$/.test(v?.trim() ?? '') || 'Paste the carrier’s tracking link (https://…)'
const costRule = (v: string) => {
  const t = v?.trim() ?? ''
  if (!t) return 'Enter the shipping cost (0.00 if it cost nothing)'
  return COST.test(t) || 'Write the cost as a number, e.g. 45.00'
}
const dateRule = (v: string) => !!v || 'Pick the ship date'
const money = (t: string) => {
  const [a, b = ''] = t.trim().split('.')
  return `${a}.${(b + '00').slice(0, 2)}`
}

async function submit() {
  if (props.busy || !(await checkForm(formRef.value))) return
  const common = {
    carrier: form.carrier,
    carrierName: other.value ? form.carrierName.trim() : null,
    tracking: hand.value ? null : form.tracking.trim() || null,
    trackingLink: other.value ? form.trackingLink.trim() : null,
    note: form.note.trim() || null,
    cost: money(form.cost),
    date: form.date,
    notifyCustomer: form.notifyCustomer,
  }
  if (props.shipment) emit('update', props.shipment.id, common)
  else emit('submit', { ...common, source: source.value!.source, supplier: source.value!.supplier, lineIds: picked.value })
}
</script>

<template>
  <v-dialog v-model="open" max-width="680" :fullscreen="xs" scrollable :persistent="busy" aria-labelledby="sd-title">
    <v-card class="sd" :rounded="xs ? 0 : 'lg'">
      <header class="sd-head">
        <div class="sd-who">
          <h2 id="sd-title" class="sd-title">{{ editing ? 'Correct shipment' : 'Record shipment' }}</h2>
          <p v-if="who || fixedSource" class="sd-sub">
            {{ who }}<template v-if="who && fixedSource"> · </template><template v-if="fixedSource">{{ fixedSource }} · {{ carrierLabel(shipment!) }}</template>
          </p>
          <!-- The id on its own line, so it shows in full unless the screen itself is too narrow (ShortRef fit). -->
          <p class="sd-ref console-mono"><ShortRef :id="request.id" fit copy /></p>
        </div>
        <dl v-if="shipTo" class="sd-to">
          <dt class="cap">Ships to</dt>
          <dd>{{ shipTo }}</dd>
        </dl>
      </header>

      <v-card-text class="sd-body">
        <v-form ref="formRef" class="sd-form" @submit.prevent="submit">
          <!-- 1 · the parcel: where it comes from and what is in it -->
          <section class="step" :class="{ done: parcelDone }" aria-labelledby="sd-parcel">
            <header class="step-head">
              <h3 id="sd-parcel" class="step-title"><span class="step-n console-mono" aria-hidden="true">1</span>Parcel</h3>
              <span class="step-state">
                <v-icon :icon="parcelDone ? IDone : IPending" size="16" />
                <span v-if="editing">Fixed</span>
                <span v-else><span class="console-mono">{{ picked.length }}</span> of <span class="console-mono">{{ parcelLines.length }}</span> {{ itemWord(parcelLines.length) }} ticked</span>
              </span>
            </header>

            <div class="step-body flush">
              <!-- Sent from: one row per source still to ship (or the fixed one when correcting). -->
              <div v-if="editing" class="src fixed">
                <v-icon :icon="shipment!.source === 'SUPPLIER' ? IDirect : IStock" size="20" class="src-icon" />
                <span class="src-text">
                  <span class="src-name">{{ fixedSource }}</span>
                  <span class="src-sub">{{ shipment!.source === 'SUPPLIER' ? 'Ships direct to the customer' : 'Picked here' }} · source and items stay as recorded</span>
                </span>
              </div>
              <fieldset v-else-if="sources.length" class="group">
                <legend class="cap lbl">Sent from</legend>
                <div class="srcs">
                  <label v-for="s in sources" :key="s.key" class="src" :class="{ on: sourceKey === s.key }">
                    <input type="radio" name="ship-source" :value="s.key" :checked="sourceKey === s.key" @change="pickSource(s.key)" />
                    <v-icon :icon="s.source === 'SUPPLIER' ? IDirect : IStock" size="20" class="src-icon" />
                    <span class="src-text">
                      <span class="src-name">{{ s.label }}</span>
                      <span class="src-sub">{{ s.source === 'SUPPLIER' ? 'Ships direct to the customer' : 'Picked here' }} · {{ s.lines.length }} {{ itemWord(s.lines.length) }}</span>
                    </span>
                    <v-icon :icon="sourceKey === s.key ? IDone : IPending" size="18" class="src-mark" />
                  </label>
                </div>
              </fieldset>

              <v-input :model-value="picked" name="ship-lines" :rules="[linesRule]" hide-details="auto" class="lines-input">
                <div id="ship-lines" class="lines-wrap">
                  <p class="cap lbl">In this parcel</p>
                  <ul class="lines">
                    <li v-for="ln in parcelLines" :key="ln.lineId" :class="{ short: !editing && short(ln) }">
                      <span v-if="editing" class="ln-fixed">
                        <span class="qty console-mono">{{ ln.qty }}×</span>
                        <span class="ln-name">{{ ln.product.name }}</span>
                      </span>
                      <v-checkbox v-else v-model="picked" :value="ln.lineId" color="primary" density="compact" hide-details :disabled="short(ln)">
                        <template #label>
                          <span class="qty console-mono">{{ ln.qty }}×</span>
                          <span class="ln-name">{{ ln.product.name }}</span>
                          <span v-if="short(ln)" class="ln-short">
                            <span class="console-mono">{{ ln.picked?.length ?? 0 }}</span> of <span class="console-mono">{{ ln.qty }}</span> picked · pick the rest first
                          </span>
                        </template>
                      </v-checkbox>
                    </li>
                    <li v-if="!parcelLines.length" class="none">Every item on this request is already in a parcel.</li>
                  </ul>
                </div>
              </v-input>
            </div>
          </section>

          <!-- 2 · carrier and tracking -->
          <section class="step" :class="{ done: carrierDone }" aria-labelledby="sd-carrier">
            <header class="step-head">
              <h3 id="sd-carrier" class="step-title"><span class="step-n console-mono" aria-hidden="true">2</span>Carrier</h3>
              <span class="step-state">
                <v-icon :icon="carrierDone ? IDone : IPending" size="16" />
                <span>{{ carrierName }}<template v-if="!hand"> · {{ form.tracking.trim() ? 'tracking entered' : 'no tracking yet' }}</template></span>
              </span>
            </header>
            <div class="step-body">
              <fieldset class="group">
                <legend class="sr-only">Carrier</legend>
                <div class="carriers">
                  <label v-for="c in CARRIERS" :key="c.value" class="carrier" :class="{ on: form.carrier === c.value }">
                    <input v-model="form.carrier" type="radio" name="ship-carrier" :value="c.value" :aria-label="c.title" />
                    <v-icon :icon="ICON[c.value]" size="22" />
                    <span class="carrier-name">{{ c.title }}</span>
                  </label>
                </div>
              </fieldset>

              <div v-if="other" class="two">
                <v-text-field v-model="form.carrierName" label="Carrier name" name="ship-carrier-name" autocomplete="off" :rules="[required('Name the carrier')]" hide-details="auto" />
                <v-text-field v-model="form.tracking" label="Tracking number" name="ship-tracking" class="mono-input" autocomplete="off" :hint="trackingHint" persistent-hint :rules="[required('Enter the tracking number')]" hide-details="auto" />
              </div>
              <v-text-field
                v-else-if="!hand"
                v-model="form.tracking"
                label="Tracking number"
                name="ship-tracking"
                class="mono-input"
                :hint="trackingHint"
                persistent-hint
                autocomplete="off"
                :rules="[required('Enter the tracking number')]"
                hide-details="auto"
              />
              <v-text-field
                v-if="other"
                v-model="form.trackingLink"
                label="Tracking link"
                name="ship-link"
                hint="The customer's Track button opens this page"
                persistent-hint
                inputmode="url"
                autocomplete="off"
                :rules="[linkRule]"
                hide-details="auto"
              />
              <v-text-field
                v-if="hand"
                v-model="form.note"
                label="Delivered by / collected by"
                name="ship-note"
                hint="No tracking number for a hand delivery: say who took it"
                persistent-hint
                hide-details="auto"
              />
            </div>
          </section>

          <!-- 3 · date, cost and a note -->
          <section class="step" :class="{ done: costDone }" aria-labelledby="sd-cost">
            <header class="step-head">
              <h3 id="sd-cost" class="step-title"><span class="step-n console-mono" aria-hidden="true">3</span>Date and cost</h3>
              <span class="step-state">
                <v-icon :icon="costDone ? IDone : IPending" size="16" />
                <span v-if="COST.test(form.cost.trim())">BBD <span class="console-mono">{{ money(form.cost) }}</span></span>
                <span v-else>Cost not entered</span>
              </span>
            </header>
            <div class="step-body">
              <div class="two">
                <DateField v-model="form.date" label="Ship date" name="ship-date" :rules="[dateRule]" hide-details="auto" />
                <v-text-field
                  v-model="form.cost"
                  label="Shipping cost"
                  name="ship-cost"
                  prefix="BBD"
                  placeholder="0.00"
                  inputmode="decimal"
                  class="mono-input"
                  autocomplete="off"
                  hint="For CIMH's records; the customer never sees it"
                  persistent-hint
                  :rules="[costRule]"
                  hide-details="auto"
                  @blur="COST.test(form.cost.trim()) && (form.cost = money(form.cost))"
                />
              </div>
              <v-text-field v-if="!hand" v-model="form.note" label="Note (optional)" name="ship-note" hide-details="auto" />
            </div>
          </section>
        </v-form>
      </v-card-text>

      <footer class="sd-foot">
        <v-switch
          v-model="form.notifyCustomer"
          color="primary"
          inset
          hide-details
          density="compact"
          class="sd-mail"
          :label="editing ? 'Email the customer the corrected details' : 'Email the customer the shipping details'"
        />
        <div class="foot-acts">
          <v-btn class="m3" variant="text" :disabled="busy" @click="open = false">Back</v-btn>
          <v-btn class="m3" color="primary" variant="flat" :prepend-icon="BTN.ship" :loading="busy" @click="submit">
            {{ editing ? 'Save changes' : 'Record shipment' }}
          </v-btn>
        </div>
      </footer>
    </v-card>
  </v-dialog>
</template>

<style scoped>
/* Golden-ratio dialog (owner 2026-11-24, as Verify and purchase): 11 px captions · 14 px body · 17.8 px section
   heads · 22.65 px title; spacing 8 · 13 · 21 · 34 (21 = the gutter, 34 between steps, with a hairline). Plain
   surface head, no washed bands. */
.sd {
  --gutter: 21px;
  --f1: 8px;
  --f2: 13px;
  --f3: 21px;
  --f4: 34px;
  background: rgb(var(--v-theme-surface));
  display: flex;
  flex-direction: column;
  font-size: 14px;
}
.cap {
  margin: 0;
  font-size: 11px;
  line-height: 1.618;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-secondary));
}
/* Head: who and which request φ : where it goes 1, a hairline under it. */
.sd-head {
  display: grid;
  grid-template-columns: minmax(0, 1.618fr) minmax(0, 1fr);
  align-items: end;
  gap: var(--f3);
  padding: var(--f3) var(--gutter);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.sd-who {
  min-width: 0;
}
.sd-title {
  margin: 0 0 var(--f1);
  font-size: 22.65px;
  line-height: 1.236;
  font-weight: 600;
  letter-spacing: -0.01em;
  text-wrap: balance;
}
.sd-sub,
.sd-ref {
  margin: 0;
  color: rgb(var(--v-theme-secondary));
  overflow-wrap: anywhere;
}
.sd-ref {
  display: flex;
  align-items: center;
  min-height: 28px;
  font-size: 13px;
}
.sd-to {
  margin: 0;
  text-align: right;
  min-width: 0;
}
.sd-to dd {
  margin: 0;
  font-size: 17.8px;
  line-height: 1.382;
  font-weight: 600;
  text-wrap: balance;
}
.sd-body {
  padding: var(--f3) var(--gutter) var(--f4) !important;
}
.sd-form {
  display: flex;
  flex-direction: column;
  gap: var(--f3);
}
/* Steps: a section head (17.8 px) with where the step stands on the right; 13 px to its content; 34 px and a
   hairline before the next step. */
.step {
  min-width: 0;
}
.step + .step {
  padding-top: var(--f4);
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.step-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 2px var(--f2);
}
.step-title {
  display: flex;
  align-items: baseline;
  gap: var(--f1);
  margin: 0;
  font-size: 17.8px;
  line-height: 1.382;
  font-weight: 600;
  white-space: nowrap;
}
.step-n {
  font-size: 14px;
  font-weight: 500;
  color: rgb(var(--v-theme-secondary));
}
.step-state {
  display: inline-flex;
  align-items: center;
  align-self: center;
  gap: 6px;
  color: rgb(var(--v-theme-secondary));
  min-width: 0;
}
.step-state .v-icon {
  color: rgb(var(--v-theme-secondary));
  flex: none;
}
.step.done .step-state {
  color: rgb(var(--v-theme-on-surface));
}
.step.done .step-state .v-icon {
  color: rgb(var(--v-theme-success));
}
.step-body {
  display: flex;
  flex-direction: column;
  gap: var(--f2);
  padding-top: var(--f2);
}
.group {
  border: 0;
  margin: 0;
  padding: 0;
  min-width: 0;
}
.lbl {
  padding: 0;
  margin: 0 0 var(--f1);
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

/* Sent from: ruled choice rows (a radio list), the chosen one in the primary tint. */
.srcs {
  display: flex;
  flex-direction: column;
  gap: var(--f1);
  padding: 0;
}
.src {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--f2);
  min-height: 52px;
  padding: var(--f1) var(--f2);
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 8px;
  cursor: pointer;
  transition:
    border-color 150ms var(--ease-out),
    background-color 150ms var(--ease-out);
}
.src.fixed {
  margin: 0;
  cursor: default;
  background: rgb(var(--v-theme-background));
}
.src input {
  position: absolute;
  z-index: 1; /* above the positioned v-icon, so a press anywhere on the tile picks it */
  inset: 0;
  opacity: 0;
  margin: 0;
  cursor: pointer;
}
.src:hover:not(.fixed) {
  border-color: rgb(var(--v-theme-primary));
}
.src:has(input:focus-visible) {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.src.on {
  border-color: rgb(var(--v-theme-primary));
  background: rgb(var(--v-theme-primary-subtle));
}
.src-icon {
  color: rgb(var(--v-theme-secondary));
  flex: none;
}
.src.on .src-icon,
.src.on .src-mark {
  color: rgb(var(--v-theme-primary));
}
.src-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1 1 auto;
}
.src-name {
  font-weight: 600;
  overflow-wrap: anywhere;
}
.src-sub {
  color: rgb(var(--v-theme-secondary));
}
.src-mark {
  flex: none;
  color: rgb(var(--v-theme-secondary));
}

/* The parcel's lines: a ruled list on the content edges; the tick boxes line up with the text above. */
.lines-input {
  min-width: 0;
}
.lines-input :deep(.v-input__control) {
  display: block;
}
.lines-input :deep(.v-input__details) {
  padding: 4px 0 0;
}
.lines-wrap {
  width: 100%;
  min-width: 0;
}
.lines {
  list-style: none;
  margin: 0;
  padding: 0;
}
.lines li {
  border-top: 1px solid rgb(var(--v-theme-seam));
  padding: 0;
  min-height: 44px;
  display: flex;
  align-items: center;
}
.lines li.short {
  background: rgb(var(--v-theme-background));
}
.lines li.none,
.ln-fixed {
  padding: var(--f1) 0;
  font-size: 14px;
}
.lines li.none {
  color: rgb(var(--v-theme-secondary));
}
.ln-fixed {
  display: flex;
  gap: var(--f1);
}
.lines :deep(.v-label) {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0 var(--f1);
  opacity: 1;
  color: rgb(var(--v-theme-on-surface));
  padding: var(--f1) 0 var(--f1) 9px; /* 13 px from the box to the words */
}
/* The box's touch area is wider than the box: pull it out so the box itself sits on the edge. */
.lines :deep(.v-selection-control__wrapper) {
  margin-inline-start: -8px;
}
.lines :deep(.v-selection-control--disabled .v-label) {
  opacity: 1;
}
.qty {
  min-width: 3ch;
  text-align: right;
  color: rgb(var(--v-theme-secondary));
  font-variant-numeric: tabular-nums;
}
.ln-name {
  font-weight: 500;
}
.ln-short {
  flex-basis: 100%;
  padding-left: calc(3ch + var(--f1) + 9px);
  color: rgb(var(--v-theme-warning-ink, var(--v-theme-on-surface-variant)));
}

/* Carrier: one row of five, icon over name; on phones the tiles wrap and stretch (3 + 2, no empty cell). */
.carriers {
  display: flex;
  flex-wrap: wrap;
  gap: var(--f1);
}
.carrier {
  position: relative;
  flex: 1 1 88px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 68px;
  padding: var(--f1) 4px;
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 8px;
  cursor: pointer;
  text-align: center;
  color: rgb(var(--v-theme-secondary));
  transition:
    border-color 150ms var(--ease-out),
    background-color 150ms var(--ease-out),
    color 150ms var(--ease-out);
}
.carrier input {
  position: absolute;
  z-index: 1;
  inset: 0;
  opacity: 0;
  margin: 0;
  cursor: pointer;
}
.carrier:hover {
  border-color: rgb(var(--v-theme-primary));
}
.carrier:has(input:focus-visible) {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.carrier.on {
  border-color: rgb(var(--v-theme-primary));
  background: rgb(var(--v-theme-primary-subtle));
  color: rgb(var(--v-theme-primary));
}
.carrier-name {
  line-height: 1.382;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
  text-wrap: balance;
}

.two {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--f2);
  align-items: start;
}
.mono-input :deep(input) {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}

.sd-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--f2);
  padding: var(--f2) var(--gutter);
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.sd-mail {
  flex: 0 1 auto;
  min-width: 0;
}
.sd-mail :deep(.v-label) {
  opacity: 1;
  padding-inline-start: var(--f2);
  color: rgb(var(--v-theme-on-surface));
}
.foot-acts {
  display: flex;
  gap: var(--f1);
  flex: none;
}

@media (max-width: 599.98px) {
  .sd {
    --gutter: var(--f2);
  }
  .sd-head {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--f1);
  }
  .sd-to {
    text-align: left;
    max-width: none;
    display: flex;
    align-items: baseline;
    gap: var(--f1);
  }
  .two {
    grid-template-columns: minmax(0, 1fr);
  }
  .sd-foot {
    flex-direction: column;
    align-items: stretch;
  }
  .foot-acts {
    justify-content: flex-end;
  }
}
@media (prefers-reduced-motion: reduce) {
  .src,
  .carrier {
    transition: none;
  }
}
</style>
