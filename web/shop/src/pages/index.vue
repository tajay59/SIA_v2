<script setup lang="ts">
/**
 * S-01 home: (1) full-width hero carousel (the only large headline), one slide per category with a button
 * into the catalogue; (2) institute masthead on the gear line-art: CIMH crest, one line on what the store is,
 * the next step for this visitor (log in / register, or catalogue / requests); (3) equipment index: one photo
 * tile per equipment family that has items (radar leads, Pro Bono in yellow), each naming a few real items;
 * (4) "How requesting works" as four short steps with the Pro Bono branch beside them. No prices, no counts
 * (the API has none; PRODUCT.md: no invented figures). Surface brief: web/shop/.impeccable/surfaces/.
 */
import {
  call,
  catalog,
  imageSrcset,
  imageVariant,
  primaryImage,
  type Product,
  type ProductPhoto,
  type ProductType,
  useSession,
} from '@cimh/web-app'
import logoWhite from '@cimh/web-app/assets/cimh-logo-white.webp'
import awsSmall from '@cimh/web-app/assets/legacy/hero-aws-800.webp'
import aws from '@cimh/web-app/assets/legacy/hero-aws.webp'
import radarSmall from '@cimh/web-app/assets/legacy/hero-radar-960.webp'
import radar from '@cimh/web-app/assets/legacy/hero-radar.webp'
import { mdiAccountPlusOutline, mdiArrowRight, mdiPackageVariant, mdiRefresh } from '@mdi/js'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import HowRequestingWorks from '../components/HowRequestingWorks.vue'

definePage({ meta: { guard: 'public', title: 'Home' } })
const session = useSession()

// Owner's hero image (src/assets/hero/, DESIGN_BRIEF §7) leads the carousel when present.
const heroFiles = import.meta.glob<string>('../assets/hero/hero*.webp', { eager: true, import: 'default', query: '?url' })
const own = Object.entries(heroFiles).find(([k]) => k.endsWith('/hero.webp'))?.[1]
const ownSmall = Object.entries(heroFiles).find(([k]) => k.endsWith('/hero-480.webp'))?.[1]

interface Slide {
  src: string
  srcSmall?: string
  alt: string
  title: string
  message: string
  action: string
  to: string
}
const slides: Slide[] = [
  ...(own
    ? [
        {
          src: own,
          srcSmall: ownSmall,
          alt: 'The Earth seen from space at night',
          title: "Instruments and supplies for the region's weather and water services",
          message:
            'CIMH Stores supplies meteorological, radar and hydrological equipment to national services and partners across the Caribbean, from CIMH stock or trusted suppliers.',
          action: 'Browse the catalogue',
          to: '/catalogue',
        },
      ]
    : []),
  {
    src: radar,
    srcSmall: radarSmall,
    alt: 'A weather radar dish at dusk under a starry sky',
    title: 'Spares for weather radars',
    message: 'Antennas, transmitters, receivers and signal processors. Send a request and CIMH quotes it for you.',
    action: 'Browse radar spares',
    to: '/catalogue?type=RAD',
  },
  {
    src: aws,
    srcSmall: awsSmall,
    alt: 'Automatic weather stations in an open field at sunset',
    title: 'Parts for weather stations',
    message: 'Temperature and humidity sensors, wind vanes, rain gauges and more for station networks.',
    action: 'Browse met-service spares',
    to: '/catalogue?type=MET',
  },
]
// No auto-advance (critique 2026-11-14): slides 2–3 hid their actions behind a timer; people move with the arrows/dots.
const slide = ref(0)

// (3) Equipment index. Families with no items are left out once loaded; Pro Bono always shows (it is a way of requesting).
interface Family {
  key: string
  title: string
  to: string
  query: { type?: ProductType; probono?: boolean }
}
const FAMILIES: Family[] = [
  { key: 'RAD', title: 'Radar spares', to: '/catalogue?type=RAD', query: { type: 'RAD' } },
  { key: 'MET', title: 'Weather station parts', to: '/catalogue?type=MET', query: { type: 'MET' } },
]
// SHOP shows only MET and RAD (plus Pro Bono of any type; catalog-svc SHOP_TYPES, owner 2026-11-16).
// null = loading; 'failed' keeps the tile (its link still works) and offers Retry instead of claiming it is empty.
const loaded = ref<Record<string, Product[] | null | 'failed'>>({})
async function loadFamily(key: string, query: Family['query']) {
  loaded.value[key] = null
  try {
    loaded.value[key] = (await call(() => catalog.GET('/products', { params: { query: { ...query, limit: 8 } } }))).items
  } catch {
    loaded.value[key] = 'failed'
  }
}
function retry(key: string) {
  const f = FAMILIES.find((x) => x.key === key)
  void loadFamily(key, f ? f.query : { probono: true })
}
const items = (key: string) => (Array.isArray(loaded.value[key]) ? (loaded.value[key] as Product[]) : [])
const photos = (key: string): ProductPhoto[] =>
  items(key)
    .map((p) => primaryImage(p))
    .filter((x): x is ProductPhoto => !!x)
    .slice(0, 2)
const examples = (key: string) =>
  items(key)
    .map((p) => p.name)
    .slice(0, 3)
// Shown: loading or failed families, and loaded ones that have items.
const shown = computed(() => FAMILIES.filter((f) => loaded.value[f.key] !== undefined && (!Array.isArray(loaded.value[f.key]) || items(f.key).length)))
// Grid: the two families side by side as large tiles (one alone takes the row); Pro Bono closes the grid full width.
const proBonoSpan = computed(() => 'pb-full')
onMounted(() => {
  for (const f of FAMILIES) loaded.value[f.key] = null
  loaded.value.PROBONO = null
  void Promise.all([...FAMILIES.map((f) => loadFamily(f.key, f.query)), loadFamily('PROBONO', { probono: true })])
  armPath()
})
onBeforeUnmount(() => io?.disconnect())

// Focal motion: the request path draws itself once, node to node, when it first comes into view. The hidden
// start state is only applied here ('armed'), so without JS or with reduced motion the steps simply show.
const how = ref<HTMLElement | null>(null)
const path = ref<'idle' | 'armed' | 'drawn'>('idle')
let io: IntersectionObserver | undefined
function armPath() {
  const el = how.value
  if (!el || !('IntersectionObserver' in window)) return
  if (el.getBoundingClientRect().top < window.innerHeight * 0.8) return // already on screen: no replay
  path.value = 'armed'
  io = new IntersectionObserver(
    (entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        path.value = 'drawn'
        io?.disconnect()
      }
    },
    { threshold: 0.35 },
  )
  io.observe(el)
}
</script>

<template>
  <div class="home">
    <!-- (1) Hero carousel -->
    <section
      class="hero"
      aria-roledescription="carousel"
      aria-label="Featured"
    >
      <v-carousel
        v-model="slide"
        show-arrows="hover"
        hide-delimiter-background
        height="auto"
        class="carousel"
      >
        <v-carousel-item v-for="(s, i) in slides" :key="s.title" :value="i" eager>
          <div class="slide">
            <img
              class="slide-img"
              :src="s.src"
              :srcset="s.srcSmall ? `${s.srcSmall} 800w, ${s.src} 1600w` : undefined"
              sizes="100vw"
              :alt="s.alt"
              :loading="i === 0 ? 'eager' : 'lazy'"
              :fetchpriority="i === 0 ? 'high' : undefined"
            />
            <div class="slide-shade" />
            <div class="slide-text">
              <component :is="i === 0 ? 'h1' : 'h2'" class="slide-title">{{ s.title }}</component>
              <p class="slide-message">{{ s.message }}</p>
              <div>
                <v-btn :to="s.to" color="white" variant="flat" size="large" class="slide-btn" :append-icon="mdiArrowRight">{{ s.action }}</v-btn>
              </div>
            </div>
          </div>
        </v-carousel-item>
      </v-carousel>
    </section>

    <!-- (2) Institute masthead -->
    <section class="masthead" aria-labelledby="masthead-title">
      <div class="masthead-inner">
        <img :src="logoWhite" alt="Caribbean Institute for Meteorology and Hydrology" class="crest" width="260" height="80" />
        <div class="masthead-text">
          <template v-if="!session.isLoggedIn">
            <h2 id="masthead-title" class="masthead-title">The institute's own store for weather and water services</h2>
            <p class="masthead-line">Sign up to request items. A CIMH administrator approves new accounts.</p>
          </template>
          <template v-else-if="session.isCimh">
            <h2 id="masthead-title" class="masthead-title">Signed in with a CIMH account</h2>
            <p class="masthead-line">You can browse everything. CIMH staff accounts can't send requests.</p>
          </template>
          <template v-else>
            <h2 id="masthead-title" class="masthead-title">Welcome back, {{ session.account?.firstname }}</h2>
            <p class="masthead-line">Quotes and agreements that wait for you are at the top of Orders.</p>
          </template>
        </div>
        <div class="masthead-actions">
          <template v-if="!session.isLoggedIn">
            <v-btn to="/signup" color="white" variant="flat" size="large" class="on-field" :prepend-icon="mdiAccountPlusOutline">Sign up</v-btn>
            <v-btn to="/login" color="white" variant="outlined" size="large">Log in</v-btn>
          </template>
          <v-btn v-else-if="session.isCimh" to="/catalogue" color="white" variant="flat" size="large" class="on-field">Browse the catalogue</v-btn>
          <template v-else>
            <v-btn to="/requests" color="white" variant="flat" size="large" class="on-field">Orders</v-btn>
            <v-btn to="/catalogue" color="white" variant="outlined" size="large">Browse the catalogue</v-btn>
          </template>
        </div>
      </div>
    </section>

    <!-- (3) Equipment index -->
    <section class="index" aria-labelledby="index-title">
      <div class="index-head">
        <h2 id="index-title" class="t-h1">Find your equipment</h2>
        <router-link to="/catalogue" class="all-link">Whole catalogue <v-icon :icon="mdiArrowRight" size="18" /></router-link>
      </div>
      <ul class="tiles">
        <li v-for="(f, i) in shown" :key="f.key" class="tile-slot feature" :class="{ solo: shown.length === 1 }">
          <router-link :to="f.to" class="tile" :aria-label="examples(f.key).length ? `${f.title}: ${examples(f.key).join(', ')}` : f.title">
            <div class="tile-photo">
              <v-skeleton-loader v-if="loaded[f.key] === null" type="image" class="fill" />
              <template v-else-if="photos(f.key).length">
                <img
                  v-for="(ph, n) in photos(f.key)"
                  :key="ph.url"
                  :class="['ph', n === 0 ? 'ph-a' : 'ph-b']"
                  :src="imageVariant(ph.url, 800)"
                  :srcset="imageSrcset(ph.url)"
                  :sizes="'(max-width: 960px) 100vw, 600px'"
                  alt=""
                  loading="lazy"
                  decoding="async"
                />
              </template>
              <v-icon v-else :icon="mdiPackageVariant" size="32" class="no-photo" />
            </div>
            <div class="tile-text">
              <h3 class="tile-title">{{ f.title }} <v-icon :icon="mdiArrowRight" size="20" class="arrow" /></h3>
              <p v-if="examples(f.key).length" class="tile-examples">{{ examples(f.key).join(' · ') }}</p>
            </div>
          </router-link>
          <div v-if="loaded[f.key] === 'failed'" class="tile-failed" role="alert">
            <span>Couldn't load these items.</span>
            <v-btn size="small" variant="text" :prepend-icon="mdiRefresh" @click="retry(f.key)">Retry</v-btn>
          </div>
        </li>
        <li class="tile-slot probono" :class="proBonoSpan">
          <router-link to="/pro-bono" class="tile tile-pb">
            <div class="pb-text">
              <span class="probono-badge">Pro Bono</span>
              <h3 class="tile-title">Free items from CIMH projects <v-icon :icon="mdiArrowRight" size="20" class="arrow" /></h3>
              <p class="tile-examples">Staff review the request. There is no quote to accept.</p>
            </div>
            <div v-if="photos('PROBONO').length" class="pb-photo">
              <img :src="imageVariant(photos('PROBONO')[0].url, 320)" alt="" loading="lazy" decoding="async" />
            </div>
          </router-link>
        </li>
      </ul>
    </section>

    <!-- (4) How requesting works -->
    <section class="how" aria-labelledby="how-title">
      <!-- Signed in: they know the process; it folds to one line and opens on demand. -->
      <details ref="how" class="how-inner" :class="`path-${path}`" :open="!session.isLoggedIn">
        <summary class="how-summary">
          <h2 id="how-title" class="t-h1">How requesting works</h2>
          <span v-if="session.isLoggedIn" class="how-fold">Request → quote → signed agreement → delivery</span>
        </summary>
        <p class="how-intro">You send a request; CIMH answers with a quote.</p>
        <HowRequestingWorks variant="band" :skip-account="session.isLoggedIn" />
        <div class="branch">
          <span class="probono-badge">Pro Bono</span>
          <p>For free items, staff approve the request and CIMH ships. There is no quote or agreement.</p>
          <router-link to="/pro-bono" class="branch-link">See Pro Bono items <v-icon :icon="mdiArrowRight" size="18" /></router-link>
        </div>
      </details>
    </section>
  </div>
</template>

<style scoped>
/* (1) hero */
.hero {
  background: #0d1117;
}
.carousel :deep(.v-carousel__controls) {
  bottom: 12px;
}
.carousel :deep(.v-carousel__controls .v-btn) {
  color: #fff;
}
.slide {
  position: relative;
  height: clamp(440px, 62vh, 600px);
  overflow: hidden;
}
.slide-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.slide-shade {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, rgba(5, 10, 18, 0.82) 0%, rgba(5, 10, 18, 0.55) 45%, rgba(5, 10, 18, 0.05) 80%);
}
.slide-text {
  position: relative;
  max-width: 1200px;
  height: 100%;
  margin: 0 auto;
  padding: 0 var(--sp-6);
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: var(--sp-5, 20px);
  color: #fff;
}
.slide-title {
  font-size: clamp(32px, 4.4vw, 52px);
  line-height: 1.1;
  font-weight: 700;
  letter-spacing: -0.02em;
  max-width: 17ch;
  margin: 0;
}
.slide-message {
  font-size: 18px;
  line-height: 1.55;
  max-width: 52ch;
  margin: 0;
  color: rgba(255, 255, 255, 0.86);
}
.slide-btn {
  color: #0f1a24 !important;
  font-weight: 600;
}
@media (max-width: 599.98px) {
  .slide-message {
    display: none;
  }
  .slide-shade {
    background: linear-gradient(0deg, rgba(5, 10, 18, 0.85) 0%, rgba(5, 10, 18, 0.35) 70%);
  }
  .slide-text {
    justify-content: flex-end;
    padding-bottom: 56px;
  }
}

/* (2) masthead: the institute's own field. Deep CIMH navy in both themes (white text ≥ 12:1; logo blue #0084C8
   would fail AA for the 16 px line), the white crest, the legacy gear line-art inverted to faint light lines,
   and a logo-blue rule along the bottom. */
.masthead {
  --field: #0a2e4a;
  position: relative;
  isolation: isolate;
  background: var(--field);
  color: #fff;
  border-bottom: 4px solid #0084c8;
  overflow: hidden;
}
.masthead::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: -1;
  background: url('@cimh/web-app/assets/legacy/gears.webp') center bottom / cover no-repeat;
  filter: invert(1);
  mix-blend-mode: screen;
  opacity: 0.22;
}
.masthead-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--sp-12, 48px) var(--sp-6);
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: var(--sp-6) var(--sp-10, 40px);
  align-items: center;
}
.crest {
  width: 260px;
  height: auto;
  padding-right: var(--sp-10, 40px);
  border-right: 1px solid rgba(255, 255, 255, 0.24);
}
.masthead-title {
  font-size: clamp(24px, 2.6vw, 34px);
  line-height: 1.2;
  font-weight: 700;
  letter-spacing: -0.01em;
  margin: 0;
  text-wrap: balance;
}
.masthead-line {
  margin: var(--sp-2) 0 0;
  font-size: 17px;
  line-height: 26px;
  color: rgba(255, 255, 255, 0.84);
  max-width: 60ch;
}
.masthead-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-3);
}
/* White filled button on the navy field: ink label (brand: never white-on-white, never blue text on navy). */
.on-field {
  color: #0f1a24 !important;
  font-weight: 600;
}
.masthead :deep(.v-btn:focus-visible) {
  outline: 2px solid #fff;
  outline-offset: 2px;
}
@media (max-width: 959.98px) {
  .masthead-inner {
    grid-template-columns: 1fr;
    padding: var(--sp-8) var(--sp-4);
  }
  .crest {
    width: 200px;
    padding: 0 0 var(--sp-4);
    border-right: 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.24);
  }
}

/* (3) equipment index */
.index {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--sp-16, 64px) var(--sp-4) var(--sp-12, 48px);
}
.index-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  flex-wrap: wrap;
  gap: var(--sp-2) var(--sp-6);
  margin-bottom: var(--sp-6);
}
.all-link {
  white-space: nowrap;
  font-weight: 600;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: var(--sp-1);
  min-height: 24px;
}
.all-link:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.tiles {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  grid-auto-flow: row dense;
  gap: var(--sp-4);
}
.tile-slot {
  grid-column: span 3;
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.tile-slot.feature {
  grid-column: span 6;
}
.tile-slot.feature.solo {
  grid-column: span 12;
}
.probono.pb-half {
  grid-column: span 6;
}
.probono.pb-quarter {
  grid-column: span 3;
}
.probono.pb-full {
  grid-column: span 12;
}
.tile {
  flex: 1;
  display: flex;
  flex-direction: column;
  color: inherit;
  text-decoration: none;
  border-radius: 12px;
  overflow: hidden;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  transition: border-color 200ms cubic-bezier(0.16, 1, 0.3, 1), box-shadow 200ms cubic-bezier(0.16, 1, 0.3, 1);
}
.tile:hover,
.tile:focus-visible {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 6px 20px -8px rgba(15, 26, 36, 0.28);
}
.tile-photo {
  position: relative;
  aspect-ratio: 16 / 10;
  /* The photo sits on a white plate inset in the tile's own surface, so dark mode is not a wall of pale grey. */
  background: rgb(var(--v-theme-surface-variant));
  overflow: hidden;
  display: grid;
  place-items: center;
}
.feature .tile-photo {
  aspect-ratio: 16 / 9;
}
.fill {
  position: absolute;
  inset: 0;
}
.fill :deep(.v-skeleton-loader__image) {
  height: 100%;
}
.ph {
  position: absolute;
  inset: var(--sp-3);
  width: calc(100% - 2 * var(--sp-3));
  height: calc(100% - 2 * var(--sp-3));
  object-fit: contain;
  padding: var(--sp-3);
  background: #fff;
  border-radius: 8px;
  transition: opacity 400ms cubic-bezier(0.16, 1, 0.3, 1), transform 600ms cubic-bezier(0.16, 1, 0.3, 1);
}
.ph-b {
  opacity: 0;
}
/* Signature: the tile shows its family's second item on hover or focus. */
.tile:hover .ph-b,
.tile:focus-visible .ph-b {
  opacity: 1;
}
.tile:hover .ph-a:not(:only-child),
.tile:focus-visible .ph-a:not(:only-child) {
  opacity: 0;
}
.tile:hover .ph,
.tile:focus-visible .ph {
  transform: scale(1.03);
}
.no-photo {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.tile-text {
  padding: var(--sp-4);
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.tile-title {
  font-size: 18px;
  line-height: 26px;
  font-weight: 600;
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.feature .tile-title {
  font-size: 24px;
  line-height: 32px;
}
.arrow {
  color: rgb(var(--v-theme-primary));
  transition: transform 200ms cubic-bezier(0.16, 1, 0.3, 1);
}
.tile:hover .arrow,
.tile:focus-visible .arrow {
  transform: translateX(4px);
}
.tile-examples {
  margin: var(--sp-1) 0 0;
  font-size: 14px;
  line-height: 20px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.tile-failed {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-2);
  padding-top: var(--sp-2);
  font-size: 14px;
}
/* Pro Bono: the one yellow field on the page, ink text only (brand rule). */
.tile-pb {
  flex-direction: row;
  align-items: stretch;
  background: rgb(var(--v-theme-accent-probono));
  border-color: transparent;
  color: var(--probono-ink);
}
.tile-pb:hover,
.tile-pb:focus-visible {
  border-color: var(--probono-ink);
}
.tile-pb .arrow,
.tile-pb .tile-examples {
  color: var(--probono-ink);
}
.pb-text {
  flex: 1;
  padding: var(--sp-6);
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: var(--sp-2);
  align-items: flex-start;
}
.tile-pb .probono-badge {
  background: var(--probono-ink);
  color: rgb(var(--v-theme-accent-probono));
}
.pb-photo {
  width: 40%;
  max-width: 220px;
  background: #fff;
  display: grid;
  place-items: center;
}
.pb-photo img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  padding: var(--sp-3);
}
.pb-quarter .pb-photo {
  display: none;
}
@media (max-width: 959.98px) {
  .tile-slot,
  .probono.pb-quarter {
    grid-column: span 6;
  }
  .tile-slot.feature,
  .probono.pb-half,
  .probono.pb-full {
    grid-column: span 12;
    grid-row: auto;
  }
  .feature .tile-photo {
    aspect-ratio: 16 / 9;
    min-height: 0;
  }
}
/* Phones: the lead family stays a card; the others become one-column rows with a thumbnail, so names are not cut mid-word. */
@media (max-width: 599.98px) {
  .index-head {
    flex-wrap: nowrap;
  }
  .index-head .t-h1 {
    font-size: 24px;
    line-height: 30px;
  }
  .tile-slot:not(.feature),
  .probono.pb-quarter {
    grid-column: span 12;
  }
  .tile-slot:not(.feature):not(.probono) .tile {
    flex-direction: row;
  }
  .tile-slot:not(.feature):not(.probono) .tile-photo {
    width: 104px;
    flex: none;
    aspect-ratio: 1;
  }
  .tile-slot:not(.feature):not(.probono) .ph {
    inset: var(--sp-2);
    width: calc(100% - 2 * var(--sp-2));
    height: calc(100% - 2 * var(--sp-2));
    padding: var(--sp-1);
  }
  .tile-slot:not(.feature):not(.probono) .tile-text {
    border-top: 0;
    border-left: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
    align-self: center;
    min-width: 0;
  }
  .tile-text {
    padding: var(--sp-3);
  }
  .tile-title {
    font-size: 16px;
    line-height: 22px;
  }
  .pb-photo {
    display: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .ph,
  .arrow,
  .tile {
    transition: none;
  }
  .tile:hover .ph,
  .tile:focus-visible .ph {
    transform: none;
  }
}

/* (4) how requesting works */
.how {
  background: rgb(var(--v-theme-surface-variant));
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.how-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--sp-12, 48px) var(--sp-4) var(--sp-16, 64px);
}
.how-summary {
  list-style: none;
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: var(--sp-2) var(--sp-4);
}
.how-summary::-webkit-details-marker {
  display: none;
}
/* Open for visitors (a heading, no control); folded for signed-in customers, where the summary is the control. */
details:not([open]) .how-summary,
details[open] .how-summary:has(.how-fold) {
  cursor: pointer;
}
.how-fold {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
details:not([open]).how-inner {
  padding-bottom: var(--sp-12, 48px);
}
.how-intro {
  margin: var(--sp-2) 0 var(--sp-8);
  font-size: 17px;
  line-height: 26px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
/* The Pro Bono branch leaves the paid path after the request: a yellow node on a short rule. */
.branch {
  margin-top: var(--sp-8);
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-2) var(--sp-4);
  padding: var(--sp-4) var(--sp-6);
  border-radius: 12px;
  border: 2px dashed rgb(var(--v-theme-accent-probono));
}
.branch p {
  margin: 0;
  flex: 1 1 32ch;
}
.branch-link {
  font-weight: 600;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: var(--sp-1);
  min-height: 24px;
}
.branch-link:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

/* ── Motion ─────────────────────────────────────────────────────────────
   Focal: the request path draws node → rule → node (i × 240 ms), the Pro Bono branch lands last.
   Supporting: photos fade in when they replace the skeleton; tiles press on tap. */
.path-armed :deep(.step::before),
.path-armed :deep(.step-title),
.path-armed :deep(.step-text) {
  opacity: 0;
}
.path-armed :deep(.step::before) {
  transform: scale(0.4);
}
.path-armed :deep(.step-title),
.path-armed :deep(.step-text) {
  transform: translateY(6px);
}
.path-armed :deep(.step:not(:last-child)::after) {
  transform: scaleX(0);
}
.path-armed .branch {
  opacity: 0;
  transform: translateY(8px);
}
.path-drawn :deep(.step::before) {
  transition: transform 420ms cubic-bezier(0.16, 1, 0.3, 1), opacity 200ms ease-out;
}
.path-drawn :deep(.step-title),
.path-drawn :deep(.step-text) {
  transition: transform 500ms cubic-bezier(0.16, 1, 0.3, 1), opacity 400ms ease-out;
}
.path-drawn :deep(.step:not(:last-child)::after) {
  transform-origin: left center;
  transition: transform 300ms cubic-bezier(0.65, 0, 0.35, 1);
}
.path-drawn :deep(.step:nth-child(1)::before) { transition-delay: 0ms; }
.path-drawn :deep(.step:nth-child(1) .step-title), .path-drawn :deep(.step:nth-child(1) .step-text) { transition-delay: 80ms; }
.path-drawn :deep(.step:nth-child(1)::after) { transition-delay: 160ms; }
.path-drawn :deep(.step:nth-child(2)::before) { transition-delay: 400ms; }
.path-drawn :deep(.step:nth-child(2) .step-title), .path-drawn :deep(.step:nth-child(2) .step-text) { transition-delay: 480ms; }
.path-drawn :deep(.step:nth-child(2)::after) { transition-delay: 560ms; }
.path-drawn :deep(.step:nth-child(3)::before) { transition-delay: 800ms; }
.path-drawn :deep(.step:nth-child(3) .step-title), .path-drawn :deep(.step:nth-child(3) .step-text) { transition-delay: 880ms; }
.path-drawn :deep(.step:nth-child(3)::after) { transition-delay: 960ms; }
.path-drawn :deep(.step:nth-child(4)::before) { transition-delay: 1200ms; }
.path-drawn :deep(.step:nth-child(4) .step-title), .path-drawn :deep(.step:nth-child(4) .step-text) { transition-delay: 1280ms; }
.path-drawn .branch {
  transition: transform 500ms cubic-bezier(0.16, 1, 0.3, 1) 1450ms, opacity 400ms ease-out 1450ms;
}
/* Phones: the path runs down, so the rule grows downward. */
@media (max-width: 759.98px) {
  .path-armed :deep(.step:not(:last-child)::after) {
    transform: scaleY(0);
  }
  .path-drawn :deep(.step:not(:last-child)::after) {
    transform-origin: center top;
  }
}

/* Photos: arrive from the skeleton instead of popping in. */
.ph-a {
  animation: ph-in 450ms cubic-bezier(0.16, 1, 0.3, 1) backwards;
}
@keyframes ph-in {
  from {
    opacity: 0;
    transform: scale(1.03);
  }
}
/* Press feedback on every tile. */
.tile:active {
  transform: scale(0.985);
  transition-duration: 100ms;
}
.tile {
  transition-property: border-color, box-shadow, transform;
}

@media (prefers-reduced-motion: reduce) {
  /* Same order of arrival, no movement: nodes, text and branch only fade. */
  .path-armed :deep(.step::before),
  .path-armed :deep(.step-title),
  .path-armed :deep(.step-text),
  .path-armed .branch {
    transform: none;
  }
  .path-armed :deep(.step:not(:last-child)::after) {
    transform: none;
    opacity: 0;
  }
  .path-drawn :deep(.step:not(:last-child)::after) {
    transition: opacity 300ms ease-out;
  }
  .ph-a {
    animation-name: ph-fade;
  }
  .tile:active {
    transform: none;
  }
}
@keyframes ph-fade {
  from {
    opacity: 0;
  }
}
</style>
