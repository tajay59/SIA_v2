<script setup lang="ts">
/**
 * S-01 home (DESIGN_BRIEF §10): short hero with one primary action and the hero photo on the right
 * (src/assets/hero/, §7; without it the hero is text only), featured MET/RAD products,
 * how requesting works, and the Pro Bono band.
 */
import { call, catalog, type Product, ProductImage, primaryImage, useSession } from '@cimh/web-app'
import { mdiArrowRight, mdiClipboardCheckOutline, mdiFileDocumentEditOutline, mdiGiftOutline, mdiTruckDeliveryOutline } from '@mdi/js'
import { onMounted, ref } from 'vue'
import ProductCard from '../components/ProductCard.vue'

definePage({ meta: { guard: 'public', title: 'Home' } })
const session = useSession()

// The hero image is optional at build time: hero.webp (+ a smaller hero-480.webp) in src/assets/hero/.
const heroFiles = import.meta.glob<string>('../assets/hero/hero*.webp', { eager: true, import: 'default', query: '?url' })
const heroMain = Object.entries(heroFiles).find(([k]) => k.endsWith('/hero.webp'))?.[1]
const heroSmall = Object.entries(heroFiles).find(([k]) => k.endsWith('/hero-480.webp'))?.[1]
const heroAlt = 'The Earth seen from space at night, with city lights across Europe, Africa and the Middle East'

const featured = ref<Product[] | null>(null)
const probono = ref<Product[]>([])

onMounted(async () => {
  try {
    const [met, rad, free] = await Promise.all([
      call(() => catalog.GET('/products', { params: { query: { type: 'MET', limit: 4 } } })),
      call(() => catalog.GET('/products', { params: { query: { type: 'RAD', limit: 4 } } })),
      call(() => catalog.GET('/products', { params: { query: { probono: true, limit: 3 } } })),
    ])
    // Alternate MET and RAD so both show, then fill up to four.
    const mix: Product[] = []
    for (let i = 0; i < 4; i++) for (const src of [met.items, rad.items]) if (src[i] && mix.length < 4) mix.push(src[i]!)
    featured.value = mix
    probono.value = free.items
  } catch {
    featured.value = []
  }
})

const steps = [
  { icon: mdiClipboardCheckOutline, title: 'Request', text: 'Choose instruments, spares or supplies and send one request. Prices are never shown up front.' },
  { icon: mdiFileDocumentEditOutline, title: 'Review the quote', text: 'CIMH quotes each line from its own stock or a supplier. You pick the options, then sign the agreement.' },
  { icon: mdiTruckDeliveryOutline, title: 'Receive', text: 'Follow your request through purchasing and shipping, with tracking, until it is delivered.' },
]
</script>

<template>
  <div>
    <section class="hero">
      <v-container max-width="1200" class="hero-inner" :class="{ split: heroMain }">
        <div class="hero-text">
          <p class="t-label eyebrow">Caribbean Institute for Meteorology and Hydrology</p>
          <h1 class="t-display">Instruments and supplies for the region's weather and water services</h1>
          <p class="t-body-lg muted prose">
            CIMH Stores supplies meteorological, radar and hydrological equipment to national services and partners
            across the Caribbean, from CIMH stock or trusted suppliers.
          </p>
          <div class="row">
            <v-btn to="/catalogue" color="primary" size="large">Browse catalogue</v-btn>
            <v-btn v-if="!session.isLoggedIn" to="/signup" variant="outlined" size="large">Create an account</v-btn>
            <v-btn v-else-if="session.isCustomer" to="/requests" variant="outlined" size="large">My requests</v-btn>
          </div>
        </div>
        <img
          v-if="heroMain"
          class="hero-img"
          :src="heroMain"
          :srcset="heroSmall ? `${heroSmall} 480w, ${heroMain} 832w` : undefined"
          sizes="(max-width: 960px) 100vw, 560px"
          width="832"
          height="624"
          :alt="heroAlt"
          fetchpriority="high"
        />
      </v-container>
    </section>

    <v-container max-width="1200" class="page stack-lg">
      <section v-if="featured === null || featured.length" class="stack">
        <div class="row">
          <h2 class="t-h2">Instruments in the catalogue</h2>
          <span class="spacer" />
          <v-btn to="/catalogue" variant="text" :append-icon="mdiArrowRight">View all</v-btn>
        </div>
        <div class="grid4">
          <template v-if="featured === null">
            <v-skeleton-loader v-for="i in 4" :key="i" type="image, list-item-two-line" />
          </template>
          <ProductCard v-for="p in featured ?? []" v-else :key="p.id" :product="p" />
        </div>
      </section>

      <section class="stack">
        <h2 class="t-h2">How requesting works</h2>
        <div class="steps">
          <v-card v-for="(s, i) in steps" :key="s.title" class="step">
            <div class="row">
              <v-icon :icon="s.icon" color="primary" size="28" />
              <span class="t-label muted">Step {{ i + 1 }}</span>
            </div>
            <h3 class="t-h3">{{ s.title }}</h3>
            <p class="t-body muted">{{ s.text }}</p>
          </v-card>
        </div>
        <p v-if="session.isCimh" class="t-body muted prose">
          You're signed in with a CIMH account: you can browse, but CIMH staff can't submit requests.
        </p>
      </section>

      <section v-if="probono.length" class="band">
        <div class="band-text stack-sm">
          <div class="row">
            <v-icon :icon="mdiGiftOutline" color="primary" />
            <h2 class="t-h2">Pro Bono items</h2>
          </div>
          <p class="t-body prose">CIMH projects supply some items free of charge. Request them like any other item.</p>
          <div><v-btn to="/pro-bono" color="primary" variant="flat">See Pro Bono items</v-btn></div>
        </div>
        <ul class="band-items">
          <li v-for="p in probono" :key="p.id">
            <router-link :to="`/catalogue/${p.id}`" class="mini">
              <ProductImage :image="primaryImage(p)" :alt="p.name" small sizes="72px" />
              <span class="t-body">{{ p.name }}</span>
            </router-link>
          </li>
        </ul>
      </section>
    </v-container>
  </div>
</template>

<style scoped>
.hero {
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgb(var(--v-theme-surface));
}
.hero-inner {
  padding: var(--sp-12, 48px) var(--sp-4);
  display: grid;
  gap: var(--sp-8);
  align-items: center;
}
.hero-inner.split {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
}
@media (max-width: 959px) {
  .hero-inner.split {
    grid-template-columns: minmax(0, 1fr);
  }
}
.hero-text {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.hero-text .t-display {
  max-width: 22ch;
}
.hero-img {
  width: 100%;
  height: auto;
  aspect-ratio: 4 / 3;
  object-fit: cover;
  border-radius: 12px;
}
.eyebrow {
  color: rgb(var(--v-theme-primary));
}
.stack-lg {
  display: flex;
  flex-direction: column;
  gap: var(--sp-12, 48px);
}
.grid4 {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--sp-4);
}
@media (max-width: 599.98px) {
  .grid4 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--sp-2);
  }
}
.steps {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: var(--sp-4);
}
.step {
  padding: var(--sp-5, 20px);
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.band {
  background: rgb(var(--v-theme-primary-subtle));
  border-radius: 12px;
  padding: var(--sp-6);
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--sp-6);
  align-items: center;
}
@media (max-width: 959px) {
  .band {
    grid-template-columns: minmax(0, 1fr);
  }
}
.band-items {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.mini {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: var(--sp-3);
  align-items: center;
  color: inherit;
  text-decoration: none;
}
.mini:hover span {
  text-decoration: underline;
}
</style>
