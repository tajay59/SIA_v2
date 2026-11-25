<script setup lang="ts">
/**
 * Send a proof of payment for a delivered paid request (owner, 2026-11-23; redesigned with the payment statement,
 * impeccable). Plain head (2026-11-24, golden-ratio dialog; was navy): what is being paid for, its reference and the amount on record. Body: one drop slot (click,
 * Enter or drop a file; the native picker stays hidden), then the chosen file as a row with Change and Remove.
 * Uploaded as `payment_proof` (document-svc; scanned like every upload); CIMH staff are emailed. Send stays enabled:
 * a press with no file says so under the slot and moves the cursor there (forms rule).
 */
import { ApiError, type OrderRequest, getRequest, requestTitle, shortRef, uploadRequestFile, useNotify } from '@cimh/web-app'
import { formatMoney } from '@cimh/web-ui'
import { mdiClose, mdiFileDocumentOutline, mdiImageOutline, mdiTrayArrowUp } from '@mdi/js'
import { computed, nextTick, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'

const props = defineProps<{ request: OrderRequest }>()
const open = defineModel<boolean>({ default: false })
const emit = defineEmits<{ sent: [OrderRequest] }>()
const notify = useNotify()
const { xs } = useDisplay()

const picker = ref<HTMLInputElement | null>(null)
const slot = ref<HTMLElement | null>(null)
const file = ref<File | null>(null)
const error = ref('')
const over = ref(false)
const busy = ref(false)
watch(open, (o) => {
  if (!o) return
  file.value = null
  error.value = ''
})

const MAX = 20 * 1024 * 1024
const TYPES = ['application/pdf', 'image/jpeg', 'image/png', 'image/webp']
const title = computed(() => requestTitle(props.request.lines[0]?.product.name, props.request.lines.length, props.request.type))
const amount = computed(() => (props.request.amountDue ? formatMoney(props.request.amountDue, props.request.currency ?? 'BBD') : null))
const size = (n: number) => (n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`)

function take(f: File | undefined | null) {
  if (!f) return
  if (!TYPES.includes(f.type)) {
    error.value = 'Choose a PDF, JPG, PNG or WebP file'
    return
  }
  if (f.size > MAX) {
    error.value = 'The file is larger than 20 MB'
    return
  }
  error.value = ''
  file.value = f
}
function onPick(e: Event) {
  const input = e.target as HTMLInputElement
  take(input.files?.[0])
  input.value = ''
}
function onDrop(e: DragEvent) {
  over.value = false
  take(e.dataTransfer?.files?.[0])
}
function choose() {
  picker.value?.click()
}
async function remove() {
  file.value = null
  await nextTick()
  slot.value?.focus()
}

/** The upload is attached at once in most cases; when it is still being checked, wait a little for it. */
async function waitForProof(fileId: string): Promise<OrderRequest> {
  for (let i = 0; i < 6; i++) {
    const r = await getRequest(props.request.id)
    if (r.files?.some((f) => f.id === fileId)) return r
    await new Promise((res) => setTimeout(res, 1000))
  }
  return getRequest(props.request.id)
}

async function send() {
  if (!file.value) {
    error.value = 'Choose the receipt or confirmation to send'
    slot.value?.focus()
    return
  }
  busy.value = true
  try {
    const up = await uploadRequestFile(props.request.id, 'payment_proof', file.value)
    const r = await waitForProof(up.id)
    notify.toast('Proof of payment sent to CIMH', 'success')
    open.value = false
    emit('sent', r)
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) {
      open.value = false
      emit('sent', await getRequest(props.request.id))
    }
    notify.report(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <v-dialog v-model="open" max-width="560" :fullscreen="xs" :persistent="busy" scrollable aria-labelledby="proof-title">
    <v-card class="proof" rounded="lg">
      <!-- Plain head (golden-ratio dialog, owner 2026-11-24): the request φ : the amount 1. -->
      <header class="dlg-head">
        <div class="dlg-who">
          <h2 id="proof-title" class="dlg-title">Send proof of payment</h2>
          <p class="dlg-what">{{ title }}</p>
          <p class="dlg-sub"><span class="t-mono">{{ shortRef(request.id) }}</span></p>
        </div>
        <dl class="dlg-key">
          <dt class="dlg-cap">Amount</dt>
          <dd v-if="amount" class="dlg-figure">{{ amount }}</dd>
          <dd v-else class="dlg-sub on-invoice">On the invoice</dd>
        </dl>
      </header>

      <v-card-text class="body">
        <p class="lead">Pay the invoice, then send CIMH the bank receipt or transfer confirmation. A PDF, a scan or a phone photo is fine.</p>

        <input ref="picker" type="file" class="picker" :accept="TYPES.join(',')" tabindex="-1" aria-hidden="true" @change="onPick" />
        <div
          v-if="!file"
          ref="slot"
          class="slot"
          :class="{ over, invalid: !!error }"
          role="button"
          tabindex="0"
          aria-describedby="proof-hint proof-error"
          @click="choose"
          @keydown.enter.prevent="choose"
          @keydown.space.prevent="choose"
          @dragover.prevent="over = true"
          @dragleave="over = false"
          @drop.prevent="onDrop"
        >
          <v-icon :icon="mdiTrayArrowUp" size="28" class="slot-icon" aria-hidden="true" />
          <span class="slot-label">Choose the receipt or drop it here</span>
          <span id="proof-hint" class="slot-hint">PDF, JPG, PNG or WebP · up to 20 MB</span>
        </div>
        <div v-else class="chosen">
          <v-icon :icon="file.type === 'application/pdf' ? mdiFileDocumentOutline : mdiImageOutline" size="24" class="chosen-icon" aria-hidden="true" />
          <span class="chosen-main">
            <span class="chosen-name">{{ file.name }}</span>
            <span class="chosen-size">{{ size(file.size) }}</span>
          </span>
          <v-btn variant="text" size="small" :disabled="busy" @click="choose">Change</v-btn>
          <v-btn :icon="mdiClose" variant="text" size="small" :disabled="busy" aria-label="Remove the file" @click="remove" />
        </div>
        <p id="proof-error" class="error" role="alert">{{ error }}</p>

        <p class="note">CIMH is emailed and checks the payment against the invoice. You can send another proof later.</p>
      </v-card-text>

      <footer class="foot">
        <v-btn variant="text" :disabled="busy" @click="open = false">Not now</v-btn>
        <v-btn color="primary" variant="flat" :loading="busy" @click="send">Send to CIMH</v-btn>
      </footer>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.proof {
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
/* Golden-ratio dialog (owner 2026-11-24): 11 · 14 · 17.8 · 22.65 px, spacing 8 · 13 · 21 · 34; head from base.css. */
.proof {
  font-size: 14px;
}
.on-invoice {
  margin: 0;
}
.body {
  padding: 21px 21px 8px !important;
}
.lead {
  margin: 0 0 21px;
  max-width: 60ch;
  line-height: 1.5;
  color: var(--dlg-muted);
}
.picker {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}
.slot {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 34px 21px;
  border: 1.5px dashed rgb(var(--v-theme-field-outline));
  border-radius: 8px;
  text-align: center;
  cursor: pointer;
  transition: border-color 140ms ease-out, background-color 140ms ease-out;
}
.slot:hover,
.slot.over {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.06);
}
.slot:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.slot.invalid {
  border-color: rgb(var(--v-theme-error));
}
.slot-icon {
  color: rgb(var(--v-theme-primary));
}
.slot-label {
  font-weight: 600;
}
.slot-hint {
  color: var(--dlg-muted);
}
.chosen {
  display: flex;
  align-items: center;
  gap: 13px;
  padding: 13px 8px 13px 13px;
  border: 1px solid var(--dlg-rule);
  border-radius: 8px;
  background: rgba(var(--v-theme-primary), 0.05);
}
.chosen-icon {
  color: rgb(var(--v-theme-primary));
}
.chosen-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.chosen-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chosen-size {
  color: var(--dlg-muted);
  font-variant-numeric: tabular-nums;
}
.error {
  min-height: 21px;
  margin: 8px 0 0;
  line-height: 21px;
  color: rgb(var(--v-theme-error));
}
.note {
  margin: 8px 0 0;
  line-height: 1.5;
  color: var(--dlg-muted);
}
.foot {
  flex: none;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 13px 21px;
  border-top: 1px solid var(--dlg-rule);
}
@media (max-width: 599.98px) {
  .foot {
    padding-inline: 13px;
  }
  .body {
    padding-inline: 13px !important;
  }
  .foot {
    flex-direction: column-reverse;
    align-items: stretch;
  }
}
@media (prefers-reduced-motion: reduce) {
  .slot {
    transition: none;
  }
}
</style>
