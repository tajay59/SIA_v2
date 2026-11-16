<script setup lang="ts">
/**
 * Record shipment (A-03, J-05 / J-06): carrier, tracking (not for hand delivery), date, optional cost and
 * note, and whether to email the customer. Emits the request body; the parent sends it and closes on success.
 */
import { CARRIERS, type Carrier, DateField, ShortRef } from '@cimh/web-app'
import { mdiAirplane, mdiHandExtendedOutline, mdiTruckDeliveryOutline } from '@mdi/js'
import { computed, reactive, watch } from 'vue'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ requestId: string; customer?: string | null; busy?: boolean }>()
const emit = defineEmits<{
  submit: [body: { carrier: Carrier; date: string; notifyCustomer: boolean; tracking: string | null; note: string | null; cost: string | null }]
}>()

const ICON: Record<Carrier, string> = { FEDEX: mdiAirplane, DHL: mdiTruckDeliveryOutline, HAND: mdiHandExtendedOutline }
const MONEY = /^\d{1,12}\.\d{2}$/
const localToday = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const f = reactive({ carrier: 'DHL' as Carrier, tracking: '', note: '', cost: '', date: localToday(), notifyCustomer: true })
// Fresh date each time the dialog opens; the rest is kept if staff close and reopen it.
watch(open, (v) => v && (f.date = localToday()))

const hand = computed(() => f.carrier === 'HAND')
const valid = computed(() => (hand.value || !!f.tracking.trim()) && !!f.date && (!f.cost || MONEY.test(f.cost)))
function submit() {
  if (!valid.value || props.busy) return
  emit('submit', {
    carrier: f.carrier,
    date: f.date,
    notifyCustomer: f.notifyCustomer,
    tracking: hand.value ? null : f.tracking.trim() || null,
    note: f.note.trim() || null,
    cost: f.cost || null,
  })
}
</script>

<template>
  <v-dialog v-model="open" max-width="560" scrollable :persistent="busy">
    <v-card class="ship" rounded="lg">
      <v-card-item>
        <v-card-title class="t-h3">Record shipment</v-card-title>
        <v-card-subtitle class="sub">
          <span class="console-mono"><ShortRef :id="requestId" /></span><template v-if="customer"> · {{ customer }}</template>
        </v-card-subtitle>
      </v-card-item>
      <v-divider />

      <v-card-text>
        <form id="ship-form" class="form" @submit.prevent="submit">
          <v-radio-group v-model="f.carrier" hide-details class="carriers">
            <template #label><span class="lbl">Carrier</span></template>
            <div class="tiles">
              <label v-for="c in CARRIERS" :key="c.value" class="tile" :class="{ on: f.carrier === c.value }">
                <v-icon :icon="ICON[c.value]" size="20" />
                <v-radio :label="c.title" :value="c.value" density="compact" hide-details />
              </label>
            </div>
          </v-radio-group>

          <v-text-field
            v-if="!hand"
            v-model="f.tracking"
            label="Tracking number"
            class="mono-input"
            :hint="`Typed from the ${f.carrier === 'FEDEX' ? 'FedEx' : 'DHL'} waybill`"
            persistent-hint
            autocomplete="off"
          />
          <v-text-field v-model="f.note" :label="hand ? 'Delivered by / collected by' : 'Note (optional)'" />

          <div class="two">
            <DateField v-model="f.date" label="Ship date" :rules="[(v: string) => !!v || 'Pick the date']" />
            <v-text-field
              v-model="f.cost"
              label="Shipping cost (optional)"
              placeholder="0.00"
              inputmode="decimal"
              class="mono-input"
              :rules="[(v: string) => !v || MONEY.test(v) || 'Use 2 decimals, e.g. 45.00']"
            />
          </div>

          <v-switch v-model="f.notifyCustomer" color="primary" inset hide-details label="Email the customer the shipping details" />
        </form>
      </v-card-text>

      <v-divider />
      <v-card-actions class="acts">
        <v-spacer />
        <v-btn class="m3" variant="text" :disabled="busy" @click="open = false">Back</v-btn>
        <v-btn class="m3" type="submit" form="ship-form" color="primary" variant="flat" :disabled="!valid" :loading="busy">Record shipment</v-btn>
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
}
.form {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding-top: var(--sp-2);
}
.lbl {
  font-size: 13px;
  font-weight: 500;
  color: rgb(var(--v-theme-on-surface));
  margin-bottom: var(--sp-2);
}
.carriers :deep(.v-selection-control-group) {
  display: block;
}
.tiles {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--sp-2);
}
.tile {
  display: flex;
  align-items: center;
  gap: var(--sp-1);
  padding: var(--sp-1) var(--sp-2) var(--sp-1) var(--sp-3);
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 8px;
  cursor: pointer;
  color: rgb(var(--v-theme-secondary));
  transition:
    border-color 150ms,
    background-color 150ms,
    color 150ms;
}
.tile:hover {
  border-color: rgb(var(--v-theme-primary));
}
.tile.on {
  border-color: rgb(var(--v-theme-primary));
  background: rgb(var(--v-theme-primary-subtle));
  color: rgb(var(--v-theme-primary));
}
.tile :deep(.v-label) {
  color: rgb(var(--v-theme-on-surface));
  opacity: 1;
  font-weight: 500;
}
.two {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sp-3);
}
.acts {
  padding: var(--sp-3) var(--sp-4);
  gap: var(--sp-2);
}
@media (max-width: 599px) {
  .tiles,
  .two {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
