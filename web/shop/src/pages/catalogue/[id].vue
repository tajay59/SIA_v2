<script setup lang="ts">
/**
 * S-03 product (impeccable 2026-11-16, "Gallery band"; brief web/shop/.impeccable/surfaces/src-pages-catalogue-id-vue.md):
 * a full-width light band shows the part first (photo on a white plate, thumbnails along its foot; no photo = a large
 * nameplate), then one request bar names it (make, name, mono model number, badges) and takes the order (quantity +
 * Add to cart); the bar pins under the app bar once the band scrolls away. Description | Specifications below,
 * How requesting works folded last. v2 rules: no price and no serial numbers for customers.
 */
import {
  ApiError,
  call,
  catalog,
  imageSrcset,
  type ProductPhoto,
  type ProductPublic,
  ProductBadges,
  ProductImage,
  typeLabel,
  useCart,
  useNotify,
  useReference,
  useSession,
} from '@cimh/web-app'
import { mdiChevronDown, mdiChevronLeft, mdiChevronRight, mdiMinus, mdiPlus } from '@mdi/js'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useRoute, useRouter } from 'vue-router'
import HowRequestingWorks from '../../components/HowRequestingWorks.vue'

definePage({ meta: { guard: 'public', title: 'Product' } })
const route = useRoute('/catalogue/[id]')
const session = useSession()
const router = useRouter()
const { mdAndUp } = useDisplay()
const { reference } = useReference()
const product = ref<ProductPublic | null>(null)
const missing = ref(false)
const index = ref(0)
const qty = ref(1)
const cart = useCart()
const notify = useNotify()
const adding = ref(false)

// Focal moment (impeccable animate): the added parts travel from the button into the cart. A token (photo or
// make initial + "× n") flies along a short arc to whichever cart button is visible (header on desktop, bottom
// bar on phones); the cart button nudges as it lands. Reduced motion: no flight, the cart only flashes.
const addBtn = ref<{ $el: HTMLElement } | null>(null)
function flyToCart(count: number) {
  const from = addBtn.value?.$el?.getBoundingClientRect()
  const target = Array.from(document.querySelectorAll<HTMLElement>('[data-cart-target]')).find((el) => el.offsetParent !== null)
  if (!from || !target) return
  const to = target.getBoundingClientRect()
  const nudge = () =>
    target.animate(
      reduced()
        ? [{ filter: 'brightness(1)' }, { filter: 'brightness(1.6)' }, { filter: 'brightness(1)' }]
        : [{ transform: 'scale(1)' }, { transform: 'scale(1.18)' }, { transform: 'scale(1)' }],
      { duration: 320, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' },
    )
  if (reduced()) return void nudge()
  const token = document.createElement('div')
  token.className = 'cart-token'
  token.setAttribute('aria-hidden', 'true')
  const pic = shown.value?.url
  token.innerHTML = (pic ? `<img src="${pic}" alt="">` : `<b>${(product.value?.make ?? product.value?.name ?? '?').slice(0, 1)}</b>`) + `<span>× ${count}</span>`
  document.body.appendChild(token)
  const x0 = from.left + from.width / 2 - 28
  const y0 = from.top + from.height / 2 - 20
  const dx = to.left + to.width / 2 - 28 - x0
  const dy = to.top + to.height / 2 - 20 - y0
  const lift = Math.min(-80, dy * 0.4)
  token.style.left = `${x0}px`
  token.style.top = `${y0}px`
  const flight = token.animate(
    [
      { transform: 'translate(0, 0) scale(1)', opacity: 0 },
      { transform: `translate(${dx * 0.08}px, ${-12}px) scale(1.05)`, opacity: 1, offset: 0.12 },
      { transform: `translate(${dx * 0.55}px, ${dy * 0.55 + lift}px) scale(0.85)`, opacity: 1, offset: 0.55 },
      { transform: `translate(${dx}px, ${dy}px) scale(0.35)`, opacity: 0.2 },
    ],
    { duration: 640, easing: 'cubic-bezier(0.45, 0, 0.2, 1)' },
  )
  flight.onfinish = () => {
    token.remove()
    nudge()
  }
}
const reduced = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

// The quantity rolls in the direction it changes.
const qtyDir = ref<'up' | 'down'>('up')
watch(qty, (n, o) => (qtyDir.value = n >= o ? 'up' : 'down'))

async function addToRequest() {
  if (!product.value) return
  adding.value = true
  try {
    await cart.add(product.value.id, qty.value)
    flyToCart(qty.value)
    notify.toast(`Added ${qty.value} × ${product.value.name} to your cart`, 'success', {
      action: { label: 'View cart', run: () => void router.push('/cart') },
    })
  } catch (e) {
    notify.report(e)
  } finally {
    adding.value = false
  }
}

async function load(id: string) {
  product.value = null
  missing.value = false
  try {
    const p = (await call(() => catalog.GET('/products/{productId}', { params: { path: { productId: id } } }))) as ProductPublic
    product.value = p
    index.value = Math.max(0, p.images.findIndex((i) => i.primary))
    qty.value = 1
    document.title = `${p.name} · CIMH Stores`
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) missing.value = true
    else throw e
  }
}
watch(() => route.params.id, (id) => void load(id), { immediate: true })

const images = computed<ProductPhoto[]>(() => product.value?.images ?? [])
const shown = computed(() => images.value[index.value] ?? null)
const step = (d: number) => (index.value = (index.value + d + images.value.length) % images.value.length)
const max = computed(() => (product.value?.probono ? (product.value.probonoMaxPerRequest ?? 99) : 99))
const specs = computed(() => {
  const p = product.value
  if (!p) return []
  return [
    ['Make', p.make],
    ['Model', p.modelname],
    ['Model number', p.modelnumber],
    ['Type', typeLabel(reference.value, p.type)],
    ['Department', p.department],
    ['Project', p.project ? (reference.value?.projects.find((x) => x.code === p.project)?.name ?? p.project) : null],
    ['Weight', p.weight != null ? `${p.weight} kg` : null],
    ['Dimensions', p.dimension],
  ].filter(([, v]) => v !== null && v !== undefined && v !== '') as [string, string | number][]
})
const makeLine = computed(() => [product.value?.make, product.value?.modelname].filter(Boolean).join(' · '))
// The no-photo nameplate never repeats the heading: make + model where known; else the model number alone, else a quiet "No photo yet".
const plateTitle = computed(() => {
  const p = product.value
  if (!p) return ''
  const t = [p.make, p.modelname].filter(Boolean).join(' ')
  return t && t !== p.name ? t : ''
})
const typeName = computed(() => (product.value ? typeLabel(reference.value, product.value.type) : ''))

// The request bar pins once the 1 px sentinel above it scrolls under the app bar.
const sentinel = ref<HTMLElement | null>(null)
const pinned = ref(false)
let io: IntersectionObserver | null = null
watch(sentinel, (el) => {
  io?.disconnect()
  if (!el || typeof IntersectionObserver === 'undefined') return
  io = new IntersectionObserver(([e]) => (pinned.value = !!e && !e.isIntersecting && e.boundingClientRect.top < 100), { rootMargin: mdAndUp.value ? '-73px 0px 0px 0px' : '0px' })
  io.observe(el)
})
onBeforeUnmount(() => io?.disconnect())
const loginLink = computed(() => ({ path: '/login', query: { returnTo: route.fullPath } }))
</script>

<template>
  <v-container max-width="1200" class="page">
    <div v-if="missing" class="stack">
      <h1 class="t-h2">Product not found</h1>
      <p class="t-body muted">It may have been withdrawn from the catalogue.</p>
      <div><v-btn to="/catalogue" variant="outlined">Back to the catalogue</v-btn></div>
    </div>
    <!-- Loading: the page's own shape (crumb, a band as tall as the real one, the request bar), so nothing below
         moves when the product arrives (Lighthouse 2026-11-25: the footer showed under a short skeleton, then jumped
         off screen: layout shift 0.47 desktop / 0.53 phone). -->
    <div v-else-if="!product" class="product loading" aria-busy="true" aria-label="Loading the product">
      <v-skeleton-loader type="text" class="crumb-skel" />
      <div class="band skel-band" />
      <v-skeleton-loader type="heading, paragraph" class="bar-skel" />
    </div>
    <article v-else class="product">
      <nav class="crumb t-body" aria-label="Breadcrumb">
        <router-link to="/catalogue">Equipment and spares</router-link>
        <template v-if="typeName">
          <v-icon :icon="mdiChevronRight" size="16" class="crumb-sep" aria-hidden="true" />
          <router-link :to="{ path: '/catalogue', query: { type: product.type } }">{{ typeName }}</router-link>
        </template>
      </nav>

      <!-- The band: the part, shown first. -->
      <section class="band" :class="{ bare: !images.length }" aria-label="Photos">
        <template v-if="images.length">
          <div class="plate">
            <Transition name="swap" mode="out-in">
              <img
                v-if="shown"
                :key="shown.fileId"
                :src="shown.url"
                :srcset="imageSrcset(shown.url)"
                sizes="(max-width: 960px) 90vw, 640px"
                :alt="product.name"
                class="plate-img"
              />
            </Transition>
          </div>
          <template v-if="images.length > 1">
            <span class="counter tnum" aria-hidden="true"><Transition name="roll-up" mode="out-in"><span :key="index">{{ index + 1 }}</span></Transition> / {{ images.length }}</span>
            <v-btn class="nav prev" :icon="mdiChevronLeft" variant="flat" size="small" aria-label="Previous photo" @click="step(-1)" />
            <v-btn class="nav next" :icon="mdiChevronRight" variant="flat" size="small" aria-label="Next photo" @click="step(1)" />
            <ul class="thumbs" aria-label="All photos">
              <li v-for="(img, i) in images" :key="img.fileId">
                <button
                  type="button"
                  class="thumb"
                  :class="{ on: i === index }"
                  :aria-label="`Photo ${i + 1} of ${images.length}`"
                  :aria-pressed="i === index"
                  @click="index = i"
                >
                  <ProductImage :image="img" alt="" small sizes="64px" />
                </button>
              </li>
            </ul>
          </template>
        </template>
        <!-- No photo yet: the band carries the part's nameplate instead. -->
        <div v-else class="nameplate-big" aria-hidden="true">
          <span v-if="plateTitle" class="np-model">{{ plateTitle }}</span>
          <span v-else-if="!product.modelnumber" class="np-model quiet">No photo yet</span>
          <span v-if="product.modelnumber" class="np-num">{{ product.modelnumber }}</span>
          <span class="np-rule" />
          <span v-if="plateTitle || product.modelnumber" class="np-note">No photo of this item yet</span>
        </div>
      </section>

      <div ref="sentinel" class="sentinel" aria-hidden="true" />

      <!-- The request bar: names the part and takes the order; pins under the app bar once the band scrolls away. -->
      <section class="bar" :class="{ pinned }" aria-labelledby="product-name">
        <div class="ident">
          <h1 id="product-name" class="name">{{ product.name }}</h1>
          <div class="ident-row">
            <span v-if="product.make" class="make">{{ product.make }}</span>
            <span v-if="product.modelnumber" class="num">{{ product.modelnumber }}</span>
            <span v-if="product.modelname && product.modelname !== product.name" class="t-body muted">{{ product.modelname }}</span>
            <ProductBadges :product="product" show-limit />
            <span v-if="product.unitquantity && product.unitquantity > 1" class="t-body muted">{{ product.unitquantity }} in each pack</span>
          </div>
        </div>

        <div class="buy">
          <template v-if="!session.isLoggedIn">
            <v-btn :to="loginLink" color="primary" size="large">Log in to request</v-btn>
            <p class="buy-note">Requests need an approved account. <router-link to="/signup">Sign up</router-link></p>
          </template>
          <p v-else-if="session.isCimh" class="buy-note staff">CIMH staff accounts can browse but can't send requests.</p>
          <template v-else>
            <div class="buy-row">
              <div class="stepper" role="group" aria-label="Quantity">
                <v-btn :icon="mdiMinus" size="small" variant="text" aria-label="Fewer" :disabled="qty <= 1" @click="qty--" />
                <span class="tnum qty" aria-live="polite"><Transition :name="`roll-${qtyDir}`" mode="out-in"><span :key="qty" class="qty-n">{{ qty }}</span></Transition></span>
                <v-btn :icon="mdiPlus" size="small" variant="text" aria-label="More" :disabled="qty >= max" @click="qty++" />
              </div>
              <v-btn ref="addBtn" color="primary" size="large" :loading="adding" @click="addToRequest">Add to cart</v-btn>
            </div>
            <p class="buy-note">{{ product.probono ? 'Free for member organisations. You send the cart as a request, and CIMH approves it.' : 'Nothing is sent or paid yet. You send the cart as a request, and CIMH quotes it.' }}</p>
          </template>
        </div>
      </section>

      <!-- Below: what it is, and its facts. -->
      <div class="cols">
        <section class="col" aria-labelledby="desc-h">
          <h2 id="desc-h" class="col-title">Description</h2>
          <p v-if="product.description" class="t-body-lg prose">{{ product.description }}</p>
          <p v-else class="t-body muted">No description yet. Ask CIMH about this part when you send your request.</p>
          <p v-if="product.details" class="t-body-lg prose details">{{ product.details }}</p>
        </section>
        <section v-if="specs.length" class="col" aria-labelledby="spec-h">
          <h2 id="spec-h" class="col-title">Specifications</h2>
          <dl class="facts">
            <template v-for="[k, v] in specs" :key="k">
              <dt>{{ k }}</dt>
              <dd :class="{ 't-mono': k === 'Model number' }">{{ v }}</dd>
            </template>
          </dl>
        </section>
      </div>

      <details v-if="!session.isCimh" class="how">
        <summary><v-icon :icon="mdiChevronDown" size="20" class="how-chev" aria-hidden="true" />How requesting works</summary>
        <HowRequestingWorks variant="list" :skip-account="session.isLoggedIn" />
      </details>
    </article>
  </v-container>
</template>

<style scoped>
.product {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.crumb {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-wrap: wrap;
}
.crumb-sep {
  color: rgb(var(--v-theme-primary));
}
.crumb a {
  text-decoration: none;
  min-height: 24px;
  display: inline-flex;
  align-items: center;
}
.crumb a:hover {
  text-decoration: underline;
}

/* Loading shape: keeps the page a screen tall so the footer stays below the fold until the product arrives. */
.page {
  min-height: 100dvh;
}
.loading .crumb-skel {
  max-width: 320px;
  background: transparent;
}
.loading .bar-skel {
  margin-top: var(--sp-6);
  background: transparent;
}
.skel-band {
  border-bottom-color: rgba(var(--v-theme-on-surface), 0.12);
}
/* The band. */
.band {
  position: relative;
  height: 440px;
  border-radius: 12px;
  /* One step darker than the page ground in both themes, so the white plate reads as the subject. */
  background: rgba(var(--v-theme-on-surface), 0.05);
  border-bottom: 4px solid #0084c8; /* the store's logo-blue rule, as the catalogue band */
  display: grid;
  place-items: center;
  padding: var(--sp-6) var(--sp-6) 88px;
  overflow: hidden;
}
.band:not(:has(.thumbs)) {
  padding-bottom: var(--sp-6);
}
/* Arrival: the plate settles onto the band once, on load. */
.plate {
  animation: plate-in 520ms cubic-bezier(0.16, 1, 0.3, 1) both;
  height: 100%;
  aspect-ratio: 4 / 3;
  max-width: 100%;
  border-radius: 8px;
  background: rgb(var(--v-theme-photo-ground));
  box-shadow: 0 16px 36px -22px rgba(10, 46, 74, 0.45);
  display: grid;
  place-items: center;
  overflow: hidden;
}
@keyframes plate-in {
  from {
    opacity: 0;
    transform: translateY(10px) scale(0.98);
    box-shadow: 0 2px 6px -4px rgba(10, 46, 74, 0.2);
  }
}
.plate-img {
  max-width: 92%;
  max-height: 92%;
  object-fit: contain;
  mix-blend-mode: multiply; /* as ProductImage: the photo takes the tone of photo-ground */
}
.counter {
  position: absolute;
  top: var(--sp-4);
  right: var(--sp-4);
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
}
.nav {
  position: absolute;
  top: calc(50% - 32px);
  background: rgb(var(--v-theme-surface)) !important;
  box-shadow: 0 4px 12px -6px rgba(10, 46, 74, 0.4);
}
.prev {
  left: var(--sp-4);
}
.next {
  right: var(--sp-4);
}
.thumbs {
  position: absolute;
  left: 50%;
  bottom: var(--sp-4);
  transform: translateX(-50%);
  display: flex;
  gap: var(--sp-2);
  list-style: none;
  margin: 0;
  padding: 0;
  max-width: calc(100% - 32px);
  overflow-x: auto;
}
.thumb {
  width: 56px;
  height: 56px;
  border-radius: 6px;
  overflow: hidden;
  border: 2px solid transparent;
  background: rgb(var(--v-theme-photo-ground));
  padding: 0;
  cursor: pointer;
  transition: border-color 150ms ease-out, transform 150ms ease-out;
}
.thumb:hover {
  transform: translateY(-2px);
}
.thumb.on {
  border-color: rgb(var(--v-theme-primary));
}
.thumb :deep(img) {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.swap-enter-active {
  transition: opacity 220ms ease-out;
}
.swap-leave-active {
  transition: opacity 100ms ease-in;
}
.swap-enter-from,
.swap-leave-to {
  opacity: 0;
}

/* No photo: the nameplate fills the band. */
/* No photo: the band becomes the store's navy field (as the catalogue band) carrying the part's nameplate. */
.band.bare {
  height: 300px;
  padding: var(--sp-8);
  background: #0a2e4a;
  color: #fff;
  border-bottom: 4px solid #0084c8;
}
.band.bare::before {
  content: '';
  position: absolute;
  inset: 0;
  background: url('@cimh/web-app/assets/legacy/gears.webp') right -40px bottom -60px / 520px auto no-repeat;
  filter: invert(1);
  mix-blend-mode: screen;
  opacity: 0.12;
  pointer-events: none;
}
.nameplate-big {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-3);
  text-align: center;
  max-width: 90%;
}
.np-model {
  font-size: clamp(32px, 4.4vw, 56px);
  line-height: 1.05;
  font-weight: 700;
  letter-spacing: -0.025em;
  text-wrap: balance;
}
.np-model.quiet {
  font-size: clamp(24px, 2.6vw, 32px);
  font-weight: 600;
  color: rgba(255, 255, 255, 0.86);
}
.np-num {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: clamp(18px, 2vw, 26px);
  padding: 2px 12px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.12);
}
.np-rule {
  width: 48px;
  height: 3px;
  border-radius: 3px;
  background: #0084c8;
  margin-top: var(--sp-2);
}
.np-note {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.82);
}

/* The request bar. */
.sentinel {
  height: 1px;
  margin-bottom: -1px;
}
.bar {
  position: sticky;
  top: 72px;
  z-index: 3;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--sp-4) var(--sp-8);
  align-items: center;
  padding: var(--sp-5, 20px) 0;
  /* The page ground, so the bar is part of the page until it pins; then it spans the window with a shadow. */
  background: rgb(var(--v-theme-background));
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  transition: padding 200ms cubic-bezier(0.16, 1, 0.3, 1), box-shadow 200ms ease-out;
}
.bar.pinned {
  padding: var(--sp-3) 0;
  box-shadow: 0 10px 16px -14px rgba(10, 46, 74, 0.35), -100vw 0 0 rgb(var(--v-theme-background)), 100vw 0 0 rgb(var(--v-theme-background));
  clip-path: inset(0 -100vw -24px -100vw);
}
.ident {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.make {
  font-size: 15px;
  line-height: 22px;
  font-weight: 600;
}
.name {
  margin: 0;
  font-size: 34px;
  line-height: 40px;
  font-weight: 700;
  letter-spacing: -0.02em;
  text-wrap: balance;
  transition: font-size 200ms cubic-bezier(0.16, 1, 0.3, 1), line-height 200ms cubic-bezier(0.16, 1, 0.3, 1);
}
.pinned .name {
  font-size: 20px;
  line-height: 28px;
}
.ident-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-2) var(--sp-3);
  margin-top: 4px;
}
.pinned .ident-row,
.pinned .buy-note {
  display: none;
}
.num {
  font-family: 'JetBrains Mono', monospace;
  font-size: 15px;
  line-height: 22px;
  padding: 1px 8px;
  border-radius: 4px;
  background: rgb(var(--v-theme-surface-variant));
}
.buy {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--sp-2);
}
.buy-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}
.buy-note {
  margin: 0;
  max-width: 34ch;
  text-align: right;
  font-size: 13px;
  line-height: 18px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.buy-note.staff {
  font-size: 15px;
  line-height: 22px;
}
.stepper {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 48px;
  padding: 0 4px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 24px;
}
.qty {
  min-width: 2.5ch;
  text-align: center;
  font-weight: 600;
  display: inline-block;
  overflow: hidden;
}
.qty-n {
  display: inline-block;
}
.roll-up-enter-active,
.roll-down-enter-active {
  transition: transform 180ms cubic-bezier(0.16, 1, 0.3, 1), opacity 180ms ease-out;
}
.roll-up-leave-active,
.roll-down-leave-active {
  transition: transform 90ms ease-in, opacity 90ms ease-in;
}
.roll-up-enter-from,
.roll-down-leave-to {
  transform: translateY(60%);
  opacity: 0;
}
.roll-up-leave-to,
.roll-down-enter-from {
  transform: translateY(-60%);
  opacity: 0;
}
.counter > span {
  display: inline-block;
}

/* Below the bar. */
.cols {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--sp-12, 48px);
  padding-top: var(--sp-6);
}
.col-title {
  margin: 0 0 var(--sp-3);
  font-size: 16px;
  line-height: 24px;
  font-weight: 700;
}
.prose {
  max-width: 62ch;
  margin: 0;
  white-space: pre-line;
}
.details {
  margin-top: var(--sp-3);
}
.facts {
  display: grid;
  grid-template-columns: minmax(120px, auto) 1fr;
  margin: 0;
}
.facts dt,
.facts dd {
  margin: 0;
  padding: 10px 0;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.facts dd.t-mono {
  font-size: inherit;
  line-height: inherit;
}
.facts dt {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  padding-right: var(--sp-4);
}
.how {
  margin-top: var(--sp-4);
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding-top: var(--sp-4);
}
.how summary {
  cursor: pointer;
  font-weight: 600;
  min-height: 24px;
  list-style: none;
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
}
.how summary::-webkit-details-marker {
  display: none;
}
.how-chev {
  color: rgb(var(--v-theme-primary));
  transition: transform 200ms cubic-bezier(0.16, 1, 0.3, 1);
}
.how[open] .how-chev {
  transform: rotate(180deg);
}
.how[open] summary {
  margin-bottom: var(--sp-4);
}

/* Phones and tablets: no top bar here (bottom navigation), so the bar pins to the top; it stacks. */
@media (max-width: 959.98px) {
  .band {
    height: 280px;
    padding: var(--sp-4) var(--sp-4) 76px;
  }
  .band:not(:has(.thumbs)) {
    padding-bottom: var(--sp-4);
  }
  .thumb {
    width: 48px;
    height: 48px;
  }
  .nav {
    top: calc(50% - 30px);
  }
  .prev {
    left: var(--sp-2);
  }
  .next {
    right: var(--sp-2);
  }
  .band.bare {
    height: 220px;
    padding: var(--sp-5, 20px);
  }
  .bar {
    top: 0;
    grid-template-columns: minmax(0, 1fr);
  }
  .name {
    font-size: 26px;
    line-height: 32px;
  }
  .buy {
    align-items: stretch;
  }
  .buy-row > :last-child {
    flex: 1;
  }
  .buy-note {
    text-align: left;
    max-width: none;
  }
  .bar.pinned {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .pinned .stepper {
    display: none;
  }
  .cols {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--sp-8);
  }
}
@media (prefers-reduced-motion: reduce) {
  .bar,
  .name {
    transition: none;
  }
  .plate {
    animation: none;
  }
  .roll-up-enter-from,
  .roll-down-leave-to,
  .roll-up-leave-to,
  .roll-down-enter-from {
    transform: none;
  }
}
</style>

<style>
/* The token that carries added parts to the cart (flyToCart; lives on <body>). */
.cart-token {
  position: fixed;
  z-index: 3000;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 40px;
  padding: 4px 10px 4px 4px;
  border-radius: 999px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  box-shadow: 0 10px 24px -10px rgba(10, 46, 74, 0.5);
  font: 600 13px/1 Inter, sans-serif;
  pointer-events: none;
  will-change: transform, opacity;
}
.cart-token img,
.cart-token b {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  object-fit: contain;
  background: #fff;
  display: grid;
  place-items: center;
  color: #0a2e4a;
}
</style>
