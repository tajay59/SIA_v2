<script setup lang="ts">
/**
 * A-04 quote builder (staff, QUOTING or revising a QUOTED request).
 *   Suppliers: name + their quote PDFs (uploaded to document-svc as supplier_quote).
 *   Lines: offer from CIMH stock (only lines with the full quantity in stock; priced by the server from the
 *   catalogue cost, converted with the exchange rate for USD requests) and/or a supplier with a unit price.
 *   A line is priced by one supplier only (server rule). Every line needs at least one option.
 * The draft saves itself (PUT quote-draft, If-Match) a moment after each change. "Send quote" saves, then
 * sends (QUOTING → QUOTED, or a new version while QUOTED); the customer is emailed.
 */
import {
  act,
  ApiError,
  fileUrl,
  getRequest,
  type OrderRequest,
  saveQuoteDraft,
  uploadRequestFile,
  useNotify,
} from '@cimh/web-app'
import { formatMoney } from '@cimh/web-ui'
import { mdiArrowLeft, mdiDeleteOutline, mdiPaperclip, mdiPlus } from '@mdi/js'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

definePage({ meta: { guard: 'staff', title: 'Quote builder' } })
const route = useRoute('/requests/[id]/quote')
const router = useRouter()
const notify = useNotify()
const r = ref<OrderRequest | null>(null)

interface Supplier { name: string; fileIds: string[]; uploading: boolean }
interface LineState { cimh: boolean; supplier: string | null; unitPrice: string }
const suppliers = ref<Supplier[]>([])
const lines = reactive<Record<string, LineState>>({})
const exchangeRate = ref('')
const saving = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')
let ready = false

type Draft = { supplierQuotes: { supplier: string; fileIds: string[]; lines: { lineId: string; unitPrice: string }[] }[]; cimh?: { lineIds: string[]; exchangeRate?: string | null } | null }

async function load() {
  ready = false
  r.value = await getRequest(route.params.id)
  if (!r.value.allowedActions?.includes('quote-draft')) return void router.replace(`/requests/${r.value.id}`)
  const draft = (r.value as unknown as { quoteDraft?: Draft }).quoteDraft
  const latest = Math.max(0, ...(r.value.quotes ?? []).map((q) => q.version))
  // Start from the draft, else from the last sent quote (revising), else empty.
  const sq: Draft['supplierQuotes'] = draft?.supplierQuotes ??
    (r.value.quotes ?? []).filter((q) => q.version === latest).map((q) => ({ supplier: q.supplier ?? '', fileIds: q.fileIds ?? [],
      lines: q.lines.map((l) => ({ lineId: l.lineId, unitPrice: l.unitPrice })) }))  // prettier-ignore
  const cimhIds = draft?.cimh?.lineIds ?? r.value.cimhQuote?.lines.map((l) => l.lineId) ?? []
  suppliers.value = sq.map((s) => ({ name: s.supplier, fileIds: [...s.fileIds], uploading: false }))
  for (const l of r.value.lines) {
    const found = sq.find((s) => s.lines.some((x) => x.lineId === l.lineId))
    lines[l.lineId] = {
      cimh: cimhIds.includes(l.lineId) && !!l.cimhAvailable,
      supplier: found?.supplier ?? null,
      unitPrice: found?.lines.find((x) => x.lineId === l.lineId)?.unitPrice ?? '',
    }
  }
  exchangeRate.value = draft?.cimh?.exchangeRate ?? r.value.cimhQuote?.exchangeRate ?? ''
  setTimeout(() => (ready = true))
}
watch(() => route.params.id, () => void load().catch((e) => notify.report(e)), { immediate: true })

const MONEY = /^\d{1,12}\.\d{2}$/
const RATE = /^\d+(\.\d{1,6})?$/
const usd = computed(() => r.value?.currency === 'USD')
const priceError = (s: LineState) => (s.supplier && !MONEY.test(s.unitPrice) ? 'Use 2 decimals, e.g. 120.00' : '')

function draftBody(): Draft {
  const names = suppliers.value.map((s) => s.name.trim()).filter(Boolean)
  return {
    supplierQuotes: suppliers.value
      .filter((s) => s.name.trim())
      .map((s) => ({
        supplier: s.name.trim(),
        fileIds: s.fileIds,
        lines: Object.entries(lines)
          .filter(([, v]) => v.supplier?.trim() === s.name.trim() && MONEY.test(v.unitPrice) && names.includes(v.supplier!.trim()))
          .map(([lineId, v]) => ({ lineId, unitPrice: v.unitPrice })),
      })),
    cimh: {
      lineIds: Object.entries(lines).filter(([, v]) => v.cimh).map(([k]) => k),
      exchangeRate: RATE.test(exchangeRate.value) ? exchangeRate.value : null,
    },
  }
}

let timer: ReturnType<typeof setTimeout> | undefined
let chain: Promise<unknown> = Promise.resolve()
function save(): Promise<unknown> {
  chain = chain.then(async () => {
    if (!r.value) return
    saving.value = 'saving'
    try {
      r.value = await saveQuoteDraft(r.value, draftBody())
      saving.value = 'saved'
    } catch (e) {
      saving.value = 'error'
      if (e instanceof ApiError && e.status === 409) await load()
      notify.report(e)
      throw e
    }
  })
  return chain
}
watch([suppliers, lines, exchangeRate], () => {
  if (!ready) return
  clearTimeout(timer)
  timer = setTimeout(() => void save().catch(() => undefined), 800)
}, { deep: true })

function addSupplier() {
  suppliers.value.push({ name: '', fileIds: [], uploading: false })
}
function removeSupplier(i: number) {
  const name = suppliers.value[i]!.name.trim()
  suppliers.value.splice(i, 1)
  for (const v of Object.values(lines)) if (v.supplier?.trim() === name) v.supplier = null
}
async function attach(s: Supplier, files: File | File[] | null) {
  const list = files ? (Array.isArray(files) ? files : [files]) : []
  if (!r.value || !list.length) return
  s.uploading = true
  try {
    for (const f of list) s.fileIds.push((await uploadRequestFile(r.value.id, 'supplier_quote', f)).id)
  } catch (e) {
    notify.report(e)
  } finally {
    s.uploading = false
  }
}

const missing = computed(() => r.value?.lines.filter((l) => !lines[l.lineId]?.cimh && !(lines[l.lineId]?.supplier && MONEY.test(lines[l.lineId]!.unitPrice))) ?? [])
const needsRate = computed(() => usd.value && Object.values(lines).some((v) => v.cimh) && !RATE.test(exchangeRate.value))
const supplierTotal = (lineId: string) => {
  const v = lines[lineId]
  const line = r.value?.lines.find((l) => l.lineId === lineId)
  if (!v || !line || !MONEY.test(v.unitPrice)) return ''
  return formatMoney((Math.round(Number(v.unitPrice) * 100) * line.qty / 100).toFixed(2), r.value?.currency ?? 'BBD')
}
const sending = ref(false)
async function send() {
  if (!r.value) return
  sending.value = true
  clearTimeout(timer)
  try {
    await save()
    r.value = await act(r.value, '/requests/{requestId}/send-quote', undefined)
    notify.toast(`Quote version ${Math.max(...(r.value.quotes ?? []).map((q) => q.version))} sent to the customer`, 'success')
    await router.push(`/requests/${r.value.id}`)
  } catch (e) {
    if (e instanceof ApiError) notify.report(e)
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <div class="page stack-md">
    <v-btn :to="`/requests/${route.params.id}`" variant="text" :prepend-icon="mdiArrowLeft" class="back">Request</v-btn>
    <v-skeleton-loader v-if="!r" type="table" />
    <template v-else>
      <p class="t-body">
        <span class="t-mono">{{ r.id }}</span> · {{ r.customerName }} · {{ r.organisationName ?? 'no organisation' }} ·
        quote in <strong>{{ r.currency }}</strong>
        <span class="saving t-caption muted" role="status">{{ { idle: '', saving: 'Saving…', saved: 'Draft saved', error: 'Not saved' }[saving] }}</span>
      </p>

      <v-card border flat>
        <v-card-title class="t-h3">Suppliers</v-card-title>
        <v-card-text class="stack-sm">
          <div v-for="(s, i) in suppliers" :key="i" class="supplier">
            <v-text-field v-model="s.name" label="Supplier name" hide-details class="name" />
            <v-file-input
              label="Quote PDF"
              :prepend-icon="mdiPaperclip"
              accept=".pdf,.jpg,.jpeg,.png"
              multiple
              hide-details
              :loading="s.uploading"
              class="file"
              @update:model-value="(f: File | File[] | null) => attach(s, f)"
            />
            <v-btn :icon="mdiDeleteOutline" variant="text" :aria-label="`Remove ${s.name || 'supplier'}`" @click="removeSupplier(i)" />
            <div v-if="s.fileIds.length" class="files">
              <v-chip v-for="f in s.fileIds" :key="f" :href="fileUrl(f)" target="_blank" size="small" label>{{ f.slice(0, 10) }}…</v-chip>
            </div>
          </div>
          <v-btn variant="text" color="primary" :prepend-icon="mdiPlus" @click="addSupplier">Add supplier</v-btn>
        </v-card-text>
      </v-card>

      <v-card border flat>
        <v-card-title class="t-h3">Prices</v-card-title>
        <v-table>
          <thead>
            <tr><th>Item</th><th class="num">Qty</th><th>From CIMH stock</th><th>Supplier</th><th>Unit price ({{ r.currency }})</th><th class="num">Line total</th></tr>
          </thead>
          <tbody>
            <tr v-for="l in r.lines" :key="l.lineId">
              <td><span class="t-label">{{ l.product.name }}</span><span class="t-caption muted d-block">{{ l.lineId }}</span></td>
              <td class="num tnum">{{ l.qty }}</td>
              <td>
                <v-checkbox v-if="l.cimhAvailable" v-model="lines[l.lineId]!.cimh" label="Offer" hide-details density="compact" />
                <span v-else class="t-caption muted">Not fully in stock</span>
              </td>
              <td class="cell">
                <v-select
                  v-model="lines[l.lineId]!.supplier"
                  :items="[{ title: 'None', value: null }, ...suppliers.filter((s) => s.name.trim()).map((s) => ({ title: s.name.trim(), value: s.name.trim() }))]"
                  density="compact"
                  hide-details
                  :aria-label="`Supplier for ${l.product.name}`"
                />
              </td>
              <td class="cell">
                <v-text-field
                  v-model="lines[l.lineId]!.unitPrice"
                  density="compact"
                  placeholder="0.00"
                  :disabled="!lines[l.lineId]!.supplier"
                  :error-messages="priceError(lines[l.lineId]!) || undefined"
                  hide-details="auto"
                  :aria-label="`Unit price for ${l.product.name}`"
                />
              </td>
              <td class="num tnum">{{ supplierTotal(l.lineId) }}</td>
            </tr>
          </tbody>
        </v-table>
        <v-card-text>
          <v-text-field
            v-if="usd"
            v-model="exchangeRate"
            label="Exchange rate (BBD per 1 USD)"
            hint="Used for CIMH-stock prices and the admin fee, which are in BBD"
            persistent-hint
            class="rate"
            :error-messages="needsRate ? 'Required when you offer CIMH stock on a USD request' : undefined"
          />
          <p class="t-caption muted">CIMH-stock prices come from the catalogue cost; the admin fee is added once to the customer's total.</p>
        </v-card-text>
      </v-card>

      <div class="send">
        <p v-if="missing.length" class="t-body text-error">No price yet for: {{ missing.map((l) => l.product.name).join(', ') }}</p>
        <v-btn color="primary" size="large" :disabled="!!missing.length || needsRate" :loading="sending" @click="send">
          {{ r.status === 'QUOTED' ? 'Send revised quote' : 'Send quote' }}
        </v-btn>
      </div>
    </template>
  </div>
</template>

<style scoped>
.saving {
  margin-left: var(--sp-3);
}
.supplier {
  display: grid;
  grid-template-columns: minmax(200px, 1fr) minmax(220px, 1fr) auto;
  gap: var(--sp-3);
  align-items: center;
}
.files {
  grid-column: 1 / -1;
  display: flex;
  gap: var(--sp-1);
  flex-wrap: wrap;
}
.num {
  text-align: right;
}
.cell {
  min-width: 160px;
}
.rate {
  max-width: 360px;
}
.send {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: var(--sp-4);
  flex-wrap: wrap;
}
</style>
