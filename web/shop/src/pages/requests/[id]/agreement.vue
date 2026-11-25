<script setup lang="ts">
/**
 * S-12 View and sign, requester only ("Three tasks, open in place", impeccable 2026-11-18; brief
 * `web/shop/.impeccable/surfaces/src-pages-requests-id-agreement-vue.md`). Nothing to choose: staff fixed where every
 * item comes from when they sent the quote, and the agreement PDF came with it.
 *
 * The usual scene: an officer reads the quote and the agreement at a desk, downloads it for whoever signs, and comes
 * back (often another day) with the scan or photo. So the page is a ruled list of three tasks, one open at a time,
 * any of them reachable at any time:
 *   1. Check the quote: every item, where it comes from, its price, estimated shipping per source, admin fee, total,
 *      ship-to; the quotes behind the prices (CIMH stock quote, then the supplier quotes) beside it.
 *   2. Get it signed: what the agreement commits to, who signs, where; Download agreement (saves the file, no new
 *      tab); the agreement beside it. document-svc renders it (and the CIMH quote) after the event, so the page polls.
 *   3. Send the signed copy: drop or choose a scan/photo (PDF/JPG/PNG, ≤ 20 MB), see it beside the task before
 *      sending (read in the browser), Send signed agreement: upload, wait until the file reaches the request
 *      (document.uploaded), POST /accept → ACCEPTED, then the request page says what CIMH does next (no toast).
 * Ticks are kept in this browser per request + quote version (a revised quote starts again); a return opens the
 * first task not done, `?task=check|sign|send` opens one, and a rejected signature opens task 3 under a notice.
 * Wide screens (≥ 1280 px): the list on the left, the open task's document on the right (sticky), pages drawn up to
 * 860 px wide so the agreement's 9.5 pt text reads at 12–14 px. Narrower: the document sits inside the open task;
 * below 760 px (phones) as rows that open a full-screen reader, since a page drawn at phone width can't be read.
 * Cancel request (the server's `decline`, reason asked) ends the list.
 */
import {
  act,
  ApiError,
  currentAgreement,
  DocumentViewer,
  expiryNote,
  FILE_KIND_LABELS,
  type FileRef,
  fileUrl,
  getRequest,
  type OrderRequest,
  type PricedLine,
  pricedQuote,
  ReasonDialog,
  requestTitle,
  ShortRef,
  uploadRequestFile,
  useNotify,
} from '@cimh/web-app'
import { formatDate, formatMoney } from '@cimh/web-ui'
import {
  mdiAlertCircleOutline,
  mdiArrowLeft,
  mdiCheck,
  mdiChevronDown,
  mdiDownload,
  mdiEmailOutline,
  mdiFileImageOutline,
  mdiFilePdfBox,
  mdiSend,
  mdiTrayArrowUp,
} from '@mdi/js'
import { useDisplay } from 'vuetify'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import DocumentRows from '../../../components/DocumentRows.vue'
import RequestDocuments from '../../../components/RequestDocuments.vue'
import { docLabel } from '../../../request-docs'

definePage({ meta: { guard: 'customer', title: 'View and sign' } })
const route = useRoute('/requests/[id]/agreement')
const router = useRouter()
const notify = useNotify()
const request = ref<OrderRequest | null>(null)
const busy = ref(false)
const { width } = useDisplay()
/** The document beside the list only where it gets ≥ ~700 px (readable); below that it sits in the task. */
const split = computed(() => width.value >= 1280)
/** Room to draw a page inside the task at a readable size; narrower, the documents open full screen. */
const roomy = computed(() => width.value >= 760)

// ---- what is being signed
const cur = computed(() => request.value?.currency ?? 'BBD')
const money = (v: string | null | undefined) => (v ? formatMoney(v, cur.value) : '—')
const quote = computed(() => (request.value ? pricedQuote(request.value) : null))
const agreement = computed(() => (request.value ? currentAgreement(request.value) : null))
const title = computed(() => {
  const r = request.value
  return r ? requestTitle(r.lines[0]?.product.name, r.lines.length, r.type) : ''
})
const expiry = computed(() => expiryNote(request.value?.quoteExpiresAt))
/** The quote by where the items come from (CIMH stock first): each source ships on its own, with its own estimate. */
const groupKey = (cimh: boolean, supplier: string | null) => (cimh ? 'CIMH' : `S:${supplier ?? ''}`)
const groups = computed(() => {
  const q = quote.value
  if (!q) return []
  const out: { key: string; cimh: boolean; title: string; rows: PricedLine[]; shipping: string | null }[] = []
  for (const x of q.rows) {
    const cimh = x.source === 'CIMH'
    const key = groupKey(cimh, x.supplier)
    let g = out.find((o) => o.key === key)
    if (!g) {
      const title = cimh ? 'From CIMH stock, shipped by CIMH' : `From ${x.supplier ?? 'the supplier'}, shipped to you directly`
      g = { key, cimh, title, rows: [], shipping: null }
      out.push(g)
    }
    g.rows.push(x)
  }
  for (const s of q.shipping) {
    const g = out.find((o) => o.key === groupKey(s.source === 'CIMH', s.label))
    if (g) g.shipping = s.amount
  }
  return out.sort((a, b) => Number(b.cimh) - Number(a.cimh))
})
/** An estimate whose source has no line (never expected): still listed, so the sum adds up on screen. */
const looseShipping = computed(() => (quote.value?.shipping ?? []).filter((s) => !groups.value.some((g) => g.key === groupKey(s.source === 'CIMH', s.label))))
const suppliers = computed(() => [...new Set((quote.value?.rows ?? []).filter((x) => x.source === 'SUPPLIER').map((x) => x.supplier ?? 'the supplier'))])
const hasCimh = computed(() => (quote.value?.rows ?? []).some((x) => x.source === 'CIMH'))
const sourcesText = computed(() => {
  const all = [...(hasCimh.value ? ['CIMH stock'] : []), ...suppliers.value]
  return all.length > 1 ? `${all.slice(0, -1).join(', ')} and ${all.at(-1)}` : (all[0] ?? '')
})
const org = computed(() => request.value?.organisationName || request.value?.shipTo?.organisation || 'your organisation')
/** Where it goes, short (organisation, town, country): the full address is on the agreement and the request page. */
const shipTo = computed(() => {
  const a = request.value?.shipTo
  if (!a) return ''
  return [a.organisation, a.city, a.country].filter(Boolean).join(', ')
})
/** Step 1's documents: the CIMH stock quote of this version first, then the supplier quotes. */
const quoteFiles = computed(() => {
  const files = request.value?.files ?? []
  const cimh = files.filter((f) => f.kind === 'cimh_quote' && f.id === request.value?.cimhQuote?.fileId)
  return [...cimh, ...files.filter((f) => f.kind === 'supplier_quote')]
})
const quoteFile = ref<string | null>(null)
/** Suppliers in this quote version whose own quote file is not on the request (their prices are in the list). */
const unfiled = computed(() =>
  (request.value?.quotes ?? [])
    .filter((q) => q.version === quote.value?.version && q.lines.length && !(q.fileIds ?? []).length)
    .map((q) => q.supplier ?? 'The supplier'),
)
/** Tab text for the supplier quote files: the supplier's name (numbered when it sent several), not the file name. */
const fileLabels = computed(() => {
  const out: Record<string, string> = {}
  for (const q of request.value?.quotes ?? []) {
    if (q.version !== quote.value?.version) continue
    const ids = q.fileIds ?? []
    ids.forEach((id, i) => (out[id] = ids.length > 1 ? `${q.supplier ?? 'Supplier'} (${i + 1})` : (q.supplier ?? 'Supplier quote')))
  }
  return out
})
/** Phones: the same documents as rows (name, what it is) that open full screen. */
const fileType = (mime: string) => (mime === 'application/pdf' ? 'PDF' : mime === 'image/png' ? 'PNG' : mime === 'image/jpeg' ? 'JPG' : 'File')
const quoteRows = computed(() =>
  quoteFiles.value.map((f: FileRef) => ({
    id: f.id,
    mime: f.mime,
    label: fileLabels.value[f.id] ?? docLabel(f, quoteFiles.value),
    kind: `${FILE_KIND_LABELS[f.kind]} · ${fileType(f.mime)}`,
  })),
)
/** Staff rejected the signed copy: the request went back from ACCEPTED to QUOTED, with their reason. */
const rejected = computed(() => {
  const last = request.value?.history?.at(-1)
  return last?.from === 'ACCEPTED' && last.to === 'QUOTED' ? (last.reason ?? 'no reason given') : null
})

async function load() {
  request.value = await getRequest(route.params.id)
  if (!request.value.allowedActions?.includes('accept')) await router.replace(`/requests/${request.value.id}`)
}
watch(() => route.params.id, () => void load().catch((e) => notify.report(e)), { immediate: true })

// ---- polling while the agreement PDF (and the CIMH stock quote, when CIMH stock is quoted) is generated
let timer: ReturnType<typeof setInterval> | null = null
const agreementFile = computed(() => agreement.value?.fileId ?? null)
const agreementMime = computed(() => request.value?.files?.find((f) => f.id === agreementFile.value)?.mime ?? 'application/pdf')
const downloadHref = computed(() => (agreementFile.value ? `${fileUrl(agreementFile.value)}?disposition=attachment` : undefined))
const agreementRows = computed(() =>
  agreementFile.value
    ? [{ id: agreementFile.value, mime: agreementMime.value, label: 'Agreement to sign', kind: `Quote version ${quote.value?.version ?? ''} · ${fileType(agreementMime.value)}` }]
    : [],
)
const cimhQuotePending = computed(() => !!request.value?.cimhQuote && !request.value.cimhQuote.fileId)
watch([request, agreementFile, cimhQuotePending], () => {
  const waiting = !!request.value && (!agreementFile.value || cimhQuotePending.value)
  if (waiting && !timer) timer = setInterval(() => void load().catch(() => undefined), 3000)
  if (!waiting && timer) {
    clearInterval(timer)
    timer = null
  }
})
onBeforeUnmount(() => timer && clearInterval(timer))

// ---- the three tasks: ticks kept in this browser (per request + quote version), one task open at a time
type Task = 1 | 2 | 3
const TASKS: { n: Task; title: string }[] = [
  { n: 1, title: 'Check the quote' },
  { n: 2, title: 'Get it signed' },
  { n: 3, title: 'Send the signed copy' },
]
/* Only what this browser saw happen: the quote checked, the agreement downloaded. "Signed" is never ticked on a press
   (nothing here can know it); "Already signed?" just opens task 3. */
type Marks = { checked?: boolean; downloadedAt?: string }
const marks = ref<Marks>({})
const storeKey = computed(() => (request.value && quote.value ? `cimh.sign.${request.value.id}.v${quote.value.version}` : ''))
watch(storeKey, (k) => {
  if (!k) return
  try {
    marks.value = JSON.parse(localStorage.getItem(k) ?? '{}') as Marks
  } catch {
    marks.value = {}
  }
})
function mark(m: Marks) {
  marks.value = { ...marks.value, ...m }
  try {
    localStorage.setItem(storeKey.value, JSON.stringify(marks.value))
  } catch {
    /* private window: the ticks last for this visit only */
  }
}
const done = (n: Task) => (n === 1 ? !!marks.value.checked || !!rejected.value : n === 2 ? !!marks.value.downloadedAt || !!rejected.value : false)

const open = ref<Task | null>(null)
/** The document beside the list follows the open task, and stays on the last one when every task is closed. */
const shown = ref<Task>(1)
watch(open, (n) => n && (shown.value = n))
const FROM_QUERY: Record<string, Task> = { check: 1, sign: 2, send: 3 }
const TO_QUERY: Record<Task, string> = { 1: 'check', 2: 'sign', 3: 'send' }
let placed = false
watch(storeKey, (k) => {
  if (!k || placed) return
  placed = true
  const asked = FROM_QUERY[String(route.query.task ?? '')]
  open.value = asked ?? (rejected.value || done(2) ? 3 : done(1) ? 2 : 1)
})
/* The address follows the open task (replace, not push: Back still leaves the page), so a reload after an
   interruption, or a link copied to whoever sends the signed copy, opens the same task. */
watch(open, (n) => {
  if (!placed || !n || route.query.task === TO_QUERY[n]) return
  void router.replace({ query: { ...route.query, task: TO_QUERY[n] } })
})

const hits: Partial<Record<Task, HTMLButtonElement>> = {}
const popped = ref<Task | null>(null)
async function finish(n: Task, m: Marks, next: Task) {
  if (!done(n) && Object.keys(m).length) popped.value = n // only a task this press completes lands a check
  mark(m)
  open.value = next
  await nextTick()
  const hit = hits[next]
  hit?.focus({ preventScroll: true })
  // After the tasks fold and unfold, bring the next one's heading into view if it went off screen.
  setTimeout(() => hit?.scrollIntoView({ block: 'nearest', behavior: reduced() ? 'auto' : 'smooth' }), 380)
}
const toggle = (n: Task) => (open.value = open.value === n ? null : n)

function summary(n: Task): string {
  const q = quote.value
  if (!q) return ''
  if (n === 1) {
    const items = `${q.rows.length} ${q.rows.length === 1 ? 'item' : 'items'}`
    const ships = q.shipping.length > 1 ? ` · ${q.shipping.length} shipments` : ''
    return `${items} from ${sourcesText.value}${ships} · ${money(q.total)}`
  }
  if (n === 2) {
    if (marks.value.downloadedAt) return `Agreement downloaded ${formatDate(marks.value.downloadedAt)}`
    return agreementFile.value ? 'Download the agreement and have it signed' : 'The agreement is being prepared'
  }
  return file.value ? file.value.name : 'A scan or a phone photo of the signed page'
}

// ---- motion: a task unfolds to its height; reduced motion = fades only
const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
function unfold(el: Element, end: () => void) {
  const e = el as HTMLElement
  if (reduced()) return void (e.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 160 }).onfinish = end)
  e.style.overflow = 'hidden'
  const a = e.animate(
    [{ height: '0px', opacity: 0 }, { height: `${e.scrollHeight}px`, opacity: 1 }],
    { duration: 380, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' },
  )
  a.onfinish = () => {
    e.style.overflow = ''
    end()
  }
}
function fold(el: Element, end: () => void) {
  const e = el as HTMLElement
  if (reduced()) return void (e.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 120 }).onfinish = end)
  e.style.overflow = 'hidden'
  e.animate([{ height: `${e.offsetHeight}px`, opacity: 1 }, { height: '0px', opacity: 0 }], {
    duration: 240,
    easing: 'cubic-bezier(0.4, 0, 1, 1)',
  }).onfinish = end
}

// ---- the signed copy: dropped or chosen, previewed, sent (the button is never disabled: a press says what is missing)
const file = ref<File | null>(null)
const tried = ref(false)
const dragging = ref(false)
const ACCEPT = ['application/pdf', 'image/jpeg', 'image/png']
const fileError = computed(() => {
  const f = file.value
  if (!f) return tried.value ? 'Choose the signed copy first' : null
  if (!ACCEPT.includes(f.type)) return 'Upload a PDF, JPG or PNG'
  if (f.size > 20 * 1024 * 1024) return 'The file is larger than 20 MB'
  return null
})
const previewable = computed(() => !!file.value && ACCEPT.includes(file.value.type))
const fileIcon = computed(() => (file.value?.type === 'application/pdf' ? mdiFilePdfBox : file.value ? mdiFileImageOutline : mdiTrayArrowUp))
const fileFacts = computed(() => {
  const f = file.value
  if (!f) return ''
  const kind = f.type === 'application/pdf' ? 'PDF' : f.type === 'image/png' ? 'PNG' : f.type === 'image/jpeg' ? 'JPG' : 'File'
  const size = f.size >= 1024 * 1024 ? `${(f.size / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(f.size / 1024))} KB`
  return `${kind} · ${size}`
})
function choose(f: File | null | undefined) {
  if (!f) return
  file.value = f
  tried.value = false
  if (open.value !== 3) open.value = 3
}
const onPick = (e: Event) => choose((e.target as HTMLInputElement).files?.[0])
function onDrop(e: DragEvent) {
  dragging.value = false
  choose(e.dataTransfer?.files?.[0])
}
const status = ref('')

async function waitForFile(id: string): Promise<OrderRequest> {
  for (let i = 0; i < 20; i++) {
    const r = await getRequest(route.params.id)
    if (r.files?.some((f) => f.id === id)) return r
    await new Promise((res) => setTimeout(res, 1500))
  }
  throw new Error('The upload is still being checked. Try Send again in a minute.')
}

/** Send: a press says what is missing; with a file it asks first (accepting the quote is not undone here and emails CIMH). */
const confirming = ref(false)
function send() {
  tried.value = true
  if (!request.value || !file.value || fileError.value) {
    document.getElementById('signed-copy')?.focus()
    return
  }
  confirming.value = true
}
async function sendNow() {
  if (!request.value || !file.value) return
  confirming.value = false
  busy.value = true
  try {
    status.value = 'Uploading…'
    const uploaded = await uploadRequestFile(request.value.id, 'signed_agreement', file.value)
    status.value = 'Checking the file…'
    request.value = await waitForFile(uploaded.id)
    status.value = 'Sending…'
    const qv = agreement.value?.quoteVersion ?? 0
    await act(request.value, '/requests/{requestId}/accept', { quoteVersion: qv, signedAgreementFileId: uploaded.id })
    await router.push(`/requests/${request.value.id}`)
  } catch (e) {
    if (e instanceof ApiError) {
      if (e.status === 409) await load()
      notify.report(e)
    } else notify.toast(e instanceof Error ? e.message : 'Upload failed', 'error')
  } finally {
    busy.value = false
    status.value = ''
  }
}

// ---- cancel request (decline the quote)
const cancelling = ref(false)
async function cancel(reason: string) {
  if (!request.value) return
  busy.value = true
  try {
    await act(request.value, '/requests/{requestId}/decline', { reason })
    notify.toast('Request cancelled', 'success')
    await router.push(`/requests/${request.value.id}`)
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) await load()
    notify.report(e)
  } finally {
    busy.value = false
    cancelling.value = false
  }
}
</script>

<template>
  <div class="sign-page">
    <!-- What is being signed, in the band every request page carries. -->
    <header class="band">
      <div class="band-in">
        <div class="band-main">
          <v-btn :to="`/requests/${route.params.id}`" variant="text" :prepend-icon="mdiArrowLeft" class="back back-text">Request</v-btn>
          <div class="band-head">
            <v-btn :to="`/requests/${route.params.id}`" variant="text" :icon="mdiArrowLeft" aria-label="Back to the request" class="back back-icon" />
            <h1 class="band-title">View and sign</h1>
          </div>
          <p v-if="request" class="band-sub">
            <span>{{ title }}</span>
            <span aria-hidden="true">·</span>
            <ShortRef :id="request.id" fit copy />
            <template v-if="quote"><span aria-hidden="true">·</span><span>quote version {{ quote.version }}</span></template>
          </p>
        </div>
        <div v-if="quote" class="band-total">
          <span class="bt-label">Total to sign</span>
          <strong class="bt-amount tnum">{{ money(quote.total) }}</strong>
          <span v-if="request?.quoteExpiresAt" class="bt-expiry" :class="{ soon: expiry?.soon }">
            Valid until {{ formatDate(request.quoteExpiresAt) }}<template v-if="expiry"> · {{ expiry.text }}</template>
          </span>
        </div>
      </div>
    </header>

    <div class="body" :class="{ split }">
      <div v-if="!request || !quote" class="tasks-col" aria-busy="true">
        <v-skeleton-loader type="list-item-avatar-two-line@3" />
      </div>
      <template v-else>
        <div class="tasks-col">
          <div v-if="rejected" class="notice" role="status">
            <v-icon :icon="mdiAlertCircleOutline" size="24" class="notice-icon" />
            <div>
              <p class="notice-title">Send the signed agreement again</p>
              <p class="notice-text">CIMH could not accept the signed copy: {{ rejected }}. Your quote still stands.</p>
            </div>
          </div>

          <ol class="tasks">
            <li
              v-for="t in TASKS"
              :key="t.n"
              class="task"
              :class="{ open: open === t.n, done: done(t.n), pop: popped === t.n }"
            >
              <span v-if="t.n < 3" class="wire" :class="{ lit: done(t.n) }" aria-hidden="true" />
              <h2 class="task-h">
                <button
                  :id="`task-h-${t.n}`"
                  :ref="(el) => (hits[t.n] = (el as HTMLButtonElement | null) ?? undefined)"
                  type="button"
                  class="task-hit"
                  :aria-expanded="open === t.n"
                  :aria-controls="`task-${t.n}`"
                  @click="toggle(t.n)"
                >
                  <span class="node" aria-hidden="true">
                    <v-icon v-if="done(t.n)" :icon="mdiCheck" size="20" />
                    <template v-else>{{ t.n }}</template>
                  </span>
                  <span class="task-text">
                    <span class="task-title">{{ t.title }}<span class="d-sr-only">{{ done(t.n) ? ', done' : '' }}</span></span>
                    <span v-if="open !== t.n" class="task-sum">{{ summary(t.n) }}</span>
                  </span>
                  <v-icon class="chev" :icon="mdiChevronDown" size="24" aria-hidden="true" />
                </button>
              </h2>

              <Transition :css="false" @enter="unfold" @leave="fold">
                <div v-if="open === t.n" :id="`task-${t.n}`" class="task-body" role="region" :aria-labelledby="`task-h-${t.n}`">
                  <!-- 1. Check the quote -->
                  <div v-if="t.n === 1" class="task-in">
                    <!-- By where the items come from: each source is one shipment with its own estimated shipping. -->
                    <section v-for="(g, gi) in groups" :key="g.key" class="grp" :aria-labelledby="`grp-${gi}`">
                      <h3 :id="`grp-${gi}`" class="grp-title">
                        <span class="src" :class="g.cimh ? 'src-cimh' : 'src-sup'">{{ g.title }}</span>
                      </h3>
                      <ul class="lines">
                        <li v-for="x in g.rows" :key="x.line.lineId" class="ln">
                          <span class="ln-name">{{ x.line.product.name }}</span>
                          <span class="ln-amt tnum">{{ money(x.total) }}</span>
                          <span class="ln-meta tnum">
                            {{ x.line.qty }} × {{ money(x.unitPrice) }}<template v-if="x.converted">
                              (supplier quote {{ formatMoney(x.converted.unitPrice, x.converted.currency) }} at {{ x.converted.rate }} BBD per USD)</template>
                          </span>
                        </li>
                        <li v-if="g.shipping" class="ln ln-ship">
                          <span class="ln-name">Estimated shipping</span>
                          <span class="ln-amt tnum">{{ money(g.shipping) }}</span>
                        </li>
                      </ul>
                    </section>
                    <dl class="sums">
                      <div v-for="s in looseShipping" :key="s.source + s.label">
                        <dt>Estimated shipping, {{ s.label }}</dt><dd class="tnum">{{ money(s.amount) }}</dd>
                      </div>
                      <div v-if="quote.fee"><dt>Admin fee (once per request)</dt><dd class="tnum">{{ money(quote.fee) }}</dd></div>
                      <div class="sum-total"><dt>Total to sign</dt><dd class="tnum">{{ money(quote.total) }}</dd></div>
                    </dl>
                    <!-- The band already states the version and validity; only what it doesn't say is repeated here. -->
                    <p v-if="shipTo || request.cimhQuote?.exchangeRate || unfiled.length" class="fine">
                      <template v-if="unfiled.length">{{ unfiled.join(' and ') }}{{ unfiled.length > 1 ? '’s quotes are' : '’s own quote is' }} not attached; {{ unfiled.length > 1 ? 'their' : 'its' }} prices are in the list above. </template>
                      <template v-if="shipTo">Ships to {{ shipTo }}.</template>
                      <template v-if="request.cimhQuote?.exchangeRate"> Exchange rate {{ request.cimhQuote.exchangeRate }} BBD per USD.</template>
                    </p>
                    <div v-if="!split" class="inline">
                      <h3 class="inline-title">The quotes behind these prices</h3>
                      <DocumentRows
                        v-if="!roomy"
                        :docs="quoteRows"
                        label="Quote files"
                        empty-title="No quote files yet"
                        :empty-text="cimhQuotePending ? 'The CIMH stock quote is being prepared.' : 'Every price is in the list above.'"
                      />
                      <div v-else class="inline-docs" :class="{ empty: !quoteFiles.length }">
                        <RequestDocuments
                          v-model:selected="quoteFile"
                          :labels="fileLabels"
                          :files="quoteFiles"
                          label="Quote files"
                          empty-title="No quote files yet"
                          :empty-text="cimhQuotePending ? 'The CIMH stock quote is being prepared.' : 'Every price is in the list above.'"
                        />
                      </div>
                    </div>
                    <div class="acts">
                      <v-btn color="primary" variant="flat" @click="finish(1, { checked: true }, 2)">Continue to the agreement</v-btn>
                    </div>
                  </div>

                  <!-- 2. Get it signed -->
                  <div v-else-if="t.n === 2" class="task-in">
                    <p class="lead">
                      This agreement for <strong class="tnum">{{ money(quote.total) }}</strong> is your organisation's commitment to pay
                      for these items, and the amount CIMH invoices (shipping in it is estimated). Nothing is paid on this site.
                    </p>
                    <dl class="facts">
                      <div><dt>Who signs</dt><dd>Someone authorised to commit {{ org }}</dd></div>
                      <div><dt>Where</dt><dd>The signature block at the end: signature, name, date and position</dd></div>
                      <div><dt>Then</dt><dd>Scan the signed page or take a photo of it, and send it here</dd></div>
                    </dl>
                    <DocumentRows v-if="!roomy && agreementFile" :docs="agreementRows" label="The agreement to sign" />
                    <div v-else-if="!split" class="inline">
                      <DocumentViewer
                        v-if="agreementFile"
                        :key="agreementFile"
                        :file-id="agreementFile"
                        name="Agreement to sign"
                        :mime="agreementMime"
                        what="Preview of"
                        link="none"
                        class="inline-doc"
                      />
                    </div>
                    <div class="acts">
                      <v-btn
                        v-if="agreementFile"
                        :href="downloadHref"
                        download
                        color="primary"
                        variant="flat"
                       
                        :prepend-icon="mdiDownload"
                        @click="mark({ downloadedAt: new Date().toISOString() })"
                      >
                        Download agreement
                      </v-btn>
                      <p v-else class="wait" role="status"><v-progress-circular indeterminate size="18" width="2" /> Preparing the agreement…</p>
                      <v-btn variant="outlined" @click="finish(2, {}, 3)">Already signed? Send the copy</v-btn>
                    </div>
                  </div>

                  <!-- 3. Send the signed copy -->
                  <div v-else class="task-in">
                    <label
                      class="slot"
                      :class="{ over: dragging, chosen: !!file, bad: !!fileError }"
                      @dragenter.prevent="dragging = true"
                      @dragover.prevent
                      @dragleave="dragging = false"
                      @drop.prevent="onDrop"
                    >
                      <input
                        id="signed-copy"
                        type="file"
                        class="slot-input"
                        accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                        :aria-invalid="!!fileError"
                        :aria-describedby="fileError ? 'signed-copy-error' : undefined"
                        @change="onPick"
                      />
                      <v-icon :icon="fileIcon" size="32" class="slot-icon" />
                      <span class="slot-title">{{ file ? file.name : 'Drop the signed agreement here' }}</span>
                      <span class="slot-hint">
                        <template v-if="file">{{ fileFacts }} · <span class="slot-link">choose another file</span></template>
                        <template v-else><span class="slot-link">or choose a file</span>. A scan or a phone photo of the signed page is fine: PDF, JPG or PNG, up to 20 MB.</template>
                      </span>
                    </label>
                    <p v-if="fileError" id="signed-copy-error" class="err" role="alert">{{ fileError }}</p>
                    <div v-if="!split && previewable" class="inline">
                      <DocumentViewer :file="file" name="Your signed copy" :mime="file!.type" what="Preview of" link="none" class="inline-doc" />
                    </div>
                    <div class="acts">
                      <v-btn color="primary" variant="flat" :loading="busy" @click="send">Send signed agreement</v-btn>
                      <span v-if="status" class="wait" role="status">{{ status }}</span>
                    </div>
                    <h3 class="next-title">After you send it</h3>
                    <ul class="next">
                      <li>CIMH staff check the signature. If something is missing they email you, and you send it again.</li>
                      <li v-if="suppliers.length">CIMH orders from {{ suppliers.join(', ') }}, who {{ suppliers.length > 1 ? 'ship their' : 'ships its' }} items straight to you.</li>
                      <li v-if="hasCimh">CIMH ships the items from its stock.</li>
                      <li>Each shipment gets its tracking number on the request page.</li>
                    </ul>
                  </div>
                </div>
              </Transition>
            </li>
          </ol>

          <div class="foot">
            <v-btn variant="text" color="error" @click="cancelling = true">Cancel request…</v-btn>
          </div>
        </div>

        <!-- Wide: the open task's document, kept in view while the list scrolls. -->
        <!-- One head per document (the viewer's own: name or file tabs, page in view, zoom, Download). -->
        <aside
          v-if="split"
          class="reader"
          :aria-label="shown === 1 ? 'The quotes behind these prices' : shown === 2 || !previewable ? 'The agreement to sign' : 'Your signed copy'"
        >
          <Transition name="swap" mode="out-in">
            <div :key="shown === 3 && !previewable ? 2 : shown" class="reader-in">
              <RequestDocuments
                v-if="shown === 1"
                v-model:selected="quoteFile"
                :labels="fileLabels"
                :files="quoteFiles"
                label="Quote files"
                empty-title="No quote files yet"
                :empty-text="cimhQuotePending ? 'The CIMH stock quote is being prepared.' : 'Every price is in the list.'"
                class="reader-doc"
              />
              <template v-else-if="shown === 2 || !previewable">
                <DocumentViewer
                  v-if="agreementFile"
                  :key="agreementFile"
                  :file-id="agreementFile"
                  name="Agreement to sign"
                  :mime="agreementMime"
                  what="Preview of"
                  link="download"
                  class="reader-doc"
                />
                <div v-else class="sheet" role="status">
                  <v-progress-circular indeterminate size="24" width="2" />
                  <p>Preparing the agreement…</p>
                </div>
              </template>
              <template v-else>
                <!-- Until a copy is chosen the agreement stays here (above); the chosen copy replaces it, to check. -->
                <DocumentViewer :file="file" name="Your signed copy" :mime="file!.type" what="Preview of" link="none" class="reader-doc" />
              </template>
            </div>
          </Transition>
        </aside>
      </template>
    </div>

    <!-- Sending accepts the quote: say what it confirms and who hears of it, then send. -->
    <v-dialog v-model="confirming" max-width="560" :fullscreen="width < 600" scrollable aria-labelledby="send-title">
      <v-card class="send" rounded="lg">
        <!-- Plain head (golden-ratio dialog, owner 2026-11-24): the request φ : the total to sign 1. -->
        <header class="dlg-head" :class="{ solo: !quote }">
          <div class="dlg-who">
            <h2 id="send-title" class="dlg-title">Send the signed agreement?</h2>
            <p class="dlg-what">{{ title }}</p>
            <p v-if="quote" class="dlg-sub">Quote version {{ quote.version }}</p>
          </div>
          <dl v-if="quote" class="dlg-key">
            <dt class="dlg-cap">Total to sign</dt>
            <dd class="dlg-figure">{{ money(quote.total) }}</dd>
          </dl>
        </header>
        <v-card-text class="send-body">
          <ol class="send-steps">
            <li v-if="quote">
              <span class="send-node" aria-hidden="true"><v-icon :icon="mdiCheck" size="18" /></span>
              <span>This accepts quote version {{ quote.version }} for <strong class="tnum">{{ money(quote.total) }}</strong>, the total CIMH invoices.</span>
            </li>
            <li>
              <span class="send-node" aria-hidden="true"><v-icon :icon="mdiEmailOutline" size="18" /></span>
              <span>CIMH staff are emailed to check the signature, then order and pick the items.</span>
            </li>
          </ol>
          <div v-if="file" class="send-file">
            <v-icon :icon="fileIcon" size="28" class="send-file-icon" aria-hidden="true" />
            <span class="send-file-main">
              <span class="send-file-name" :title="file.name">{{ file.name }}</span>
              <span class="send-file-facts">{{ fileFacts }}</span>
            </span>
          </div>
        </v-card-text>
        <footer class="send-foot">
          <v-btn variant="text" @click="confirming = false">Back</v-btn>
          <v-btn color="primary" variant="flat" :prepend-icon="mdiSend" @click="sendNow">Send signed agreement</v-btn>
        </footer>
      </v-card>
    </v-dialog>

    <ReasonDialog
      :model-value="cancelling"
      title="Cancel this request?"
      text="The quote lapses and nothing will be ordered. You can send a new request later."
      confirm="Cancel request"
      danger
      :busy="busy"
      @update:model-value="(v: boolean) => (cancelling = v)"
      @submit="cancel"
    />
  </div>
</template>

<style scoped>
/* Wider than the other request pages (1280): the document beside the list needs ~860 px to be read. */
.sign-page {
  --page-max: 1480px;
}
/* ---- the band: deep navy field with the logo-blue rule (as /cart and the request page) */
.band {
  background: #0a2e4a;
  color: #fff;
  border-bottom: 4px solid #0084c8;
}
.band-in {
  max-width: var(--page-max);
  margin: 0 auto;
  padding: var(--sp-3) var(--sp-6) var(--sp-4);
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--sp-2) var(--sp-6);
  flex-wrap: wrap;
}
.band-main {
  min-width: 0;
}
/* Title, subtitle and the task list share one left edge. Back: a "← Request" button above the title, or, where the
   page has a gutter wide enough (≥ 1580 px: (1580 − 1480) / 2 + 24 px padding), an arrow hung in the gutter beside
   the title (the band stays one title block tall, so the whole checklist fits the first view). */
.band-head {
  position: relative;
}
.back {
  color: #fff;
}
.back-text {
  margin-left: calc(-1 * var(--sp-3));
}
.back-icon {
  display: none !important;
}
@media (min-width: 1580px) {
  .back-text {
    display: none !important;
  }
  .back-icon {
    display: inline-flex !important;
    position: absolute;
    right: calc(100% + var(--sp-2));
    top: 50%;
    transform: translateY(-50%);
  }
}
.band-title {
  margin: 0;
  font-size: clamp(28px, 3.2vw, 36px);
  line-height: 1.2;
  font-weight: 700;
  letter-spacing: -0.015em;
}
.band-sub :deep(.short-ref),
.band-sub > span {
  white-space: nowrap;
}
.band-sub {
  display: flex;
  flex-wrap: wrap;
  gap: 0 var(--sp-2);
  margin: var(--sp-1) 0 0;
  font-size: 15px;
  line-height: 22px;
  color: #cfe3f1;
}
.band-total {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  text-align: right;
}
.bt-label {
  font-size: 14px;
  line-height: 20px;
  color: #cfe3f1;
}
.bt-amount {
  font-size: clamp(28px, 3vw, 34px);
  line-height: 1.2;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.bt-expiry {
  font-size: 14px;
  line-height: 20px;
  font-weight: 600;
  color: #5cc2ff;
}
.bt-expiry.soon {
  color: #ffd166;
}

/* ---- body: the task list, and on wide screens the open task's document beside it */
.body {
  max-width: var(--page-max);
  margin: 0 auto;
  padding: var(--sp-4) var(--sp-6) var(--sp-12);
  /* Documents lie on a desk, so the sheet's edge reads (the viewer's own ground is near-white in SHOP light). */
  --doc-ground: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 10%, rgb(var(--v-theme-surface)));
  /* An A4 page at 860 px puts the agreement's 9.5 pt body at ~13.7 px (the shared default, 760, at ~12). */
  --doc-page-max: 860px;
}
/* The list gives the document the room: 400–480 px of tasks, the rest is the page being read. */
.body.split {
  padding-bottom: var(--sp-6);
  display: grid;
  grid-template-columns: minmax(400px, 480px) minmax(0, 1fr);
  gap: clamp(24px, 2.5vw, 40px);
  align-items: start;
}
.tasks-col {
  min-width: 0;
  max-width: 860px;
}

.notice {
  display: flex;
  gap: var(--sp-3);
  padding: var(--sp-4);
  margin-bottom: var(--sp-6);
  border-radius: 8px;
  background: rgba(var(--v-theme-warning), 0.12);
  border: 1px solid rgba(var(--v-theme-warning), 0.55);
}
.notice-icon {
  color: rgb(var(--v-theme-warning));
  flex: none;
}
.notice p {
  margin: 0;
}
.notice-title {
  font-weight: 700;
  font-size: 16px;
  line-height: 24px;
}
.notice-text {
  font-size: 15px;
  line-height: 22px;
}

/* ---- the tasks: a ruled list; a node per task on one wire that fills as tasks are done */
.tasks {
  --node: 36px;
  --pad-x: var(--sp-4);
  --pad-y: var(--sp-3);
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.task {
  position: relative;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  transition: background-color 240ms ease-out;
}
.task.open {
  background: rgba(var(--v-theme-primary), 0.06);
}
/* From this node's centre to the next one's: every row starts its node at the same offset. */
.wire {
  position: absolute;
  left: calc(var(--pad-x) + var(--node) / 2 - 1.5px);
  top: calc(var(--pad-y) + var(--node) / 2);
  height: 100%;
  width: 3px;
  background: rgba(var(--v-border-color), 0.28);
  pointer-events: none;
}
.wire::after {
  content: '';
  position: absolute;
  inset: 0;
  background: rgb(var(--v-theme-primary));
  transform: scaleY(0);
  transform-origin: top center;
  transition: transform 480ms cubic-bezier(0.16, 1, 0.3, 1) 120ms;
}
.wire.lit::after {
  transform: scaleY(1);
}
.task-h {
  margin: 0;
  font: inherit;
}
.task-hit {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-start;
  gap: var(--sp-4);
  width: 100%;
  padding: var(--pad-y) var(--pad-x);
  background: none;
  border: 0;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  border-radius: 4px;
  scroll-margin-top: 88px;
}
.task-hit:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.node {
  flex: none;
  display: grid;
  place-items: center;
  width: var(--node);
  height: var(--node);
  border-radius: 50%;
  font-size: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  background: rgb(var(--v-theme-background));
  border: 3px solid rgb(var(--v-theme-field-outline));
  color: rgb(var(--v-theme-on-surface-variant));
  transition: background-color 240ms ease-out, border-color 240ms ease-out, color 240ms ease-out, box-shadow 240ms ease-out;
}
.task.open .node {
  border-color: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-primary));
  box-shadow: 0 0 0 6px rgba(var(--v-theme-primary), 0.14);
}
.task.done .node {
  background: rgb(var(--v-theme-primary));
  border-color: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}
/* Just done: the check lands. */
.task.pop .node {
  animation: node-pop 420ms cubic-bezier(0.16, 1, 0.3, 1);
}
@keyframes node-pop {
  0% {
    transform: scale(0.7);
  }
  60% {
    transform: scale(1.1);
  }
  100% {
    transform: scale(1);
  }
}
.task-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-top: 5px;
}
.task-title {
  font-size: 20px;
  line-height: 26px;
  font-weight: 700;
  text-wrap: balance;
}
.task-sum {
  font-size: 15px;
  line-height: 20px;
  color: rgb(var(--v-theme-on-surface-variant));
  overflow-wrap: anywhere;
}
.chev {
  flex: none;
  margin-top: 6px;
  color: rgb(var(--v-theme-on-surface-variant));
  transition: transform 240ms cubic-bezier(0.16, 1, 0.3, 1);
}
.task.open .chev {
  transform: rotate(180deg);
}
.task-hit:hover .task-title {
  text-decoration: underline;
  text-underline-offset: 4px;
  text-decoration-thickness: 1px;
}

/* An open task's content hangs under its title, clear of the wire. */
.task-in {
  position: relative;
  z-index: 1;
  padding: 0 var(--pad-x) var(--sp-4) calc(var(--pad-x) + var(--node) + var(--sp-4));
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.lead {
  margin: 0;
  font-size: 16px;
  line-height: 25px;
  max-width: 62ch;
  text-wrap: pretty;
}

/* the quote, line by line: ruled, amounts in one column */
.lines {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.ln {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  column-gap: var(--sp-4);
  row-gap: 0;
  padding: var(--sp-2) 0;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.ln-name {
  font-weight: 600;
  overflow-wrap: anywhere;
}
.ln-amt {
  font-weight: 600;
  white-space: nowrap;
  text-align: right;
}
.ln-meta {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: 0 var(--sp-3);
  font-size: 14px;
  line-height: 20px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.src {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.src::before {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  flex: none;
}
.src-cimh::before {
  background: rgb(var(--v-theme-on-surface));
}
.src-sup::before {
  background: #0084c8;
}
/* a source: its heading, its items, its estimated shipping */
.grp {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}
.grp-title {
  margin: 0;
  font-size: 15px;
  line-height: 22px;
  font-weight: 700;
}
.ln-ship {
  padding: 6px 0;
  color: rgb(var(--v-theme-on-surface-variant));
}
.ln-ship .ln-name,
.ln-ship .ln-amt {
  font-weight: 400;
}
.sums,
.facts {
  margin: 0;
}
.sums > div,
.facts > div {
  display: flex;
  justify-content: space-between;
  gap: var(--sp-4);
  padding: 3px 0;
}
.sums dd,
.facts dd {
  margin: 0;
  text-align: right;
  overflow-wrap: anywhere;
}
.sums dd {
  white-space: nowrap;
}
.sum-total {
  margin-top: var(--sp-1);
  padding-top: var(--sp-2) !important;
  border-top: 2px solid rgb(var(--v-theme-on-surface));
  font-size: 18px;
  line-height: 26px;
  font-weight: 700;
}
/* Facts are words, not amounts: a label column and left-aligned text. */
.facts {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.facts > div {
  display: grid;
  grid-template-columns: 7.5rem minmax(0, 1fr);
  gap: var(--sp-4);
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding: var(--sp-2) 0;
}
.facts dt {
  color: rgb(var(--v-theme-on-surface-variant));
}
.facts dd {
  text-align: left;
  text-wrap: pretty;
}
.fine {
  margin: 0;
  font-size: 14px;
  line-height: 20px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.acts {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-3);
  margin-top: var(--sp-2);
}
.wait {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  margin: 0;
  font-size: 15px;
  color: rgb(var(--v-theme-on-surface-variant));
}

/* narrower screens: the task's document inside it */
.inline {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.inline-title {
  margin: var(--sp-2) 0 0;
  font-size: 17px;
  line-height: 24px;
  font-weight: 700;
}
.inline-docs {
  height: clamp(420px, 72vh, 860px);
}
.inline-docs.empty {
  height: auto;
}
.inline-doc {
  --doc-height: auto;
  --doc-max-height: clamp(360px, 72vh, 900px);
}

/* the signed copy: a drop slot that is also the file picker */
.slot {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-1);
  padding: var(--sp-6) var(--sp-4);
  border: 2px dashed rgba(var(--v-theme-primary), 0.55);
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
  text-align: center;
  cursor: pointer;
  transition: border-color 160ms ease-out, background-color 160ms ease-out;
}
.slot:hover,
.slot.over {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.08);
}
.slot.chosen {
  border-style: solid;
  border-color: rgba(var(--v-theme-primary), 0.7);
}
.slot.bad {
  border-color: rgb(var(--v-theme-error));
}
.slot:focus-within {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.slot-input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}
.slot-icon {
  color: rgb(var(--v-theme-primary));
}
.slot-title {
  font-size: 17px;
  line-height: 24px;
  font-weight: 700;
  overflow-wrap: anywhere;
}
.slot-hint {
  max-width: 46ch;
  font-size: 14px;
  line-height: 20px;
  color: rgb(var(--v-theme-on-surface-variant));
  text-wrap: pretty;
}
.slot-link {
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 3px;
}
/* On the tinted slot primary text drops under 4.5:1, so the link takes the ink colour. */
.slot:hover .slot-link,
.slot.over .slot-link {
  color: rgb(var(--v-theme-on-surface));
}
.err {
  margin: calc(-1 * var(--sp-2)) 0 0;
  font-size: 14px;
  line-height: 20px;
  font-weight: 500;
  color: rgb(var(--v-theme-error));
}
.next-title {
  margin: var(--sp-4) 0 0;
  font-size: 17px;
  line-height: 24px;
  font-weight: 700;
}
.next {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.next li {
  padding: var(--sp-2) 0;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  font-size: 15px;
  line-height: 22px;
  text-wrap: pretty;
}

.foot {
  margin-top: var(--sp-4);
  margin-left: calc(-1 * var(--sp-1));
}

/* ---- the reader: the open task's document, sticky under the app bar. It leaves room for the page's end (body
   padding + slim footer), so scrolled to the bottom it still sits under the app bar instead of being pushed up. */
.reader {
  position: sticky;
  top: calc(72px + var(--sp-4));
  height: calc(100vh - 72px - var(--sp-4) - 104px);
  min-height: 460px;
  max-height: calc(100vh - 72px - 2 * var(--sp-4)); /* never past the window (a short window met min-height) */
  min-height: min(460px, calc(100vh - 72px - 2 * var(--sp-4)));
  min-width: 0;
}
.reader-in {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.reader-doc {
  flex: 1 1 0;
  min-height: 0;
}
.sheet {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
  padding: var(--sp-8);
  border-radius: 8px;
  background: rgb(var(--v-theme-surface-variant));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  color: rgb(var(--v-theme-on-surface-variant));
  text-align: center;
}
.sheet p {
  margin: 0;
  max-width: 40ch;
}
/* Golden-ratio dialog (owner 2026-11-24): 11 · 14 · 17.8 · 22.65 px, spacing 8 · 13 · 21 · 34; head from base.css. */
.send {
  overflow: hidden;
  display: flex;
  flex-direction: column;
  font-size: 14px;
}
.send-body {
  padding: 13px 21px 8px !important;
}
.send-steps {
  list-style: none;
  margin: 0;
  padding: 0;
}
.send-steps li {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 13px;
  align-items: start;
  padding: 13px 0;
  line-height: 1.5;
}
.send-steps li + li {
  border-top: 1px solid var(--dlg-rule);
}
.send-node {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
  margin-top: -3px;
}
.send-file {
  display: flex;
  align-items: center;
  gap: 13px;
  margin-top: 8px;
  padding: 13px;
  border-radius: 8px;
  border: 1px solid var(--dlg-rule);
}
.send-file-icon {
  flex: none;
  color: rgb(var(--v-theme-primary));
}
.send-file-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.send-file-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.send-file-facts {
  line-height: 1.5;
  color: var(--dlg-muted);
}
.send-foot {
  flex: none;
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  padding: 13px 21px;
  border-top: 1px solid var(--dlg-rule);
}
@media (max-width: 599px) {
  .send-body {
    padding-inline: 13px !important;
  }
  .send-foot {
    padding-inline: 13px;
    margin-top: auto;
  }
  .send-foot .v-btn {
    flex: 1 1 auto;
  }
}
.sheet-title {
  font-size: 17px;
  line-height: 24px;
  font-weight: 700;
  color: rgb(var(--v-theme-on-surface));
}
.swap-enter-active {
  transition: opacity 220ms ease-out, transform 320ms cubic-bezier(0.16, 1, 0.3, 1);
}
.swap-leave-active {
  transition: opacity 120ms ease-in;
}
.swap-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.swap-leave-to {
  opacity: 0;
}

/* ---- phones */
@media (max-width: 959.98px) {
  .body {
    padding: var(--sp-6) 0 120px; /* clear of the bottom bar and toasts */
  }
  .band-in {
    padding: var(--sp-4) var(--sp-4) var(--sp-4);
    gap: var(--sp-3);
  }
  .band-total {
    align-items: flex-start;
    text-align: left;
  }
  .tasks {
    --pad-x: var(--sp-4);
    --node: 32px;
  }
  .task-title {
    font-size: 18px;
    line-height: 24px;
  }
  .task-text {
    padding-top: 3px;
  }
  .foot {
    margin-left: var(--sp-2);
  }
}
@media (max-width: 599.98px) {
  /* The content uses the row's whole width: the wire stops at the open task's heading. */
  .task-in {
    padding-left: var(--pad-x);
  }
  .task.open .wire {
    display: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .wire::after,
  .chev,
  .node {
    transition: none;
  }
  .task.pop .node {
    animation: none;
  }
  .swap-enter-active {
    transition: opacity 160ms;
  }
  .swap-enter-from {
    transform: none;
  }
}
</style>
