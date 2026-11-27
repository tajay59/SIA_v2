<script setup lang="ts">
/**
 * One announcement as the banner shows it (AnnouncementBar) and as the admin editor previews it (A-22).
 * Tone by icon + word + colour; long text folds to two lines with More; site links and product links stay in the
 * app (a product link opens that product's page in this app: SHOP /catalogue/<id>, SIA /products/<id>), other
 * links open a new tab (said for screen readers); Close only when `dismissible` (never on an alert).
 * Images (owner 2026-11-26): a `picture` sits at the right; a product link shows the product's photo there instead
 * of link text, and the photo is the link (a button-like tile named by the link label). A `background` fills the
 * row under a dark wash (text turns white). A row with either grows to fit them, at most 300 px.
 * Height (owner 2026-11-26): with `height` set the row is that tall on wide screens and scales with its own width on
 * narrower ones (half on phones, never under 40 px); padding, text size, icon, the number of lines and the picture
 * all follow that height. Text that doesn't fit ends with More, which opens the row to its full text.
 * Look and effects (owner 2026-11-26, per announcement): look SOFT (wash) | GRADIENT (tone fading to the right) |
 * STRONG (solid tone, its own text colour); effects loop quietly to draw the eye: sweep (a band of light every 7 s),
 * glint (a light running along the bottom edge), ring (the icon rings every 3 s, alerts 2 s), drift (the tone
 * colours drift; not over a background image), zoom (the background image zooms slowly), nudge (the picture's link
 * badge nudges). All pause on hover and keyboard focus and are off with reduced motion (WCAG 2.2.2 / 2.3.3).
 * `app` overrides the running app (the admin preview shows SHOP rows inside SIA).
 */
import { mdiAlertCircle, mdiArrowTopRight, mdiClose, mdiInformation, mdiOpenInNew } from '@mdi/js'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { type Announcement, type AnnouncementApp, announcementHref, announcementImageSrcset } from '../announcements'
import { useTheme } from 'vuetify'
import { useAppName } from '../bootstrap'

const props = withDefaults(
  defineProps<{
    announcement: Pick<Announcement, 'message' | 'tone' | 'link' | 'dismissible'> &
      Partial<Pick<Announcement, 'picture' | 'background' | 'height' | 'look' | 'effects'>>
    preview?: boolean
    app?: AnnouncementApp
  }>(),
  { preview: false, app: undefined },
)
const running = useAppName()
const emit = defineEmits<{ dismiss: [] }>()
const a = computed(() => props.announcement)
const alert = computed(() => a.value.tone === 'ALERT')
const long = computed(() => a.value.message.length > 140)
const open = ref(false)
const href = computed(() => (a.value.link ? announcementHref(a.value.link, props.app ?? running) : null))
const isSitePath = (url: string) => url.startsWith('/') && !url.startsWith('//')

const productPhoto = computed(() => (a.value.link?.productId ? (a.value.link.imageUrl ?? null) : null))
/** The picture at the right: the uploaded one, else the linked product's photo. */
const side = computed(() => a.value.picture?.url ?? productPhoto.value)
const isProductPhoto = computed(() => !a.value.picture?.url && !!productPhoto.value)
const bg = computed(() => a.value.background?.url ?? null)
/** A product link with a picture: the picture is the link, no link text. */
const pictureIsLink = computed(() => !!(side.value && href.value && a.value.link?.productId))
const showLinkText = computed(() => !!(a.value.link && href.value && a.value.link.label) && !pictureIsLink.value)
const external = computed(() => !!href.value && !isSitePath(href.value))
const pictureName = computed(() => `${a.value.link?.label ?? 'Open'}${external.value ? ' (opens in a new tab)' : ''}`)

// ---- look and effects (an effect that has nothing to act on is left out: zoom without a background, ...)
const theme = useTheme() // the nearest theme: the admin preview draws light and dark rows side by side
const look = computed(() => (a.value.look ?? 'SOFT').toLowerCase())
const fx = computed(() => {
  const on = new Set(a.value.effects ?? [])
  return {
    sweep: on.has('sweep'),
    glint: on.has('glint'),
    ring: on.has('ring'),
    drift: on.has('drift') && !bg.value,
    zoom: on.has('zoom') && !!bg.value,
    nudge: on.has('nudge') && pictureIsLink.value,
  }
})
const rowClasses = computed(() => [
  `look-${look.value}`,
  { 'is-dark': theme.current.value.dark },
  ...Object.entries(fx.value)
    .filter(([, v]) => v)
    .map(([k]) => `fx-${k}`),
])

// ---- set height: everything is worked out from the row's own height (and that from its width)
const root = ref<HTMLElement | null>(null)
const textEl = ref<HTMLElement | null>(null)
const width = ref(0)
const overflow = ref(false)
const fixed = computed(() => typeof a.value.height === 'number' && a.value.height > 0)
const box = computed(() => {
  if (!fixed.value) return null
  const scale = Math.min(1, Math.max(0.5, (width.value || 1100) / 1100)) // full height from 1100 px wide, half on phones
  const h = Math.max(40, Math.round(a.value.height! * scale))
  const pad = Math.min(24, Math.max(6, Math.round(h * 0.08)))
  const inner = h - 2 * pad
  const fs = Math.round(13 + ((Math.min(h, 300) - 40) * 13) / 260) // 13 px at 40 → 26 px at 300
  const lh = Math.round(fs * 1.4)
  return { h, pad, inner, fs, lh, icon: Math.round(fs * 1.35), lines: Math.max(1, Math.floor(inner / lh)) }
})
const vars = computed(() =>
  box.value
    ? {
        '--ann-h': `${box.value.h}px`,
        '--ann-pad': `${box.value.pad}px`,
        '--ann-fs': `${box.value.fs}px`,
        '--ann-lh': `${box.value.lh}px`,
        '--ann-lines': String(box.value.lines),
        '--ann-pic': `${box.value.inner}px`,
      }
    : undefined,
)
function measure() {
  const el = textEl.value
  overflow.value = !!(fixed.value && !open.value && el && el.scrollHeight > el.clientHeight + 1)
}
let ro: ResizeObserver | undefined
onMounted(() => {
  if (!root.value) return
  ro = new ResizeObserver(([e]) => {
    width.value = e.contentRect.width
    void nextTick(measure)
  })
  ro.observe(root.value)
})
onBeforeUnmount(() => ro?.disconnect())
watch([box, () => a.value.message, () => a.value.link?.label, open], () => void nextTick(measure), { flush: 'post' })
</script>

<template>
  <div
    ref="root"
    class="ann-row"
    :class="[
      alert ? 'is-alert' : 'is-info',
      `in-${props.app ?? running}`,
      { 'has-bg': bg, 'has-media': bg || side, fixed, expanded: fixed && open },
      rowClasses,
    ]"
    :style="vars"
  >
    <img v-if="bg" class="ann-bg" :src="bg" :srcset="announcementImageSrcset(bg)" sizes="100vw" alt="" decoding="async" />
    <span v-if="fx.sweep" class="ann-sweep" aria-hidden="true" />
    <span v-if="fx.glint" class="ann-glint" aria-hidden="true" />
    <div class="ann-content">
      <span class="ann-icon-wrap">
        <v-icon :icon="alert ? mdiAlertCircle : mdiInformation" :size="box ? box.icon : 20" class="ann-icon" aria-hidden="true" />
      </span>
      <p ref="textEl" class="ann-text">
        <span class="ann-word">{{ alert ? 'Alert' : 'Information' }}:</span>
        <span class="ann-msg" :class="{ clamp: long && !open }">{{ a.message || ' ' }}</span>
        <button v-if="long && !fixed" type="button" class="ann-more" :aria-expanded="open" @click="open = !open">{{ open ? 'Less' : 'More' }}</button>
        <template v-if="showLinkText && a.link && href">
          <span v-if="preview" class="ann-link">{{ a.link.label }}</span>
          <router-link v-else-if="isSitePath(href)" :to="href" class="ann-link">{{ a.link.label }}</router-link>
          <a v-else :href="href" target="_blank" rel="noopener noreferrer" class="ann-link">
            {{ a.link.label }}<v-icon :icon="mdiOpenInNew" size="14" aria-hidden="true" /><span class="ann-sr"> (opens in a new tab)</span>
          </a>
        </template>
      </p>
      <button v-if="fixed && (overflow || open)" type="button" class="ann-more out" :aria-expanded="open" @click="open = !open">
        {{ open ? 'Less' : 'More' }}
      </button>
      <template v-if="side">
        <!-- The product's photo is its link (named by the label); a picture beside a text link repeats that link
             for pointers only (out of the tab order); a picture without a link is decoration. -->
        <component
          :is="preview ? 'span' : isSitePath(href!) ? 'router-link' : 'a'"
          v-if="href && (pictureIsLink || showLinkText)"
          v-bind="preview ? {} : isSitePath(href) ? { to: href } : { href, target: '_blank', rel: 'noopener noreferrer' }"
          class="ann-pic is-link"
          :class="{ product: isProductPhoto }"
          :aria-label="pictureIsLink ? pictureName : undefined"
          :aria-hidden="pictureIsLink ? undefined : 'true'"
          :tabindex="pictureIsLink ? undefined : -1"
          :title="pictureIsLink ? a.link?.label : undefined"
        >
          <img :src="side" :srcset="announcementImageSrcset(side)" sizes="(max-width: 599px) 120px, 300px" alt="" decoding="async" />
          <span v-if="pictureIsLink" class="ann-go" aria-hidden="true"><v-icon :icon="mdiArrowTopRight" size="16" /></span>
        </component>
        <span v-else class="ann-pic" :class="{ product: isProductPhoto }">
          <img :src="side" :srcset="announcementImageSrcset(side)" sizes="(max-width: 599px) 120px, 300px" alt="" decoding="async" />
        </span>
      </template>
      <v-btn
        v-if="a.dismissible && !alert"
        :icon="mdiClose"
        variant="text"
        size="small"
        density="comfortable"
        class="ann-close"
        :aria-label="`Close this information: ${a.message.slice(0, 60)}`"
        :disabled="preview"
        @click="emit('dismiss')"
      />
    </div>
  </div>
</template>

<style scoped>
.ann-sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.ann-row {
  --tone: var(--v-theme-primary);
  --ink: rgb(var(--v-theme-on-surface));
  position: relative;
  isolation: isolate;
  overflow: hidden;
  max-height: 300px;
  background: color-mix(in srgb, rgb(var(--tone)) 14%, rgb(var(--v-theme-surface)));
  border-bottom: 1px solid color-mix(in srgb, rgb(var(--tone)) 45%, rgb(var(--v-theme-surface)));
  color: var(--ink);
}
.ann-row {
  --on-tone: var(--v-theme-on-primary);
  --sweep: rgba(255, 255, 255, 0.6);
}
.ann-row.is-alert {
  --tone: var(--v-theme-warning);
  --on-tone: var(--v-theme-on-warning);
  background: color-mix(in srgb, rgb(var(--tone)) 22%, rgb(var(--v-theme-surface)));
}
/* Looks (not over a background image, whose dark wash decides the colours). */
.ann-row.look-gradient:not(.has-bg) {
  background: linear-gradient(
    90deg,
    color-mix(in srgb, rgb(var(--tone)) 32%, rgb(var(--v-theme-surface))),
    color-mix(in srgb, rgb(var(--tone)) 6%, rgb(var(--v-theme-surface)))
  );
}
.ann-row.look-strong:not(.has-bg) {
  --ink: rgb(var(--on-tone));
  background: rgb(var(--tone));
  border-bottom-color: color-mix(in srgb, rgb(var(--tone)) 70%, #000);
}
.ann-row.look-strong:not(.has-bg) .ann-icon {
  color: var(--ink);
}
.ann-row.look-strong:not(.has-bg) .ann-go {
  background: var(--ink);
  color: rgb(var(--tone));
}
.ann-row.look-strong:not(.has-bg) :is(.ann-more, .ann-link, .ann-pic.is-link):focus-visible {
  outline-color: var(--ink);
}
.ann-row:is(.is-dark, .has-bg, .look-strong) {
  --sweep: rgba(255, 255, 255, 0.16);
}
/* Background image: fills the row under a dark wash (stronger behind the words), so white text reads at 4.5:1
   whatever the photo is. The tone stays in the edge colour and the icon. */
.ann-bg {
  position: absolute;
  inset: 0;
  z-index: -2;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.has-bg::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: -1;
  background: linear-gradient(90deg, rgba(6, 10, 16, 0.86) 0%, rgba(6, 10, 16, 0.74) 55%, rgba(6, 10, 16, 0.5) 100%);
}
.has-bg {
  --ink: #fff;
  background: #0a0f16;
}
/* SHOP: the header's column (max 1200 px, 16 px inset), so the icon lines up with the logo. SIA: full width. */
.ann-content {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-2);
  max-width: 1200px;
  margin: 0 auto;
  padding: 10px var(--sp-4);
  min-height: 40px;
}
.in-sia .ann-content {
  max-width: none;
}
/* With images the row grows: words centred on the picture, at most 300 px in all. */
.has-media .ann-content {
  align-items: center;
  gap: var(--sp-3);
  padding-block: 16px;
  min-height: 120px;
  max-height: 300px;
}
.ann-icon {
  flex: none;
  color: rgb(var(--tone));
}
.has-bg .ann-icon {
  color: color-mix(in srgb, rgb(var(--tone)) 55%, #fff);
}
.ann-text {
  flex: 1;
  min-width: 0;
  margin: 0;
  font-size: 14px;
  line-height: 20px;
  text-wrap: pretty;
  overflow-wrap: anywhere;
}
.has-media .ann-text {
  font-size: 16px;
  line-height: 24px;
}
.ann-word {
  font-weight: 700;
  margin-right: 6px;
}
.ann-msg.clamp {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.has-media .ann-msg.clamp {
  -webkit-line-clamp: 4;
  line-clamp: 4;
}
.ann-more {
  border: 0;
  background: none;
  padding: 0;
  margin-left: 6px;
  font: inherit;
  font-weight: 600;
  color: var(--ink);
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
  min-height: 24px;
}
.ann-link {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-left: var(--sp-2);
  font-weight: 600;
  color: var(--ink);
  text-decoration: underline;
  text-underline-offset: 3px;
  min-height: 24px;
}
/* The picture: as tall as the row allows (268 = 300 − 2 × 16), never wider than 40 % of it. */
.ann-pic {
  position: relative;
  flex: none;
  display: block;
  max-width: 40%;
  border-radius: 8px;
  overflow: hidden;
  line-height: 0;
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--ink) 18%, transparent);
}
.ann-pic img {
  display: block;
  height: clamp(88px, 15vw, 268px);
  width: auto;
  max-width: 100%;
  object-fit: cover;
}
/* A product photo sits on a white plate (studio shots on white), square, like the catalogue. */
.ann-pic.product {
  background: #fff;
}
.ann-pic.product img {
  width: clamp(88px, 15vw, 268px);
  object-fit: contain;
  mix-blend-mode: multiply;
}
.ann-pic.is-link {
  cursor: pointer;
  transition:
    transform 160ms cubic-bezier(0.2, 0, 0, 1),
    box-shadow 160ms ease;
}
.ann-pic.is-link:hover {
  transform: translateY(-2px);
  box-shadow:
    0 0 0 2px rgb(var(--v-theme-primary)),
    0 6px 16px rgba(0, 0, 0, 0.24);
}
.ann-pic.is-link:active {
  transform: translateY(0) scale(0.98);
}
.ann-go {
  position: absolute;
  right: 6px;
  bottom: 6px;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.3);
}
.ann-close {
  flex: none;
  margin: -6px -8px -6px 0;
  color: var(--ink);
}
.has-media .ann-close {
  align-self: flex-start;
  margin-top: -8px;
}
.ann-more:focus-visible,
.ann-link:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
  border-radius: 2px;
}
.ann-pic.is-link:focus-visible {
  outline: 3px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.has-bg .ann-more:focus-visible,
.has-bg .ann-link:focus-visible,
.has-bg .ann-pic.is-link:focus-visible {
  outline-color: #fff;
}
@media (max-width: 599px) {
  .ann-content {
    padding: 10px 12px;
  }
  .has-media .ann-content {
    padding-block: 12px;
    min-height: 96px;
  }
  .has-media .ann-text {
    font-size: 14px;
    line-height: 20px;
  }
  .ann-pic img,
  .ann-pic.product img {
    height: 72px;
  }
  .ann-pic.product img {
    width: 72px;
  }
}
/* Set height: the row is exactly --ann-h; text, lines and picture follow it (worked out in the script). */
.ann-row.fixed {
  max-height: none;
}
.ann-row.fixed .ann-content {
  height: var(--ann-h);
  min-height: 0;
  max-height: none;
  padding-block: var(--ann-pad);
  align-items: center;
  gap: calc(var(--ann-fs) * 0.7);
}
.ann-row.fixed.expanded .ann-content {
  height: auto;
  min-height: var(--ann-h);
}
.ann-row.fixed .ann-text {
  font-size: var(--ann-fs);
  line-height: var(--ann-lh);
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: var(--ann-lines);
  line-clamp: var(--ann-lines);
  overflow: hidden;
  max-height: calc(var(--ann-lh) * var(--ann-lines));
}
.ann-row.fixed.expanded .ann-text {
  display: block;
  max-height: none;
}
.ann-row.fixed .ann-link,
.ann-row.fixed .ann-more {
  min-height: 0;
}
.ann-more.out {
  flex: none;
  align-self: center;
  margin: 0;
  font-size: max(13px, calc(var(--ann-fs) * 0.85));
  min-height: 24px;
}
.ann-row.fixed .ann-pic img,
.ann-row.fixed .ann-pic.product img {
  height: var(--ann-pic);
}
.ann-row.fixed .ann-pic.product img {
  width: var(--ann-pic);
}
.ann-row.fixed .ann-go {
  width: clamp(16px, calc(var(--ann-pic) * 0.16), 28px);
  height: clamp(16px, calc(var(--ann-pic) * 0.16), 28px);
  right: 4px;
  bottom: 4px;
}
.ann-row.fixed .ann-go :deep(.v-icon) {
  font-size: clamp(12px, calc(var(--ann-pic) * 0.1), 16px);
  width: auto;
  height: auto;
}
.ann-row.fixed .ann-close {
  align-self: center;
  margin-block: 0;
}
/* ---- effects: transform/opacity loops (drift moves a background), each mostly at rest */
.ann-sweep {
  position: absolute;
  inset: 0;
  z-index: -1;
  overflow: hidden;
  pointer-events: none;
}
.ann-sweep::before {
  content: '';
  position: absolute;
  top: -20%;
  bottom: -20%;
  left: 0;
  width: 35%;
  background: linear-gradient(100deg, transparent, var(--sweep) 50%, transparent);
  transform: translateX(-130%) skewX(-14deg);
  animation: ann-sweep 7s cubic-bezier(0.4, 0, 0.2, 1) 1.2s infinite;
}
@keyframes ann-sweep {
  0% {
    transform: translateX(-130%) skewX(-14deg);
  }
  22%,
  100% {
    transform: translateX(420%) skewX(-14deg);
  }
}
.ann-glint {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 2px;
  overflow: hidden;
  pointer-events: none;
  background: rgb(var(--tone));
}
.ann-row.look-strong:not(.has-bg) .ann-glint {
  background: color-mix(in srgb, var(--ink) 35%, transparent);
}
.ann-glint::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 22%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.95), transparent);
  transform: translateX(-100%);
  animation: ann-glint 4.5s linear infinite;
}
@keyframes ann-glint {
  to {
    transform: translateX(560%);
  }
}
.ann-icon-wrap {
  position: relative;
  flex: none;
  display: inline-grid;
  place-items: center;
}
.fx-ring .ann-icon-wrap::after {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: 50%;
  border: 2px solid rgb(var(--tone));
  opacity: 0;
  pointer-events: none;
  animation: ann-ring 3s cubic-bezier(0.2, 0, 0, 1) infinite;
}
.fx-ring.is-alert .ann-icon-wrap::after {
  animation-duration: 2s;
}
.fx-ring:is(.look-strong, .has-bg) .ann-icon-wrap::after {
  border-color: var(--ink);
}
@keyframes ann-ring {
  0% {
    transform: scale(0.9);
    opacity: 0.75;
  }
  45%,
  100% {
    transform: scale(2.1);
    opacity: 0;
  }
}
.ann-row.fx-drift:not(.has-bg) {
  background-size: 300% 100%;
  background-image: linear-gradient(
    110deg,
    color-mix(in srgb, rgb(var(--tone)) 8%, rgb(var(--v-theme-surface))),
    color-mix(in srgb, rgb(var(--tone)) 28%, rgb(var(--v-theme-surface))),
    color-mix(in srgb, rgb(var(--tone)) 8%, rgb(var(--v-theme-surface))),
    color-mix(in srgb, rgb(var(--tone)) 28%, rgb(var(--v-theme-surface)))
  );
  animation: ann-drift 14s ease-in-out infinite alternate;
}
.ann-row.fx-drift.look-gradient {
  background-image: linear-gradient(
    110deg,
    color-mix(in srgb, rgb(var(--tone)) 34%, rgb(var(--v-theme-surface))),
    color-mix(in srgb, rgb(var(--tone)) 6%, rgb(var(--v-theme-surface))),
    color-mix(in srgb, rgb(var(--tone)) 34%, rgb(var(--v-theme-surface))),
    color-mix(in srgb, rgb(var(--tone)) 6%, rgb(var(--v-theme-surface)))
  );
}
.ann-row.fx-drift.look-strong {
  background-image: linear-gradient(
    110deg,
    rgb(var(--tone)),
    color-mix(in srgb, rgb(var(--tone)) 80%, #000),
    rgb(var(--tone)),
    color-mix(in srgb, rgb(var(--tone)) 80%, #000)
  );
}
@keyframes ann-drift {
  from {
    background-position: 0% 50%;
  }
  to {
    background-position: 100% 50%;
  }
}
.fx-zoom .ann-bg {
  transform-origin: 60% 50%;
  animation: ann-zoom 22s ease-in-out infinite alternate;
}
@keyframes ann-zoom {
  from {
    transform: scale(1);
  }
  to {
    transform: scale(1.07);
  }
}
.fx-nudge .ann-go {
  animation: ann-nudge 3.5s cubic-bezier(0.3, 0, 0.2, 1) infinite;
}
@keyframes ann-nudge {
  0%,
  62%,
  100% {
    transform: translate(0, 0);
  }
  74% {
    transform: translate(3px, -3px);
  }
  84% {
    transform: translate(0, 0);
  }
  92% {
    transform: translate(2px, -2px);
  }
}
/* Hover or keyboard focus anywhere in the row pauses every effect (WCAG 2.2.2). */
.ann-row:is(:hover, :focus-within),
.ann-row:is(:hover, :focus-within) .ann-bg,
.ann-row:is(:hover, :focus-within) .ann-go,
.ann-row:is(:hover, :focus-within) .ann-sweep::before,
.ann-row:is(:hover, :focus-within) .ann-glint::after,
.ann-row:is(:hover, :focus-within) .ann-icon-wrap::after {
  animation-play-state: paused;
}
/* Reduced motion: none at all (the global rule only shortens animations, which would make these loops flicker). */
@media (prefers-reduced-motion: reduce) {
  .ann-row,
  .ann-bg,
  .ann-go,
  .ann-sweep::before,
  .ann-glint::after,
  .ann-icon-wrap::after {
    animation: none !important;
  }
  .ann-sweep,
  .ann-glint::after,
  .ann-icon-wrap::after {
    display: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .ann-pic.is-link {
    transition: none;
  }
  .ann-pic.is-link:hover {
    transform: none;
  }
}
</style>
