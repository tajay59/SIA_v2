<script setup lang="ts">
/**
 * A-22 record: write or change one announcement and see it on SHOP and SIA, light and dark, as you type.
 * Fields: message (≤ 280), tone, shown on, keep for (presets from the start, Until…, or the current end when
 * editing), starts (now or later), link (a product from the catalogue, owner 2026-11-23, or a web address),
 * closable (locked off for alerts). Publish / Save changes ask first (everyone sees it at once); End now asks in
 * red. Submit, then mark: buttons stay enabled and a press marks every field that is missing.
 */
import {
  type AnnouncementAdmin,
  type AnnouncementInput,
  type AnnouncementPatch,
  ApiError,
  call,
  catalog,
  checkForm,
  createAnnouncement,
  DateField,
  endAnnouncement,
  type ProductStaff,
  updateAnnouncement,
  useNotify,
} from '@cimh/web-app'
import { formatDateTime } from '@cimh/web-ui'
import { mdiAlertCircle, mdiInformation } from '@mdi/js'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import AnnouncementPreview from './AnnouncementPreview.vue'
import ProductPicker from './ProductPicker.vue'
import SaveState from './SaveState.vue'
import SegmentedChoice from './SegmentedChoice.vue'

const props = defineProps<{ announcement: AnnouncementAdmin | null }>()
const emit = defineEmits<{ saved: [a: AnnouncementAdmin]; ended: [id: string] }>()
const notify = useNotify()
const display = useDisplay()
const phone = computed(() => display.width.value < 600)

type Keep = 'current' | '1h' | '1d' | '7d' | '30d' | 'until'
type LinkKind = 'none' | 'product' | 'url'
const HOUR = 3_600_000
const PRESET_MS: Record<'1h' | '1d' | '7d' | '30d', number> = { '1h': HOUR, '1d': 24 * HOUR, '7d': 7 * 24 * HOUR, '30d': 30 * 24 * HOUR }
const MAX_MS = 90 * 24 * HOUR
// In the script, not the template: a literal https:// in a template attribute breaks vue-tsc (CLAUDE.md).
const urlHint = 'https://… or /catalogue'

const pad = (n: number) => String(n).padStart(2, '0')
const dateOf = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
const timeOf = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}`
const at = (date: string, time: string) => (date ? new Date(`${date}T${time || '00:00'}`) : null)

const editing = computed(() => !!props.announcement)
function blank() {
  const a = props.announcement
  const tomorrow = new Date(Date.now() + 24 * HOUR)
  const starts = a ? new Date(a.startsAt) : new Date()
  return {
    message: a?.message ?? '',
    tone: (a?.tone ?? 'INFO') as 'INFO' | 'ALERT',
    audience: (a?.audience ?? 'BOTH') as 'SHOP' | 'SIA' | 'BOTH',
    linkKind: (a?.link?.productId ? 'product' : a?.link?.url ? 'url' : 'none') as LinkKind,
    linkLabel: a?.link?.label ?? '',
    linkUrl: a?.link?.url ?? '',
    productId: a?.link?.productId ?? '',
    start: (a && starts.getTime() > Date.now() ? 'later' : 'now') as 'now' | 'later',
    startDate: dateOf(starts),
    startTime: timeOf(starts),
    keep: (a ? 'current' : '1d') as Keep,
    untilDate: dateOf(a ? new Date(a.expiresAt) : tomorrow),
    untilTime: timeOf(a ? new Date(a.expiresAt) : tomorrow),
    dismissible: a ? a.dismissible : true,
  }
}
const form = reactive(blank())
let initial = JSON.stringify(form)
const product = ref<ProductStaff | null>(null)
const dirty = computed(() => JSON.stringify(form) !== initial)
const saved = ref(false)
const formRef = ref()

onMounted(async () => {
  const pid = props.announcement?.link?.productId
  if (!pid) return
  try {
    product.value = (await call(() => catalog.GET('/products/{productId}', { params: { path: { productId: pid } } }))) as ProductStaff
  } catch {
    // inactive or gone: the picker stays empty and the save asks for another product
  }
})
watch(product, (p) => (form.productId = p?.id ?? ''))
watch(
  () => form.tone,
  (t) => t === 'ALERT' && (form.dismissible = false),
)

// ---- derived times
const startsAt = computed(() => (form.start === 'later' ? at(form.startDate, form.startTime) : new Date()))
const endsAt = computed<Date | null>(() => {
  if (form.keep === 'current') return props.announcement ? new Date(props.announcement.expiresAt) : null
  if (form.keep === 'until') return at(form.untilDate, form.untilTime)
  const s = startsAt.value
  return s ? new Date(s.getTime() + PRESET_MS[form.keep]) : null
})
const when = (d: Date | null) => (d ? formatDateTime(d.toISOString()) : '—')
const range = computed(() => `${form.start === 'later' ? `From ${when(startsAt.value)}` : 'From now'} until ${when(endsAt.value)}`)

// ---- options
const toneOptions = [
  { title: 'Information', value: 'INFO' as const },
  { title: 'Alert', value: 'ALERT' as const },
]
const audienceOptions = [
  { title: 'SHOP', value: 'SHOP' as const },
  { title: 'SIA', value: 'SIA' as const },
  { title: 'Both', value: 'BOTH' as const },
]
const keepOptions = computed(() => [
  ...(editing.value ? [{ title: 'Current end', value: 'current' as Keep }] : []),
  { title: '1 hour', value: '1h' as Keep },
  { title: '1 day', value: '1d' as Keep },
  { title: '1 week', value: '7d' as Keep },
  { title: '30 days', value: '30d' as Keep },
  { title: 'Until…', value: 'until' as Keep },
])
const startOptions = [
  { title: 'Now', value: 'now' as const },
  { title: 'Later', value: 'later' as const },
]
const linkOptions = [
  { title: 'No link', value: 'none' as LinkKind },
  { title: 'A product', value: 'product' as LinkKind },
  { title: 'A web address', value: 'url' as LinkKind },
]

// ---- rules (marked on Publish / Save; a wrong value at once)
const rules = {
  message: [(v: string) => !!v.trim() || 'Write the message', (v: string) => v.length <= 280 || 'At most 280 characters'],
  label: [(v: string) => form.linkKind !== 'url' || !!v.trim() || 'Give the link a label', (v: string) => v.length <= 40 || 'At most 40 characters'],
  url: [
    (v: string) => form.linkKind !== 'url' || !!v.trim() || 'Give the address',
    (v: string) => form.linkKind !== 'url' || /^(https:\/\/\S+|\/(?!\/)\S*)$/i.test(v.trim()) || 'Use https://… or a page on this site (/…)',
  ],
  start: [() => form.start !== 'later' || (!!startsAt.value && startsAt.value.getTime() > Date.now() - 60_000) || 'Choose a start in the future'],
  until: [
    () => form.keep !== 'until' || !!endsAt.value || 'Choose an end date',
    () => !endsAt.value || !startsAt.value || endsAt.value > startsAt.value || 'The end must be after the start',
    () => !endsAt.value || endsAt.value.getTime() <= Date.now() + MAX_MS || 'At most 90 days from now',
  ],
}
// Products customers can open on SHOP: sellable, active, and MET/RAD or Pro Bono (catalog-svc PUBLIC_FILTER).
const productOnShop = computed(() => {
  const p = product.value
  return !p || (p.sellable && p.active !== false && (p.type === 'MET' || p.type === 'RAD' || !!p.probono))
})
const productRules = [
  () => form.linkKind !== 'product' || !!form.productId || 'Choose a product',
  () => form.linkKind !== 'product' || form.audience === 'SIA' || productOnShop.value || "Customers can't open this product on SHOP: show it on SIA only",
]

const previewModel = computed(() => ({
  message: form.message,
  tone: form.tone,
  audience: form.audience,
  dismissible: form.dismissible && form.tone !== 'ALERT',
  link:
    form.linkKind === 'product' && form.productId
      ? { label: form.linkLabel.trim() || product.value?.name || 'See the product', productId: form.productId }
      : form.linkKind === 'url' && form.linkUrl.trim()
        ? { label: form.linkLabel.trim() || 'Link', url: form.linkUrl.trim() }
        : null,
}))

// ---- save
const confirming = ref(false)
const busy = ref(false)
const confirmTitle = computed(() =>
  editing.value ? 'Save for everyone now?' : form.start === 'later' ? 'Schedule this announcement?' : 'Publish to everyone now?',
)
const reach = computed(() => (form.audience === 'BOTH' ? 'SHOP and SIA' : form.audience))

async function ask() {
  if (!(await checkForm(formRef.value))) return
  confirming.value = true
}

function linkBody() {
  if (form.linkKind === 'product') return { productId: form.productId, ...(form.linkLabel.trim() ? { label: form.linkLabel.trim() } : {}) }
  if (form.linkKind === 'url') return { url: form.linkUrl.trim(), label: form.linkLabel.trim() }
  return null
}
function ttlBody() {
  if (form.keep === 'until') return { until: endsAt.value!.toISOString() }
  return { preset: form.keep as '1h' | '1d' | '7d' | '30d' }
}

async function save() {
  busy.value = true
  try {
    let result: AnnouncementAdmin
    if (!props.announcement) {
      const body: AnnouncementInput = {
        message: form.message.trim(),
        tone: form.tone,
        audience: form.audience,
        dismissible: form.dismissible,
        ttl: ttlBody(),
        ...(linkBody() ? { link: linkBody()! } : {}),
        ...(form.start === 'later' && startsAt.value ? { startsAt: startsAt.value.toISOString() } : {}),
      }
      result = await createAnnouncement(body)
      notify.toast(form.start === 'later' ? `Scheduled for ${when(startsAt.value)}` : 'Published: everyone sees it now', 'success')
    } else {
      const was = blank()
      const patch: AnnouncementPatch = {}
      if (form.message !== was.message) patch.message = form.message.trim()
      if (form.tone !== was.tone) patch.tone = form.tone
      if (form.audience !== was.audience) patch.audience = form.audience
      if (form.dismissible !== was.dismissible) patch.dismissible = form.dismissible
      if (form.linkKind !== was.linkKind || form.linkLabel !== was.linkLabel || form.linkUrl !== was.linkUrl || form.productId !== was.productId)
        patch.link = linkBody()
      if (form.start === 'later' && (form.startDate !== was.startDate || form.startTime !== was.startTime || was.start !== 'later')) patch.startsAt = startsAt.value!.toISOString()
      if (form.keep !== 'current') patch.ttl = ttlBody()
      result = await updateAnnouncement(props.announcement, patch)
      notify.toast('Saved: open pages show the change now', 'success')
    }
    confirming.value = false
    initial = JSON.stringify(form)
    saved.value = true
    setTimeout(() => (saved.value = false), 1800)
    emit('saved', result)
  } catch (e) {
    confirming.value = false
    notify.report(e)
    if (e instanceof ApiError && e.status === 422 && e.errors.length) await checkForm(formRef.value)
  } finally {
    busy.value = false
  }
}

const ending = ref(false)
async function endNow() {
  if (!props.announcement) return
  busy.value = true
  try {
    await endAnnouncement(props.announcement)
    ending.value = false
    notify.toast('Ended: it has left every open page', 'success')
    emit('ended', props.announcement.id)
  } catch (e) {
    ending.value = false
    notify.report(e)
  } finally {
    busy.value = false
  }
}

// Leaving with unsaved edits asks (route leave is the page's job; this covers the tab).
function beforeUnload(e: BeforeUnloadEvent) {
  if (dirty.value) e.preventDefault()
}
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
defineExpose({ dirty })
</script>

<template>
  <v-form ref="formRef" class="editor" @submit.prevent="ask">
    <div class="fields">
      <div class="cell wide">
        <label class="cap" for="ann-message">Message</label>
        <v-textarea
          id="ann-message"
          v-model="form.message"
          name="message"
          :rules="rules.message"
          rows="3"
          auto-grow
          counter="280"
          maxlength="280"
          placeholder="What should everyone know? e.g. New WXT536 weather stations in stock."
        />
      </div>

      <section class="preview-wrap cell wide" aria-labelledby="ann-prev">
        <h3 id="ann-prev" class="console-title">Preview</h3>
        <AnnouncementPreview :announcement="previewModel" />
      </section>

      <div class="cell">
        <span class="cap">Tone</span>
        <SegmentedChoice v-model="form.tone" name="tone" scroll label="Tone" :options="toneOptions" />
        <p class="hint">
          <v-icon :icon="form.tone === 'ALERT' ? mdiAlertCircle : mdiInformation" size="14" />
          {{ form.tone === 'ALERT' ? 'Amber, can’t be closed. For changes people must not miss.' : 'Blue, people can close it.' }}
        </p>
      </div>
      <div class="cell">
        <span class="cap">Shown on</span>
        <SegmentedChoice v-model="form.audience" name="audience" scroll label="Shown on" :options="audienceOptions" />
        <p class="hint">{{ form.audience === 'SIA' ? 'Signed-in staff only.' : form.audience === 'SHOP' ? 'Every SHOP visitor, signed in or not.' : 'Every SHOP visitor and signed-in staff.' }}</p>
      </div>

      <div class="cell wide">
        <span class="cap">Keep for</span>
        <SegmentedChoice v-model="form.keep" name="keep" scroll label="Keep for" :options="keepOptions" />
        <div v-if="form.keep === 'until'" class="pair">
          <DateField v-model="form.untilDate" label="End date" name="untilDate" :rules="rules.until" hide-details="auto" />
          <v-text-field v-model="form.untilTime" type="time" label="Time" name="untilTime" hide-details="auto" />
        </div>
        <p class="hint mono">{{ range }}</p>
      </div>

      <div class="cell">
        <span class="cap">Starts</span>
        <SegmentedChoice v-model="form.start" name="starts" scroll label="Starts" :options="startOptions" />
        <div v-if="form.start === 'later'" class="pair">
          <DateField v-model="form.startDate" label="Date" name="startDate" :rules="rules.start" hide-details="auto" />
          <v-text-field v-model="form.startTime" type="time" label="Time" name="startTime" hide-details="auto" />
        </div>
      </div>

      <div class="cell switch-cell">
        <v-switch
          v-model="form.dismissible"
          :disabled="form.tone === 'ALERT'"
          color="primary"
          inset
          hide-details
          :label="form.tone === 'ALERT' ? 'People can close it (alerts always stay)' : 'People can close it'"
        />
      </div>

      <div class="cell wide">
        <span class="cap">Link</span>
        <SegmentedChoice v-model="form.linkKind" name="linkKind" scroll label="Link" :options="linkOptions" />
        <div v-if="form.linkKind === 'product'" class="pair link">
          <div class="grow">
            <ProductPicker v-model="product" label="Product it is about" />
            <v-input :model-value="form.productId" :rules="productRules" name="product" class="rule-only" />
          </div>
          <v-text-field v-model="form.linkLabel" label="Link text (optional)" name="linkLabel" :placeholder="product?.name ?? 'Product name'" :rules="rules.label" hide-details="auto" />
        </div>
        <div v-else-if="form.linkKind === 'url'" class="pair link">
          <v-text-field v-model="form.linkUrl" label="Address" name="linkUrl" :placeholder="urlHint" :rules="rules.url" hide-details="auto" class="grow" />
          <v-text-field v-model="form.linkLabel" label="Link text" name="linkLabel" :rules="rules.label" hide-details="auto" />
        </div>
        <p v-if="form.linkKind === 'product'" class="hint">Opens the product’s page: the catalogue page on SHOP, the product record on SIA.</p>
      </div>

    </div>


    <footer class="foot">
      <v-btn v-if="editing" class="m3 m3-danger" variant="outlined" :disabled="busy" @click="ending = true">End now…</v-btn>
      <span class="spacer" />
      <SaveState v-if="editing" :dirty="dirty" :saved="saved" quiet />
      <v-btn class="m3" color="primary" variant="flat" type="submit" :loading="busy && !ending" :disabled="editing && !dirty">
        {{ editing ? 'Save changes' : form.start === 'later' ? 'Schedule' : 'Publish' }}
      </v-btn>
    </footer>
  </v-form>

  <v-dialog v-model="confirming" max-width="560" :fullscreen="phone" scrollable :aria-label="confirmTitle">
    <v-card :title="confirmTitle">
      <!-- Scrolls on phones: focusable so keyboard users can scroll it (axe scrollable-region-focusable). -->
      <v-card-text class="confirm" tabindex="0" role="region" aria-label="What happens">
        <p>
          {{ editing ? 'Open pages change at once on' : form.start === 'later' ? 'It appears on' : 'It appears at once at the top of every page on' }}
          <strong>{{ reach }}</strong>.
        </p>
        <p class="mono">{{ range }}</p>
        <div class="confirm-preview"><AnnouncementPreview :announcement="{ ...previewModel, audience: form.audience }" /></div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="confirming = false">Keep editing</v-btn>
        <v-btn class="m3" color="primary" variant="flat" :loading="busy" @click="save">
          {{ editing ? 'Save changes' : form.start === 'later' ? 'Schedule' : 'Publish now' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-dialog v-model="ending" max-width="480" aria-label="End this announcement now?">
    <v-card title="End this announcement now?">
      <v-card-text>It leaves every open page on {{ reach }} at once and can’t be brought back (post it again instead).</v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="ending = false">Keep it</v-btn>
        <v-btn class="m3" color="error" variant="flat" :loading="busy" @click="endNow">End now</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.editor {
  container-type: inline-size;
  display: flex;
  flex-direction: column;
  min-height: 100%;
}
.fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px var(--sp-6);
  padding: var(--sp-4) 20px;
}
.cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.cell.wide {
  grid-column: 1 / -1;
}
.cap {
  font: 500 13px/18px Inter, system-ui, sans-serif;
  color: rgb(var(--v-theme-secondary));
}
.hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: 12px;
  line-height: 16px;
  color: rgb(var(--v-theme-secondary));
}
.mono {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.pair {
  display: grid;
  align-items: start;
  grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr);
  gap: var(--sp-2);
  margin-top: 4px;
}
.pair.link {
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr);
}
.grow {
  min-width: 0;
}
.switch-cell {
  justify-content: flex-end;
}
.rule-only :deep(.v-input__control) {
  display: none;
}
.preview-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.preview-wrap h3 {
  margin: 0;
}
/* Sticky inside the record pane on wide screens (it scrolls on its own); at the end of the form on phones,
   where a sticky bar over a scrolling page kept moving under the finger. */
.foot {
  margin-top: auto;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) 20px;
  border-top: 1px solid rgb(var(--v-theme-seam));
  background: rgb(var(--v-theme-surface));
}
.spacer {
  flex: 1;
}
.confirm {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.confirm p {
  margin: 0;
}
@container (min-width: 521px) {
  .foot {
    position: sticky;
    bottom: 0;
  }
}
/* Phones: the save state goes on its own line above the buttons; the buttons share the row. */
@container (max-width: 420px) {
  .foot .save-state {
    order: -1;
    flex-basis: 100%;
  }
}
@container (max-width: 520px) {
  .fields {
    grid-template-columns: minmax(0, 1fr);
    padding-inline: var(--sp-4);
  }
  .foot {
    padding-inline: var(--sp-4);
  }
  .pair,
  .pair.link {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
