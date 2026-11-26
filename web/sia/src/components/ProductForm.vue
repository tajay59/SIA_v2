<script setup lang="ts">
/**
 * A-06 / A-07 product form (all ProductInput fields). Pro Bono must be chosen explicitly (PRD C5); a Pro Bono
 * item is always sellable and may have a per-request limit. Cost is BBD with two decimals (staff only).
 */
import { checkForm, type FormLike, type ProductStaff, PRODUCT_TYPES, type ProductType, rule, typeLabel, useDraft, useNotify, useReference } from '@cimh/web-app'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { z } from 'zod/mini'
import SaveState from './SaveState.vue'

const props = defineProps<{
  product?: ProductStaff | null
  saving?: boolean
  errors?: Record<string, string>
  /** sessionStorage key for unsaved changes (APD §2); the parent removes it after a successful save. */
  draftKey?: string | null
  /** New product: show a Photos section (slot `photos`); the page uploads them after the product exists. */
  withPhotos?: boolean
  /** Heading level of the section titles (2 on a page, 3 inside a record that is itself under an h2). */
  level?: 2 | 3
}>()
const hs = computed(() => `h${props.level ?? 2}`)
const emit = defineEmits<{ save: [body: Record<string, unknown>] }>()
const { reference } = useReference()
const notify = useNotify()

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
const formRef = ref<FormLike | null>(null)
const valid = ref<boolean | null>(null)
/** True once Create/Save was pressed: from then on the bar says whether fields are still marked. */
const pressed = ref(false)
/** "Saved" for a moment after the product comes back with a new version (the parent saved it). */
const justSaved = ref(false)
/** Set when this form emitted save; the next new version is that save landing. */
let savePending = false
let savedTimer: ReturnType<typeof setTimeout> | undefined
watch(
  () => props.product,
  (p, before) => {
    Object.assign(d, fromProduct(p))
    if (p && before && p.id === before.id && p.version !== before.version && savePending) {
      savePending = false
      justSaved.value = true
      clearTimeout(savedTimer)
      savedTimer = setTimeout(() => (justSaved.value = false), 2600)
    }
  },
)
onBeforeUnmount(() => clearTimeout(savedTimer))
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

const money = z.string().check(z.trim(), z.regex(/^\d{1,12}(\.\d{1,2})?$/, 'An amount like 1250 or 1250.50'))
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

async function submit() {
  if (props.saving) return
  pressed.value = true
  // The button is never disabled: every missing field is marked and the first one gets the cursor.
  if (await checkForm(formRef.value)) {
    savePending = !isNew.value
    emit('save', body())
  }
}
defineExpose({ body })
/** Editing: something differs from the saved product (what Save would send). */
const dirty = computed(() => !isNew.value && Object.keys(body()).length > 0)

// Section index (wide screens): jump to a section; the one in view is marked.
const SECTIONS = [
  { id: 'pf-product', title: 'Product' },
  { id: 'pf-probono', title: 'Pro Bono and visibility' },
  { id: 'pf-model', title: 'Make and model' },
  { id: 'pf-desc', title: 'Description' },
  { id: 'pf-stock', title: 'Stock and cost' },
]
const PHOTOS = { id: 'pf-photos', title: 'Photos' }
const index = computed(() => (props.withPhotos ? [...SECTIONS, PHOTOS] : SECTIONS))
const current = ref(SECTIONS[0]!.id)
let observer: IntersectionObserver | null = null
onMounted(() => {
  if (typeof IntersectionObserver === 'undefined') return
  observer = new IntersectionObserver(
    (entries) => {
      const top = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0]
      if (top) current.value = top.target.id
    },
    { rootMargin: '-10% 0px -60% 0px' },
  )
  for (const s of index.value) {
    const el = document.getElementById(s.id)
    if (el) observer.observe(el)
  }
})
onBeforeUnmount(() => observer?.disconnect())

// Ctrl+S / ⌘S saves an edited product (owner 2026-11-25), with the same rules as Save changes; it never creates a
// new product. The browser's own "save page" is held back while the form is open; nothing happens if nothing changed.
function onSaveKey(e: KeyboardEvent) {
  if (!(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey || e.key.toLowerCase() !== 's') return
  if (isNew.value || document.querySelector('[role="dialog"]')) return
  e.preventDefault()
  if (dirty.value) void submit()
}
onMounted(() => addEventListener('keydown', onSaveKey))
onBeforeUnmount(() => removeEventListener('keydown', onSaveKey))
// Stepping to another product, closing the record or leaving the page keeps unsaved edits as a draft (useDraft,
// per product version); say so, so nobody thinks they were saved or lost.
onBeforeUnmount(() => {
  if (props.product && dirty.value && !props.saving) notify.toast(`Unsaved changes to ${props.product.name} are kept: open it again to finish.`, 'info')
})
function jump(id: string) {
  const el = document.getElementById(id)
  if (!el) return
  el.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' })
  current.value = id
  el.querySelector<HTMLElement>('input, textarea')?.focus({ preventScroll: true })
}
</script>

<template>
  <v-form ref="formRef" v-model="valid" class="pform" @submit.prevent="submit">
    <nav class="index" aria-label="Form sections">
      <a
        v-for="s in index"
        :key="s.id"
        :href="`#${s.id}`"
        :aria-current="current === s.id ? 'true' : undefined"
        @click.prevent="jump(s.id)"
      >{{ s.title }}</a>
    </nav>

    <div class="sections">
      <section :id="SECTIONS[0]!.id" class="sec" aria-labelledby="pf-product-h">
        <component :is="hs" id="pf-product-h" class="sec-title">Product</component>
        <div class="fields">
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
          <v-text-field
            v-if="isNew"
            v-model="d.id"
            label="Barcode / id (optional)"
            hint="Leave empty to generate one; scan an existing label to keep it"
            persistent-hint
            class="mono"
            :error-messages="errors?.id"
          />
        </div>
      </section>

      <section :id="SECTIONS[1]!.id" class="sec" aria-labelledby="pf-probono-h">
        <component :is="hs" id="pf-probono-h" class="sec-title">Pro Bono and visibility</component>
        <div class="fields">
          <v-radio-group
            v-model="d.probono"
            inline
            class="yesno span-2"
            :rules="[(v: unknown) => v !== null || 'Choose Yes or No']"
            :error-messages="errors?.probono"
          >
            <template #label><span>Is this a Pro Bono (free) item?</span></template>
            <v-radio label="No" :value="false" />
            <v-radio label="Yes" :value="true" />
          </v-radio-group>
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
            :class="{ 'span-2': !d.probono }"
          />
        </div>
      </section>

      <section :id="SECTIONS[2]!.id" class="sec" aria-labelledby="pf-model-h">
        <component :is="hs" id="pf-model-h" class="sec-title">Make and model</component>
        <div class="fields">
          <v-text-field v-model="d.make" label="Make" maxlength="100" />
          <v-text-field v-model="d.modelname" label="Model name" maxlength="100" />
          <v-text-field v-model="d.modelnumber" label="Model number" maxlength="100" class="mono" />
          <span class="gap" aria-hidden="true" />
          <v-text-field v-model="d.sn" label="Serial / part ref." maxlength="100" class="mono" />
          <v-text-field v-model="d.sn1" label="Second serial / part ref." maxlength="100" class="mono" />
        </div>
        <p class="sec-note">Serials are for staff only: customers never see them.</p>
      </section>

      <section :id="SECTIONS[3]!.id" class="sec" aria-labelledby="pf-desc-h">
        <component :is="hs" id="pf-desc-h" class="sec-title">Description</component>
        <div class="fields one">
          <v-textarea v-model="d.description" label="Short description (shown to customers)" rows="2" auto-grow counter="5000" maxlength="5000" />
          <v-textarea v-model="d.details" label="Details and specifications" rows="3" auto-grow counter="5000" maxlength="5000" />
          <v-combobox v-model="d.keywords" label="Search keywords" multiple chips closable-chips hint="Press Enter after each keyword" persistent-hint>
            <template #chip="{ props: chip, item }">
              <v-chip v-bind="chip" :close-label="`Remove keyword ${item.title}`" />
            </template>
          </v-combobox>
        </div>
      </section>

      <section :id="SECTIONS[4]!.id" class="sec" aria-labelledby="pf-stock-h">
        <component :is="hs" id="pf-stock-h" class="sec-title">Stock and cost</component>
        <div class="fields">
          <v-text-field v-model="d.cost" label="Cost (BBD, staff only)" prefix="BBD" inputmode="decimal" class="mono" :rules="[(v: string) => !v || rule(money)(v)]" :error-messages="errors?.cost" />
          <v-text-field v-model.number="d.threshold" type="number" min="0" label="Low-stock alert at" hint="Staff are warned when available units reach this number" persistent-hint :rules="[required, wholeAtLeast(0)]" :error-messages="errors?.threshold" />
          <v-text-field v-model.number="d.unitquantity" type="number" min="1" label="Units per pack" :rules="[wholeAtLeast(1)]" />
          <v-text-field v-model.number="d.weight" type="number" min="0" step="0.01" label="Weight" suffix="kg" />
          <v-text-field v-model="d.dimension" label="Dimensions" maxlength="100" placeholder="e.g. 30 × 20 × 15 cm" class="span-2" />
        </div>
      </section>

      <section v-if="withPhotos" :id="PHOTOS.id" class="sec" aria-labelledby="pf-photos-h">
        <component :is="hs" id="pf-photos-h" class="sec-title">Photos</component>
        <slot name="photos" />
      </section>

      <div class="bar">
        <span v-if="pressed && valid === false" class="t-caption need" role="alert">Fix the fields marked in red.</span>
        <span v-else-if="isNew" class="t-caption muted">{{ withPhotos ? 'Photos upload once the product is created.' : 'Photos come next, after the product is created.' }}</span>
        <SaveState v-else :dirty="dirty" :saved="justSaved" />
        <span v-if="!isNew && dirty" class="keyhint" aria-hidden="true"><kbd>Ctrl</kbd><kbd>S</kbd> saves</span>
        <span class="spacer" />
        <slot name="actions" />
        <!-- Editing: Save waits for a change (next to the save state, DESIGN.md "Submit, then mark"); never for missing input. -->
        <v-btn type="submit" class="m3" color="primary" :loading="saving" :disabled="!isNew && !dirty && !saving" :title="isNew ? undefined : 'Save changes (Ctrl+S)'" :aria-keyshortcuts="isNew ? undefined : 'Control+S'">{{ isNew ? 'Create product' : 'Save changes' }}</v-btn>
      </div>
      <!-- Below the save bar, in the sections' column (the product record puts Deactivate here). -->
      <slot name="after" />
    </div>
  </v-form>
</template>

<style scoped>
/* Golden-ratio system (as the product record and the dialogs): 17.8 px section heads, 14 px fields and notes,
   Fibonacci 8 · 13 · 21 · 34. Sections are plain heads over hairlines, no box per section. */
.pform {
  --rule: rgb(var(--v-theme-seam));
  display: grid;
  grid-template-columns: 200px minmax(0, 880px);
  gap: 34px;
  align-items: start;
}
.index {
  position: sticky;
  top: 21px;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--rule);
}
.index a {
  transition: color 150ms ease, border-color 200ms var(--ease-out);
  padding: 6px 13px;
  margin-left: -1px;
  border-left: 2px solid transparent;
  color: rgb(var(--v-theme-secondary));
  text-decoration: none;
  font-size: 14px;
}
.index a:hover {
  color: rgb(var(--v-theme-on-surface));
}
.index a[aria-current='true'] {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 600;
  border-left-color: rgb(var(--v-theme-primary));
}
.sections {
  display: flex;
  flex-direction: column;
}
.sec {
  scroll-margin-top: 21px;
}
.sec + .sec {
  margin-top: 13px;
  padding-top: 21px;
  border-top: 1px solid var(--rule);
}
.sec-title {
  margin: 0 0 13px;
  font-size: 17.8px;
  line-height: 1.382;
  font-weight: 600;
  letter-spacing: -0.005em;
}
.fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 21px;
}
.fields.one {
  grid-template-columns: minmax(0, 1fr);
}
.span-2 {
  grid-column: 1 / -1;
}
.sec-note {
  margin: 0;
  font-size: 12px;
  color: rgb(var(--v-theme-secondary));
}
.yesno :deep(.v-selection-control-group) {
  gap: 21px;
}
/* The question and the switch's words read as text, in ink (the primary colour is for the control itself). */
.yesno :deep(.v-label),
.fields :deep(.v-switch .v-label) {
  color: rgb(var(--v-theme-on-surface));
  opacity: 1;
}
.fields :deep(.v-selection-control .v-label) {
  padding-inline-start: 9px; /* + the control's own 4 px = 13 px from the control to its words */
}
/* Field hints that wrap (phones) keep a readable line height (Vuetify draws 12/12). */
.fields :deep(.v-messages__message) {
  line-height: 1.4;
}
.mono :deep(input) {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}
.need {
  color: rgb(var(--v-theme-error));
}
.keyhint {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: rgb(var(--v-theme-secondary));
}
.keyhint kbd {
  padding: 0 5px;
  font: 500 11px/18px 'JetBrains Mono', ui-monospace, monospace;
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 3px;
}
.bar {
  position: sticky;
  bottom: 0;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 13px;
  margin-top: 21px;
  padding: 13px 0;
  border-top: 1px solid var(--rule);
  background: var(--form-ground, rgb(var(--v-theme-surface)));
}
@media (max-width: 1099.98px) {
  .pform {
    grid-template-columns: minmax(0, 1fr);
  }
  .index {
    display: none;
  }
}
@media (max-width: 599.98px) {
  .fields {
    grid-template-columns: minmax(0, 1fr);
  }
  .gap {
    display: none;
  }
  .bar {
    position: static;
  }
}
</style>

