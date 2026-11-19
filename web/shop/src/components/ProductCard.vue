<script setup lang="ts">
/**
 * Product card ("Showcase card", 2026-11-19, from the owner's reference): a bordered card with the photo on a
 * tinted plate, a row of photo thumbnails under it (hover, focus or press swaps the plate; the shown one is
 * ringed), the name, make · model · number, a family tag, then where a webshop prints the price: what to expect
 * (In stock / On request, pack size). At the foot a full-width navy Add to cart beside a square open button.
 * Pro Bono flags the plate's corner. No photo = the part's nameplate on the plate. Search matches are marked.
 * No prices (v2). Logged out or CIMH staff (can't request): the foot is one "View item".
 */
import { imageSrcset, imageVariant, primaryImage, useCart, useNotify, useSession, type Product } from '@cimh/web-app'
import { mdiArrowRight, mdiCartPlus, mdiCheckCircleOutline, mdiClockOutline, mdiPackageVariant } from '@mdi/js'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

const props = withDefaults(defineProps<{ product: Product; highlight?: string }>(), { highlight: '' })
const session = useSession()
const cart = useCart()
const notify = useNotify()
const router = useRouter()
const href = computed(() => `/catalogue/${props.product.id}`)
const images = computed(() => props.product.images ?? [])
const chosen = ref<number | null>(null)
const photo = computed(() => (chosen.value != null ? images.value[chosen.value] : primaryImage(props.product)) ?? null)
const THUMBS = 4
const thumbs = computed(() => (images.value.length > 1 ? images.value.slice(0, THUMBS) : []))
const extra = computed(() => Math.max(0, images.value.length - THUMBS))
const FAMILY: Record<string, string> = { MET: 'Meteorological', RAD: 'Radar', EQUIP: 'Equipment', SUPP: 'Supplies', MISC: 'Miscellaneous', PRO: 'Project item' }
const family = computed(() => FAMILY[props.product.type] ?? props.product.type)
const model = computed(() => [props.product.make, props.product.modelname, props.product.modelnumber].filter(Boolean).join(' · '))
const canAdd = computed(() => session.isLoggedIn && !session.isCimh)
const adding = ref(false)

async function add() {
  adding.value = true
  try {
    await cart.add(props.product.id, 1)
    const target = Array.from(document.querySelectorAll<HTMLElement>('[data-cart-target]')).find((el) => el.offsetParent !== null)
    if (!matchMedia('(prefers-reduced-motion: reduce)').matches)
      target?.animate([{ transform: 'scale(1)' }, { transform: 'scale(1.18)' }, { transform: 'scale(1)' }], { duration: 320, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' })
    notify.toast(`Added 1 × ${props.product.name} to your cart`, 'success', { action: { label: 'View cart', run: () => void router.push('/cart') } })
  } catch (e) {
    notify.report(e)
  } finally {
    adding.value = false
  }
}

/** Splits text into plain and matched parts (case-insensitive, every word of the query). */
function parts(text: string): { t: string; m: boolean }[] {
  const words = props.highlight
    .split(/\s+/)
    .filter((w) => w.length >= 2)
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  if (!words.length || !text) return [{ t: text, m: false }]
  const rx = new RegExp(`(${words.join('|')})`, 'gi')
  const whole = new RegExp(`^(${words.join('|')})$`, 'i')
  return text
    .split(rx)
    .filter(Boolean)
    .map((t) => ({ t, m: whole.test(t) }))
}
</script>

<template>
  <article class="pc">
    <div class="plate">
      <img
        v-if="photo"
        :key="photo.url"
        class="photo"
        :src="imageVariant(photo.url, 320)"
        :srcset="imageSrcset(photo.url)"
        sizes="(max-width: 600px) 50vw, 260px"
        alt=""
        loading="lazy"
        decoding="async"
      />
      <!-- No photo yet: the part's nameplate on the plate. -->
      <div v-else class="nameplate" aria-hidden="true">
        <span v-if="product.make" class="np-make">{{ product.make }}</span>
        <span v-if="product.modelname || product.modelnumber" class="np-model">{{ product.modelname || product.modelnumber }}</span>
        <v-icon v-else :icon="mdiPackageVariant" size="28" class="np-icon" />
        <span v-if="product.modelname && product.modelnumber" class="np-number">{{ product.modelnumber }}</span>
      </div>
      <span v-if="product.probono" class="flag probono-badge">Pro Bono</span>
    </div>

    <div v-if="thumbs.length" class="thumbs" role="group" :aria-label="`Photos of ${product.name}`">
      <button
        v-for="(im, i) in thumbs"
        :key="im.url"
        type="button"
        class="thumb"
        :class="{ on: photo?.url === im.url }"
        :aria-label="`Photo ${i + 1} of ${images.length}`"
        :aria-pressed="photo?.url === im.url"
        @mouseenter="chosen = i"
        @focus="chosen = i"
        @click="chosen = i"
      >
        <img :src="imageVariant(im.url, 320)" alt="" loading="lazy" decoding="async" />
      </button>
      <span v-if="extra" class="more">+{{ extra }}</span>
    </div>

    <div class="info">
      <router-link :to="href" class="name">
        <template v-for="(p, i) in parts(product.name)" :key="i"><mark v-if="p.m">{{ p.t }}</mark><template v-else>{{ p.t }}</template></template>
      </router-link>
      <span v-if="model" class="model">
        <template v-for="(p, i) in parts(model)" :key="i"><mark v-if="p.m">{{ p.t }}</mark><template v-else>{{ p.t }}</template></template>
      </span>
    </div>

    <div class="status">
      <span class="stock" :class="{ in: product.inStock }">
        <v-icon :icon="product.inStock ? mdiCheckCircleOutline : mdiClockOutline" size="16" />
        {{ product.inStock ? 'In stock' : 'On request' }}
      </span>
      <span v-if="product.unitquantity && product.unitquantity > 1" class="pack">{{ product.unitquantity }} per pack</span>
    </div>

    <div class="acts">
      <template v-if="canAdd">
        <v-btn class="add" variant="flat" :prepend-icon="mdiCartPlus" :loading="adding" @click="add">Add to cart</v-btn>
        <v-btn class="go" variant="outlined" :to="href" :icon="mdiArrowRight" :aria-label="`Open ${product.name}`" tabindex="-1" />
      </template>
      <v-btn v-else class="add" variant="flat" :to="href" :append-icon="mdiArrowRight" tabindex="-1">View item</v-btn>
    </div>
  </article>
</template>

<style scoped>
.pc {
  --plate: #f1f4f7;
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  min-width: 0;
  padding: var(--sp-2) var(--sp-2) var(--sp-3);
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  transition: border-color 160ms ease-out, box-shadow 200ms ease-out;
}
/* The whole card opens the item: the name's link stretches over it; thumbnails and buttons sit above it. */
.name::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 12px;
}
.thumbs,
.acts {
  position: relative;
  z-index: 1;
}
.pc:hover {
  border-color: rgba(var(--v-theme-primary), 0.6);
  box-shadow: 0 10px 24px -14px rgba(10, 46, 74, 0.45);
}
.pc:has(.name:focus-visible) {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.name:focus-visible {
  outline: none;
}
.plate {
  position: relative;
  aspect-ratio: 4 / 3;
  border-radius: 8px;
  overflow: hidden;
  background: var(--plate);
}
/* Photos are shot on white: multiply lets the plate's tint through the white (Design Brief §7). */
.photo {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  padding: 10%;
  mix-blend-mode: multiply;
  animation: photo-in 220ms ease-out;
  transition: transform 300ms cubic-bezier(0.16, 1, 0.3, 1);
}
.pc:hover .photo {
  transform: scale(1.04);
}
.flag {
  position: absolute;
  top: var(--sp-2);
  left: var(--sp-2);
}
.nameplate {
  position: absolute;
  inset: var(--sp-3);
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  padding: var(--sp-3) var(--sp-4);
  border-radius: 6px;
  background: #fff;
  color: #0f1a24;
  border: 1px solid rgba(15, 26, 36, 0.14);
  box-shadow: inset 0 0 0 3px #fff, inset 0 0 0 4px rgba(15, 26, 36, 0.14);
  overflow: hidden;
  overflow-wrap: break-word;
}
.np-make {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #4a5866;
}
.np-model {
  font-size: 17px;
  line-height: 1.2;
  font-weight: 700;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.np-icon {
  margin-top: var(--sp-2);
  color: #4a5866;
}
.np-number {
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  font-size: 13px;
  color: #006fa8;
}
.thumbs {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: calc(-1 * var(--sp-1));
}
.thumb {
  width: 40px;
  height: 30px;
  padding: 2px;
  border-radius: 6px;
  background: var(--plate);
  border: 1px solid transparent;
  cursor: pointer;
  transition: border-color 140ms ease-out;
}
.thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  mix-blend-mode: multiply;
}
.thumb:hover {
  border-color: rgba(var(--v-border-color), 0.4);
}
.thumb.on {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 0 0 1px rgb(var(--v-theme-primary));
}
.thumb:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 1px;
}
.more {
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
}
.info {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 0 var(--sp-1);
  min-width: 0;
}
.name {
  color: inherit;
  text-decoration: none;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.pc:hover .name {
  color: rgb(var(--v-theme-primary));
}
.model {
  max-width: 100%;
  font-size: 13px;
  line-height: 18px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* Family tag: small caps on a primary wash (the reference's category chip). */
.tag {
  margin-top: 2px;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.1);
}
mark {
  animation: mark-in 400ms ease-out backwards 120ms;
  background: rgba(245, 196, 0, 0.45);
  color: inherit;
  border-radius: 2px;
  padding: 0 1px;
}
/* Where a webshop prints the price: what to expect (in stock now, or found on request). */
.status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-1) var(--sp-2);
  margin-top: auto;
  padding: 0 var(--sp-1);
  font-size: 14px;
  font-weight: 600;
}
.stock {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.stock.in {
  color: var(--stock-in, #116329);
}
.pack {
  font-size: 12px;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.acts {
  display: flex;
  gap: var(--sp-2);
}
/* Navy action (light) / white action (dark), like the reference's two card grounds. */
.acts .add {
  flex: 1;
  min-width: 0;
  height: 40px;
  border-radius: 8px;
  background: var(--act-bg, #0a2e4a);
  color: var(--act-ink, #fff);
}
.acts .go {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  border-color: rgba(var(--v-border-color), var(--v-border-opacity));
}
@media (max-width: 599.98px) {
  .name {
    font-size: 14px;
  }
  .np-model {
    font-size: 15px;
  }
  .acts .go {
    display: none;
  }
  .thumb:nth-child(n + 4) {
    display: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .pc,
  .photo {
    transition: none;
    animation: none;
  }
  .pc:hover .photo {
    transform: none;
  }
}
@keyframes photo-in {
  from {
    opacity: 0.4;
  }
}
@keyframes mark-in {
  from {
    background-color: transparent;
  }
}
</style>
<style>
.v-theme--cimhDark {
  --stock-in: rgb(var(--v-theme-success));
}
/* Dark: the plate is a lit tray in the dark card (multiply keeps photos clean), the action turns white. */
.v-theme--cimhDark .pc {
  --plate: #d6dee6;
  --act-bg: #fff;
  --act-ink: #0a2e4a;
}
</style>
