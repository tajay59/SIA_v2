<script setup lang="ts">
/**
 * A-01 dashboard, Graphite Console (surface brief web/sia): a slim photo header line (greeting, date, updated
 * time), the request flow as one connected strip (counts per status, each opens the desk filtered), then two
 * panels: "Needs you now" (requests waiting on staff, longest wait first) and the selected request with its
 * next action, so staff act without leaving the queue. Colour marks state only: amber = verify, red = quote
 * about to expire. Counts come from the shared work counts (drawer too); the queue refreshes with them.
 */
import { call, orders, type RequestSummary, useSession } from '@cimh/web-app'
import { mdiAlertOutline, mdiArrowRight } from '@mdi/js'
import { computed, onMounted, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import radar from '@cimh/web-app/assets/legacy/hero-radar.webp'
import radarSm from '@cimh/web-app/assets/legacy/hero-radar-960.webp'
import RequestDetail from '../components/RequestDetail.vue'
import RequestQueue from '../components/RequestQueue.vue'
import { BTN, expiresSoon } from '../request-queue'
import { type CountKey, countLabel, REQUEST_STATUS, useWorkCounts } from '../work-counts'

definePage({ meta: { guard: 'staff', title: 'Dashboard', ownHeading: true } })

const session = useSession()
const { counts, updatedAt, loading, refresh } = useWorkCounts()

const flow: { key: CountKey; title: string; hint: string }[] = [
  { key: 'new', title: 'New', hint: 'Submitted, not started' },
  { key: 'quoting', title: 'Quoting', hint: 'Quote being prepared' },
  { key: 'quoted', title: 'Quoted', hint: 'Waiting for the customer' },
  { key: 'signature', title: 'Awaiting signature', hint: 'Customer signs the agreement' },
  { key: 'verify', title: 'Agreements to verify', hint: 'Signed copy uploaded' },
  { key: 'fulfil', title: 'Pick & purchase', hint: 'Approved, picking or purchasing' },
]
const URGENT: CountKey[] = ['verify']

const greeting = computed(() => {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
})
const today = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })
const time = computed(() =>
  updatedAt.value ? updatedAt.value.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : '',
)

// "Needs you now": requests where staff act next. Quoted ones only when the quote expires within 3 days.
const QUEUE_STATUS = 'SUBMITTED,ACCEPTED,APPROVED,PICKING,PURCHASING,QUOTED'
const QUEUE_PAGE = 100
const queue = ref<RequestSummary[] | null>(null)
const queueMore = ref(false)
const queueFailed = ref(false)
const selectedId = ref<string | null>(null)
const selected = computed(() => queue.value?.find((r) => r.id === selectedId.value) ?? null)
// Phones get the first 10 (longest wait first) and a link to the desk: 100 rows made a 4,000 px page.
const PHONE_ROWS = 10
const display = useDisplay()
const shownQueue = computed(() => (queue.value && display.width.value < 600 ? queue.value.slice(0, PHONE_ROWS) : queue.value))
const queueCut = computed(() => !!queue.value && !!shownQueue.value && (shownQueue.value.length < queue.value.length || queueMore.value))
const caption = computed(() =>
  queue.value ? `${queue.value.length}${queueMore.value ? '+' : ''} · longest wait first · quotes 3 days before expiry` : '',
)

async function loadQueue() {
  queueFailed.value = false
  try {
    const res = (await call(() =>
      orders.GET('/requests', {
        params: { query: { scope: 'all', status: QUEUE_STATUS, sort: 'waiting', limit: QUEUE_PAGE } as never },
      }),
    )) as { items: RequestSummary[]; nextCursor: string | null }
    queue.value = res.items.filter((r) => r.status !== 'QUOTED' || expiresSoon(r))
    queueMore.value = !!res.nextCursor
    // Keep the selection across refreshes; fall back to the first row when it has left the queue.
    if (!selected.value) selectedId.value = queue.value[0]?.id ?? null
  } catch {
    queueFailed.value = true
  }
}
function refreshAll() {
  void refresh()
  void loadQueue()
}
onMounted(loadQueue)
// The shell refreshes the counts every 2 minutes; the queue follows so the two never disagree.
watch(updatedAt, (_now, before) => {
  if (before && !loading.value) void loadQueue()
})
</script>

<template>
  <div class="dash">
    <header class="banner">
      <img :src="radar" :srcset="`${radarSm} 960w, ${radar} 1920w`" sizes="100vw" alt="" class="banner-img" />
      <div class="banner-text">
        <h1 class="greet">{{ greeting }}, {{ session.account?.firstname }}</h1>
        <p class="banner-date">{{ today }}</p>
      </div>
      <div class="updated">
        <span v-if="time" class="t-caption">Updated {{ time }}</span>
        <v-btn
          variant="text"
          size="small"
          :icon="BTN.retry"
          :loading="loading"
          aria-label="Refresh counts and queue"
          @click="refreshAll"
        />
      </div>
    </header>

    <div class="floor" aria-label="Floor work">
      <v-btn to="/pick" variant="outlined" class="m3" :prepend-icon="BTN.pick">Pick</v-btn>
      <v-btn to="/pick?op=stow" variant="outlined" class="m3" :prepend-icon="BTN.stow">Stow</v-btn>
      <v-btn to="/inventory?op=lookup" variant="outlined" class="m3" :prepend-icon="BTN.scan">Scan</v-btn>
    </div>

    <nav class="flow" aria-label="Requests by status">
      <template v-for="s in flow" :key="s.key">
        <div v-if="counts[s.key].failed" class="stage failed">
          <span class="stage-title">{{ s.title }}</span>
          <span class="stage-n tnum">{{ countLabel(counts[s.key]) }}</span>
          <span class="stage-hint">
            Couldn't load ·
            <button type="button" class="console-retry" @click="refresh(s.key)">Retry</button>
          </span>
        </div>
        <router-link
          v-else
          :to="{ path: '/requests', query: { status: REQUEST_STATUS[s.key] } }"
          class="stage"
          :class="{ urgent: URGENT.includes(s.key) && (counts[s.key].n ?? 0) > 0, zero: counts[s.key].n === 0 }"
        >
          <span class="stage-title">{{ s.title }}</span>
          <span class="stage-n tnum"><span :key="countLabel(counts[s.key])" class="console-roll">{{ countLabel(counts[s.key]) }}</span></span>
          <span class="stage-hint">{{ s.hint }}</span>
        </router-link>
      </template>
    </nav>

    <div class="also t-label">
      <router-link to="/reports/stock" class="also-item" :class="{ attention: (counts.low.n ?? 0) > 0 }">
        <v-icon v-if="(counts.low.n ?? 0) > 0" :icon="mdiAlertOutline" size="16" color="warning" />
        <span class="tnum">{{ countLabel(counts.low) }}</span> products low on stock
        <span v-if="(counts.low.n ?? 0) > 0" class="also-go">Restock board <v-icon :icon="mdiArrowRight" size="14" /></span>
      </router-link>
      <router-link v-if="session.isAdmin" to="/admin/approvals" class="also-item" :class="{ attention: (counts.approvals.n ?? 0) > 0 }">
        <span class="tnum">{{ countLabel(counts.approvals) }}</span> accounts waiting for approval
      </router-link>
    </div>

    <div class="console-panels">
      <RequestQueue
        v-model:selected="selectedId"
        :items="shownQueue"
        :failed="queueFailed"
        title="Needs you now"
        label="Requests that need staff"
        :caption="caption"
        empty-title="Nothing is waiting on staff."
        empty-text="New requests, agreements to verify and quotes within 3 days of expiry appear here."
        @retry="loadQueue"
      >
        <template v-if="queueCut && display.width.value < 600" #foot>
          <router-link to="/requests" class="all-link t-label">All {{ queue!.length }}{{ queueMore ? '+' : '' }} on the Requests desk</router-link>
        </template>
      </RequestQueue>
      <RequestDetail :summary="selected" @changed="refreshAll" />
    </div>
  </div>
</template>

<style scoped>
.all-link {
  display: block;
  padding: var(--sp-3) var(--sp-4);
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.dash {
  padding: var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
/* Everything under the banner: at most 1500 px wide, centred (owner, 2026-11-11). */
.dash > :not(.banner) {
  width: 100%;
  max-width: 1500px;
  margin-inline: auto;
}
/* Photo header line (owner keeps the radar photo): one 96 px band, greeting + date on the left,
   updated time on the right; a left-to-right scrim keeps white text readable. Phones drop the photo. */
.banner {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-4);
  height: 96px;
  margin: calc(-1 * var(--sp-6)) calc(-1 * var(--sp-6)) 0;
  padding: 0 var(--sp-6);
  overflow: hidden;
  color: #fff;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.banner-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 55%;
}
.banner::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, rgba(10, 12, 15, 0.86) 0%, rgba(10, 12, 15, 0.55) 55%, rgba(10, 12, 15, 0.7) 100%);
}
.banner-text,
.updated {
  position: relative;
  z-index: 1;
}
.greet {
  margin: 0;
  font-size: 22px;
  line-height: 28px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.banner-date {
  margin: 0;
  font-size: 13px;
  line-height: 18px;
  color: rgba(255, 255, 255, 0.86);
}
.updated {
  display: flex;
  align-items: center;
  gap: var(--sp-1);
  color: rgba(255, 255, 255, 0.86);
}
.updated .v-btn {
  color: #fff;
}
.floor {
  display: none;
  gap: var(--sp-2);
}
.floor .v-btn {
  flex: 1;
}

/* Request flow: one connected strip of neutral cells cut by seams; only "verify" with work turns amber.
   A changed count rolls up into its cell (console-roll). */
.flow {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
  overflow: hidden;
}
.stage {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--sp-3) var(--sp-4);
  color: inherit;
  text-decoration: none;
  transition: background-color 120ms ease-out;
}
.stage + .stage {
  border-left: 1px solid rgb(var(--v-theme-seam));
}
a.stage:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.stage-title {
  font-size: 11px;
  line-height: 16px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgb(var(--v-theme-secondary));
}
.stage-n {
  display: block;
  overflow: hidden;
  font: 500 28px/32px 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
  margin: 2px 0;
}
.stage.zero .stage-n {
  color: rgb(var(--v-theme-secondary));
}
.stage.urgent {
  box-shadow: inset 0 2px 0 rgb(var(--v-theme-warning));
}
.stage.urgent .stage-n,
.stage.urgent .stage-title {
  color: rgb(var(--v-theme-warning));
}
.stage-hint {
  font-size: 12px;
  line-height: 16px;
  color: rgb(var(--v-theme-secondary));
}
.also {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-6);
}
.also-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: rgb(var(--v-theme-on-surface));
  text-decoration: none;
}
.also-item .tnum {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-weight: 600;
}
.also-item:hover {
  color: rgb(var(--v-theme-primary));
}
/* Work waiting outside the request flow: a cell on the console seams with an amber edge and a way in, so it is
   not lost as a line of small text next to the counters (critique 2026-11-15). Quiet when the count is 0. */
.also-item.attention {
  padding: 6px var(--sp-3);
  border: 1px solid rgb(var(--v-theme-warning));
  border-radius: 4px;
  background: rgba(var(--v-theme-warning), 0.1);
}
.also-go {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-left: var(--sp-2);
  color: rgb(var(--v-theme-primary));
}

/* Wide screens: the page fits the window; only the queue and the detail panel scroll (owner, 2026-11-11). */
@media (min-width: 1280px) {
  .dash {
    height: 100dvh;
    overflow: hidden;
  }
  .dash > :not(.console-panels) {
    flex-shrink: 0;
  }
}
@media (max-width: 1279.98px) {
  .flow {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .stage:nth-child(4) {
    border-left: 0;
  }
  .stage:nth-child(n + 4) {
    border-top: 1px solid rgb(var(--v-theme-seam));
  }
}
@media (max-width: 599.98px) {
  .dash {
    padding: var(--sp-4);
  }
  /* Phones: no photo; a plain header line so floor work sits at the top. */
  .banner {
    height: auto;
    margin: 0;
    padding: 0;
    color: inherit;
    border-bottom: 0;
  }
  .banner-img,
  .banner::after {
    display: none;
  }
  .banner-date,
  .updated,
  .updated .v-btn {
    color: rgb(var(--v-theme-secondary));
  }
  .greet {
    font-size: 18px;
    line-height: 24px;
  }
  .floor {
    display: flex;
  }
  .flow {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .stage:nth-child(n) {
    border-left: 0;
    border-top: 1px solid rgb(var(--v-theme-seam));
  }
  .stage:nth-child(2n) {
    border-left: 1px solid rgb(var(--v-theme-seam));
  }
  .stage:nth-child(-n + 2) {
    border-top: 0;
  }
  .stage-n {
    font-size: 24px;
    line-height: 28px;
  }
}
</style>
