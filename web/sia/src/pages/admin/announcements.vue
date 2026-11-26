<script setup lang="ts">
/**
 * A-22 announcements (plan 2026-11-23; owner chose "List beside the record"): the banner at the top of every
 * SHOP/SIA page. Search + filter chips (Live · Starting later · SHOP · SIA) and New announcement; the list
 * (Live now, Starting later) beside the open message's editor and its four-up preview (`?open=<id>`,
 * `?open=new`). Narrow screens show the record alone with a way back. Admins only.
 */
import { type AnnouncementAdmin, listAnnouncements, useNotify } from '@cimh/web-app'
import { mdiAlertCircle, mdiArrowLeft, mdiInformation, mdiLinkVariant, mdiMagnify, mdiPlus } from '@mdi/js'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import AnnouncementEditor from '../../components/AnnouncementEditor.vue'
import SegmentedChoice from '../../components/SegmentedChoice.vue'
import { pinLeaving } from '../../list-motion'

definePage({ meta: { guard: 'admin', title: 'Announcements', ownHeading: true } })

const route = useRoute()
const router = useRouter()
const display = useDisplay()
const notify = useNotify()
const str = (v: unknown) => (typeof v === 'string' && v ? v : null)
const openId = computed(() => str(route.query.open))
const isNew = computed(() => openId.value === 'new')
const wide = computed(() => display.width.value >= 1280)

const items = ref<AnnouncementAdmin[]>([])
const loaded = ref(false)
const failed = ref(false)
const q = ref('')
const where = ref<'all' | 'SHOP' | 'SIA'>('all')
const whereOptions = [
  { title: 'All', value: 'all' as const },
  { title: 'On SHOP', value: 'SHOP' as const },
  { title: 'On SIA', value: 'SIA' as const },
]
const now = ref(Date.now())
let tick: ReturnType<typeof setInterval> | undefined

async function load() {
  failed.value = false
  try {
    items.value = await listAnnouncements()
  } catch (e) {
    failed.value = true
    notify.report(e)
  } finally {
    loaded.value = true
  }
}
onMounted(() => {
  void load()
  tick = setInterval(() => {
    now.value = Date.now()
    // Drop ones that ran out while the page was open (the server's TTL removes them too).
    items.value = items.value.filter((a) => Date.parse(a.expiresAt) > now.value)
  }, 15_000)
})
onBeforeUnmount(() => clearInterval(tick))

// A minute of grace: the server's clock may run a little ahead of this browser's (a "now" post must not read as later).
const isLive = (a: AnnouncementAdmin) => Date.parse(a.startsAt) <= now.value + 60_000
const matches = (a: AnnouncementAdmin) => {
  const t = q.value.trim().toLowerCase()
  if (t && !a.message.toLowerCase().includes(t) && !(a.link?.label ?? '').toLowerCase().includes(t)) return false
  if (where.value !== 'all' && a.audience !== where.value && a.audience !== 'BOTH') return false
  return true
}
const live = computed(() =>
  items.value
    .filter((a) => isLive(a) && matches(a))
    .sort((a, b) => Number(b.tone === 'ALERT') - Number(a.tone === 'ALERT') || b.startsAt.localeCompare(a.startsAt)),
)
const later = computed(() => items.value.filter((a) => !isLive(a) && matches(a)).sort((a, b) => a.startsAt.localeCompare(b.startsAt)))
const liveCount = computed(() => items.value.filter(isLive).length)
const laterCount = computed(() => items.value.length - liveCount.value)

function rel(ms: number) {
  const m = Math.max(1, Math.round(ms / 60_000))
  if (m < 60) return `${m} min`
  const h = Math.round(m / 60)
  if (h < 48) return `${h} h`
  return `${Math.round(h / 24)} d`
}
const audienceWord = (a: AnnouncementAdmin) => (a.audience === 'BOTH' ? 'Both' : a.audience)
const meta = (a: AnnouncementAdmin) =>
  [
    a.tone === 'ALERT' ? 'Alert' : 'Information',
    audienceWord(a),
    isLive(a) ? `ends in ${rel(Date.parse(a.expiresAt) - now.value)}` : `starts in ${rel(Date.parse(a.startsAt) - now.value)}`,
  ].join(' · ')

const open = (id: string) => void router.replace({ query: { open: id } })
const close = () => void router.replace({ query: {} })
const selected = computed(() => items.value.find((a) => a.id === openId.value) ?? null)
// A link to a message that ended: say so once and close it.
watch([openId, loaded], () => {
  if (loaded.value && openId.value && !isNew.value && !selected.value) {
    notify.toast('That announcement has ended', 'info')
    close()
  }
})

const editor = ref<InstanceType<typeof AnnouncementEditor> | null>(null)
// Unsaved edits: leaving (another row, Close, another page) asks in a dialog first.
const leaving = ref(false)
let settle: ((ok: boolean) => void) | null = null
function confirmLeave(): Promise<boolean> {
  if (!editor.value?.dirty) return Promise.resolve(true)
  leaving.value = true
  return new Promise((resolve) => (settle = resolve))
}
function answerLeave(ok: boolean) {
  leaving.value = false
  settle?.(ok)
  settle = null
}
onBeforeRouteLeave(() => confirmLeave())

function onSaved(a: AnnouncementAdmin) {
  now.value = Date.now()
  const i = items.value.findIndex((x) => x.id === a.id)
  if (i >= 0) items.value.splice(i, 1, a)
  else items.value = [a, ...items.value]
  justSaved.value = a.id
  setTimeout(() => (justSaved.value = null), 1200)
  open(a.id)
  // The editor re-keys on the new version: settle on the message, not mid-preview.
  void nextTick(() => recordScroll.value?.scrollTo({ top: 0 }))
}
function onEnded(id: string) {
  items.value = items.value.filter((a) => a.id !== id)
  close()
}
const justSaved = ref<string | null>(null)
const recordScroll = ref<HTMLElement | null>(null)

function onRowKey(e: KeyboardEvent) {
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
  e.preventDefault()
  const rows = Array.from(document.querySelectorAll<HTMLElement>('.arow'))
  const i = rows.indexOf(e.target as HTMLElement)
  rows[Math.max(0, Math.min(rows.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))]?.focus()
}
async function go(id: string) {
  if (id === openId.value || !(await confirmLeave())) return
  open(id)
}
async function closeRecord() {
  if (await confirmLeave()) close()
}
</script>

<template>
  <div class="anns" :class="{ alone: !wide && openId }">
    <div class="top">
      <h1 class="t-h1">Announcements</h1>
      <span class="console-mono counts" aria-live="polite">{{ liveCount }} live · {{ laterCount }} starting later</span>
    </div>

    <div class="strip">
      <v-text-field v-model="q" data-page-search :prepend-inner-icon="mdiMagnify" label="Search messages" clearable hide-details class="search" @click:clear="q = ''" />
      <SegmentedChoice v-model="where" name="where" label="Filter by app" :options="whereOptions" />
      <span class="spacer" />
      <v-btn class="m3" color="primary" variant="flat" :prepend-icon="mdiPlus" @click="go('new')">New announcement</v-btn>
    </div>

    <div class="console-panels panels" :class="{ split: wide && openId }">
      <section v-if="wide || !openId" class="alist" aria-label="Announcements">
        <div class="console-head">
          <h2 class="console-title">{{ loaded ? `${live.length + later.length} ${live.length + later.length === 1 ? 'announcement' : 'announcements'}` : 'Loading…' }}</h2>
        </div>
        <div class="console-scroll">
          <div v-if="!loaded" class="skel-rows"><div v-for="i in 5" :key="i" class="console-skel skel-row" /></div>
          <div v-else-if="failed" class="empty">
            <p class="t-body">Couldn’t load the announcements.</p>
            <v-btn class="m3" variant="outlined" @click="load">Retry</v-btn>
          </div>
          <div v-else-if="!items.length" class="empty">
            <p class="t-body">Nothing on the banner right now. A message posted here shows at the top of every SHOP and SIA page at once.</p>
            <div><v-btn class="m3" variant="outlined" :prepend-icon="mdiPlus" @click="go('new')">Write the first one</v-btn></div>
          </div>
          <div v-else-if="!live.length && !later.length" class="empty">
            <p class="t-body">No announcement matches.</p>
            <div><v-btn class="m3" variant="outlined" @click="(q = ''), (where = 'all')">Clear filters</v-btn></div>
          </div>
          <template v-else>
            <template v-for="group in [{ key: 'live', title: 'Live now', rows: live }, { key: 'later', title: 'Starting later', rows: later }]" :key="group.key">
              <h3 v-if="group.rows.length" class="group">{{ group.title }} <span class="console-mono">{{ group.rows.length }}</span></h3>
              <TransitionGroup tag="ul" name="arow" class="rows" @before-leave="pinLeaving">
                <li v-for="(a, i) in group.rows" :key="a.id" :style="{ '--i': Math.min(i, 12) }">
                  <a
                    :href="`/admin/announcements?open=${a.id}`"
                    class="arow"
                    :class="{ on: openId === a.id, alert: a.tone === 'ALERT', later: group.key === 'later', fresh: justSaved === a.id }"
                    :aria-current="openId === a.id ? 'true' : undefined"
                    @click.prevent="go(a.id)"
                    @keydown="onRowKey"
                  >
                    <v-icon :icon="a.tone === 'ALERT' ? mdiAlertCircle : mdiInformation" size="18" class="tone" aria-hidden="true" />
                    <span class="txt">
                      <span class="msg">{{ a.message }}</span>
                      <span class="meta console-mono">{{ meta(a) }}<template v-if="a.link"> · <v-icon :icon="mdiLinkVariant" size="13" aria-hidden="true" /> {{ a.link.label }}</template></span>
                    </span>
                  </a>
                </li>
              </TransitionGroup>
            </template>
          </template>
        </div>
      </section>

      <section v-if="openId" class="record" :aria-label="isNew ? 'New announcement' : 'Selected announcement'">
        <div class="console-head">
          <v-btn v-if="!wide" variant="text" size="small" class="m3" :prepend-icon="mdiArrowLeft" @click="closeRecord">All announcements</v-btn>
          <h2 v-else class="console-title head-title">{{ isNew ? 'New announcement' : 'Selected announcement' }}</h2>
          <span v-if="selected" class="console-mono by">
            {{ isLive(selected) ? 'Live' : 'Starting later' }} · {{ selected.updatedBy?.name ?? selected.createdBy?.name ?? 'admin' }}
          </span>
          <v-btn v-if="wide" variant="text" size="small" class="m3" @click="closeRecord">Close</v-btn>
        </div>
        <div ref="recordScroll" class="console-scroll">
          <AnnouncementEditor
            v-if="isNew || selected"
            ref="editor"
            :key="isNew ? 'new' : `${selected!.id}:${selected!.version}`"
            :announcement="isNew ? null : selected"
            @saved="onSaved"
            @ended="onEnded"
          />
          <div v-else class="skel-rows"><div v-for="i in 4" :key="i" class="console-skel skel-row" /></div>
        </div>
      </section>
    </div>

    <v-dialog v-model="leaving" max-width="440" persistent aria-label="Leave without saving?">
      <v-card title="Leave without saving?">
        <v-card-text>Your changes to this announcement are lost. What viewers see stays as it is.</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="answerLeave(false)">Keep editing</v-btn>
          <v-btn class="m3" color="primary" variant="flat" @click="answerLeave(true)">Leave</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.anns {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding: var(--sp-4) var(--sp-6) var(--sp-6);
  font-size: 14px;
}
@media (min-width: 1280px) {
  .anns {
    height: calc(100dvh - var(--v-layout-top, 0px));
    min-height: 560px;
  }
  .anns > :not(.panels) {
    flex-shrink: 0;
  }
}
.top {
  display: flex;
  align-items: baseline;
  gap: var(--sp-3);
  flex-wrap: wrap;
  margin-bottom: var(--sp-3); /* + the 12 px gap = 24 px under the title */
}
.counts {
  font-size: 12px;
  color: rgb(var(--v-theme-secondary));
}
.strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-3);
}
.search {
  flex: 1 1 240px;
  max-width: 420px;
}
.spacer {
  flex: 1;
}
.alone .strip {
  display: none;
}
.panels {
  grid-template-columns: minmax(0, 1fr);
  min-height: 0;
  flex: 1;
}
.panels.split {
  grid-template-columns: minmax(340px, 440px) minmax(0, 1fr);
}
.record {
  background: rgb(var(--v-theme-background));
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.record .console-scroll {
  flex: 1;
}
.split .record {
  border-left: 1px solid rgb(var(--v-theme-seam));
}
.head-title {
  flex: none;
  white-space: nowrap;
}
.by {
  margin-left: auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: rgb(var(--v-theme-secondary));
}
@media (max-width: 599.98px) {
  .by {
    display: none;
  }
}
.group {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  gap: var(--sp-2);
  align-items: baseline;
  margin: 0;
  padding: 8px var(--sp-4);
  font: 600 11px/16px Inter, system-ui, sans-serif;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-secondary));
  background: rgb(var(--v-theme-background));
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.rows {
  list-style: none;
  position: relative;
  margin: 0;
  padding: 0;
}
.arow {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  gap: var(--sp-3);
  align-items: start;
  padding: 10px var(--sp-4);
  color: inherit;
  text-decoration: none;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
  transition: background-color 120ms ease;
}
.arow:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.arow.on {
  background: rgba(var(--v-theme-primary), 0.14);
  box-shadow: inset 2px 0 rgb(var(--v-theme-primary));
}
.arow:focus-visible {
  outline-offset: -2px;
}
.tone {
  margin-top: 1px;
  color: rgb(var(--v-theme-primary));
}
.arow.alert .tone {
  color: rgb(var(--v-theme-warning));
}
.arow.later .tone {
  color: rgb(var(--v-theme-secondary));
}
.txt {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.msg {
  font-weight: 500;
  line-height: 20px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
}
.meta {
  font-size: 12px;
  line-height: 16px;
  color: rgb(var(--v-theme-secondary));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta .v-icon {
  vertical-align: -2px;
}
/* A save lands: the row washes in Action Blue and settles. */
.arow.fresh {
  animation: arow-landed 1100ms var(--ease-out);
}
@keyframes arow-landed {
  from {
    background: rgba(var(--v-theme-primary), 0.32);
  }
}
.skel-rows {
  padding: var(--sp-2) var(--sp-4);
}
.skel-row {
  height: 40px;
  margin: 12px 0;
  border-radius: 4px;
}
.empty {
  padding: var(--sp-8) var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  max-width: 52ch;
}
.empty p {
  margin: 0;
}
.arow-enter-active {
  transition:
    opacity 220ms var(--ease-out),
    transform 220ms var(--ease-out);
  transition-delay: calc(var(--i, 0) * 24ms);
}
.arow-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.arow-leave-active {
  position: absolute;
  transition: opacity 140ms ease-in;
}
.arow-leave-to {
  opacity: 0;
}
.arow-move {
  transition: transform 280ms var(--ease-out);
}
@media (max-width: 599.98px) {
  .anns {
    padding: var(--sp-3) var(--sp-4) var(--sp-6);
  }
  .search {
    max-width: none;
  }
  .strip .spacer {
    display: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .arow-enter-active {
    transition: opacity 160ms ease;
    transition-delay: 0ms;
  }
  .arow-enter-from {
    transform: none;
  }
  .arow-move {
    transition: none;
  }
  .arow.fresh {
    animation-duration: 600ms;
  }
}
</style>
