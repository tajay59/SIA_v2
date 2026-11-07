<script setup lang="ts">
/**
 * S-03 product (DESIGN_BRIEF §10): gallery (4:3 + thumbnails) left; name, make/model, availability, Pro Bono
 * badge with its limit, quantity and "Add to request" right; specs below. Never a price.
 * Requests (cart) arrive with order-svc (P5): until then the button explains that instead of failing.
 */
import {
  ApiError,
  call,
  catalog,
  makeModel,
  primaryImage,
  type ProductPhoto,
  type ProductPublic,
  ProductBadges,
  ProductImage,
  typeLabel,
  useReference,
  useSession,
} from '@cimh/web-app'
import { mdiMinus, mdiPlus } from '@mdi/js'
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

definePage({ meta: { guard: 'public', title: 'Product' } })
const route = useRoute('/catalogue/[id]')
const session = useSession()
const { reference } = useReference()
const product = ref<ProductPublic | null>(null)
const missing = ref(false)
const shown = ref<ProductPhoto | null>(null)
const qty = ref(1)

async function load(id: string) {
  product.value = null
  missing.value = false
  try {
    product.value = (await call(() => catalog.GET('/products/{productId}', { params: { path: { productId: id } } }))) as ProductPublic
    shown.value = primaryImage(product.value) ?? null
    qty.value = 1
    document.title = `${product.value.name} · CIMH Stores`
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) missing.value = true
    else throw e
  }
}
watch(() => route.params.id, (id) => void load(id), { immediate: true })

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
    ['Units per pack', p.unitquantity],
    ['Weight', p.weight != null ? `${p.weight} kg` : null],
    ['Dimensions', p.dimension],
  ].filter(([, v]) => v !== null && v !== undefined && v !== '') as [string, string | number][]
})
const loginLink = computed(() => ({ path: '/login', query: { returnTo: route.fullPath } }))
</script>

<template>
  <v-container max-width="1200" class="page">
    <div v-if="missing" class="stack">
      <h1 class="t-h2">Product not found</h1>
      <p class="t-body muted">It may have been withdrawn from the catalogue.</p>
      <div><v-btn to="/catalogue" variant="outlined">Back to the catalogue</v-btn></div>
    </div>
    <v-skeleton-loader v-else-if="!product" type="image, article" />
    <article v-else class="stack">
      <v-breadcrumbs :items="[{ title: 'Catalogue', to: '/catalogue' }, { title: product.name, disabled: true }]" class="pa-0" />
      <div class="top">
        <div class="gallery">
          <ProductImage :image="shown" :alt="product.name" sizes="(max-width: 960px) 100vw, 560px" eager />
          <ul v-if="product.images.length > 1" class="thumbs" aria-label="Photos">
            <li v-for="(img, i) in product.images" :key="img.fileId">
              <button
                type="button"
                class="thumb"
                :class="{ on: shown?.fileId === img.fileId }"
                :aria-label="`Photo ${i + 1} of ${product.images.length}`"
                :aria-pressed="shown?.fileId === img.fileId"
                @click="shown = img"
              >
                <ProductImage :image="img" :alt="''" small sizes="80px" />
              </button>
            </li>
          </ul>
        </div>
        <div class="buy stack">
          <h1 class="t-h1">{{ product.name }}</h1>
          <p v-if="makeModel(product)" class="t-body muted">
            {{ [product.make, product.modelname].filter(Boolean).join(' · ') }}
            <span v-if="product.modelnumber" class="t-mono"> {{ product.modelnumber }}</span>
          </p>
          <ProductBadges :product="product" show-limit />
          <p v-if="product.description" class="t-body prose">{{ product.description }}</p>

          <v-card class="pa-4 stack-sm">
            <template v-if="!session.isLoggedIn">
              <p class="t-body">Log in with an approved account to request this item.</p>
              <div><v-btn :to="loginLink" color="primary">Log in to request</v-btn></div>
            </template>
            <template v-else-if="session.isCimh">
              <p class="t-body muted">CIMH staff accounts can browse but can't submit requests.</p>
            </template>
            <template v-else>
              <div class="row">
                <span class="t-label">Quantity</span>
                <div class="stepper" role="group" aria-label="Quantity">
                  <v-btn :icon="mdiMinus" size="small" variant="text" aria-label="Fewer" :disabled="qty <= 1" @click="qty--" />
                  <span class="tnum qty" aria-live="polite">{{ qty }}</span>
                  <v-btn :icon="mdiPlus" size="small" variant="text" aria-label="More" :disabled="qty >= max" @click="qty++" />
                </div>
              </div>
              <div><v-btn color="primary" disabled>Add to request</v-btn></div>
              <p class="t-caption muted">Adding items to a request opens with the next release. Prices are quoted after you send a request.</p>
            </template>
          </v-card>
        </div>
      </div>

      <section v-if="specs.length || product.details" class="stack-sm specs">
        <h2 class="t-h3">Specifications</h2>
        <p v-if="product.details" class="t-body prose details">{{ product.details }}</p>
        <dl v-if="specs.length" class="facts">
          <template v-for="[k, v] in specs" :key="k">
            <dt>{{ k }}</dt>
            <dd :class="{ 't-mono': k === 'Model number' }">{{ v }}</dd>
          </template>
        </dl>
      </section>
    </article>
  </v-container>
</template>

<style scoped>
.top {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
  gap: var(--sp-8);
  align-items: start;
}
@media (max-width: 959px) {
  .top {
    grid-template-columns: minmax(0, 1fr);
  }
}
.gallery {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.thumbs {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  gap: var(--sp-2);
  flex-wrap: wrap;
}
.thumb {
  width: 80px;
  padding: 2px;
  border: 2px solid transparent;
  border-radius: 8px;
  background: none;
  cursor: pointer;
}
.thumb.on {
  border-color: rgb(var(--v-theme-primary));
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
.details {
  white-space: pre-line;
}
.facts {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: var(--sp-2) var(--sp-8);
  margin: 0;
  max-width: 720px;
}
.facts dt {
  font-size: 13px;
  font-weight: 500;
  opacity: 0.72;
}
.facts dd {
  margin: 0;
}
</style>
