<script setup lang="ts">
/**
 * /inventory "Places" panel: sites → locations → shelves as a disclosure tree. Each place is a link that
 * opens it beside the tree (`?code=<barcode>`); the place that is open (or holds the open shelf / unit) is
 * marked and its branch kept expanded.
 */
import { mdiChevronRight, mdiPlus } from '@mdi/js'
import { computed, nextTick, ref, watch } from 'vue'
import { placeTo, usePlaces } from '../places'

/** current = the open code; where = the site / location that holds it (the page works it out). */
const props = defineProps<{ current?: string | null; where?: { site?: string | null; location?: string | null } | null }>()
const places = usePlaces()
const open = ref<Set<string>>(new Set())

const toggle = (code: string) => {
  const next = new Set(open.value)
  if (next.has(code)) next.delete(code)
  else next.add(code)
  open.value = next
}
const to = (code: string, site?: string) => placeTo(code, site)

// Keep the branch of whatever is open expanded.
const path = computed(() => [props.where?.site, props.where?.location].filter((x): x is string => !!x))
watch(
  path,
  (p) => {
    if (p.some((c) => !open.value.has(c))) open.value = new Set([...open.value, ...p])
  },
  { immediate: true },
)
// One site: open it straight away.
watch(
  () => places.sites.value,
  (s) => {
    if (s.length === 1 && !open.value.size) open.value = new Set([s[0]!.barcode])
  },
  { immediate: true },
)
// An opened site loads its locations (once).
watch(
  open,
  (codes) => codes.forEach((c) => places.site(c) && void places.ensureSite(c).catch(() => {})),
  { immediate: true },
)
watch(() => places.sites.value, () => open.value.forEach((c) => places.site(c) && void places.ensureSite(c).catch(() => {})))
// Many sites: a filter by name (the open place's site always stays listed).
const filter = ref('')
const matching = computed(() => {
  const q = filter.value.trim().toLowerCase()
  if (!q) return places.sites.value
  return places.sites.value.filter((s) => s.name.toLowerCase().includes(q) || path.value.includes(s.barcode))
})
// Cap the list (critique 2026-11-14: ~200 dev sites made an 11,000 px page on phones). The open place's site
// always stays listed; the filter or "Show all" reaches the rest.
const CAP = 40
const showAll = ref(false)
const shown = computed(() => {
  if (showAll.value || matching.value.length <= CAP) return matching.value
  const head = matching.value.slice(0, CAP)
  const extra = matching.value.slice(CAP).filter((s) => path.value.includes(s.barcode))
  return [...head, ...extra]
})
const hidden = computed(() => matching.value.length - shown.value.length)
// Bring the open place into view once its branch has rendered, and move the place marker (one 2 px bar that
// glides from the previous place to the new one: the page's focal motion) onto it.
const root = ref<HTMLElement | null>(null)
const marker = ref<{ y: number; h: number; placed: boolean } | null>(null)
watch(
  () => [props.current, path.value.join(), open.value.size, filter.value, ...path.value.map((c) => !!places.locations[c])],
  () =>
    void nextTick(() => {
      const el = root.value?.querySelector<HTMLElement>('.here')
      const box = root.value
      if (!el || !box) {
        marker.value = null
        return
      }
      const place = () => {
        const r = el.getBoundingClientRect()
        const b = box.getBoundingClientRect()
        const was = marker.value
        marker.value = { y: r.top - b.top + box.scrollTop, h: r.height, placed: !!was }
      }
      const r = el.getBoundingClientRect()
      const b = box.getBoundingClientRect()
      // Scroll the tree's own box only: scrollIntoView would also move the window (on phones the tree sits
      // under the record, so the page jumped away from what was just opened).
      if (r.top < b.top || r.bottom > b.bottom) box.scrollTop += r.top - b.top - (b.height - r.height) / 2
      place()
    }),
  { immediate: true, flush: 'post' },
)
const isHere = (code: string) => props.current === code
const onPath = (code: string) => path.value.includes(code)
</script>

<template>
  <div v-if="places.sites.value.length > 8" class="filter">
    <v-text-field v-model="filter" label="Filter sites" density="compact" hide-details clearable />
  </div>
  <nav ref="root" class="tree" aria-label="Places">
    <span
      v-if="marker"
      class="marker"
      :class="{ placed: marker.placed }"
      aria-hidden="true"
      :style="{ transform: `translateY(${marker.y}px)`, height: `${marker.h}px` }"
    />
    <div v-if="places.state.value === 'loading' && !places.sites.value.length" class="pad">
      <div v-for="n in 4" :key="n" class="skel console-skel" />
    </div>
    <p v-else-if="places.state.value === 'error'" class="pad t-body">
      The places could not be loaded. <button type="button" class="console-retry" @click="places.load().catch(() => {})">Try again</button>
    </p>
    <p v-else-if="!places.sites.value.length" class="pad t-body muted">
      No sites yet. <router-link :to="{ path: '/inventory', query: { op: 'site' } }">Register the first site</router-link>.
    </p>

    <ul v-else class="lvl" role="list">
      <li v-for="s in shown" :key="s.barcode">
        <div class="node site" :class="{ here: isHere(s.barcode), path: onPath(s.barcode) }">
          <button
            type="button"
            class="twist"
            :class="{ on: open.has(s.barcode) }"
            :aria-expanded="open.has(s.barcode)"
            :aria-label="`${open.has(s.barcode) ? 'Collapse' : 'Expand'} ${s.name}`"
            @click="toggle(s.barcode)"
          >
            <v-icon :icon="mdiChevronRight" size="18" />
          </button>
          <router-link :to="to(s.barcode)" class="name" :aria-current="isHere(s.barcode) ? 'page' : undefined">{{ s.name }}</router-link>
          <span class="n console-mono" :title="`${places.locations[s.barcode]?.length ?? 0} locations`">{{ places.locations[s.barcode]?.length ?? '' }}</span>
        </div>

        <div v-if="open.has(s.barcode) && !places.locations[s.barcode]" class="pad-sm"><div class="skel console-skel" /></div>
        <Transition name="branch">
        <ul v-if="open.has(s.barcode) && places.locations[s.barcode]" class="lvl" role="list">
          <li v-for="l in places.locations[s.barcode] ?? []" :key="l.barcode">
            <div class="node loc" :class="{ here: isHere(l.barcode), path: onPath(l.barcode) }">
              <button
                type="button"
                class="twist"
                :class="{ on: open.has(l.barcode) }"
                :aria-expanded="open.has(l.barcode)"
                :aria-label="`${open.has(l.barcode) ? 'Collapse' : 'Expand'} ${l.name}`"
                :disabled="!l.shelves?.length"
                @click="toggle(l.barcode)"
              >
                <v-icon :icon="mdiChevronRight" size="18" />
              </button>
              <router-link :to="to(l.barcode, s.barcode)" class="name" :aria-current="isHere(l.barcode) ? 'page' : undefined">{{ l.name }}</router-link>
              <span class="n console-mono" :title="`${l.shelfCount ?? 0} shelves`">{{ l.shelfCount ?? 0 }}</span>
            </div>
            <Transition name="branch">
            <ul v-if="open.has(l.barcode) && l.shelves?.length" class="lvl shelves" role="list">
              <li v-for="sh in l.shelves" :key="sh.barcode">
                <router-link
                  :to="to(sh.barcode)"
                  class="node shelf"
                  :class="{ here: isHere(sh.barcode) || onPath(sh.barcode) }"
                  :aria-current="isHere(sh.barcode) ? 'page' : undefined"
                >
                  Shelf <span class="console-mono">{{ sh.number }}</span>
                </router-link>
              </li>
            </ul>
            </Transition>
            <router-link v-if="open.has(l.barcode)" :to="to(l.barcode, s.barcode)" class="node add shelf-add"><v-icon :icon="mdiPlus" size="16" />Add shelves</router-link>
          </li>
          <li>
            <router-link :to="to(s.barcode)" class="node add loc"><v-icon :icon="mdiPlus" size="16" />Add location</router-link>
          </li>
        </ul>
        </Transition>
      </li>
    </ul>
    <p v-if="filter && !shown.length" class="pad t-body muted">No site matches “{{ filter }}”.</p>
    <div v-if="hidden > 0" class="more">
      <span class="t-caption muted">{{ hidden }} more {{ hidden === 1 ? 'site' : 'sites' }}{{ filter ? '' : '. Filter by name, or' }}</span>
      <v-btn variant="text" size="small" class="m3" @click="showAll = true">Show all {{ matching.length }}</v-btn>
    </div>
  </nav>
</template>

<style scoped>
.more {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-4);
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.filter {
  padding: var(--sp-2) var(--sp-3);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.tree {
  position: relative;
  overflow: auto;
  min-height: 0;
  padding: var(--sp-1) 0 var(--sp-3);
}
.pad-sm {
  padding: var(--sp-1) var(--sp-4) 0 38px;
}
.pad {
  padding: var(--sp-4);
}
.skel {
  height: 20px;
  margin-bottom: var(--sp-3);
  border-radius: 4px;
}
.lvl {
  list-style: none;
  margin: 0;
  padding: 0;
}
.node {
  display: flex;
  align-items: center;
  gap: var(--sp-1);
  min-height: 36px;
  padding-right: var(--sp-4);
  color: rgb(var(--v-theme-on-surface));
  text-decoration: none;
  transition: background-color 120ms;
}
.node:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.node {
  font-size: 14px;
  line-height: 20px;
}
.site {
  padding-left: var(--sp-2);
  font-weight: 600;
}
.loc {
  padding-left: 28px;
  font-weight: 500;
}
.shelf-add {
  padding-left: 66px;
  min-height: 32px;
}
.shelf {
  padding-left: 66px;
  min-height: 32px;
  font-size: 13px;
}
.add {
  padding-left: 38px;
  gap: var(--sp-2);
  color: rgb(var(--v-theme-primary));
  font-size: 13px;
  font-weight: 500;
}
.here {
  background: rgb(var(--v-theme-primary-subtle));
  transition: background-color 200ms var(--ease-out);
}
.path:not(.here) > .name {
  color: rgb(var(--v-theme-on-surface));
}
.name {
  flex: 1;
  min-width: 0;
  padding: var(--sp-2) 0;
  color: inherit;
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.name:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.n {
  font-size: 12px;
  color: rgb(var(--v-theme-secondary));
}
.twist {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  flex: none;
  border: 0;
  border-radius: 4px;
  background: none;
  color: rgb(var(--v-theme-secondary));
  cursor: pointer;
}
.twist:disabled {
  visibility: hidden;
}
.twist .v-icon {
  transition: transform 200ms var(--ease-out);
}
.twist.on .v-icon {
  transform: rotate(90deg);
}
/* The place marker: one bar, moved with transform only. Placed without motion the first time. */
.marker {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 1;
  width: 2px;
  background: rgb(var(--v-theme-primary));
  pointer-events: none;
  animation: console-fade-in 160ms var(--ease-out);
}
.marker.placed {
  transition:
    transform 340ms var(--ease-out),
    height 200ms var(--ease-out);
}
/* Branches unfold: children slide down out of their parent row and fade in; fold faster. */
.branch-enter-active {
  transition:
    opacity 200ms var(--ease-out),
    transform 220ms var(--ease-out),
    clip-path 220ms var(--ease-out);
}
.branch-leave-active {
  transition:
    opacity 120ms ease-in,
    transform 120ms ease-in;
}
.branch-enter-from {
  opacity: 0;
  transform: translateY(-6px);
  clip-path: inset(0 0 100% 0);
}
.branch-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
@media (prefers-reduced-motion: reduce) {
  .marker.placed {
    transition: none;
  }
  .branch-enter-active,
  .branch-leave-active {
    transition: opacity 120ms;
  }
  .branch-enter-from,
  .branch-leave-to {
    transform: none;
    clip-path: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .twist .v-icon {
    transition: none;
  }
}
</style>
