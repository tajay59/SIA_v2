<script setup lang="ts">
/**
 * S-12 choose and sign (DESIGN_BRIEF "agreement stepper"), requester only.
 *   1. Choose CIMH stock or supplier for every line offered both ways; live total (incl. the admin fee).
 *      Confirm → POST /agreement (QUOTED → AWAITING_AGREEMENT; a new choice replaces the agreement).
 *   2. Download the agreement PDF. document-svc renders it after the event, so the page polls until it appears.
 *   3. Upload the signed copy (PDF/JPG/PNG, ≤ 20 MB). The file reaches the request asynchronously
 *      (document.uploaded), so the page waits for it, then POST /accept → ACCEPTED.
 */
import {
  act,
  ApiError,
  fileUrl,
  getRequest,
  type LineChoice,
  type OrderRequest,
  QuoteTable,
  uploadRequestFile,
  useNotify,
} from '@cimh/web-app'
import { formatMoney } from '@cimh/web-ui'
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

async function confirmChoices() {
  if (!request.value) return
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
    notify.toast('Quote accepted. CIMH will verify the signature and order your items.', 'success')
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
    <v-stepper v-else v-model="step" flat class="stepper" alt-label>
      <v-stepper-header>
        <v-stepper-item :value="1" title="Choose options" :complete="step > 1" />
        <v-divider />
        <v-stepper-item :value="2" title="Download agreement" :complete="step > 2" />
        <v-divider />
        <v-stepper-item :value="3" title="Upload signed copy" />
      </v-stepper-header>
      <v-stepper-window>
        <v-stepper-window-item :value="1">
          <p class="t-body">For items CIMH holds in stock you can choose between stock and a supplier order.</p>
          <QuoteTable ref="table" v-model="choices" :request="request" choosable />
          <div class="nav-row">
            <v-btn variant="text" :to="`/requests/${request.id}`">Cancel</v-btn>
            <v-btn color="primary" :disabled="!table?.complete" :loading="busy" @click="confirmChoices">Confirm choices</v-btn>
          </div>
        </v-stepper-window-item>

        <v-stepper-window-item :value="2">
          <p class="t-body">
            Your agreement for <strong class="tnum">{{ total }}</strong> is the commitment to pay for these items.
            Download it, sign it, then upload the signed copy.
          </p>
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
          <v-file-input
            v-model="file"
            label="Signed agreement"
            accept=".pdf,.jpg,.jpeg,.png"
            :error-messages="fileError ?? undefined"
            hint="PDF, JPG or PNG, up to 20 MB"
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
  </v-container>
</template>

<style scoped>
.stepper {
  background: transparent;
  margin-top: var(--sp-4);
}
.nav-row {
  display: flex;
  gap: var(--sp-3);
  justify-content: flex-end;
  margin-top: var(--sp-6);
}
.download {
  margin: var(--sp-6) 0;
}
</style>
