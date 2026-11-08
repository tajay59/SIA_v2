<script setup lang="ts">
/**
 * S-03 product, same structure as the legacy InventoryItem page: left (about 3/4) a vertical strip of
 * thumbnails beside a large photo carousel; right (1/4) one card with the name, availability, product
 * description, details, units per pack, quantity and a full-width button. On phones the name sits above
 * the photos. v2 rules: no price and no serial numbers for customers. The button adds to the cart (S-07).
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
import { mdiArrowLeft, mdiChevronLeft, mdiChevronRight, mdiMinus, mdiPlus } from '@mdi/js'
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useRoute, useRouter } from 'vue-router'

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

async function addToRequest() {
  if (!product.value) return
  adding.value = true
  try {
    await cart.add(product.value.id, qty.value)
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
const loginLink = computed(() => ({ path: '/login', query: { returnTo: route.fullPath } }))
</script>

<template>
  <v-container max-width="1440" class="page">
    <div v-if="missing" class="stack">
      <h1 class="t-h2">Product not found</h1>
      <p class="t-body muted">It may have been withdrawn from the catalogue.</p>
      <div><v-btn to="/catalogue" variant="outlined">Back to the catalogue</v-btn></div>
    </div>
    <v-skeleton-loader v-else-if="!product" type="image, article" />
    <article v-else class="product">
      <router-link to="/catalogue" class="back t-body"><v-icon :icon="mdiArrowLeft" size="18" /> Equipment and Spares</router-link>

      <header v-if="!mdAndUp" class="stack-sm">
        <h1 class="t-h1">{{ product.name }}</h1>
        <p v-if="makeLine || product.modelnumber" class="t-body muted">
          {{ makeLine }} <span v-if="product.modelnumber" class="t-mono">{{ product.modelnumber }}</span>
        </p>
      </header>

      <div class="layout">
        <!-- Left: thumbnails + carousel -->
        <section class="media" aria-label="Photos">
          <ul v-if="images.length > 1 && mdAndUp" class="thumbs" aria-label="All photos">
            <li v-for="(img, i) in images" :key="img.fileId">
              <button
                type="button"
                class="thumb"
                :class="{ on: i === index }"
                :aria-label="`Photo ${i + 1} of ${images.length}`"
                :aria-pressed="i === index"
                @click="index = i"
              >
                <ProductImage :image="img" alt="" small sizes="96px" />
              </button>
            </li>
          </ul>
          <div class="stage">
            <img
              v-if="shown"
              :key="shown.fileId"
              :src="shown.url"
              :srcset="imageSrcset(shown.url)"
              sizes="(max-width: 960px) 100vw, 900px"
              :alt="product.name"
              class="stage-img"
            />
            <ProductImage v-else :image="null" :alt="product.name" class="stage-empty" />
            <template v-if="images.length > 1">
              <v-btn class="nav prev" :icon="mdiChevronLeft" variant="flat" size="small" aria-label="Previous photo" @click="step(-1)" />
              <v-btn class="nav next" :icon="mdiChevronRight" variant="flat" size="small" aria-label="Next photo" @click="step(1)" />
              <span class="counter t-caption">{{ index + 1 }} / {{ images.length }}</span>
            </template>
          </div>
        </section>

        <!-- Right: the product card -->
        <aside class="panel">
          <div v-if="mdAndUp" class="stack-sm">
            <h1 class="t-h2">{{ product.name }}</h1>
            <p v-if="makeLine || product.modelnumber" class="t-body muted">
              {{ makeLine }} <span v-if="product.modelnumber" class="t-mono">{{ product.modelnumber }}</span>
            </p>
          </div>
          <ProductBadges :product="product" show-limit />

          <section v-if="product.description" class="block">
            <h2 class="block-title">Product description</h2>
            <p class="t-body">{{ product.description }}</p>
          </section>
          <section v-if="product.details || specs.length" class="block">
            <h2 class="block-title">Details</h2>
            <p v-if="product.details" class="t-body details">{{ product.details }}</p>
            <dl v-if="specs.length" class="facts">
              <template v-for="[k, v] in specs" :key="k">
                <dt>{{ k }}</dt>
                <dd :class="{ 't-mono': k === 'Model number' }">{{ v }}</dd>
              </template>
            </dl>
          </section>
          <p v-if="product.unitquantity && product.unitquantity > 1" class="pack">{{ product.unitquantity }} in each pack</p>

          <div class="buy">
            <template v-if="!session.isLoggedIn">
              <v-btn :to="loginLink" color="primary" size="large" block>Log in to request</v-btn>
              <p class="t-caption muted">Requests need an approved account. Prices are quoted after you send a request.</p>
            </template>
            <p v-else-if="session.isCimh" class="t-body muted">CIMH staff accounts can browse but can't submit requests.</p>
            <template v-else>
              <div class="qty-row">
                <span class="t-label">Quantity</span>
                <div class="stepper" role="group" aria-label="Quantity">
                  <v-btn :icon="mdiMinus" size="small" variant="text" aria-label="Fewer" :disabled="qty <= 1" @click="qty--" />
                  <span class="tnum qty" aria-live="polite">{{ qty }}</span>
                  <v-btn :icon="mdiPlus" size="small" variant="text" aria-label="More" :disabled="qty >= max" @click="qty++" />
                </div>
              </div>
              <v-btn color="primary" size="large" block :loading="adding" @click="addToRequest">Add to request</v-btn>
              <p class="t-caption muted">Prices are quoted after you send a request.</p>
            </template>
          </div>
        </aside>
      </div>
    </article>
  </v-container>
</template>

<style scoped>
.product {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  text-decoration: none;
  width: fit-content;
}
.layout {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(300px, 1fr);
  gap: var(--sp-8);
  align-items: start;
}
@media (max-width: 959px) {
  .layout {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--sp-6);
  }
}
.media {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: var(--sp-3);
}
.thumbs {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  max-height: 600px;
  overflow-y: auto;
}
.thumb {
  width: 96px;
  padding: 2px;
  border: 2px solid transparent;
  border-radius: 10px;
  background: none;
  cursor: pointer;
}
.thumb.on {
  border-color: rgb(var(--v-theme-primary));
}
.stage {
  grid-column: 2;
  position: relative;
  background: #fff;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 16px;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
@media (max-width: 959px) {
  .stage {
    grid-column: 1 / -1;
  }
}
.stage-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  padding: 4%;
}
.stage-empty {
  width: 100%;
}
.nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  background: rgba(255, 255, 255, 0.92) !important;
  color: #0f1a24 !important;
  box-shadow: 0 1px 4px rgba(15, 26, 36, 0.2);
  opacity: 0;
  transition: opacity 160ms;
}
.stage:hover .nav,
.nav:focus-visible {
  opacity: 1;
}
@media (hover: none) {
  .nav {
    opacity: 1;
  }
}
.prev {
  left: 12px;
}
.next {
  right: 12px;
}
.counter {
  position: absolute;
  bottom: 10px;
  right: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(15, 26, 36, 0.6);
  color: #fff;
}
.panel {
  position: sticky;
  top: 96px;
  display: flex;
  flex-direction: column;
  gap: var(--sp-5, 20px);
  padding: var(--sp-6);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 16px;
  background: rgb(var(--v-theme-surface));
}
@media (max-width: 959px) {
  .panel {
    position: static;
  }
}
.block {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding-top: var(--sp-4);
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.block-title {
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  opacity: 0.72;
  margin: 0;
}
.details {
  white-space: pre-line;
}
.facts {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 6px var(--sp-4);
  margin: 0;
  font-size: 14px;
}
.facts dt {
  opacity: 0.72;
}
.facts dd {
  margin: 0;
}
.pack {
  font-size: 18px;
  font-weight: 700;
  margin: 0;
}
.buy {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding-top: var(--sp-4);
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.qty-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.stepper {
  display: inline-flex;
  align-items: center;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}
.qty {
  min-width: 2.5ch;
  text-align: center;
}
</style>
