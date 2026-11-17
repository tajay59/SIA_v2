<script setup lang="ts">
/**
 * S-12 choose and sign (DESIGN_BRIEF "agreement stepper"), requester only.
 *   1. Choose CIMH stock or supplier for every line offered both ways; live total (incl. the admin fee).
 *      Confirm → POST /agreement (QUOTED → AWAITING_AGREEMENT; a new choice replaces the agreement).
 *   2. Download the agreement PDF. document-svc renders it after the event, so the page polls until it appears.
 *   3. Upload the signed copy (PDF/JPG/PNG, ≤ 20 MB). The file reaches the request asynchronously
 *      (document.uploaded), so the page waits for it, then POST /accept → ACCEPTED. It ends on the request
 *      page, whose "Quote accepted" banner says what CIMH does next (no toast: it would vanish).
 * A summary (choices, admin fee, total, expiry, ship-to) stays beside the stepper on wide screens and sits
 * above the step actions on phones, so the customer always sees what they are signing.
 */
import {
  act,
  addCents,
  ApiError,
  fileUrl,
  getRequest,
  type LineChoice,
  type OrderRequest,
  QuoteTable,
  quoteRows,
  uploadRequestFile,
  useNotify,
} from '@cimh/web-app'
import { formatDate, formatMoney } from '@cimh/web-ui'
import { useDisplay } from 'vuetify'
import { mdiArrowLeft, mdiDownload } from '@mdi/js'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

definePage({ meta: { guard: 'customer', title: 'Choose and sign' } })
const route = useRoute('/requests/[id]/agreement')
const router = useRouter()
const notify = useNotify()
const request = ref<OrderRequest | null>(null)
const step = ref(1)
const choices = ref<Record<string, LineChoice>>({})
const table = ref<InstanceType<typeof QuoteTable> | null>(null)
const busy = ref(false)
const { mdAndUp } = useDisplay()

// ---- summary of what is being signed
const cur = computed(() => request.value?.currency ?? 'BBD')
const money = (v: string | null | undefined) => (v ? formatMoney(v, cur.value) : '—')
const summary = computed(() => {
  const r = request.value
  if (!r) return []
  return quoteRows(r).rows.map(({ line, supplier, cimh }) => {
    const c: LineChoice | null = supplier && cimh ? (choices.value[line.lineId] ?? null) : cimh ? 'CIMH' : supplier ? 'SUPPLIER' : null
    const amount = c === 'CIMH' ? cimh?.total : c === 'SUPPLIER' ? supplier?.total : null
    return { id: line.lineId, name: line.product.name, qty: line.qty, choice: c, amount }
  })
})
const summaryTotal = computed(() =>
  summary.value.every((l) => l.choice) ? money(addCents(...summary.value.map((l) => l.amount), request.value?.adminFee)) : null,
)
const shipTo = computed(() => {
  const a = request.value?.shipTo
  if (!a) return ''
  return [a.organisation, a.line1, a.line2, a.city, a.parish, a.country].filter(Boolean).join(', ')
})

async function load() {
  request.value = await getRequest(route.params.id)
  const r = request.value
  if (!r.allowedActions?.includes('agreement')) {
    await router.replace(`/requests/${r.id}`)
    return
  }
  if (r.status === 'AWAITING_AGREEMENT' && r.agreement) {
    choices.value = Object.fromEntries((r.agreement.choices ?? []).map((c) => [c.lineId!, c.choice!]))
    if (step.value === 1) step.value = 2
  }
}
watch(() => route.params.id, () => void load().catch((e) => notify.report(e)), { immediate: true })

// ---- polling while the agreement PDF is generated
let timer: ReturnType<typeof setInterval> | null = null
const agreementFile = computed(() => request.value?.agreement?.fileId ?? null)
watch([step, agreementFile], () => {
  const waiting = step.value >= 2 && !agreementFile.value
  if (waiting && !timer) timer = setInterval(() => void load().catch(() => undefined), 3000)
  if (!waiting && timer) {
    clearInterval(timer)
    timer = null
  }
})
onBeforeUnmount(() => timer && clearInterval(timer))

// Confirm is never disabled (harden rule): a press with lines still open says so and goes to the first one.
const choiceArea = ref<HTMLElement | null>(null)
const choiceError = ref<string | null>(null)
watch(choices, () => {
  if (table.value?.complete) choiceError.value = null
}, { deep: true })

async function confirmChoices() {
  if (!request.value) return
  if (!table.value?.complete) {
    choiceError.value = 'Choose CIMH stock or a supplier for every item first. The first one left is selected.'
    const groups: HTMLElement[] = choiceArea.value ? Array.from(choiceArea.value.querySelectorAll('.v-radio-group')) : []
    const open = groups.find((g) => g.offsetParent !== null && !g.querySelector('input:checked'))
    ;(open?.querySelector('input') as HTMLInputElement | null | undefined)?.focus()
    return
  }
  busy.value = true
  try {
    const qv = Math.max(...(request.value.quotes ?? []).map((q) => q.version))
    const body = { quoteVersion: qv, choices: Object.entries(choices.value).map(([lineId, choice]) => ({ lineId, choice })) }
    request.value = await act(request.value, '/requests/{requestId}/agreement', body)
    step.value = 2
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) await load()
    notify.report(e)
  } finally {
    busy.value = false
  }
}

// ---- upload + accept
const file = ref<File | null>(null)
const ACCEPT = ['application/pdf', 'image/jpeg', 'image/png']
const fileError = computed(() => {
  const f = file.value
  if (!f) return null
  if (!ACCEPT.includes(f.type)) return 'Upload a PDF, JPG or PNG'
  if (f.size > 20 * 1024 * 1024) return 'The file is larger than 20 MB'
  return null
})
const status = ref('')

async function waitForFile(id: string): Promise<OrderRequest> {
  for (let i = 0; i < 20; i++) {
    const r = await getRequest(route.params.id)
    if (r.files?.some((f) => f.id === id)) return r
    await new Promise((res) => setTimeout(res, 1500))
  }
  throw new Error('The upload is still being checked. Try Accept again in a minute.')
}

async function accept() {
  if (!request.value || !file.value || fileError.value) return
  busy.value = true
  try {
    status.value = 'Uploading…'
    const uploaded = await uploadRequestFile(request.value.id, 'signed_agreement', file.value)
    status.value = 'Checking the file…'
    request.value = await waitForFile(uploaded.id)
    status.value = 'Accepting…'
    const qv = request.value.agreement?.quoteVersion ?? 0
    await act(request.value, '/requests/{requestId}/accept', { quoteVersion: qv, signedAgreementFileId: uploaded.id })
    await router.push(`/requests/${request.value.id}`)
  } catch (e) {
    if (e instanceof ApiError) notify.report(e)
    else notify.toast(e instanceof Error ? e.message : 'Upload failed', 'error')
  } finally {
    busy.value = false
    status.value = ''
  }
}
const total = computed(() =>
  request.value?.agreement?.total ? formatMoney(request.value.agreement.total, request.value.currency ?? 'BBD') : '',
)
</script>

<template>
  <v-container class="page" max-width="1000">
    <v-btn :to="`/requests/${route.params.id}`" variant="text" :prepend-icon="mdiArrowLeft">Back to the request</v-btn>
    <h1 class="t-h1">Choose and sign</h1>
    <v-skeleton-loader v-if="!request" type="table" />
    <div v-else class="layout">
    <v-stepper v-model="step" flat class="stepper" alt-label :mobile="!mdAndUp">
      <v-stepper-header>
        <v-stepper-item :value="1" title="Choose options" aria-label="Choose options" :complete="step > 1" />
        <v-divider />
        <v-stepper-item :value="2" title="Download agreement" aria-label="Download agreement" :complete="step > 2" />
        <v-divider />
        <v-stepper-item :value="3" title="Upload signed copy" aria-label="Upload signed copy" />
      </v-stepper-header>
      <v-stepper-window>
        <v-stepper-window-item :value="1">
          <p class="t-body-lg prose">
            Choose where each item comes from. Items CIMH holds can come from CIMH stock or be ordered from a supplier;
            the others have one option. The total follows your choices.
          </p>
          <div ref="choiceArea"><QuoteTable ref="table" v-model="choices" :request="request" choosable /></div>
          <v-alert v-if="choiceError" type="error" variant="tonal" density="compact" role="alert" class="mt-3">{{ choiceError }}</v-alert>
          <div class="nav-row">
            <v-btn variant="text" :to="`/requests/${request.id}`">Cancel</v-btn>
            <v-btn color="primary" :loading="busy" @click="confirmChoices">Confirm choices</v-btn>
          </div>
        </v-stepper-window-item>

        <v-stepper-window-item :value="2">
          <p class="t-body-lg prose">
            This agreement for <strong class="tnum">{{ total }}</strong> is your organisation's commitment to pay for these items.
            Nothing is paid on this site.
          </p>
          <ol class="t-body todo">
            <li>Download the agreement and check it against the summary.</li>
            <li>Have it signed by someone authorised to commit your organisation.</li>
            <li>Scan the signed page or take a photo of it, then upload it in the next step.</li>
          </ol>
          <div class="download">
            <v-btn v-if="agreementFile" :href="fileUrl(agreementFile)" target="_blank" color="primary" :prepend-icon="mdiDownload">
              Download agreement
            </v-btn>
            <p v-else class="t-body muted" role="status"><v-progress-circular indeterminate size="18" /> Preparing the agreement…</p>
          </div>
          <div class="nav-row">
            <v-btn variant="text" @click="step = 1">Change choices</v-btn>
            <v-btn color="primary" @click="step = 3">I have signed it</v-btn>
          </div>
        </v-stepper-window-item>

        <v-stepper-window-item :value="3">
          <p class="t-body-lg">Upload the signed agreement to accept the quote. After that:</p>
          <ul class="t-body next">
            <li>CIMH staff check the signature on your copy. If something is missing they email you and you upload it again.</li>
            <li>Items from CIMH stock are reserved for you as soon as you accept.</li>
            <li>Supplier items are ordered by CIMH once the signature is verified, and shipped straight to you.</li>
          </ul>
          <v-file-input
            v-model="file"
            label="Signed agreement"
            accept=".pdf,.jpg,.jpeg,.png"
            :error-messages="fileError ?? undefined"
            hint="A scan or a phone photo of the signed page is fine. PDF, JPG or PNG, up to 20 MB"
            persistent-hint
            show-size
          />
          <p v-if="status" class="t-body muted" role="status">{{ status }}</p>
          <div class="nav-row">
            <v-btn variant="text" @click="step = 2">Back</v-btn>
            <v-btn color="primary" :disabled="!file || !!fileError" :loading="busy" @click="accept">Accept quote</v-btn>
          </div>
        </v-stepper-window-item>
      </v-stepper-window>
    </v-stepper>
    <aside class="summary" :class="{ first: step > 1 }" aria-labelledby="summary-title">
      <h2 id="summary-title" class="t-h3">What you are signing</h2>
      <ul class="sum-lines">
        <li v-for="l in summary" :key="l.id">
          <span class="sum-name">{{ l.name }} <span class="muted tnum">× {{ l.qty }}</span>
            <span class="t-caption muted d-block">{{ l.choice === 'CIMH' ? 'From CIMH stock' : l.choice === 'SUPPLIER' ? 'Ordered from a supplier' : 'Not chosen yet' }}</span></span>
          <span class="tnum">{{ l.choice ? money(l.amount) : '—' }}</span>
        </li>
      </ul>
      <dl class="sum-facts">
        <div v-if="request.adminFee && request.adminFee !== '0.00'"><dt>Admin fee</dt><dd class="tnum">{{ money(request.adminFee) }}</dd></div>
        <div class="sum-total"><dt>Total ({{ cur }})</dt><dd class="tnum">{{ summaryTotal ?? 'After your choices' }}</dd></div>
        <div v-if="request.quoteExpiresAt"><dt>Quote valid until</dt><dd>{{ formatDate(request.quoteExpiresAt) }}</dd></div>
        <div v-if="shipTo"><dt>Ship to</dt><dd>{{ shipTo }}</dd></div>
      </dl>
    </aside>
    </div>
  </v-container>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: var(--sp-6);
  align-items: start;
  margin-top: var(--sp-4);
}
.stepper {
  background: transparent;
  min-width: 0;
}
.summary {
  position: sticky;
  top: 80px;
  padding: var(--sp-4);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
}
/* Phones and tablets: the summary sits under the step content, before nothing else scrolls past it. */
@media (max-width: 959px) {
  /* Every step ends in its buttons: keep them clear of the bottom bar and toasts. */
  .page {
    padding-bottom: 120px;
  }
  .layout {
    grid-template-columns: minmax(0, 1fr);
  }
  .summary {
    position: static;
  }
  /* Steps 2-3: the summary comes first, so the customer reads it before downloading or signing. */
  .summary.first {
    order: -1;
  }
}
.sum-lines {
  list-style: none;
  padding: 0;
  margin: var(--sp-3) 0;
}
.sum-lines li,
.sum-facts > div {
  display: flex;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: var(--sp-1) 0;
}
.sum-name {
  min-width: 0;
  overflow-wrap: anywhere;
}
.sum-facts {
  margin: 0;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding-top: var(--sp-2);
}
.sum-facts dd {
  margin: 0;
  text-align: right;
  overflow-wrap: anywhere;
}
.sum-total {
  font-weight: 600;
}
/* Labels and amounts never break ("Ship / to", "BBD / 300.00" at 360 px); names and addresses wrap instead. */
.sum-facts dt,
.sum-lines li > .tnum {
  white-space: nowrap;
  flex-shrink: 0;
}
.next,
.todo {
  margin: var(--sp-3) 0 var(--sp-4);
  padding-left: var(--sp-5, 20px);
}
.next li + li,
.todo li + li {
  margin-top: var(--sp-1);
}
.nav-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-3);
  justify-content: flex-end;
  margin-top: var(--sp-6);
}
.download {
  margin: var(--sp-6) 0;
}
</style>
