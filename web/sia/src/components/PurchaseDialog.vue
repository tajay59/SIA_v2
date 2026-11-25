<script lang="ts">
export type PurchaseBody = { agreementVerified: true; purchaseOrders: { supplier: string; poNumber: string; lineIds: string[] }[] }
</script>

<script setup lang="ts">
/**
 * A-03 Verify and purchase (J-06): staff check the signed agreement, then record one purchase order per supplier;
 * the request moves ACCEPTED → PURCHASING (no email to the customer). Graphite Console dialog: a washed head band
 * (what, which request, the agreed total), two seamed step panels with their own washed heads that say where each
 * step stands, and the footer saying what pressing does. Start purchasing is never disabled for missing input: a
 * press marks what is missing and moves the cursor there (checkForm). Not right? "Reject the signature" hands over
 * to the parent's reason dialog. Emits the request body; the parent sends it and closes on success.
 */
import { checkForm, type OrderRequest, ShortRef } from '@cimh/web-app'
import { formatMoney } from '@cimh/web-ui'
import { computed, reactive, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import IDone from '~icons/material-symbols/check-circle-rounded'
import IPending from '~icons/material-symbols/radio-button-unchecked'
import IEdit from '~icons/material-symbols/edit-rounded'
import IStock from '~icons/material-symbols/inventory-2-rounded'
import IDirect from '~icons/material-symbols/local-shipping-rounded'
import IFile from '~icons/material-symbols/description-rounded'
import { BTN } from '../request-queue'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ request: OrderRequest; busy?: boolean; canReject?: boolean }>()
const emit = defineEmits<{ submit: [body: PurchaseBody]; preview: [id: string, title: string]; reject: [] }>()
const { xs } = useDisplay()

type Row = { supplier: string; poNumber: string; lineIds: string[]; renaming: boolean }
const state = reactive({ verified: false, rows: [] as Row[] })
const formRef = ref()

const line = (id: string) => props.request.lines.find((l) => l.lineId === id)
const stockLines = computed(() => props.request.lines.filter((l) => l.source === 'CIMH'))
const signedId = computed(() => props.request.agreement?.signedFileId ?? null)
const signedFile = computed(() => (props.request.files ?? []).find((f) => f.id === signedId.value) ?? null)
const version = computed(() => props.request.agreement?.quoteVersion ?? null)
const total = computed(() => {
  const t = props.request.agreement?.total
  return t ? formatMoney(t, props.request.currency ?? 'BBD') : null
})
const who = computed(() => props.request.organisationName || props.request.customerName)
const kb = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`)
const day = (iso?: string) => (iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '')

// One row per supplier on the latest quote version; a line belongs to one supplier only.
watch(open, (o) => {
  if (!o) return
  formRef.value?.resetValidation?.()
  const x = props.request
  const supplierLines = new Set(x.lines.filter((l) => l.source === 'SUPPLIER').map((l) => l.lineId))
  const latest = Math.max(0, ...(x.quotes ?? []).map((q) => q.version))
  const bySupplier = new Map<string, string[]>()
  const taken = new Set<string>()
  for (const q of x.quotes ?? []) {
    if (q.version !== latest) continue
    for (const l of q.lines) {
      if (!supplierLines.has(l.lineId) || taken.has(l.lineId)) continue
      taken.add(l.lineId)
      const name = q.supplier ?? ''
      bySupplier.set(name, [...(bySupplier.get(name) ?? []), l.lineId])
    }
  }
  state.verified = false
  state.rows = [...bySupplier].map(([supplier, lineIds]) => ({ supplier, poNumber: '', lineIds, renaming: !supplier.trim() }))
})

const recorded = computed(() => state.rows.filter((r) => r.supplier.trim() && r.poNumber.trim()).length)
const posDone = computed(() => recorded.value === state.rows.length)
const required = (what: string) => (v: string) => !!v?.trim() || what
const mustVerify = (v: boolean) => v === true || 'Check the signed agreement first'

async function submit() {
  if (props.busy || !(await checkForm(formRef.value))) return
  emit('submit', {
    agreementVerified: true,
    purchaseOrders: state.rows.map((r) => ({ supplier: r.supplier.trim(), poNumber: r.poNumber.trim(), lineIds: r.lineIds })),
  })
}
</script>

<template>
  <v-dialog v-model="open" max-width="680" :fullscreen="xs" scrollable :persistent="busy" aria-labelledby="vp-title">
    <v-card class="vp" :rounded="xs ? 0 : 'lg'">
      <header class="vp-head">
        <div class="vp-who">
          <h2 id="vp-title" class="vp-title">Verify and purchase</h2>
          <p class="vp-sub">
            <template v-if="who">{{ who }} · </template>quote version <span class="console-mono">{{ version ?? '—' }}</span>
          </p>
          <!-- The id on its own line, so it shows in full unless the screen itself is too narrow (ShortRef fit). -->
          <p class="vp-ref console-mono"><ShortRef :id="request.id" fit copy /></p>
        </div>
        <dl v-if="total" class="vp-total">
          <dt class="cap">Agreed total</dt>
          <dd class="console-mono">{{ total }}</dd>
        </dl>
      </header>

      <v-card-text class="vp-body">
        <v-form ref="formRef" class="vp-form" @submit.prevent="submit">
          <!-- 1 · the signature: the copy, then the one check. -->
          <section class="step" :class="{ done: state.verified }" aria-labelledby="vp-sign">
            <header class="step-head">
              <h3 id="vp-sign" class="step-title"><span class="step-n console-mono" aria-hidden="true">1</span>Signature</h3>
              <span class="step-state">
                <v-icon :icon="state.verified ? IDone : IPending" size="16" />{{ state.verified ? 'Checked' : 'Not checked' }}
              </span>
            </header>
            <div class="step-body">
              <div v-if="signedId" class="doc">
                <v-icon :icon="IFile" size="21" class="doc-icon" />
                <span class="doc-text">
                  <span class="doc-name" :title="signedFile?.name">{{ signedFile?.name ?? 'Signed agreement' }}</span>
                  <span class="doc-meta">
                    <template v-if="signedFile?.quoteVersion">Quote version <span class="console-mono">{{ signedFile.quoteVersion }}</span></template><template v-if="signedFile?.uploadedAt"> · sent {{ day(signedFile.uploadedAt) }}</template><template v-if="signedFile?.size"> · {{ kb(signedFile.size) }}</template>
                  </span>
                </span>
                <v-btn
                  class="m3"
                  variant="tonal"
                  color="primary"
                  :prepend-icon="BTN.signed"
                  aria-label="Open the signed agreement"
                  aria-haspopup="dialog"
                  @click="emit('preview', signedId, 'Signed agreement')"
                >
                  Open
                </v-btn>
              </div>
              <p v-else class="missing">No signed agreement is attached to this request.</p>

              <div class="check-row">
                <v-checkbox v-model="state.verified" name="vp-verified" color="primary" :rules="[mustVerify]" hide-details="auto" class="check">
                  <template #label>
                    Every page is there, dated and signed by an authorised person<template v-if="who"> for {{ who }}</template>
                  </template>
                </v-checkbox>
                <v-btn v-if="canReject" variant="text" size="small" class="m3 reject-btn" :disabled="busy" @click="emit('reject')">Reject the signature…</v-btn>
              </div>
            </div>
          </section>

          <!-- 2 · purchase orders: a table without rules, one row per supplier (where it comes from φ : PO number 1),
               CIMH stock last for context. -->
          <section class="step" :class="{ done: posDone && state.rows.length > 0 }" aria-labelledby="vp-po">
            <header class="step-head">
              <h3 id="vp-po" class="step-title"><span class="step-n console-mono" aria-hidden="true">2</span>Purchase orders</h3>
              <span v-if="state.rows.length" class="step-state">
                <v-icon :icon="posDone ? IDone : IPending" size="16" /><span><span class="console-mono">{{ recorded }}</span> of <span class="console-mono">{{ state.rows.length }}</span> recorded</span>
              </span>
              <span v-else class="step-state">Not needed</span>
            </header>
            <div class="step-body">
              <p v-if="!state.rows.length" class="note">Every item comes from CIMH stock: no purchase order is needed.</p>
              <table v-else class="otab">
                <thead>
                  <tr>
                    <th scope="col" class="cap">From</th>
                    <th scope="col" class="cap">PO number</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, i) in state.rows" :key="i" class="order">
                    <th scope="row" class="src">
                      <span v-if="!row.renaming" class="src-name">
                        <span :id="`vp-sup-${i}`">{{ row.supplier.trim() || 'Supplier' }}</span>
                        <v-btn variant="text" size="x-small" :icon="IEdit" :aria-label="`Rename ${row.supplier}`" class="src-edit" @click="row.renaming = true" />
                      </span>
                      <v-text-field
                        v-else
                        v-model="row.supplier"
                        aria-label="Supplier"
                        placeholder="Supplier"
                        :name="`vp-supplier-${i}`"
                        class="cell"
                        autocomplete="off"
                        :rules="[required('Name the supplier')]"
                        hide-details="auto"
                      />
                      <ul class="items">
                        <li v-for="id in row.lineIds" :key="id"><span class="qty console-mono">{{ line(id)?.qty ?? 0 }}×</span>{{ line(id)?.product.name ?? id }}</li>
                      </ul>
                    </th>
                    <td>
                      <v-text-field
                        v-model="row.poNumber"
                        :aria-label="`PO number for ${row.supplier.trim() || 'the supplier'}`"
                        :name="`vp-po-${i}`"
                        class="cell mono-input"
                        placeholder="PO number"
                        autocomplete="off"
                        maxlength="100"
                        :rules="[required('Enter the PO number')]"
                        hide-details="auto"
                      />
                    </td>
                  </tr>
                  <tr v-if="stockLines.length" class="order stock">
                    <th scope="row" class="src">
                      <span class="src-name">CIMH stock</span>
                      <ul class="items">
                        <li v-for="l in stockLines" :key="l.lineId"><span class="qty console-mono">{{ l.qty }}×</span>{{ l.product.name }}</li>
                      </ul>
                    </th>
                    <td class="none">Picked here, none needed</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </v-form>
      </v-card-text>

      <footer class="vp-foot">
        <p class="foot-note">Moves the request to Purchasing. The customer is not emailed.</p>
        <div class="foot-acts">
          <v-btn class="m3" variant="text" :disabled="busy" @click="open = false">Back</v-btn>
          <v-btn class="m3" color="primary" variant="flat" :prepend-icon="BTN.verify" :loading="busy" @click="submit">Start purchasing</v-btn>
        </div>
      </footer>
    </v-card>
  </v-dialog>
</template>

<style scoped>
/* Golden-ratio system (owner 2026-11-24, as the invoice builder):
   type   11 px captions (14/√φ) · 14 px body and fields · 17.8 px title (14·√φ) · 22.65 px agreed total (14·φ);
   space  Fibonacci 8 · 13 · 21 · 34: 8 inside a group, 13 between rows, 21 the gutter and step inset, 34 between steps;
   layout the purchase-order table: where it comes from φ : PO number 1. Fields: 8 px corners, 32 px high. */
.vp {
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
}
/* Head: plain surface (owner: not so colourful), who φ : agreed total 1, a hairline under it. */
.vp-head {
  display: grid;
  grid-template-columns: minmax(0, 1.618fr) minmax(0, 1fr);
  align-items: end;
  gap: var(--f3);
  padding: var(--f3) var(--gutter);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.vp-who {
  min-width: 0;
}
.vp-title {
  margin: 0 0 var(--f1);
  font-size: 22.65px;
  line-height: 1.236;
  letter-spacing: -0.01em;
  font-weight: 600;
  text-wrap: balance;
}
.vp-sub,
.vp-ref {
  margin: 0;
  color: rgb(var(--v-theme-secondary));
  overflow-wrap: anywhere;
}
.vp-ref {
  display: flex;
  align-items: center;
  min-height: 28px;
  font-size: 13px;
}
.vp-total {
  margin: 0;
  text-align: right;
  flex: none;
}
.vp-total dt {
  color: rgb(var(--v-theme-secondary));
}
.vp-total dd {
  margin: 0;
  font-size: 22.65px;
  line-height: 1.236;
  font-weight: 700;
  letter-spacing: -0.01em;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
/* No side padding: the strips run edge to edge and each part carries the gutter itself (negative margins made
   the body scroll sideways when a field took focus). */
.vp-body {
  padding: var(--f3) var(--gutter) var(--f4) !important;
}
.vp-form {
  display: flex;
  flex-direction: column;
  gap: var(--f4);
}
/* Steps: no box, no wash. A section head (17.8 px = 14·√φ, between the 22.65 title and the 14 body) with where
   the step stands on the right; 13 px to its content, 34 px and a hairline to the next step. */
.step + .step {
  padding-top: var(--f4);
  margin-top: calc(var(--f4) * -1 + var(--f3));
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
  gap: 6px;
  align-self: center;
  color: rgb(var(--v-theme-secondary));
  white-space: nowrap;
}
.step-state .v-icon {
  color: rgb(var(--v-theme-secondary));
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
.note {
  margin: 0;
  color: rgb(var(--v-theme-secondary));
}
/* The signed copy: a file row (the one bordered row in the dialog), then the one check under it. */
.doc {
  display: flex;
  align-items: center;
  gap: var(--f2);
  padding: var(--f2) var(--f2) var(--f2) var(--f2);
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 8px;
}
.doc-icon {
  color: rgb(var(--v-theme-primary));
  flex: none;
}
.doc-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1 1 auto;
  line-height: 1.5;
}
.doc-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doc-meta {
  color: rgb(var(--v-theme-secondary));
}
.doc .v-btn {
  flex: none;
}
.missing {
  margin: 0;
  color: rgb(var(--v-theme-error));
}
.check-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--f1) var(--f2);
  flex-wrap: wrap;
  margin-left: -6px; /* the checkbox's own touch inset, so its box sits on the gutter */
}
.check {
  flex: 1 1 320px;
  min-width: 0;
}
.check :deep(.v-messages) {
  padding-inline-start: 37px; /* under the label, not under the box */
}
.check :deep(.v-label) {
  opacity: 1;
  font-size: 14px;
  line-height: 1.5;
  color: rgb(var(--v-theme-on-surface));
  padding: 9px 0 9px 9px; /* 13 px from the box to the words (the box is drawn 4 px inside its 24 px icon) */
}
.reject-btn {
  flex: none;
  margin-top: 5px;
  color: rgb(var(--v-theme-error)) !important;
  letter-spacing: 0;
}
/* Purchase orders: a table without rules. */
.otab {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  table-layout: fixed;
}
.otab thead th {
  padding: 0 0 var(--f1);
  text-align: left;
  color: rgb(var(--v-theme-on-surface-variant));
}
.otab thead th:first-child {
  width: 61.8%;
}
.otab thead th:last-child {
  padding-left: 10px;
}
.otab tbody th,
.otab tbody td {
  padding: var(--f1) 0;
  vertical-align: top;
  text-align: left;
  font-weight: 400;
}
.otab tbody tr + tr > * {
  padding-top: var(--f2);
}
.src {
  padding-right: var(--f3) !important;
}
.src-name {
  display: flex;
  align-items: center;
  gap: 2px;
  min-height: 32px;
  font-weight: 600;
}
.src-edit {
  color: rgb(var(--v-theme-on-surface-variant));
}
.items {
  list-style: none;
  margin: 0;
  padding: 0;
  color: rgb(var(--v-theme-secondary));
  line-height: 1.5;
}
.items li {
  display: flex;
  gap: var(--f1);
}
.qty {
  min-width: 3ch;
  font-variant-numeric: tabular-nums;
}
.none {
  color: rgb(var(--v-theme-secondary));
  line-height: 32px;
  padding-left: 10px !important;
}
/* Fields: 8 px corners, 32 px high, 10 px inset (as the invoice builder's table cells). */
.cell :deep(.v-field) {
  border-radius: 8px;
  --v-field-padding-start: 10px;
  --v-field-padding-end: 10px;
}
.cell :deep(.v-field__input) {
  min-height: 32px;
  padding-top: 6px;
  padding-bottom: 6px;
  font-size: 14px;
}
.cell :deep(.v-messages) {
  padding-inline: 10px;
}
.mono-input :deep(input) {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}
.vp-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--f2);
  padding: var(--f2) var(--gutter);
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.foot-note {
  margin: 0;
  color: rgb(var(--v-theme-secondary));
}
.foot-acts {
  display: flex;
  gap: var(--f1);
  flex: none;
}

@media (max-width: 599.98px) {
  .vp {
    --gutter: var(--f2);
  }
  .vp-head {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--f1);
  }
  .reject-btn {
    /* Wrapped under the check: its words on the gutter (the row sits 6 px out for the checkbox). */
    margin: 0 0 0 6px;
    padding-inline: 0 !important;
    min-width: 0;
  }
  .vp-total {
    text-align: left;
    display: flex;
    align-items: baseline;
    gap: var(--f1);
  }
  .otab thead {
    display: none;
  }
  .otab,
  .otab tbody,
  .otab tr,
  .otab tbody th,
  .otab tbody td {
    display: block;
    width: 100%;
  }
  .src {
    padding-right: 0 !important;
  }
  .otab tbody td {
    padding-top: var(--f1) !important;
  }
  .none {
    padding-left: 0 !important;
    line-height: 1.5;
  }
  .vp-foot {
    flex-direction: column;
    align-items: stretch;
  }
  .foot-acts {
    justify-content: flex-end;
  }
}
</style>
