<script setup lang="ts">
/**
 * Product card ("Search desk", 2026-11-16): every card is the same size. The tile is a 4:3 frame holding either
 * the photo on a white plate or, when there is no photo, the part's nameplate (make, model, model number) at
 * the same size, so a page of photo-less items is a page of readable plates, not grey slabs. Under it: name,
 * make · model · model number, and one status line (In stock / On request, Pro Bono, pack size). While
 * searching, the matched text is marked. No prices (v2).
 */
import { imageSrcset, imageVariant, primaryImage, type Product } from '@cimh/web-app'
import { mdiCheckCircleOutline, mdiClockOutline, mdiPackageVariant } from '@mdi/js'
import { computed } from 'vue'

const props = withDefaults(defineProps<{ product: Product; highlight?: string }>(), { highlight: '' })
const photo = computed(() => primaryImage(props.product))
const FAMILY: Record<string, string> = { MET: 'Meteorological', RAD: 'Radar', EQUIP: 'Equipment', SUPP: 'Supplies', MISC: 'Miscellaneous', PRO: 'Project item' }
const family = computed(() => FAMILY[props.product.type] ?? props.product.type)
const model = computed(() => [props.product.make, props.product.modelname, props.product.modelnumber].filter(Boolean).join(' · '))

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
  <router-link :to="`/catalogue/${product.id}`" class="card">
    <div class="tile" :class="{ plate: !photo }">
      <img
        v-if="photo"
        class="photo"
        :src="imageVariant(photo.url, 320)"
        :srcset="imageSrcset(photo.url)"
        sizes="(max-width: 600px) 50vw, 240px"
        alt=""
        loading="lazy"
        decoding="async"
      />
      <!-- No photo yet: the part's nameplate, same size as a photo. -->
      <div v-else class="nameplate" aria-hidden="true">
        <!-- Nothing but a name on record: the plate names the family instead of repeating the name below it. -->
        <span class="np-make">{{ product.make || family }}</span>
        <span v-if="product.modelname || product.modelnumber" class="np-model">{{ product.modelname || product.modelnumber }}</span>
        <v-icon v-else :icon="mdiPackageVariant" size="28" class="np-icon" />
        <span v-if="product.modelname && product.modelnumber" class="np-number">{{ product.modelnumber }}</span>
      </div>
    </div>
    <div class="info">
      <span class="name">
        <template v-for="(p, i) in parts(product.name)" :key="i"><mark v-if="p.m">{{ p.t }}</mark><template v-else>{{ p.t }}</template></template>
      </span>
      <span v-if="model" class="model">
        <template v-for="(p, i) in parts(model)" :key="i"><mark v-if="p.m">{{ p.t }}</mark><template v-else>{{ p.t }}</template></template>
      </span>
      <span class="status">
        <span class="stock" :class="{ in: product.inStock }">
          <v-icon :icon="product.inStock ? mdiCheckCircleOutline : mdiClockOutline" size="14" />
          {{ product.inStock ? 'In stock' : 'On request' }}
        </span>
        <span v-if="product.probono" class="probono-badge">Pro Bono</span>
        <span v-if="product.unitquantity && product.unitquantity > 1" class="pack">{{ product.unitquantity }} per pack</span>
      </span>
    </div>
  </router-link>
</template>

<style scoped>
.card {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  min-width: 0;
  color: inherit;
  text-decoration: none;
  border-radius: 12px;
}
.tile {
  position: relative;
  aspect-ratio: 4 / 3;
  border-radius: 12px;
  overflow: hidden;
  background: rgb(var(--v-theme-surface-variant));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  transition: border-color 160ms ease-out, box-shadow 160ms ease-out, transform 160ms cubic-bezier(0.16, 1, 0.3, 1);
}
/* The photo sits on a white plate inset in the tile (Design Brief §7: white behind product photos, also in dark). */
.photo {
  position: absolute;
  inset: var(--sp-2);
  width: calc(100% - 2 * var(--sp-2));
  height: calc(100% - 2 * var(--sp-2));
  object-fit: contain;
  padding: 8%;
  background: #fff;
  border-radius: 8px;
}
/* Nameplate: an engraved plate inset in the tile, like the plate on the instrument itself. */
.nameplate {
  position: absolute;
  inset: var(--sp-2);
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  padding: var(--sp-3) var(--sp-4);
  border-radius: 8px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  box-shadow: inset 0 0 0 3px rgb(var(--v-theme-surface)), inset 0 0 0 4px rgba(var(--v-border-color), var(--v-border-opacity));
  overflow: hidden;
  overflow-wrap: anywhere;
}
.np-make {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
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
  color: rgba(var(--v-theme-on-surface), 0.55);
}
.np-number {
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  font-size: 13px;
  color: rgb(var(--v-theme-primary));
}
.card:hover .tile {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 6px 18px -8px rgba(15, 26, 36, 0.3);
}
.card:active .tile {
  transform: scale(0.98);
  transition-duration: 100ms;
}
.card:focus-visible {
  outline: none;
}
.card:focus-visible .tile {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 2px;
  min-width: 0;
}
.name {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card:hover .name {
  color: rgb(var(--v-theme-primary));
}
.model {
  font-size: 13px;
  line-height: 18px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
mark {
  animation: mark-in 400ms ease-out backwards 120ms;
  background: rgba(245, 196, 0, 0.45);
  color: inherit;
  border-radius: 2px;
  padding: 0 1px;
}
.status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-1) var(--sp-2);
  margin-top: var(--sp-1);
  font-size: 12px;
  font-weight: 600;
}
.stock {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.stock.in {
  /* #116329 = 7:1 on white (the theme success green is 4.4:1, below AA for 12 px); dark uses the theme green. */
  color: var(--stock-in, #116329);
}
.pack {
  color: rgb(var(--v-theme-primary));
}
@media (max-width: 599.98px) {
  .name {
    font-size: 14px;
  }
  .np-model {
    font-size: 15px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .tile {
    transition: none;
  }
}
</style>
<style>
.v-theme--cimhDark {
  --stock-in: rgb(var(--v-theme-success));
}
</style>
<style scoped>
/* Search marks fade in after the card, so the eye lands on what matched. */
@keyframes mark-in {
  from {
    background-color: transparent;
  }
}
@media (prefers-reduced-motion: reduce) {
  .card:active .tile {
    transform: none;
  }
}
</style>
