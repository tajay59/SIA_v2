<script setup lang="ts">
/**
 * A-06 / A-07 product form (all ProductInput fields). Pro Bono must be chosen explicitly (PRD C5); a Pro Bono
 * item is always sellable and may have a per-request limit. Cost is BBD with two decimals (staff only).
 */
import { type ProductStaff, PRODUCT_TYPES, type ProductType, rule, typeLabel, useDraft, useReference } from '@cimh/web-app'
import { computed, reactive, ref, watch } from 'vue'
import { z } from 'zod'

const props = defineProps<{
  product?: ProductStaff | null
  saving?: boolean
  errors?: Record<string, string>
  /** sessionStorage key for unsaved changes (APD §2); the parent removes it after a successful save. */
  draftKey?: string | null
}>()
const emit = defineEmits<{ save: [body: Record<string, unknown>] }>()
const { reference } = useReference()

interface Draft {
  id: string
  name: string
  type: ProductType | null
  department: string | null
  project: string | null
  make: string
  modelname: string
  modelnumber: string
  description: string
  details: string
  sellable: boolean
  probono: boolean | null
  probonoMaxPerRequest: number | null
  cost: string
  threshold: number
  unitquantity: number | null
  weight: number | null
  dimension: string
  sn: string
  sn1: string
  keywords: string[]
}

function fromProduct(p?: ProductStaff | null): Draft {
  return {
    id: '',
    name: p?.name ?? '',
    type: (p?.type as ProductType) ?? null,
    department: p?.department ?? null,
    project: p?.project ?? null,
    make: p?.make ?? '',
    modelname: p?.modelname ?? '',
    modelnumber: p?.modelnumber ?? '',
    description: p?.description ?? '',
    details: p?.details ?? '',
    sellable: p?.sellable ?? true,
    probono: p ? p.probono : null,
    probonoMaxPerRequest: p?.probonoMaxPerRequest ?? null,
    cost: p?.cost ?? '',
    threshold: p?.threshold ?? 0,
    unitquantity: p?.unitquantity ?? null,
    weight: p?.weight ?? null,
    dimension: p?.dimension ?? '',
    sn: p?.sn ?? '',
    sn1: p?.sn1 ?? '',
    keywords: [...(p?.keywords ?? [])],
  }
}

const d = reactive<Draft>(fromProduct(props.product))
const valid = ref(false)
watch(
  () => props.product,
  (p) => Object.assign(d, fromProduct(p)),
)
useDraft(
  () => props.draftKey ?? null,
  () => ({ ...d, keywords: [...d.keywords] }),
  (v) => Object.assign(d, v),
  () => fromProduct(props.product),
)
watch(
  () => d.probono,
  (on) => {
    if (on) d.sellable = true
    else d.probonoMaxPerRequest = null
  },
)

const isNew = computed(() => !props.product)
const typeItems = computed(() => PRODUCT_TYPES.map((k) => ({ value: k, title: `${typeLabel(reference.value, k)} (${k})` })))
const projectItems = computed(() => (reference.value?.projects ?? []).map((p) => ({ value: p.code, title: p.name })))
const departments = computed(() => reference.value?.departments ?? [])

const money = z.string().trim().regex(/^\d{1,12}(\.\d{1,2})?$/, 'An amount like 1250 or 1250.50')
const required = (v: unknown) => (v !== null && v !== undefined && v !== '') || 'Required'
const wholeAtLeast = (min: number) => (v: unknown) =>
  v === null || v === '' || (Number.isInteger(Number(v)) && Number(v) >= min) || `A whole number, ${min} or more`

/** Body for POST (all fields) or PATCH (changed fields only). */
function body(): Record<string, unknown> {
  const t = (s: string) => s.trim() || null
  const full: Record<string, unknown> = {
    name: d.name.trim(),
    type: d.type,
    department: d.department,
    project: d.project || null,
    make: t(d.make),
    modelname: t(d.modelname),
    modelnumber: t(d.modelnumber),
    description: t(d.description),
    details: t(d.details),
    sellable: d.probono ? true : d.sellable,
    probono: d.probono,
    probonoMaxPerRequest: d.probono && d.probonoMaxPerRequest ? Number(d.probonoMaxPerRequest) : null,
    cost: d.cost.trim() ? Number(d.cost).toFixed(2) : null,
    threshold: Number(d.threshold),
    unitquantity: d.unitquantity ? Number(d.unitquantity) : null,
    weight: d.weight === null || (d.weight as unknown) === '' ? null : Number(d.weight),
    dimension: t(d.dimension),
    sn: t(d.sn),
    sn1: t(d.sn1),
    keywords: d.keywords.map((k) => k.trim()).filter(Boolean),
  }
  if (isNew.value) {
    if (d.id.trim()) full.id = d.id.trim()
    return full
  }
  const p = props.product as unknown as Record<string, unknown>
  return Object.fromEntries(Object.entries(full).filter(([k, v]) => JSON.stringify(p[k] ?? null) !== JSON.stringify(v)))
}

function submit() {
  if (valid.value) emit('save', body())
}
defineExpose({ body })
</script>

<template>
  <v-form v-model="valid" class="stack form" @submit.prevent="submit">
    <section class="stack-sm">
      <h2 class="t-h3">Product</h2>
      <div class="grid-2">
        <v-text-field v-model="d.name" label="Name" counter="200" maxlength="200" :rules="[required]" :error-messages="errors?.name" class="span-2" />
        <v-select v-model="d.type" :items="typeItems" label="Type" :rules="[required]" :error-messages="errors?.type" />
        <v-combobox
          v-model="d.department"
          :items="departments"
          label="Department"
          :rules="[required]"
          :error-messages="errors?.department"
          :hint="departments.length ? 'From the department list (Settings → Reference)' : ''"
          persistent-hint
        />
        <v-select v-model="d.project" :items="projectItems" label="Project (optional)" clearable :error-messages="errors?.project" />
        <v-text-field v-if="isNew" v-model="d.id" label="Barcode / id (optional)" hint="Leave empty to generate one; scan an existing label to keep it" persistent-hint :error-messages="errors?.id" />
      </div>
    </section>

    <section class="stack-sm">
      <h2 class="t-h3">Pro Bono</h2>
      <v-radio-group v-model="d.probono" inline class="yesno" :rules="[(v: unknown) => v !== null || 'Choose Yes or No']" :error-messages="errors?.probono">
        <template #label><span>Is this a Pro Bono (free) item?</span></template>
        <v-radio label="No" :value="false" />
        <v-radio label="Yes" :value="true" />
      </v-radio-group>
      <div class="grid-2">
        <v-text-field
          v-if="d.probono"
          v-model.number="d.probonoMaxPerRequest"
          type="number"
          min="1"
          label="Max per request (optional)"
          hint="Empty = no limit"
          persistent-hint
          :rules="[wholeAtLeast(1)]"
          :error-messages="errors?.probonoMaxPerRequest"
        />
        <v-switch
          v-model="d.sellable"
          :disabled="!!d.probono"
          color="primary"
          inset
          label="Customers can see and request it (sellable)"
          :hint="d.probono ? 'Pro Bono items are always visible to customers' : ''"
          persistent-hint
        />
      </div>
    </section>

    <section class="stack-sm">
      <h2 class="t-h3">Make and model</h2>
      <div class="grid-2">
        <v-text-field v-model="d.make" label="Make" maxlength="100" />
        <v-text-field v-model="d.modelname" label="Model name" maxlength="100" />
        <v-text-field v-model="d.modelnumber" label="Model number" maxlength="100" class="mono" />
        <v-text-field v-model="d.sn" label="Serial / part ref. (staff only)" maxlength="100" class="mono" />
        <v-text-field v-model="d.sn1" label="Second serial / part ref. (staff only)" maxlength="100" class="mono" />
      </div>
    </section>

    <section class="stack-sm">
      <h2 class="t-h3">Description</h2>
      <v-textarea v-model="d.description" label="Short description (shown to customers)" rows="2" auto-grow counter="5000" maxlength="5000" />
      <v-textarea v-model="d.details" label="Details and specifications" rows="3" auto-grow counter="5000" maxlength="5000" />
      <v-combobox v-model="d.keywords" label="Search keywords" multiple chips closable-chips hint="Press Enter after each keyword" persistent-hint />
    </section>

    <section class="stack-sm">
      <h2 class="t-h3">Stock and cost</h2>
      <div class="grid-2">
        <v-text-field v-model="d.cost" label="Cost (BBD, staff only)" prefix="BBD" inputmode="decimal" :rules="[(v: string) => !v || rule(money)(v)]" :error-messages="errors?.cost" />
        <v-text-field v-model.number="d.threshold" type="number" min="0" label="Low-stock alert at" :rules="[required, wholeAtLeast(0)]" :error-messages="errors?.threshold" />
        <v-text-field v-model.number="d.unitquantity" type="number" min="1" label="Units per pack" :rules="[wholeAtLeast(1)]" />
        <v-text-field v-model.number="d.weight" type="number" min="0" step="0.01" label="Weight" suffix="kg" />
        <v-text-field v-model="d.dimension" label="Dimensions" maxlength="100" placeholder="e.g. 30 × 20 × 15 cm" />
      </div>
    </section>

    <div class="row-end">
      <slot name="actions" />
      <v-btn type="submit" color="primary" :loading="saving" :disabled="!valid">{{ isNew ? 'Create product' : 'Save changes' }}</v-btn>
    </div>
  </v-form>
</template>

<style scoped>
.form {
  max-width: 880px;
}
.yesno :deep(.v-selection-control-group) {
  gap: var(--sp-6);
}
.span-2 {
  grid-column: 1 / -1;
}
.mono :deep(input) {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}
</style>
