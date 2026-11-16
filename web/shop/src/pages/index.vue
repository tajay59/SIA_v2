<script setup lang="ts">
/**
 * S-01 home: (1) full-width hero carousel (the only large headline), one slide per category with a button
 * into the catalogue; (2) logo band on the gear line-art with the next step for this visitor (log in /
 * register, or catalogue / requests); (3) "How requesting works": approval → request → quote → signed
 * agreement, plus the Pro Bono entry; (4) "Radar spares" and "Met-service spares": a sliding row of
 * products each, with Retry when the row can't be loaded. No prices (v2 rule).
 */
import { call, catalog, type Product, useSession, useThemeMode } from '@cimh/web-app'
import logoColour from '@cimh/web-app/assets/cimh-logo-blue.webp'
import logoWhite from '@cimh/web-app/assets/cimh-logo-white.webp'
import awsSmall from '@cimh/web-app/assets/legacy/hero-aws-800.webp'
import aws from '@cimh/web-app/assets/legacy/hero-aws.webp'
import radarSmall from '@cimh/web-app/assets/legacy/hero-radar-960.webp'
import radar from '@cimh/web-app/assets/legacy/hero-radar.webp'
import { mdiAccountPlusOutline, mdiArrowRight, mdiRefresh } from '@mdi/js'
import { computed, onMounted, ref } from 'vue'
import HowRequestingWorks from '../components/HowRequestingWorks.vue'
import ProductCard from '../components/ProductCard.vue'

definePage({ meta: { guard: 'public', title: 'Home' } })
const session = useSession()
const { dark } = useThemeMode()

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

const sections = [
  {
    key: 'RAD',
    title: 'Radar spares',
    text: 'Antennas, transmitters, receivers and signal processors for weather radars.',
  },
  {
    key: 'MET',
    title: 'Met-service spares',
    text: 'Sensors, wind vanes, rain gauges and other parts for weather stations and climate networks.',
  },
] as const
type Key = (typeof sections)[number]['key']
// null = loading; 'failed' is not "empty": the row offers Retry instead of claiming the catalogue has nothing.
const products = ref<Record<Key, Product[] | null | 'failed'>>({ RAD: null, MET: null })
async function loadRow(key: Key) {
  products.value[key] = null
  try {
    products.value[key] = (await call(() => catalog.GET('/products', { params: { query: { type: key, limit: 12 } } }))).items
  } catch {
    products.value[key] = 'failed'
  }
}
const row = (key: Key) => (Array.isArray(products.value[key]) ? (products.value[key] as Product[]) : [])
onMounted(async () => {
  for (const s of sections) await loadRow(s.key)
})
const logo = computed(() => (dark.value ? logoWhite : logoColour))
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

    <!-- (2) Logo band -->
    <section class="band">
      <div class="band-inner">
        <img :src="logo" alt="Caribbean Institute for Meteorology and Hydrology" class="band-logo" width="220" height="68" />
        <v-card class="next" variant="flat" color="surface" elevation="2">
          <v-card-text class="stack-sm">
            <template v-if="!session.isLoggedIn">
              <h2 class="t-h3">Request items</h2>
              <p class="t-body muted">Log in or register to send a request. A CIMH administrator approves new accounts.</p>
              <div class="row">
                <v-btn to="/login" color="primary" variant="flat">Log in</v-btn>
                <v-btn to="/signup" variant="text" :prepend-icon="mdiAccountPlusOutline">Register</v-btn>
              </div>
            </template>
            <template v-else-if="session.isCimh">
              <h2 class="t-h3">Signed in with a CIMH account</h2>
              <p class="t-body muted">You can browse the catalogue. CIMH staff accounts can't send requests.</p>
              <div class="row"><v-btn to="/catalogue" color="primary" variant="flat">Browse the catalogue</v-btn></div>
            </template>
            <template v-else>
              <h2 class="t-h3">Welcome back, {{ session.account?.firstname }}</h2>
              <p class="t-body muted">Quotes and agreements that wait for you are at the top of My requests.</p>
              <div class="row">
                <v-btn to="/requests" color="primary" variant="flat">My requests</v-btn>
                <v-btn to="/catalogue" variant="text">Browse the catalogue</v-btn>
              </div>
            </template>
          </v-card-text>
        </v-card>
      </div>
    </section>

    <!-- (3) How requesting works -->
    <section class="how" aria-labelledby="how-title">
      <div class="how-head">
        <h2 id="how-title" class="t-h1">How requesting works</h2>
        <p class="t-body-lg muted how-intro">
          CIMH Stores is the institute's own store for the region's weather and water services. You send a request; CIMH answers with a quote.
        </p>
      </div>
      <HowRequestingWorks />
      <p class="t-body-lg probono-line">
        <span class="probono-badge">Pro Bono</span>
        Some items are free through CIMH projects. Staff review those requests; there is no quote to accept.
        <router-link to="/pro-bono">See Pro Bono items</router-link>
      </p>
    </section>

    <!-- (4) Category sections -->
    <section v-for="s in sections" :key="s.key" class="spares">
      <div class="spares-head">
        <div>
          <h2 class="t-h2">{{ s.title }}</h2>
          <p class="t-body-lg muted">{{ s.text }}</p>
        </div>
        <v-btn :to="`/catalogue?type=${s.key}`" variant="text" :append-icon="mdiArrowRight">View all {{ s.title.toLowerCase() }}</v-btn>
      </div>
      <template v-if="row(s.key).length">
        <v-slide-group show-arrows class="slider hide-xs" :aria-label="s.title">
          <v-slide-group-item v-for="p in row(s.key)" :key="p.id">
            <div class="slot"><ProductCard :product="p" /></div>
          </v-slide-group-item>
        </v-slide-group>
        <!-- Phones: a slider showed one card and a sliver; four whole cards in two columns, then "View all". -->
        <ul class="phone-grid show-xs" :aria-label="s.title">
          <li v-for="p in row(s.key).slice(0, 4)" :key="p.id"><ProductCard :product="p" /></li>
        </ul>
      </template>
      <div v-else-if="products[s.key] === null" class="skeletons">
        <v-skeleton-loader v-for="i in 4" :key="i" type="image, list-item-two-line" class="slot" />
      </div>
      <div v-else-if="products[s.key] === 'failed'" class="row-state" role="alert">
        <p class="t-body">Couldn't load {{ s.title.toLowerCase() }}. Check your connection and try again.</p>
        <v-btn variant="outlined" :prepend-icon="mdiRefresh" @click="loadRow(s.key)">Retry</v-btn>
      </div>
      <p v-else class="t-body muted row-state">No {{ s.title.toLowerCase() }} in the catalogue yet.</p>
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

/* (2) logo band */
.band {
  background-color: rgb(var(--v-theme-surface));
  background-image: url('@cimh/web-app/assets/legacy/gears.webp');
  background-size: cover;
  background-position: center bottom;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.v-theme--cimhDark .band {
  background-blend-mode: multiply;
}
.band-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--sp-12, 48px) var(--sp-6);
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--sp-12, 48px);
  align-items: center;
}
@media (max-width: 959px) {
  .band-inner {
    grid-template-columns: 1fr;
    justify-items: center;
    text-align: center;
  }
}
.band-logo {
  width: 220px;
  height: auto;
}
.next {
  max-width: 400px;
  text-align: left;
  justify-self: end;
}
@media (max-width: 959px) {
  .next {
    justify-self: center;
  }
}

/* (3) how requesting works */
.how {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--sp-16, 64px) var(--sp-4) var(--sp-12, 48px);
}
.how-head {
  margin-bottom: var(--sp-8);
}
.how-intro {
  max-width: 68ch;
  margin: var(--sp-2) 0 0;
}
.probono-line {
  margin: var(--sp-8) 0 0;
  max-width: 78ch;
}
.probono-line .probono-badge {
  margin-right: var(--sp-2);
  vertical-align: 1px;
}

/* (4) category sections */
.spares {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--sp-10, 40px) var(--sp-4) var(--sp-4);
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.spares-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: var(--sp-2) var(--sp-6);
  margin-bottom: var(--sp-6);
}
.spares-head p {
  margin: var(--sp-1) 0 0;
  max-width: 68ch;
}
.row-state {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-3);
  padding: var(--sp-6) 0;
}
.row-state p {
  margin: 0;
}
.slot {
  width: 220px;
  margin: 0 var(--sp-2) var(--sp-4);
}
/* The row's last whole card ends in a fade, so a cut tile reads as "more this way", not as broken. */
.slider :deep(.v-slide-group__container) {
  mask-image: linear-gradient(to right, #000 calc(100% - 48px), transparent);
}
.phone-grid {
  list-style: none;
  margin: 0 0 var(--sp-4);
  padding: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sp-3);
}
@media (max-width: 599.98px) {
  .slot {
    width: 160px;
  }
}
.skeletons {
  display: flex;
  gap: var(--sp-4);
  overflow: hidden;
}
</style>
