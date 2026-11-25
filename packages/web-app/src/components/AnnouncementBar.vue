<script setup lang="ts">
/**
 * Announcement banner (plan 2026-11-23): the very top of every page in SHOP and SIA, above the app bar and the
 * drawer. A Vuetify layout item (`v-app-bar` with order −1 and its measured height), so nothing is covered: the
 * app bar, drawer and page move down by its height.
 * Up to 3 rows (alerts first), more behind "n more" (D6). Each row is an AnnouncementRow (icon + word + colour;
 * information closable in this browser until edited, alerts never). A message that arrives while the page is
 * open is read out by screen readers (polite for information, assertive for alerts); the ones already there at
 * load are not. `enabled` = false hides it and closes the feed (SIA: only signed-in staff, D2).
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { type Announcement, type AnnouncementApp, type AnnouncementFeed, useAnnouncementFeed } from '../announcements'
import AnnouncementRow from './AnnouncementRow.vue'

const props = withDefaults(defineProps<{ app: AnnouncementApp; enabled?: boolean }>(), { enabled: true })

const MAX_ROWS = 3
let feed: AnnouncementFeed | null = null
const items = ref<Announcement[]>([])
const politeText = ref('')
const alertText = ref('')
const expanded = ref(false)

let stops: (() => void)[] = []
let clearTimer: ReturnType<typeof setTimeout> | undefined
function startFeed() {
  const f = useAnnouncementFeed(props.app)
  feed = f
  stops = [
    watch(f.items, (v) => (items.value = v), { immediate: true }),
    watch(f.arrivals, (list) => {
      if (!list.length) return
      const live = new Set(f.items.value.map((a) => a.id))
      const fresh = list.filter((a) => live.has(a.id))
      const word = (a: Announcement) => `${a.tone === 'ALERT' ? 'Alert' : 'Information'}: ${a.message}`
      // Cleared first, so the same text set again is read again.
      politeText.value = ''
      alertText.value = ''
      void nextTick(() => {
        politeText.value = fresh.filter((a) => a.tone !== 'ALERT').map(word).join(' ')
        alertText.value = fresh.filter((a) => a.tone === 'ALERT').map(word).join(' ')
      })
      // Read once, then cleared: an ended message must not linger in the page's text.
      clearTimeout(clearTimer)
      clearTimer = setTimeout(() => ((politeText.value = ''), (alertText.value = '')), 7000)
      f.arrivals.value = []
    }),
  ]
}
function stopFeed() {
  stops.forEach((s) => s())
  stops = []
  feed?.stop()
  feed = null
  items.value = []
}
watch(
  () => props.enabled,
  (on) => (on ? startFeed() : stopFeed()),
  { immediate: true },
)
onBeforeUnmount(() => {
  stopFeed()
  clearTimeout(clearTimer)
})

const shown = computed(() => (expanded.value ? items.value : items.value.slice(0, MAX_ROWS)))
const more = computed(() => items.value.length - MAX_ROWS)
watch(more, (n) => n <= 0 && (expanded.value = false))

// The banner wraps, so its height is measured for the layout.
const { smAndDown } = useDisplay()
const inner = ref<HTMLElement | null>(null)
const height = ref(0)
let ro: ResizeObserver | undefined
watch(inner, (el) => {
  ro?.disconnect()
  if (!el) return
  ro = new ResizeObserver(() => (height.value = Math.ceil(el.getBoundingClientRect().height)))
  ro.observe(el)
})
onBeforeUnmount(() => ro?.disconnect())
</script>

<template>
  <div class="ann-live" aria-live="polite" role="status">{{ politeText }}</div>
  <div class="ann-live" aria-live="assertive" role="alert">{{ alertText }}</div>
  <v-app-bar
    v-if="items.length"
    :order="-1"
    :height="height || (smAndDown ? 48 : 40)"
    flat
    density="default"
    color="transparent"
    class="ann-bar"
    tag="section"
    aria-label="Announcements"
    data-testid="announcements"
  >
    <div ref="inner" class="ann-inner">
      <TransitionGroup name="ann" tag="ul" class="ann-list">
        <li v-for="a in shown" :key="a.id">
          <AnnouncementRow :announcement="a" @dismiss="feed?.dismiss(a)" />
        </li>
      </TransitionGroup>
      <button v-if="more > 0" type="button" class="ann-toggle" :aria-expanded="expanded" @click="expanded = !expanded">
        {{ expanded ? 'Show fewer' : `${more} more ${more === 1 ? 'announcement' : 'announcements'}` }}
      </button>
    </div>
  </v-app-bar>
</template>

<style scoped>
.ann-live {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.ann-bar {
  /* The bar is only the layout slot; the rows paint themselves. */
  box-shadow: none !important;
}
.ann-bar :deep(.v-toolbar__content) {
  height: auto !important;
  padding: 0;
  align-items: flex-start;
}
.ann-inner {
  width: 100%;
}
.ann-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.ann-toggle {
  display: block;
  width: 100%;
  min-height: 28px;
  padding: 4px var(--sp-4);
  border: 0;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgb(var(--v-theme-surface));
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}
.ann-toggle:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
/* Arrival slides down, leaving fades. */
.ann-enter-active {
  transition:
    opacity 180ms ease-out,
    transform 180ms cubic-bezier(0.16, 1, 0.3, 1);
}
.ann-leave-active {
  transition: opacity 140ms ease-in;
}
.ann-enter-from {
  opacity: 0;
  transform: translateY(-100%);
}
.ann-leave-to {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .ann-enter-active {
    transition: opacity 120ms ease-out;
  }
  .ann-enter-from {
    transform: none;
  }
}
</style>
