<script setup lang="ts">
/**
 * One storage unit (A-11 lookup result): product, where it is, who stowed / picked / holds it, and the
 * actions that fit its state: Move to another shelf, Issue to a person, Return, Pick with a reason.
 */
import { type AccountSummary, newScanKey, scan, scanError, type Unit, unitState, unitWhere, useAccountNames } from '@cimh/web-app'
import { formatDateTime } from '@cimh/web-ui'
import { computed, nextTick, ref } from 'vue'
import PersonPicker from './PersonPicker.vue'
import ScanField from './ScanField.vue'

const props = defineProps<{ unit: Unit }>()
const emit = defineEmits<{ updated: [unit: Unit] }>()
const { name } = useAccountNames()

type Action = 'move' | 'issue' | 'return' | 'pick'
const action = ref<Action | null>(null)
const person = ref<AccountSummary | null>(null)
const reason = ref('')
const reasonField = ref<{ focus: () => void } | null>(null)
const busy = ref(false)
const error = ref('')
const state = computed(() => unitState(props.unit))
const can = computed(() => ({
  move: props.unit.stowed && !props.unit.picked,
  issue: !props.unit.picked && !props.unit.reservedFor && !props.unit.assignedTo,
  return: !!props.unit.assignedTo,
  pick: props.unit.stowed && !props.unit.picked && !props.unit.reservedFor,
}))

function open(a: Action) {
  action.value = action.value === a ? null : a
  error.value = ''
  person.value = null
  reason.value = ''
  if (action.value === 'pick') void nextTick(() => reasonField.value?.focus())
}

async function run(path: '/relocate' | '/assign' | '/unassign' | '/pick', body: Record<string, unknown>) {
  busy.value = true
  error.value = ''
  try {
    emit('updated', await scan(path, { unit: props.unit.barcode, ...body }, newScanKey()))
    action.value = null
  } catch (e) {
    error.value = scanError(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <v-card class="pa-5 stack" variant="outlined">
    <div class="row">
      <div class="stack-sm grow">
        <router-link :to="`/products/${unit.product}`" class="t-h3">{{ unit.productName ?? unit.product }}</router-link>
        <span class="t-mono muted">{{ unit.barcode }}</span>
      </div>
      <v-chip :color="state.tone === 'neutral' ? undefined : state.tone" label size="small">{{ state.label }}</v-chip>
    </div>

    <dl class="facts">
      <dt>Where</dt><dd>{{ unit.assignedTo ? `With ${name(unit.assignedTo)}` : unitWhere(unit) }}</dd>
      <template v-if="unit.siteName"><dt>Site</dt><dd>{{ unit.siteName }}</dd></template>
      <template v-if="unit.serial"><dt>Serial</dt><dd class="t-mono">{{ unit.serial }}</dd></template>
      <template v-if="unit.stowDate"><dt>Stowed</dt><dd>{{ formatDateTime(unit.stowDate) }} by {{ name(unit.stowBy) }}</dd></template>
      <template v-if="unit.picked">
        <dt>Picked</dt>
        <dd>{{ unit.pickedDate ? formatDateTime(unit.pickedDate) : '' }} by {{ name(unit.pickedBy) }}<template v-if="unit.pickedReason"> · {{ unit.pickedReason }}</template></dd>
      </template>
      <template v-if="unit.reservedFor"><dt>Reserved for</dt><dd class="t-mono">{{ unit.reservedFor }}</dd></template>
      <template v-if="unit.orderId"><dt>Picked for</dt><dd class="t-mono">{{ unit.orderId }}</dd></template>
    </dl>

    <div class="row">
      <v-btn v-if="can.move" size="small" variant="tonal" :active="action === 'move'" @click="open('move')">Move</v-btn>
      <v-btn v-if="can.issue" size="small" variant="tonal" :active="action === 'issue'" @click="open('issue')">Issue to a person</v-btn>
      <v-btn v-if="can.return" size="small" variant="tonal" :active="action === 'return'" @click="open('return')">Return</v-btn>
      <v-btn v-if="can.pick" size="small" variant="tonal" :active="action === 'pick'" @click="open('pick')">Pick</v-btn>
    </div>

    <div v-if="action === 'move'">
      <ScanField label="New shelf" :loading="busy" autofocus @scan="(code) => run('/relocate', { toShelf: code })" />
    </div>
    <div v-else-if="action === 'issue'" class="stack-sm">
      <PersonPicker v-model="person" />
      <div class="row-end">
        <v-btn color="primary" :disabled="!person" :loading="busy" @click="run('/assign', { accountId: person!.id })">Issue</v-btn>
      </div>
    </div>
    <div v-else-if="action === 'return'" class="row">
      <span class="t-body">{{ name(unit.assignedTo) }} returned it. Stow it on a shelf afterwards.</span>
      <v-btn color="primary" :loading="busy" @click="run('/unassign', {})">Confirm return</v-btn>
    </div>
    <form v-else-if="action === 'pick'" class="stack-sm" @submit.prevent="reason.trim() && run('/pick', { reason: reason.trim() })">
      <v-text-field ref="reasonField" v-model="reason" label="Reason" counter="300" maxlength="300" />
      <div class="row-end"><v-btn type="submit" color="primary" :disabled="!reason.trim()" :loading="busy">Pick</v-btn></div>
    </form>
    <v-alert v-if="error" type="error" variant="tonal" density="compact">{{ error }}</v-alert>
  </v-card>
</template>

<style scoped>
.grow {
  flex: 1 1 auto;
  min-width: 0;
}
.facts {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: var(--sp-1) var(--sp-4);
  margin: 0;
}
.facts dt {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.facts dd {
  margin: 0;
}
</style>
