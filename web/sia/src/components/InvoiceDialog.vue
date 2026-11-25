<script setup lang="ts">
/**
 * Invoice builder (A-03): the request's invoice / commercial invoice, one of each (plan 2026-11-24-invoice-crud).
 * Opens on the current one when it exists (edit: its lines, number and the saved PDF; locked once the request is
 * marked paid), otherwise starts a new one from the request. The PDF as it will be printed (legacy SIA layout) on
 * the left: the saved copy until something changes, then a live preview; on the right who is emailed, the number,
 * the date, the lines (each can be edited, removed or added) and fees, discount and shipping. Create stores rev 1;
 * Save changes issues the next revision (the earlier PDF stays for staff); Delete voids it with a reason.
 */
import {
  ApiError,
  createInvoice,
  DateField,
  DocumentViewer,
  getInvoice,
  getInvoiceDraft,
  type InvoiceKind,
  type InvoiceRecord,
  type OrderRequest,
  previewInvoice,
  ReasonDialog,
  reviseInvoice,
  ShortRef,
  useNotify,
  useSession,
  voidInvoice,
} from '@cimh/web-app'
import { formatDate, formatMoney } from '@cimh/web-ui'
import { mdiClose, mdiDeleteOutline, mdiPlus, mdiRestore } from '@mdi/js'
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import FilePreviewDialog from './FilePreviewDialog.vue'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ request: OrderRequest; kind: InvoiceKind }>()
/** The request's invoices changed (created, saved as a new revision or voided): reload the request. */
const emit = defineEmits<{ changed: [] }>()

const notify = useNotify()
const session = useSession()
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
const noun = computed(() => (commercial.value ? 'commercial invoice' : 'invoice'))

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
/** The lines "Undo changes" goes back to: the saved revision's, or the request's for a new invoice. */
const draftLines = ref<Row[]>([])
const loading = ref(false)
const loadFailed = ref(false)
const busy = ref(false)
const tried = ref(false)
const panel = ref<HTMLElement | null>(null)

// ---- which invoice: none yet (new), the current one (edit), or the current one once the request is paid (locked).
const record = ref<InvoiceRecord | null>(null)
const mode = computed<'new' | 'edit' | 'locked'>(() => (!record.value ? 'new' : record.value.locked ? 'locked' : 'edit'))
const locked = computed(() => mode.value === 'locked')
/** Made before invoices kept their lines: the form starts from the request; saving issues the next revision. */
const legacy = computed(() => !!record.value && record.value.lines == null)
const canVoid = computed(() => mode.value === 'edit' || (locked.value && session.isAdmin))
const earlier = computed(() => (record.value?.revisions ?? []).slice(0, -1).reverse())
const headTitle = computed(() => {
  if (mode.value === 'new') return `Create ${noun.value}`
  return `${title.value} ${record.value?.number ?? ''}`.trim()
})

const toRow = (l: { lineId?: string | null; description: string; qty: number; unitPrice: string }): Row => ({
  key: nextKey++,
  lineId: l.lineId ?? null,
  description: l.description,
  qty: String(l.qty),
  unitPrice: l.unitPrice,
})

const lineKey = (rs: Row[]) => JSON.stringify(rs.map((r) => [r.lineId, r.description, r.qty, r.unitPrice]))
const snapshot = () => JSON.stringify([form.number.trim(), form.date, form.fees, form.discount, form.shipping, lineKey(rows.value)])
const saved = ref('')
/** Something differs from what was loaded (edit: the saved revision). */
const dirty = computed(() => !loading.value && saved.value !== '' && snapshot() !== saved.value)
/** Save changes: only when something changed (forms rule), or to give a legacy invoice its lines. */
const canSave = computed(() => dirty.value || legacy.value)

const numberTaken = ref('')
const conflict = ref('')
watch(() => form.number, () => (numberTaken.value = ''))

async function load() {
  loading.value = true
  loadFailed.value = false
  conflict.value = ''
  numberTaken.value = ''
  saved.value = ''
  try {
    const rec = await getInvoice(props.request.id, props.kind)
    record.value = rec
    if (rec?.lines) {
      draftLines.value = rec.lines.map(toRow)
      rows.value = rec.lines.map(toRow)
      recipient.value = rec.recipient
      Object.assign(form, {
        number: rec.number ?? '',
        date: rec.date?.slice(0, 10) || localToday(),
        fees: rec.fees ?? '0.00',
        discount: rec.discount ?? '0.00',
        shipping: rec.shipping ?? '0.00',
      })
    } else {
      const d = await getInvoiceDraft(props.request.id, props.kind)
      draftLines.value = d.lines.map(toRow)
      rows.value = d.lines.map(toRow)
      recipient.value = d.recipient
      Object.assign(form, {
        number: rec?.number ?? d.number ?? d.suggestedNumber ?? '',
        date: rec?.date?.slice(0, 10) || localToday(),
        fees: d.fees,
        discount: d.discount,
        shipping: d.shipping,
      })
    }
    // A new invoice is mailed by default; a corrected one only when staff tick it (D8).
    form.emailCustomer = !rec
    form.emailStaff = !rec
    saved.value = snapshot()
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
  record.value = null
  rows.value = []
  void load()
})

function addRow() {
  rows.value.push({ key: nextKey++, lineId: null, description: '', qty: '1', unitPrice: '0.00' })
  void nextTick(() => panel.value?.querySelector<HTMLTextAreaElement>('.line:last-child textarea')?.focus())
}
function removeRow(key: number) {
  rows.value = rows.value.filter((r) => r.key !== key)
}
/** "Undo changes" shows only once the lines differ from where they started. */
const edited = computed(() => !loading.value && draftLines.value.length > 0 && lineKey(rows.value) !== lineKey(draftLines.value))
function resetRows() {
  rows.value = draftLines.value.map((r) => ({ ...r, key: nextKey++ }))
}

const qtyOk = (q: string) => /^\d{1,6}$/.test(q.trim()) && Number(q) >= 1
const cents = (v: string) => (MONEY.test(v.trim()) ? Math.round(Number(v) * 100) : 0)
const amount = (r: Row) => (qtyOk(r.qty) ? cents(r.unitPrice) * Number(r.qty) : 0)
const subtotal = computed(() => rows.value.reduce((s, r) => s + amount(r), 0))
const total = computed(() => subtotal.value + cents(form.fees) + (commercial.value ? 0 : cents(form.shipping)) - cents(form.discount))
const money = (c: number) => formatMoney((c / 100).toFixed(2), 'BBD')
/** A line amount without the currency (the ledger names it once). */
const plain = (c: number) => (c / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const problems = computed(() => {
  const out: string[] = []
  if (!form.number.trim()) out.push(`Enter the ${noun.value} number`)
  if (numberTaken.value) out.push(numberTaken.value)
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

// ---- preview: the saved PDF while nothing has changed; a live preview 500 ms after the last change (the number may
// still be empty), once the lines can be drawn.
const previewFile = ref<File | null>(null)
const previewProblem = ref('')
const previewing = ref(false)
const showSaved = computed(() => !!record.value && !dirty.value)
let timer: ReturnType<typeof setTimeout> | undefined
let seq = 0
const drawable = computed(() => problems.value.filter((p) => !p.startsWith('Enter the') && p !== numberTaken.value).length === 0)
async function refreshPreview() {
  if (!open.value || loading.value || showSaved.value) return
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

const emailed = () => [form.emailCustomer && 'the customer', form.emailStaff && 'staff'].filter(Boolean).join(' and ')

/** Someone else changed it meanwhile (or made one first): say so; Reload shows theirs (what is typed here is lost). */
function refused(e: unknown): boolean {
  if (!(e instanceof ApiError)) return false
  if (e.code === 'INVOICE_NUMBER_TAKEN') {
    numberTaken.value = e.detail ?? `This number is already used by another ${noun.value}`
    void nextTick(() => panel.value?.querySelector<HTMLInputElement>('.ident input')?.focus())
    return true
  }
  if (e.code === 'VERSION_CONFLICT' || e.code === 'INVOICE_EXISTS' || e.code === 'INVOICE_LOCKED') {
    conflict.value = e.detail ?? `The ${noun.value} changed meanwhile.`
    return true
  }
  return false
}

async function submit() {
  tried.value = true
  if (problems.value.length) {
    await nextTick()
    panel.value?.querySelector<HTMLElement>('.problems')?.scrollIntoView({ block: 'nearest' })
    return
  }
  if (busy.value || locked.value) return
  busy.value = true
  try {
    const who = emailed()
    if (record.value) {
      const rev = record.value.rev + 1
      await reviseInvoice(props.request.id, props.kind, record.value.rev, body())
      notify.toast(`${title.value} ${form.number.trim()} saved as revision ${rev}${who ? `; emailed to ${who}` : ''}`, 'success')
    } else {
      await createInvoice(props.request.id, body())
      notify.toast(`${title.value} ${form.number.trim()} created${who ? `; emailed to ${who}` : ''}`, 'success')
    }
    emit('changed')
    open.value = false
  } catch (e) {
    if (!refused(e)) notify.report(e)
  } finally {
    busy.value = false
  }
}

// ---- void (Delete invoice…): asks for a reason first; nobody is emailed.
const voidOpen = ref(false)
const voiding = ref(false)
const voidText = computed(() => {
  const n = record.value?.number ? ` ${record.value.number}` : ''
  return `The customer no longer sees it and is not emailed. Number${n} stays used. You can create a new ${noun.value} afterwards.`
})
async function doVoid(reason: string) {
  if (!record.value) return
  voiding.value = true
  try {
    await voidInvoice(props.request.id, props.kind, record.value.rev, reason)
    notify.toast(`${title.value} ${record.value.number ?? ''} voided`.replace('  ', ' '), 'success')
    voidOpen.value = false
    emit('changed')
    open.value = false
  } catch (e) {
    voidOpen.value = false
    if (!refused(e)) notify.report(e)
  } finally {
    voiding.value = false
  }
}

// ---- earlier copies (revisions before the current one), opened in the file preview.
const copyOpen = ref(false)
const copy = ref<{ fileId: string; title: string } | null>(null)
function openCopy(rev: { rev: number; fileId: string; number: string | null }) {
  copy.value = { fileId: rev.fileId, title: `${title.value} ${rev.number ?? ''} · revision ${rev.rev}`.replace('  ', ' ') }
  copyOpen.value = true
}
const day = (iso: string | null) => (iso ? formatDate(iso.slice(0, 10)) : '')
</script>

<template>
  <v-dialog v-model="open" :max-width="1440" :fullscreen="smAndDown" scrollable :persistent="busy">
    <v-card class="inv" :rounded="smAndDown ? 0 : 'lg'">
      <v-card-item>
        <v-card-title class="t-h3">{{ headTitle }}</v-card-title>
        <v-card-subtitle class="sub">
          <span class="console-mono"><ShortRef :id="request.id" /></span>
          <template v-if="request.organisationName || request.customerName"> · {{ request.organisationName || request.customerName }}</template>
          <template v-if="commercial"> · CIMH stock only (supplier items ship direct)</template>
        </v-card-subtitle>
        <p v-if="record" class="state" data-testid="invoice-state">
          <span>Revision {{ record.rev }}</span>
          <span v-if="record.source === 'AUTO'"> · Made automatically from the request</span>
          <span v-if="locked" class="locked"> · Paid: read-only{{ session.isAdmin ? '' : '. Only an administrator can void it' }}</span>
        </p>
        <p v-if="earlier.length" class="earlier">
          <span class="cap">Earlier copies</span>
          <v-btn
            v-for="c in earlier"
            :key="c.rev"
            variant="text"
            size="small"
            class="m3 copy"
            @click="openCopy(c)"
          >Revision {{ c.rev }}<template v-if="c.at"> · {{ day(c.at) }}</template></v-btn>
        </p>
      </v-card-item>
      <v-divider />

      <v-card-text class="body">
        <section class="preview" :class="{ drawing: previewing && !!previewFile }" aria-label="Preview" :aria-busy="previewing">
          <span class="sweep" aria-hidden="true" />
          <DocumentViewer
            v-if="showSaved && record"
            :file-id="record.fileId"
            :name="`${title} ${record.number ?? ''} revision ${record.rev}`"
            mime="application/pdf"
            what="Saved copy"
            link="none"
            class="paper"
          />
          <DocumentViewer
            v-else-if="previewFile"
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
          <p v-if="!showSaved && previewFile && previewProblem" class="preview-note" role="status">{{ previewProblem }}</p>
          <p v-if="mode !== 'new'" class="preview-note" role="status">
            {{ showSaved ? 'The copy the customer has.' : 'Preview of your changes: saving issues revision ' + ((record?.rev ?? 0) + 1) + '.' }}
          </p>
        </section>

        <div ref="panel" class="panel">
          <div v-if="loadFailed" class="failed">
            <p>The request's lines could not be loaded.</p>
            <v-btn class="m3" variant="outlined" @click="load">Retry</v-btn>
          </div>
          <div v-else-if="conflict" class="conflict" role="alert">
            <p>{{ conflict }} Reload to see the latest; what you typed here is not kept.</p>
            <v-btn class="m3" variant="outlined" size="small" @click="load">Reload</v-btn>
          </div>
          <form v-if="!loadFailed" id="inv-form" class="form" novalidate @submit.prevent="submit">
            <p v-if="legacy" class="note legacy">
              This {{ noun }} was made before invoices kept their lines, so the lines below come from the request.
              Check them against the copy on the left; saving issues revision {{ (record?.rev ?? 0) + 1 }}.
            </p>
            <!-- 1 · Which invoice: number (φ) beside date (1), then who it is for. -->
            <section class="sec" aria-label="Invoice details">
              <div class="ident">
                <v-text-field
                  v-model="form.number"
                  :label="commercial ? 'Commercial invoice #' : 'Invoice #'"
                  class="mono-input square"
                  autocomplete="off"
                  hide-details
                  :error="(tried && !form.number.trim()) || !!numberTaken"
                  :readonly="locked"
                />
                <DateField v-model="form.date" label="Date" class="square" hide-details :readonly="locked" :menu-props="{ location: 'bottom end', origin: 'top end' }" />
              </div>
              <div v-if="recipient.length" class="to">
                <span class="cap">{{ commercial ? 'Ship to' : 'Billed to' }}</span>
                <p class="to-who">{{ recipient[0] }}</p>
                <p v-if="recipient.length > 1" class="to-rest">{{ recipient.slice(1).join(' · ') }}</p>
              </div>
            </section>

            <!-- 2 · Lines: a table without rules; each cell is the field itself (square corners, so the row reads as one
                 row of a table, not a stack of pills). -->
            <section class="sec" aria-label="Lines">
              <v-skeleton-loader v-if="loading" type="list-item-two-line@2" />
              <p v-else-if="!rows.length" class="note">{{ commercial ? 'No CIMH-stock lines on this request.' : 'No lines yet.' }}</p>
              <table v-else class="ltab">
                <colgroup>
                  <col />
                  <col class="c-qty" />
                  <col class="c-price" />
                  <col class="c-amt" />
                  <col class="c-del" />
                </colgroup>
                <thead>
                  <tr>
                    <th scope="col">Item</th>
                    <th scope="col" class="r">Qty</th>
                    <th scope="col" class="r">Price</th>
                    <th scope="col" class="r">Amount</th>
                    <th scope="col"><span class="sr-only">Remove</span></th>
                  </tr>
                </thead>
                <TransitionGroup tag="tbody" name="line">
                  <tr v-for="(r, i) in rows" :key="r.key" class="line">
                    <td class="desc-c">
                      <v-textarea
                        v-model="r.description"
                        :aria-label="`Line ${i + 1} description`"
                        class="desc cell"
                        rows="1"
                        auto-grow
                        hide-details
                        :error="tried && !r.description.trim()"
                        :readonly="locked"
                        @keydown.enter.prevent
                      />
                    </td>
                    <td class="qty-c"><v-text-field v-model="r.qty" :aria-label="`Line ${i + 1} quantity`" inputmode="numeric" class="cell mono-input num" hide-details :error="tried && !qtyOk(r.qty)" :readonly="locked" /></td>
                    <td class="price-c"><v-text-field v-model="r.unitPrice" :aria-label="`Line ${i + 1} price`" inputmode="decimal" class="cell mono-input num" hide-details :error="tried && !MONEY.test(r.unitPrice.trim())" :readonly="locked" /></td>
                    <td class="amt-c console-mono"><span class="amt"><Transition name="roll" mode="out-in"><span :key="amount(r)">{{ plain(amount(r)) }}</span></Transition></span></td>
                    <td class="del-c"><v-btn v-if="!locked" :icon="mdiClose" variant="text" size="x-small" class="del" :aria-label="`Remove line ${i + 1}`" @click="removeRow(r.key)" /></td>
                  </tr>
                </TransitionGroup>
              </table>
              <div v-if="!locked" class="line-acts">
                <v-btn class="m3" variant="text" size="small" :prepend-icon="mdiPlus" @click="addRow">Add line</v-btn>
                <v-btn v-if="edited" size="small" variant="text" class="m3 quiet" :prepend-icon="mdiRestore" @click="resetRows">Undo changes</v-btn>
              </div>
            </section>

            <!-- 3 · Totals: a ledger 1/φ of the panel wide, set right like the printed invoice; the adjustments are typed
                 in place (no second copy of them above). -->
            <section class="sec" aria-label="Totals">
              <dl class="ledger">
                <div><dt>Sub-total</dt><dd class="console-mono rolls"><Transition name="roll" mode="out-in"><span :key="money(subtotal)">{{ money(subtotal) }}</span></Transition></dd></div>
                <div>
                  <dt><label for="inv-fees">Fees</label></dt>
                  <dd><v-text-field id="inv-fees" v-model="form.fees" inputmode="decimal" class="mono-input num adj cell" hide-details :error="tried && !MONEY.test(form.fees.trim())" :readonly="locked" /></dd>
                </div>
                <div>
                  <dt><label for="inv-discount">Discount</label></dt>
                  <dd><v-text-field id="inv-discount" v-model="form.discount" inputmode="decimal" class="mono-input num adj cell" hide-details :error="tried && !MONEY.test(form.discount.trim())" :readonly="locked" /></dd>
                </div>
                <div v-if="!commercial">
                  <dt><label for="inv-shipping">Shipping</label></dt>
                  <dd><v-text-field id="inv-shipping" v-model="form.shipping" inputmode="decimal" class="mono-input num adj cell" hide-details :error="tried && !MONEY.test(form.shipping.trim())" :readonly="locked" /></dd>
                </div>
                <div class="grand"><dt>Total</dt><dd class="console-mono rolls"><Transition name="roll" mode="out-in"><span :key="money(total)">{{ money(total) }}</span></Transition></dd></div>
              </dl>
              <p v-if="commercial" class="note r">Printed with “The cost does not cover shipping fees.”</p>
            </section>

            <Transition name="drop"><ul v-if="tried && problems.length" class="problems" role="alert">
              <li v-for="p in problems" :key="p">{{ p }}</li>
            </ul></Transition>
          </form>
        </div>
      </v-card-text>

      <v-divider />
      <v-card-actions class="acts">
        <v-btn
          v-if="record && canVoid && !loading"
          class="m3 m3-danger void"
          variant="outlined"
          :prepend-icon="mdiDeleteOutline"
          :disabled="busy"
          @click="voidOpen = true"
        >{{ locked ? 'Void' : 'Delete' }} {{ noun }}…</v-btn>
        <fieldset v-if="!loadFailed && !locked" class="email">
          <legend class="email-q">Email {{ record ? 'the corrected copy ' : '' }}to</legend>
          <v-checkbox v-model="form.emailCustomer" color="primary" hide-details density="compact" label="Customer" />
          <v-checkbox v-model="form.emailStaff" color="primary" hide-details density="compact" label="Staff" title="The invoice email list" />
        </fieldset>
        <v-spacer />
        <v-btn class="m3" variant="text" :disabled="busy" @click="open = false">{{ locked ? 'Close' : 'Back' }}</v-btn>
        <v-btn
          v-if="mode === 'new'"
          class="m3"
          type="submit"
          form="inv-form"
          color="primary"
          variant="flat"
          :loading="busy"
          :disabled="loadFailed || loading"
        >Create {{ noun }}</v-btn>
        <v-btn
          v-else-if="mode === 'edit'"
          class="m3"
          type="submit"
          form="inv-form"
          color="primary"
          variant="flat"
          :loading="busy"
          :disabled="loadFailed || loading || !canSave"
        >Save changes</v-btn>
      </v-card-actions>
    </v-card>
    <ReasonDialog
      v-model="voidOpen"
      :title="`${locked ? 'Void' : 'Delete'} ${noun} ${record?.number ?? ''}?`"
      :text="voidText"
      :confirm="`${locked ? 'Void' : 'Delete'} ${noun}`"
      danger
      :busy="voiding"
      @submit="doVoid"
    />
    <FilePreviewDialog v-model="copyOpen" :request="request" :file-id="copy?.fileId ?? null" :title="copy?.title" />
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
  grid-template-columns: minmax(0, 1.272fr) minmax(520px, 1fr);
  gap: var(--f3);
  /* Same 24 px edge as the title above (v-card-item), so preview and panel line up with it. */
  padding: var(--sp-4) var(--sp-6) !important;
  align-items: start;
}
.preview {
  position: sticky;
  top: 0;
  min-width: 0;
  /* The paper's ground, no line around it: the preview and the panel share the title's edges. */
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
/* ---- form panel (impeccable distill + typeset, 2026-11-24). Golden ratio throughout:
   type   body 14 px; caption 14/√φ = 11 px; total 14·φ = 22.65 px (three sizes, no others in the panel);
   space  Fibonacci 8 · 13 · 21 · 34 (each ≈ the last × φ): 8 inside a group, 13 label to content, 34 between sections;
   layout preview √φ : panel 1 (owner: a little wider than φ : 1); number φ : date 1; item φ : figures 1; the totals ledger 1/φ of the panel wide. */
.inv {
  --phi-cap: 11px;
  --phi-body: 14px;
  --phi-lead: 22.65px;
  --f1: 8px;
  --f2: 13px;
  --f3: 21px;
  --f4: 34px;
}
.panel {
  min-width: 0;
  font-size: var(--phi-body);
}
.form {
  display: flex;
  flex-direction: column;
  gap: var(--f4);
}
.sec {
  display: flex;
  flex-direction: column;
  gap: var(--f1);
  min-width: 0;
}
.cap {
  margin: 0;
  font-size: var(--phi-cap);
  line-height: 1.618;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-on-surface-variant));
}
.ident {
  display: grid;
  grid-template-columns: minmax(0, 1.618fr) minmax(0, 1fr);
  gap: var(--f1);
}
.to {
  margin-top: var(--f2);
}
.to .cap {
  display: block;
  margin-bottom: 2px;
}
.to-who,
.to-rest {
  margin: 0;
  line-height: 1.5;
}
.to-who {
  color: rgb(var(--v-theme-on-surface));
}
.to-rest {
  color: rgb(var(--v-theme-on-surface-variant));
  overflow-wrap: anywhere;
  text-wrap: pretty;
}
.note {
  margin: 0;
  color: rgb(var(--v-theme-on-surface-variant));
}
.r {
  text-align: right;
}
/* Lines table: no rules, no cell borders; rows 8 px apart (half of the 8 px gap on each side of a cell). */
.ltab {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  table-layout: fixed;
}
.c-qty { width: 64px; }
.c-price { width: 104px; }
.c-amt { width: 96px; }
.c-del { width: 32px; }
.ltab th {
  padding: 0 0 var(--f1) var(--f1);
  font-size: var(--phi-cap);
  line-height: 1.618;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  text-align: left;
  color: rgb(var(--v-theme-on-surface-variant));
}
.ltab th:first-child {
  padding-left: 10px; /* over the cell text */
}
.ltab th.r {
  text-align: right;
  padding-right: 10px;
}
.ltab th:nth-child(4) {
  padding-right: 0;
}
.ltab td {
  padding: 4px 0 4px var(--f1);
  vertical-align: top;
}
.ltab td:first-child {
  padding-left: 0;
}
.ltab td.amt-c,
.ltab td.del-c {
  vertical-align: middle;
}
.num :deep(input) {
  text-align: right;
}
/* Cells: 8 px corners (the chip radius), 32 px high, 10 px inset: fields that read as table cells. */
.square :deep(.v-field) {
  border-radius: 8px;
}
.cell :deep(.v-field) {
  border-radius: 8px;
  --v-field-padding-start: 10px;
  --v-field-padding-end: 10px;
}
.cell :deep(.v-field__input) {
  min-height: 32px;
  padding-top: 6px;
  padding-bottom: 6px;
}
.desc :deep(textarea) {
  /* One line high until the text needs more; never a scroll bar inside. */
  line-height: 20px;
  min-height: 32px;
  overflow: hidden;
  resize: none;
  mask-image: none;
}
.amt-c {
  text-align: right;
  white-space: nowrap;
  color: rgb(var(--v-theme-on-surface));
}
.del-c {
  text-align: right;
}
.del {
  color: rgb(var(--v-theme-on-surface-variant));
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.line-acts {
  display: flex;
  justify-content: space-between;
  margin-left: calc(var(--f1) * -1);
}
/* Every field and choice in the panel reads at the body size (Vuetify sets 16 px). */
.panel :deep(.v-field__input),
.panel :deep(.v-field__input textarea),
.acts :deep(.v-label) {
  font-size: var(--phi-body);
}
.acts :deep(.v-label) {
  opacity: 1;
  color: rgb(var(--v-theme-on-surface));
}
.quiet {
  color: rgb(var(--v-theme-on-surface-variant)) !important;
}
/* The ledger: 1/φ of the panel, set right; rows on a 34 px beat (8 · 13 · 21 · 34), the total φ larger. */
.ledger {
  margin: 0 0 0 auto;
  width: 61.8%;
  min-width: 260px;
  display: flex;
  flex-direction: column;
  gap: var(--f1);
}
.ledger > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--f2);
  min-height: var(--f4);
}
.ledger dt {
  color: rgb(var(--v-theme-on-surface-variant));
}
.ledger dt label {
  cursor: pointer;
}
.ledger dd {
  margin: 0;
  text-align: right;
}
.adj {
  width: 120px;
}
.ledger .grand {
  margin-top: var(--f2);
  padding-top: var(--f2);
  border-top: 1px solid rgb(var(--v-theme-seam));
  align-items: baseline;
}
.ledger .grand dt {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 600;
}
.ledger .grand dd {
  font-size: var(--phi-lead);
  line-height: 1.236;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.problems {
  margin: 0;
  padding: var(--f2) var(--f2) var(--f2) var(--f3);
  border-radius: 8px;
  background: rgb(var(--v-theme-error), 0.08);
  color: rgb(var(--v-theme-error));
}
.failed {
  display: flex;
  flex-direction: column;
  gap: var(--f1);
  align-items: flex-start;
}
.acts {
  padding: var(--f1) var(--sp-6);
  flex-wrap: wrap;
  gap: var(--f1);
}
.email {
  display: flex;
  align-items: center;
  gap: var(--f2);
  border: 0;
  padding: 0;
  margin: 0;
  min-width: 0;
}
.email-q {
  float: left;
  padding: 0;
  font-size: var(--phi-cap);
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-on-surface-variant));
}
.email :deep(.v-checkbox) {
  flex: none;
}
/* Existing invoice: its revision and state under the subtitle; earlier copies as quiet links. */
.state,
.earlier {
  margin: var(--f1) 0 0;
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.state .locked {
  color: rgb(var(--v-theme-on-surface));
}
.earlier {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0 var(--f1);
}
.earlier .cap {
  margin-right: var(--f1);
}
.earlier .copy {
  min-width: 0;
  padding: 0 var(--f1);
}
.conflict {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--f1) var(--f2);
  margin-bottom: var(--f3);
  padding: var(--f2);
  border-radius: 8px;
  background: rgb(var(--v-theme-warning), 0.12);
}
.conflict p {
  margin: 0;
  flex: 1 1 260px;
}
.legacy {
  padding: var(--f2);
  border-radius: 8px;
  background: rgb(var(--v-theme-surface-variant));
}
.void {
  margin-right: var(--f2);
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
  .ledger {
    width: 100%;
    min-width: 0;
  }
}
/* Phone: each table row becomes two (the item across, then qty · price · amount · remove under it). */
@media (max-width: 600px) {
  /* The footer wraps: Delete keeps its own row at the left edge, apart from Back and Save. */
  .acts .void {
    margin-right: auto;
  }
  .ltab,
  .ltab thead,
  .ltab tbody {
    display: block;
  }
  .ltab tr {
    display: grid;
    grid-template-columns: 64px 104px minmax(0, 1fr) 32px;
    grid-template-areas: "desc desc desc desc" "qty price amt del";
    row-gap: 0;
  }
  .ltab thead tr {
    grid-template-areas: "qty price amt del";
  }
  .ltab th:first-child {
    display: none;
  }
  .ltab th:nth-child(2) { grid-area: qty; }
  .ltab th:nth-child(3) { grid-area: price; }
  .ltab th:nth-child(4) { grid-area: amt; }
  .ltab th:nth-child(5) { grid-area: del; }
  .ltab td { display: block; }
  .ltab .desc-c { grid-area: desc; padding-left: 0; }
  .ltab .qty-c { grid-area: qty; padding-left: 0; }
  .ltab .price-c { grid-area: price; }
  .ltab .amt-c { grid-area: amt; align-self: center; }
  .ltab .del-c { grid-area: del; align-self: center; }
  .ltab tbody tr + tr {
    margin-top: var(--f2);
  }
  .ident {
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
