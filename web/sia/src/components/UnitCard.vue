<script setup lang="ts">
/**
 * One storage unit (A-11 lookup result): product, where it is, who stowed / picked / holds it, and the
 * actions that fit its state: Move to another shelf, Issue to a person, Return, Pick with a reason.
 */
import { type AccountSummary, newScanKey, scan, scanError, type Unit, unitState, unitWhere, useAccountNames } from '@cimh/web-app'
import { formatDateTime } from '@cimh/web-ui'
import { mdiAccountArrowLeftOutline, mdiAccountArrowRightOutline, mdiArrowRightBold, mdiHandBackRightOutline } from '@mdi/js'
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

const ACTIONS: { key: Action; title: string; icon: string }[] = [
  { key: 'move', title: 'Move', icon: mdiArrowRightBold },
  { key: 'issue', title: 'Issue to a person', icon: mdiAccountArrowRightOutline },
  { key: 'return', title: 'Return', icon: mdiAccountArrowLeftOutline },
  { key: 'pick', title: 'Pick', icon: mdiHandBackRightOutline },
]

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
  <div class="unit-card stack">
    <div class="row">
      <div class="stack-sm grow">
        <router-link :to="`/products/${unit.product}`" class="t-h3">{{ unit.productName ?? unit.product }}</router-link>
        <span class="t-mono muted">{{ unit.barcode }}</span>
      </div>
      <v-chip :color="state.tone === 'neutral' ? undefined : state.tone" label size="small">{{ state.label }}</v-chip>
    </div>

    <dl class="facts">
      <dt>Where</dt>
      <dd>
        <template v-if="unit.assignedTo">With {{ name(unit.assignedTo) }}</template>
        <router-link v-else-if="unit.stowed && unit.shelf" :to="{ path: '/inventory', query: { code: unit.shelf } }">{{ unitWhere(unit) }}</router-link>
        <template v-else>{{ unitWhere(unit) }}</template>
      </dd>
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

    <!-- Actions are buttons (outlined M3 pills with an icon), not grey tags; the open one is filled. -->
    <div v-if="can.move || can.issue || can.return || can.pick" class="acts" role="group" aria-label="Unit actions">
      <v-btn
        v-for="a in ACTIONS.filter((x) => can[x.key])"
        :key="a.key"
        class="m3"
        :variant="action === a.key ? 'flat' : 'outlined'"
        :color="action === a.key ? 'primary' : undefined"
        :prepend-icon="a.icon"
        :aria-pressed="action === a.key"
        @click="open(a.key)"
      >
        {{ a.title }}
      </v-btn>
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
  </div>
</template>

<style scoped>
.acts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
}
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
