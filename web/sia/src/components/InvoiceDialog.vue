<script setup lang="ts">
/**
 * Invoice builder (A-03): Create invoice / Create commercial invoice. The PDF as it will be printed (legacy SIA
 * layout, marked as a preview) on the left, redrawn as staff type; on the right who is emailed, the number, the
 * date, the lines (from the request: every priced line, or only CIMH-stock lines for a commercial invoice; each
 * can be edited, removed or added) and fees, discount and shipping. Create stores it on the request.
 */
import {
  ApiError,
  createInvoice,
  DateField,
  DocumentViewer,
  getInvoiceDraft,
  type InvoiceKind,
  type OrderRequest,
  previewInvoice,
  ShortRef,
  useNotify,
} from '@cimh/web-app'
import { formatMoney } from '@cimh/web-ui'
import { mdiDeleteOutline, mdiPlus, mdiRestore } from '@mdi/js'
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ request: OrderRequest; kind: InvoiceKind }>()
const emit = defineEmits<{ created: [] }>()

const notify = useNotify()
const { smAndDown } = useDisplay()
const MONEY = /^\d{1,12}(\.\d{1,2})?$/
const localToday = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

interface Row { key: number; lineId: string | null; description: string; qty: string; unitPrice: string }
let nextKey = 1
const commercial = computed(() => props.kind === 'commercial_invoice')
const title = computed(() => (commercial.value ? 'Commercial invoice' : 'Invoice'))

const form = reactive({
  emailCustomer: true,
  emailStaff: true,
  number: '',
  date: localToday(),
  fees: '0.00',
  discount: '0.00',
  shipping: '0.00',
})
const rows = ref<Row[]>([])
const recipient = ref<string[]>([])
const draftLines = ref<Row[]>([])
const loading = ref(false)
const loadFailed = ref(false)
const busy = ref(false)
const tried = ref(false)
const panel = ref<HTMLElement | null>(null)

const toRow = (l: { lineId?: string | null; description: string; qty: number; unitPrice: string }): Row => ({
  key: nextKey++,
  lineId: l.lineId ?? null,
  description: l.description,
  qty: String(l.qty),
  unitPrice: l.unitPrice,
})

async function loadDraft() {
  loading.value = true
  loadFailed.value = false
  try {
    const d = await getInvoiceDraft(props.request.id, props.kind)
    draftLines.value = d.lines.map(toRow)
    rows.value = d.lines.map(toRow)
    recipient.value = d.recipient
    Object.assign(form, { number: d.number ?? '', fees: d.fees, discount: d.discount, shipping: d.shipping })
  } catch (e) {
    loadFailed.value = true
    notify.report(e)
  } finally {
    loading.value = false
  }
}

watch(open, (v) => {
  if (!v) return
  tried.value = false
  previewFile.value = null
  previewProblem.value = ''
  Object.assign(form, { emailCustomer: true, emailStaff: true, number: '', date: localToday() })
  rows.value = []
  void loadDraft()
})

function addRow() {
  rows.value.push({ key: nextKey++, lineId: null, description: '', qty: '1', unitPrice: '0.00' })
  void nextTick(() => panel.value?.querySelector<HTMLInputElement>('.line:last-child input')?.focus())
}
function removeRow(key: number) {
  rows.value = rows.value.filter((r) => r.key !== key)
}
function resetRows() {
  rows.value = draftLines.value.map((r) => ({ ...r, key: nextKey++ }))
}

const qtyOk = (q: string) => /^\d{1,6}$/.test(q.trim()) && Number(q) >= 1
const cents = (v: string) => (MONEY.test(v.trim()) ? Math.round(Number(v) * 100) : 0)
const amount = (r: Row) => (qtyOk(r.qty) ? cents(r.unitPrice) * Number(r.qty) : 0)
const subtotal = computed(() => rows.value.reduce((s, r) => s + amount(r), 0))
const total = computed(() => subtotal.value + cents(form.fees) + (commercial.value ? 0 : cents(form.shipping)) - cents(form.discount))
const money = (c: number) => formatMoney((c / 100).toFixed(2), 'BBD')

const problems = computed(() => {
  const out: string[] = []
  if (!form.number.trim()) out.push(`Enter the ${commercial.value ? 'commercial invoice' : 'invoice'} number`)
  if (!form.date) out.push('Pick the invoice date')
  if (!rows.value.length) out.push('Add at least one line')
  rows.value.forEach((r, i) => {
    if (!r.description.trim()) out.push(`Line ${i + 1}: describe the item`)
    if (!qtyOk(r.qty)) out.push(`Line ${i + 1}: quantity must be a whole number from 1`)
    if (!MONEY.test(r.unitPrice.trim())) out.push(`Line ${i + 1}: write the price like 150.00`)
  })
  for (const [k, label] of [['fees', 'Fees'], ['discount', 'Discount'], ['shipping', 'Shipping cost']] as const) {
    if (k === 'shipping' && commercial.value) continue
    if (!MONEY.test(form[k].trim())) out.push(`${label}: write it like 0.00`)
  }
  if (total.value < 0) out.push('The discount is larger than the total')
  return out
})

function body(number?: string) {
  return {
    kind: props.kind,
    number: (number ?? form.number).trim(),
    date: form.date,
    lines: rows.value.map((r) => ({ lineId: r.lineId, description: r.description.trim(), qty: Number(r.qty), unitPrice: r.unitPrice.trim() })),
    fees: form.fees.trim(),
    discount: form.discount.trim(),
    shipping: commercial.value ? '0.00' : form.shipping.trim(),
    emailCustomer: form.emailCustomer,
    emailStaff: form.emailStaff,
  }
}

// ---- live preview: redrawn 500 ms after the last change, once the lines can be drawn (the number may still be empty).
const previewFile = ref<File | null>(null)
const previewProblem = ref('')
const previewing = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
let seq = 0
const drawable = computed(() => problems.value.filter((p) => !p.startsWith('Enter the')).length === 0)
async function refreshPreview() {
  if (!open.value || loading.value) return
  if (!drawable.value) {
    previewProblem.value = 'Fix the marked fields to see the invoice.'
    return
  }
  const mine = ++seq
  previewing.value = true
  try {
    const blob = await previewInvoice(props.request.id, body(form.number.trim() || '—'))
    if (mine !== seq) return
    previewFile.value = new File([blob], `${props.kind}-preview.pdf`, { type: 'application/pdf', lastModified: Date.now() })
    previewProblem.value = ''
  } catch (e) {
    if (mine !== seq) return
    previewProblem.value = e instanceof ApiError ? (e.detail ?? e.message) : 'The preview could not be drawn.'
  } finally {
    if (mine === seq) previewing.value = false
  }
}
watch(
  [() => ({ ...form }), rows, loading],
  () => {
    clearTimeout(timer)
    timer = setTimeout(() => void refreshPreview(), 500)
  },
  { deep: true },
)
onBeforeUnmount(() => clearTimeout(timer))

async function submit() {
  tried.value = true
  if (problems.value.length) {
    await nextTick()
    panel.value?.querySelector<HTMLElement>('.problems')?.scrollIntoView({ block: 'nearest' })
    return
  }
  if (busy.value) return
  busy.value = true
  try {
    await createInvoice(props.request.id, body())
    const who = [form.emailCustomer && 'the customer', form.emailStaff && 'staff'].filter(Boolean).join(' and ')
    notify.toast(`${title.value} ${form.number.trim()} created${who ? `; emailed to ${who}` : ''}`, 'success')
    emit('created')
    open.value = false
  } catch (e) {
    notify.report(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <v-dialog v-model="open" :max-width="1320" :fullscreen="smAndDown" scrollable :persistent="busy">
    <v-card class="inv" :rounded="smAndDown ? 0 : 'lg'">
      <v-card-item>
        <v-card-title class="t-h3">Create {{ commercial ? 'commercial invoice' : 'invoice' }}</v-card-title>
        <v-card-subtitle class="sub">
          <span class="console-mono"><ShortRef :id="request.id" /></span>
          <template v-if="request.organisationName || request.customerName"> · {{ request.organisationName || request.customerName }}</template>
          <template v-if="commercial"> · CIMH stock only (supplier items ship direct)</template>
        </v-card-subtitle>
      </v-card-item>
      <v-divider />

      <v-card-text class="body">
        <section class="preview" :class="{ drawing: previewing && !!previewFile }" aria-label="Preview" :aria-busy="previewing">
          <span class="sweep" aria-hidden="true" />
          <DocumentViewer
            v-if="previewFile"
            :file="previewFile"
            :name="`${title} preview`"
            mime="application/pdf"
            what="Preview"
            link="none"
            class="paper"
          />
          <div v-else class="preview-empty">
            <v-progress-circular v-if="loading || previewing" indeterminate size="28" color="primary" />
            <p v-else>{{ previewProblem || `The ${commercial ? 'commercial invoice' : 'invoice'} shows here.` }}</p>
          </div>
          <p v-if="previewFile && previewProblem" class="preview-note" role="status">{{ previewProblem }}</p>
        </section>

        <div ref="panel" class="panel">
          <div v-if="loadFailed" class="failed">
            <p>The request's lines could not be loaded.</p>
            <v-btn class="m3" variant="outlined" @click="loadDraft">Retry</v-btn>
          </div>
          <form v-else id="inv-form" class="form" novalidate @submit.prevent="submit">
            <fieldset class="email">
              <legend class="email-q">Email the {{ commercial ? 'commercial invoice' : 'invoice' }}?</legend>
              <p class="hint">Sent when you press Create.</p>
              <v-switch v-model="form.emailCustomer" color="primary" inset hide-details density="compact" label="Customer" />
              <v-switch v-model="form.emailStaff" color="primary" inset hide-details density="compact" label="Staff (invoice email list)" />
            </fieldset>

            <div class="two">
              <v-text-field
                v-model="form.number"
                :label="commercial ? 'Commercial invoice #' : 'Invoice #'"
                class="mono-input"
                autocomplete="off"
                :error="tried && !form.number.trim()"
              />
              <DateField v-model="form.date" label="Date" :menu-props="{ location: 'bottom end', origin: 'top end' }" />
            </div>

            <div v-if="recipient.length" class="to">
              <p class="lbl">{{ commercial ? 'To (ship-to)' : 'Billed to' }}</p>
              <p class="to-text">{{ recipient.join(' · ') }}</p>
            </div>

            <fieldset class="lines-group">
              <legend class="lbl lines-head">
                <span>Lines</span>
                <v-btn v-if="draftLines.length" size="small" variant="text" class="m3" :prepend-icon="mdiRestore" @click="resetRows">From the request</v-btn>
              </legend>
              <v-skeleton-loader v-if="loading" type="list-item-two-line@2" />
              <p v-else-if="!rows.length" class="hint">
                {{ commercial ? 'No CIMH-stock lines on this request.' : 'No lines.' }} Add one below.
              </p>
              <TransitionGroup v-else tag="ol" name="line" class="lines">
                <li v-for="(r, i) in rows" :key="r.key" class="line">
                  <span class="n console-mono" aria-hidden="true">{{ i + 1 }}</span>
                  <v-text-field v-model="r.description" :label="`Line ${i + 1} description`" class="desc" hide-details="auto" :error="tried && !r.description.trim()" />
                  <v-text-field v-model="r.qty" label="Qty" inputmode="numeric" class="qty mono-input" hide-details :error="tried && !qtyOk(r.qty)" />
                  <v-text-field v-model="r.unitPrice" label="Price" inputmode="decimal" class="price mono-input" hide-details :error="tried && !MONEY.test(r.unitPrice.trim())" />
                  <span class="amt console-mono"><Transition name="roll" mode="out-in"><span :key="amount(r)">{{ money(amount(r)) }}</span></Transition></span>
                  <v-btn :icon="mdiDeleteOutline" variant="text" size="small" :aria-label="`Remove line ${i + 1}`" @click="removeRow(r.key)" />
                </li>
              </TransitionGroup>
              <v-btn class="m3 add" variant="outlined" size="small" :prepend-icon="mdiPlus" @click="addRow">Add line</v-btn>
            </fieldset>

            <div class="three">
              <v-text-field v-model="form.fees" label="Fees" inputmode="decimal" class="mono-input" :error="tried && !MONEY.test(form.fees.trim())" />
              <v-text-field v-model="form.discount" label="Discount" inputmode="decimal" class="mono-input" :error="tried && !MONEY.test(form.discount.trim())" />
              <v-text-field
                v-if="!commercial"
                v-model="form.shipping"
                label="Shipping cost"
                inputmode="decimal"
                class="mono-input"
                :error="tried && !MONEY.test(form.shipping.trim())"
              />
            </div>

            <dl class="totals">
              <div><dt>Sub-total</dt><dd class="rolls"><Transition name="roll" mode="out-in"><span :key="money(subtotal)">{{ money(subtotal) }}</span></Transition></dd></div>
              <div v-if="cents(form.discount)"><dt>Discount</dt><dd>− {{ money(cents(form.discount)) }}</dd></div>
              <div v-if="cents(form.fees)"><dt>Fees</dt><dd>{{ money(cents(form.fees)) }}</dd></div>
              <div v-if="!commercial && cents(form.shipping)"><dt>Shipping</dt><dd>{{ money(cents(form.shipping)) }}</dd></div>
              <div class="grand"><dt>Total</dt><dd class="rolls"><Transition name="roll" mode="out-in"><span :key="money(total)">{{ money(total) }}</span></Transition></dd></div>
            </dl>
            <p v-if="commercial" class="hint">The printed commercial invoice adds: “The cost does not cover shipping fees.”</p>

            <Transition name="drop"><ul v-if="tried && problems.length" class="problems" role="alert">
              <li v-for="p in problems" :key="p">{{ p }}</li>
            </ul></Transition>
          </form>
        </div>
      </v-card-text>

      <v-divider />
      <v-card-actions class="acts">
        <v-spacer />
        <v-btn class="m3" variant="text" :disabled="busy" @click="open = false">Back</v-btn>
        <v-btn class="m3" type="submit" form="inv-form" color="primary" variant="flat" :loading="busy" :disabled="loadFailed">
          Create {{ commercial ? 'commercial invoice' : 'invoice' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.inv {
  background: rgb(var(--v-theme-surface));
}
.inv :deep(.v-divider) {
  opacity: 1;
  border-color: rgb(var(--v-theme-seam));
}
.sub {
  white-space: normal;
  opacity: 1;
  color: rgb(var(--v-theme-on-surface-variant));
}
.body {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(380px, 1fr);
  gap: var(--sp-4);
  padding: var(--sp-4) !important;
  align-items: start;
}
.preview {
  position: sticky;
  top: 0;
  min-width: 0;
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 8px;
  overflow: hidden;
  background: rgb(var(--v-theme-surface-variant));
  --doc-page-max: 640px;
}
.preview-empty {
  display: grid;
  place-items: center;
  min-height: 420px;
  padding: var(--sp-4);
  text-align: center;
  color: rgb(var(--v-theme-on-surface-variant));
}
.preview-note {
  margin: 0;
  padding: var(--sp-2) var(--sp-3);
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.panel {
  min-width: 0;
}
.form {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.email {
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 8px;
  padding: var(--sp-2) var(--sp-3) var(--sp-3);
  margin: 0;
  min-width: 0;
}
.email-q {
  padding: 0 var(--sp-1);
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
}
.hint {
  margin: 0;
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.two {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-2);
}
.three {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--sp-2);
}
.lbl {
  font-size: 13px;
  font-weight: 500;
  color: rgb(var(--v-theme-on-surface));
  margin: 0 0 var(--sp-1);
  padding: 0;
}
.to-text {
  margin: 0;
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.lines-group {
  border: 0;
  margin: 0;
  padding: 0;
  min-width: 0;
}
.lines-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.lines {
  list-style: none;
  margin: 0 0 var(--sp-2);
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.line {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) 72px 104px 96px 36px;
  gap: var(--sp-2);
  align-items: center;
}
.n {
  color: rgb(var(--v-theme-on-surface-variant));
  text-align: right;
}
.amt {
  text-align: right;
  font-size: 13px;
}
.add {
  align-self: flex-start;
}
.totals {
  margin: 0;
  padding: var(--sp-2) 0 0;
  border-top: 1px solid rgb(var(--v-theme-seam));
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.totals div {
  display: flex;
  justify-content: space-between;
}
.totals dt {
  color: rgb(var(--v-theme-on-surface-variant));
}
.totals dd {
  margin: 0;
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
}
.totals .grand {
  font-weight: 700;
  font-size: 16px;
  padding-top: var(--sp-1);
}
.totals .grand dt {
  color: rgb(var(--v-theme-on-surface));
}
.problems {
  margin: 0;
  padding: var(--sp-2) var(--sp-3) var(--sp-2) var(--sp-5);
  border-radius: 8px;
  background: rgb(var(--v-theme-error), 0.08);
  color: rgb(var(--v-theme-error));
  font-size: 14px;
}
.failed {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  align-items: flex-start;
}
.acts {
  padding: var(--sp-2) var(--sp-4);
}
/* Narrow: the panel first (it is what staff work in), the preview under it. */
@media (max-width: 1100px) {
  .body {
    grid-template-columns: minmax(0, 1fr);
  }
  .preview {
    position: static;
    order: 2;
  }
}
@media (max-width: 600px) {
  .line {
    grid-template-columns: 20px minmax(0, 1fr) 36px;
    grid-template-areas: 'n desc del' '. qty qty' '. price price' '. amt amt';
  }
  .line .n { grid-area: n; }
  .line .desc { grid-area: desc; }
  .line .qty { grid-area: qty; }
  .line .price { grid-area: price; }
  .line .amt { grid-area: amt; }
  .line > :last-child { grid-area: del; }
  .two,
  .three {
    grid-template-columns: minmax(0, 1fr);
  }
}
/* ---- motion (impeccable animate, 2026-11-20). Focal: the paper redrawing. The page on screen stays while the next
   version renders (dims, softens 1.5 px, a hairline sweeps the pane's top edge), then the new paper settles in sharp;
   never a blank between versions. Lines rise in, fold out, glide on reorder; figures roll; the to-do list drops open. */
.preview {
  isolation: isolate;
}
.sweep {
  position: absolute;
  inset: 0 0 auto;
  height: 2px;
  z-index: 2;
  background: linear-gradient(90deg, transparent, rgb(var(--v-theme-primary)), transparent);
  background-size: 40% 100%;
  background-repeat: no-repeat;
  opacity: 0;
  transition: opacity 160ms ease-in;
  pointer-events: none;
}
.preview.drawing .sweep {
  opacity: 1;
  animation: sweep 1.1s cubic-bezier(0.65, 0, 0.35, 1) infinite;
}
@keyframes sweep {
  from { background-position: -40% 0; }
  to { background-position: 140% 0; }
}
/* Settling back (the new version painted in place) is the slow, eased half; going soft is quick. */
.paper {
  transition: opacity 360ms cubic-bezier(0.16, 1, 0.3, 1), filter 360ms cubic-bezier(0.16, 1, 0.3, 1);
}
.preview.drawing .paper {
  opacity: 0.55;
  filter: blur(1.5px) saturate(0.8);
  transition-duration: 160ms;
  transition-timing-function: ease-in;
}
.line-enter-active {
  transition: opacity 220ms cubic-bezier(0.16, 1, 0.3, 1), transform 220ms cubic-bezier(0.16, 1, 0.3, 1);
}
.line-leave-active {
  transition: opacity 140ms ease-in, transform 140ms ease-in;
  position: absolute;
  inset-inline: 0;
}
.lines {
  position: relative;
}
.line-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.line-leave-to {
  opacity: 0;
  transform: translateX(12px);
}
.line-move {
  transition: transform 280ms cubic-bezier(0.16, 1, 0.3, 1);
}
.rolls,
.amt {
  display: inline-block;
  overflow: hidden;
  vertical-align: bottom;
}
.roll-enter-active {
  transition: opacity 200ms cubic-bezier(0.16, 1, 0.3, 1), transform 200ms cubic-bezier(0.16, 1, 0.3, 1);
}
.roll-leave-active {
  transition: opacity 90ms ease-in, transform 90ms ease-in;
}
.roll-enter-from {
  opacity: 0;
  transform: translateY(60%);
}
.roll-leave-to {
  opacity: 0;
  transform: translateY(-60%);
}
.roll-enter-active,
.roll-leave-active {
  display: inline-block;
}
.drop-enter-active {
  transition: opacity 200ms cubic-bezier(0.16, 1, 0.3, 1), clip-path 240ms cubic-bezier(0.16, 1, 0.3, 1);
}
.drop-leave-active {
  transition: opacity 120ms ease-in;
}
.drop-enter-from {
  opacity: 0;
  clip-path: inset(0 0 100% 0);
}
.drop-leave-to {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .preview.drawing .sweep {
    animation: none;
    background-size: 100% 100%;
    opacity: 0.6;
  }
  .preview.drawing .paper {
    filter: none;
  }
  .line-enter-from,
  .line-leave-to,
  .roll-enter-from,
  .roll-leave-to {
    transform: none;
  }
  .line-move {
    transition: none;
  }
  .drop-enter-from {
    clip-path: none;
  }
}
</style>
