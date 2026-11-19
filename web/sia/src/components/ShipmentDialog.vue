<script setup lang="ts">
/**
 * Record or correct one shipment (A-03, J-06 / J-07). A request ships in parcels: CIMH stock (picked here) and
 * each supplier's direct shipment. Choose where the parcel comes from, its lines (every unshipped line of that
 * source is ticked), the carrier (OTHER = name + the carrier's https tracking link), tracking (not for hand
 * delivery), date, optional cost and note, and whether to email the customer. Editing keeps source and lines.
 * Emits the request body; the parent sends it and closes on success.
 */
import {
  CARRIERS,
  type Carrier,
  carrierLabel,
  DateField,
  type OpenSource,
  openSources,
  type OrderRequest,
  type Shipment,
  type ShipmentInput,
  type ShipmentPatch,
  ShortRef,
} from '@cimh/web-app'
import { mdiAirplane, mdiDotsHorizontalCircleOutline, mdiHandExtendedOutline, mdiPackageVariantClosed, mdiTruckDeliveryOutline } from '@mdi/js'
import { computed, reactive, ref, watch } from 'vue'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ request: OrderRequest; shipment?: Shipment | null; busy?: boolean }>()
const emit = defineEmits<{ submit: [body: ShipmentInput]; update: [id: string, body: ShipmentPatch] }>()

const ICON: Record<Carrier, string> = {
  FEDEX: mdiAirplane,
  DHL: mdiTruckDeliveryOutline,
  UPS: mdiPackageVariantClosed,
  HAND: mdiHandExtendedOutline,
  OTHER: mdiDotsHorizontalCircleOutline,
}
const MONEY = /^\d{1,12}\.\d{2}$/
const localToday = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

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
const tried = ref(false)

function pickSource(key: string) {
  sourceKey.value = key
  picked.value = (sources.value.find((s) => s.key === key)?.lines ?? []).map((l) => l.lineId)
}
const source = computed(() => sources.value.find((s) => s.key === sourceKey.value) ?? null)
// A line that comes from CIMH stock ships only once every unit is picked.
const short = (ln: OpenSource['lines'][number]) => source.value?.source === 'CIMH' && (ln.picked?.length ?? 0) < ln.qty

watch(open, (v) => {
  if (!v) return
  tried.value = false
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
  // Every new parcel starts blank (the last one's tracking or note must never carry over); carrier stays as a guess.
  Object.assign(form, { carrierName: '', tracking: '', trackingLink: '', note: '', cost: '', date: localToday(), notifyCustomer: true })
  if (form.carrier === 'HAND' || form.carrier === 'OTHER') form.carrier = 'DHL'
  // Start on a source that can ship now (supplier parcels, or CIMH stock once picked).
  const ready = sources.value.find((x) => x.source === 'SUPPLIER' || x.lines.every((l) => (l.picked?.length ?? 0) >= l.qty))
  pickSource((ready ?? sources.value[0])?.key ?? '')
})

const hand = computed(() => form.carrier === 'HAND')
const trackingHint = computed(() => (form.carrier === 'OTHER' ? 'As printed on the waybill' : `Typed from the ${carrierLabel({ carrier: form.carrier })} waybill`))
const other = computed(() => form.carrier === 'OTHER')
const problems = computed(() => {
  const out: string[] = []
  if (!editing.value) {
    if (!source.value) out.push('Choose where the parcel comes from')
    else if (!picked.value.length) out.push('Tick the items in this parcel')
    else if (source.value.lines.some((l) => picked.value.includes(l.lineId) && short(l))) out.push('Pick every unit of the ticked CIMH items first')
  }
  if (other.value && !form.carrierName.trim()) out.push('Name the carrier')
  if (!hand.value && !form.tracking.trim()) out.push('Enter the tracking number')
  if (other.value && !/^https:\/\/\S+$/.test(form.trackingLink.trim())) out.push('Paste the carrier’s tracking link (https://…)')
  if (!form.date) out.push('Pick the ship date')
  if (form.cost && !MONEY.test(form.cost)) out.push('Write the cost with 2 decimals, e.g. 45.00')
  return out
})

function submit() {
  tried.value = true
  if (problems.value.length || props.busy) return
  const common = {
    carrier: form.carrier,
    carrierName: other.value ? form.carrierName.trim() : null,
    tracking: hand.value ? null : form.tracking.trim() || null,
    trackingLink: other.value ? form.trackingLink.trim() : null,
    note: form.note.trim() || null,
    cost: form.cost || null,
    date: form.date,
    notifyCustomer: form.notifyCustomer,
  }
  if (props.shipment) emit('update', props.shipment.id, common)
  else emit('submit', { ...common, source: source.value!.source, supplier: source.value!.supplier, lineIds: picked.value })
}
</script>

<template>
  <v-dialog v-model="open" max-width="600" scrollable :persistent="busy">
    <v-card class="ship" rounded="lg">
      <v-card-item>
        <v-card-title class="t-h3">{{ editing ? 'Correct shipment' : 'Record shipment' }}</v-card-title>
        <v-card-subtitle class="sub">
          <span class="console-mono"><ShortRef :id="request.id" /></span>
          <template v-if="request.organisationName || request.customerName"> · {{ request.organisationName || request.customerName }}</template>
          <template v-if="shipment"> · {{ shipment.source === 'SUPPLIER' ? shipment.supplier : 'CIMH stock' }} · {{ carrierLabel(shipment) }}</template>
        </v-card-subtitle>
      </v-card-item>
      <v-divider />

      <v-card-text>
        <form id="ship-form" class="form" novalidate @submit.prevent="submit">
          <template v-if="!editing">
            <fieldset class="group">
              <legend class="lbl">Sent from</legend>
              <div class="tiles">
                <label v-for="s in sources" :key="s.key" class="tile" :class="{ on: sourceKey === s.key }">
                  <input type="radio" name="ship-source" :value="s.key" :checked="sourceKey === s.key" @change="pickSource(s.key)" />
                  <span class="tile-name">{{ s.label }}</span>
                  <span class="tile-sub">{{ s.source === 'SUPPLIER' ? 'Ships direct' : 'Picked here' }} · {{ s.lines.length }} {{ s.lines.length === 1 ? 'item' : 'items' }}</span>
                </label>
              </div>
            </fieldset>

            <fieldset v-if="source" class="group">
              <legend class="lbl">In this parcel</legend>
              <ul class="lines">
                <li v-for="ln in source.lines" :key="ln.lineId">
                  <v-checkbox v-model="picked" :value="ln.lineId" density="compact" hide-details :disabled="short(ln)">
                    <template #label>
                      <span class="ln-name">{{ ln.product.name }}</span>
                      <span class="ln-qty">qty {{ ln.qty }}</span>
                      <span v-if="short(ln)" class="ln-short">{{ ln.picked?.length ?? 0 }} of {{ ln.qty }} picked</span>
                    </template>
                  </v-checkbox>
                </li>
              </ul>
            </fieldset>
          </template>

          <fieldset class="group">
            <legend class="lbl">Carrier</legend>
            <v-radio-group v-model="form.carrier" hide-details class="carriers">
              <div class="tiles carriers-grid">
                <label v-for="c in CARRIERS" :key="c.value" class="tile row" :class="{ on: form.carrier === c.value }">
                  <v-icon :icon="ICON[c.value]" size="20" />
                  <v-radio :label="c.title" :value="c.value" density="compact" hide-details />
                </label>
              </div>
            </v-radio-group>
          </fieldset>

          <v-text-field v-if="other" v-model="form.carrierName" label="Carrier name" autocomplete="off" />
          <v-text-field
            v-if="!hand"
            v-model="form.tracking"
            label="Tracking number"
            class="mono-input"
            :hint="trackingHint"
            persistent-hint
            autocomplete="off"
          />
          <v-text-field
            v-if="other"
            v-model="form.trackingLink"
            label="Tracking link"
            hint="The customer's Track button opens this page"
            persistent-hint
            inputmode="url"
            autocomplete="off"
          />
          <v-text-field v-model="form.note" :label="hand ? 'Delivered by / collected by' : 'Note (optional)'" />

          <div class="two">
            <DateField v-model="form.date" label="Ship date" />
            <v-text-field v-model="form.cost" label="Shipping cost (optional)" placeholder="0.00" inputmode="decimal" class="mono-input" hint="For CIMH's records; the customer never sees it" persistent-hint />
          </div>

          <v-switch
            v-model="form.notifyCustomer"
            color="primary"
            inset
            hide-details
            :label="editing ? 'Email the customer the corrected details' : 'Email the customer the shipping details'"
          />

          <ul v-if="tried && problems.length" class="problems" role="alert">
            <li v-for="p in problems" :key="p">{{ p }}</li>
          </ul>
        </form>
      </v-card-text>

      <v-divider />
      <v-card-actions class="acts">
        <v-spacer />
        <v-btn class="m3" variant="text" :disabled="busy" @click="open = false">Back</v-btn>
        <v-btn class="m3" type="submit" form="ship-form" color="primary" variant="flat" :loading="busy">
          {{ editing ? 'Save changes' : 'Record shipment' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.ship {
  background: rgb(var(--v-theme-surface));
}
.ship :deep(.v-divider) {
  opacity: 1;
  border-color: rgb(var(--v-theme-seam));
}
.sub {
  white-space: normal;
  opacity: 1; /* Vuetify fades subtitles below 4.5:1 */
  color: rgb(var(--v-theme-on-surface-variant));
}
.form {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding-top: var(--sp-2);
}
.group {
  border: 0;
  margin: 0;
  padding: 0;
  min-width: 0;
}
.lbl {
  font-size: 13px;
  font-weight: 500;
  color: rgb(var(--v-theme-on-surface));
  margin-bottom: var(--sp-2);
  padding: 0;
}
.carriers :deep(.v-selection-control-group) {
  display: block;
}
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: var(--sp-2);
}
.carriers-grid {
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
}
.tile {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 8px;
  cursor: pointer;
  color: rgb(var(--v-theme-secondary));
  transition:
    border-color 150ms,
    background-color 150ms,
    color 150ms;
}
.tile.row {
  flex-direction: row;
  align-items: center;
  gap: var(--sp-1);
  padding: var(--sp-1) var(--sp-2) var(--sp-1) var(--sp-3);
}
.tile input[type='radio'] {
  position: absolute;
  opacity: 0;
  inset: 0;
  margin: 0;
  cursor: pointer;
}
.tile:has(input:focus-visible) {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.tile:hover {
  border-color: rgb(var(--v-theme-primary));
}
.tile.on {
  border-color: rgb(var(--v-theme-primary));
  background: rgb(var(--v-theme-primary-subtle));
  color: rgb(var(--v-theme-primary));
}
.tile-name {
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
}
.tile-sub {
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.tile :deep(.v-label) {
  color: rgb(var(--v-theme-on-surface));
  opacity: 1;
  font-weight: 500;
}
.lines {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.lines li {
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.lines :deep(.v-label) {
  display: flex;
  flex-wrap: wrap;
  gap: 0 var(--sp-2);
  opacity: 1;
  color: rgb(var(--v-theme-on-surface));
}
.ln-qty {
  color: rgb(var(--v-theme-on-surface-variant));
  font-variant-numeric: tabular-nums;
}
.ln-short {
  color: rgb(var(--v-theme-warning-ink, var(--v-theme-on-surface-variant)));
  font-size: 13px;
}
.two {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sp-3);
}
.problems {
  margin: 0;
  padding-left: var(--sp-4);
  color: rgb(var(--v-theme-error));
  font-size: 14px;
}
.acts {
  padding: var(--sp-3) var(--sp-4);
  gap: var(--sp-2);
}
@media (max-width: 599px) {
  .two {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
