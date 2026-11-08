<script setup lang="ts">
/**
 * S-01 home, same structure as the legacy SHOP Home: (1) full-width hero carousel, one slide per category,
 * each with a title, a message and a button into the catalogue; (2) logo band on the gear line-art with
 * "The Instrumentation and Equipment Spares" and the Online Stores sign-in card; (3) "Radar Spares" and
 * (4) "Met-service Spares": text and a sliding row of products. No prices (v2 rule).
 */
import { call, catalog, type Product, useSession, useThemeMode } from '@cimh/web-app'
import logoColour from '@cimh/web-app/assets/cimh-logo-blue.webp'
import logoWhite from '@cimh/web-app/assets/cimh-logo-white.webp'
import awsSmall from '@cimh/web-app/assets/legacy/hero-aws-800.webp'
import aws from '@cimh/web-app/assets/legacy/hero-aws.webp'
import radarSmall from '@cimh/web-app/assets/legacy/hero-radar-960.webp'
import radar from '@cimh/web-app/assets/legacy/hero-radar.webp'
import { mdiAccountPlusOutline, mdiArrowRight } from '@mdi/js'
import { computed, onMounted, ref } from 'vue'
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
    title: 'Discover the latest radar equipment',
    message:
      'Explore our comprehensive range of radar spare parts designed to ensure optimal performance and reliability for your radar systems.',
    action: 'Explore radar spares',
    to: '/catalogue?type=RAD',
  },
  {
    src: aws,
    srcSmall: awsSmall,
    alt: 'Automatic weather stations in an open field at sunset',
    title: 'Browse our meteorological-service parts',
    message:
      'From temperature and humidity sensors to wind vanes and rain gauges, we offer a wide selection of spare parts for all your meteorological needs.',
    action: 'Explore met-service spares',
    to: '/catalogue?type=MET',
  },
]
const slide = ref(0)
const reduceMotion = typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
const paused = ref(false)

const sections = [
  {
    key: 'RAD',
    title: 'Radar Spares',
    text: 'From antennas and transmitters to receivers and signal processors, we offer high-quality components sourced from leading manufacturers in the industry. Whether you need to replace a faulty part or upgrade your radar system, our selection of radar spares has you covered.',
  },
  {
    key: 'MET',
    title: 'Met-service Spares',
    text: "Whether you're maintaining a weather station, a climate monitoring network or a specialised meteorological service, our range of spare parts has everything you need to keep your systems operating at peak performance, with the precision and durability accurate weather data needs.",
  },
] as const
const products = ref<Record<string, Product[] | null>>({ RAD: null, MET: null })
onMounted(async () => {
  for (const s of sections) {
    try {
      products.value[s.key] = (await call(() => catalog.GET('/products', { params: { query: { type: s.key, limit: 12 } } }))).items
    } catch {
      products.value[s.key] = []
    }
  }
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
      @mouseenter="paused = true"
      @mouseleave="paused = false"
      @focusin="paused = true"
      @focusout="paused = false"
    >
      <v-carousel
        v-model="slide"
        :cycle="!reduceMotion && !paused"
        interval="15000"
        :show-arrows="false"
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
        <div class="band-text">
          <p class="band-title">The Instrumentation and Equipment Spares</p>
          <v-card v-if="!session.isLoggedIn" class="signin" variant="flat" color="surface" elevation="2">
            <v-card-title class="t-h3">Online Stores</v-card-title>
            <v-card-text class="stack-sm">
              <p class="t-body muted">Log in or register to request items from the catalogue.</p>
              <div class="row">
                <v-btn to="/login" color="primary" variant="flat">Log in</v-btn>
                <v-btn to="/signup" variant="text" :prepend-icon="mdiAccountPlusOutline">Register</v-btn>
              </div>
            </v-card-text>
          </v-card>
          <p v-else-if="session.isCimh" class="t-body muted">
            Signed in with a CIMH account: you can browse, but CIMH staff can't submit requests.
          </p>
          <div v-else-if="session.isCustomer" class="row">
            <v-btn to="/catalogue" color="primary" variant="flat">Browse the catalogue</v-btn>
            <v-btn to="/requests" variant="outlined">My requests</v-btn>
          </div>
        </div>
      </div>
    </section>

    <!-- (3, 4) Category sections -->
    <section v-for="s in sections" :key="s.key" class="spares">
      <div class="spares-head">
        <h2 class="t-h1">{{ s.title }}</h2>
        <p class="t-body-lg muted spares-text">{{ s.text }}</p>
      </div>
      <v-slide-group v-if="products[s.key]?.length" show-arrows class="slider" :aria-label="s.title">
        <v-slide-group-item v-for="p in products[s.key]" :key="p.id">
          <div class="slot"><ProductCard :product="p" /></div>
        </v-slide-group-item>
      </v-slide-group>
      <div v-else-if="products[s.key] === null" class="skeletons">
        <v-skeleton-loader v-for="i in 4" :key="i" type="image, list-item-two-line" class="slot" />
      </div>
      <p v-else class="t-body muted empty">No {{ s.title.toLowerCase() }} in the catalogue yet.</p>
      <div class="more"><v-btn :to="`/catalogue?type=${s.key}`" variant="text" :append-icon="mdiArrowRight">View all {{ s.title.toLowerCase() }}</v-btn></div>
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
.band-text {
  display: flex;
  flex-direction: column;
  gap: var(--sp-6);
}
.band-title {
  font-size: clamp(28px, 3.4vw, 44px);
  font-weight: 600;
  letter-spacing: -0.015em;
  line-height: 1.15;
  margin: 0;
  opacity: 0.85;
}
.signin {
  max-width: 340px;
  text-align: left;
}
@media (max-width: 959px) {
  .signin {
    margin: 0 auto;
  }
  .band-text .row {
    justify-content: center;
  }
}

/* (3, 4) category sections */
.spares {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--sp-16, 64px) var(--sp-4) var(--sp-8);
}
.spares + .spares {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.spares-head {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-4);
  margin-bottom: var(--sp-8);
}
.spares-text {
  max-width: 70ch;
}
.slot {
  width: 220px;
  margin: 0 var(--sp-2) var(--sp-4);
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
.empty {
  text-align: center;
}
.more {
  display: flex;
  justify-content: center;
  margin-top: var(--sp-2);
}
</style>
