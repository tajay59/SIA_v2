<script setup lang="ts">
/**
 * Sign-in pages (impeccable 2026-11-16, round 2: the category-standard split sign-in, owner's choice; quality bar
 * Stripe / Linear / Notion; brief packages/web-app/.impeccable/surfaces/src-components-authcard-vue.md).
 * Left: one large picture (or silent looping video) inset in a frame, with optional `steps` over its foot
 * (the way to an approved account, on its own plate); SIA also puts the white CIMH crest there, bottom right. Right: the
 * form column: crest + app name (SIA: the SIA mark alone, centred), heading, one line, the form,
 * footer links. SHOP is light and daytime, SIA dark and night-time, whatever theme is stored.
 * Phones: the picture becomes a band on top. Motion between sign-in pages: auth-motion.ts.
 */
import { computed, onMounted, ref } from 'vue'
import { color } from '@cimh/web-ui'
import logo from '../assets/cimh-logo-blue.webp'
import logoWhite from '../assets/cimh-logo-white.webp'
import siaMark from '../assets/brand/sia-mark.svg'
import { useAppName } from '../bootstrap'
import { authMedia, takeArrival } from '../auth-motion'

/** `steps`: the way to an approved account (sign-up), drawn on the picture (desktop) or under the form (phones). */
defineProps<{ title: string; subtitle?: string; width?: number; steps?: string[] }>()
const sia = useAppName() === 'sia'
const media = authMedia(sia ? 'sia' : 'shop')
const arrival = takeArrival()

/*
 * Colours from the Design Brief tokens (one source; was a copy in hex). Fixed per app, whatever theme is stored:
 * SHOP light (white side), SIA dark (graphite page ground #0D1117 = dark `bg`, not SIA's console surface).
 */
const tone = sia
  ? { ink: color.dark.ink, ink2: color.dark['ink-muted'], side: color.dark.bg, frame: color.dark.surface, line: color.dark.hairline }
  : { ink: color.light.ink, ink2: color.light['ink-muted'], side: color.light.surface, frame: color.light['surface-2'], line: color.light.hairline }
const palette = { '--ink': tone.ink, '--ink-2': tone.ink2, '--side': tone.side, '--frame': tone.frame, '--line': tone.line }

/*
 * Which width the browser needs: phones show a 200 px band as wide as the screen; desktop crops the picture to a
 * tall panel, so a landscape photo is drawn about 1.5 × the panel's height wide, a 3:4 still as wide as the panel.
 */
const sizes = media.generated
  ? '(max-width: 959.98px) calc(100vw - 24px), 50vw'
  : '(max-width: 959.98px) calc(100vw - 24px), calc(150vh - 48px)'

// Video only when motion is welcome; a pause control for anything that moves longer than 5 s (WCAG 2.2.2).
const video = ref<HTMLVideoElement | null>(null)
const playing = ref(false)
const reduced = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
const showVideo = computed(() => !!media.video && !reduced)
function toggleVideo() {
  const v = video.value
  if (!v) return
  if (v.paused) void v.play().catch(() => undefined)
  else v.pause()
}
onMounted(() => {
  if (video.value) void video.value.play().catch(() => undefined)
})
</script>

<template>
  <div class="auth" :class="[sia ? 'sia' : 'shop', `arrive-${arrival}`]" :style="palette">
    <aside class="visual">
      <div class="frame">
        <video
          v-if="showVideo"
          ref="video"
          class="media"
          :poster="media.still"
          :src="media.video!"
          muted
          loop
          playsinline
          aria-hidden="true"
          @play="playing = true"
          @pause="playing = false"
        />
        <img
          v-else
          :src="media.still"
          :srcset="media.srcset"
          :sizes="media.srcset ? sizes : undefined"
          alt=""
          class="media"
          :class="{ legacy: !media.generated }"
          fetchpriority="high"
          decoding="async"
        />
        <div class="scrim" />
        <div class="visual-foot">
          <div class="foot-start">
            <ol v-if="steps?.length" class="steps on-photo">
              <li v-for="s in steps" :key="s">{{ s }}</li>
            </ol>
            <span class="caption">{{ media.caption }}</span>
          </div>
          <!-- SIA: the institute's crest sits on the picture, bottom right; the form side carries only the SIA mark. -->
          <img v-if="sia" :src="logoWhite" alt="Caribbean Institute for Meteorology and Hydrology" width="396" height="124" class="crest on-photo" />
        </div>
        <button v-if="showVideo" type="button" class="media-btn" :aria-pressed="!playing" @click="toggleVideo">
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
            <path v-if="!playing" d="M8 5v14l11-7z" fill="currentColor" />
            <path v-else d="M7 5h4v14H7zm6 0h4v14h-4z" fill="currentColor" />
          </svg>
          {{ playing ? 'Pause video' : 'Play video' }}
        </button>
      </div>
    </aside>

    <v-theme-provider :theme="sia ? 'cimhDark' : 'cimhLight'" with-background class="side-theme">
    <!-- Not <main>: the app shell's v-main#main is the page's one main landmark (skip link target). -->
    <div class="side">
      <div class="column" :style="{ maxWidth: `${width ? Math.min(width - 80, 460) : 400}px` }">
      <header v-if="sia" class="brand sia-brand">
        <router-link to="/" class="brand-link" aria-label="SIA home">
          <img :src="siaMark" alt="" width="96" height="96" class="sia-mark" />
        </router-link>
      </header>
      <header v-else class="brand">
        <router-link to="/" class="brand-link" aria-label="Home">
          <img :src="logo" alt="CIMH" width="176" height="55" class="crest" />
        </router-link>
        <span class="brand-app">CIMH Stores</span>
      </header>

        <div class="words">
          <h1 id="auth-title" class="title">{{ title }}</h1>
          <p v-if="subtitle" class="subtitle">{{ subtitle }}</p>
        </div>
        <div class="form">
          <slot />
        </div>
        <div v-if="$slots.footer" class="foot">
          <slot name="footer" />
        </div>
        <ol v-if="steps?.length" class="steps on-panel">
          <li v-for="s in steps" :key="s">{{ s }}</li>
        </ol>
      </div>

      <p class="legal">Caribbean Institute for Meteorology and Hydrology · Barbados</p>
    </div>
    </v-theme-provider>
  </div>
</template>

<style scoped>
/* --ink, --ink-2, --side, --frame, --line come from the tokens (script, `palette`). */
.auth {
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  background: var(--side);
  color: var(--ink);
}
/* The picture, inset in a frame like a print on a mat. */
.visual {
  padding: 16px;
  background: var(--side);
  min-height: 100vh;
  position: sticky;
  top: 0;
  height: 100vh;
}
.frame {
  position: relative;
  height: 100%;
  border-radius: 12px;
  box-shadow: 0 24px 48px -28px rgba(8, 20, 32, 0.45);
  view-transition-name: auth-visual;
  overflow: hidden;
  background: var(--frame);
  isolation: isolate;
}
.media {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.arrive-load .media {
  animation: settle 1400ms var(--ease-out) both;
}
/* The stand-in photo is landscape and busy; calm it until the generated picture arrives. */
.media.legacy {
  object-position: 55% 50%;
}
/* From opacity 0 on purpose: measured 2026-11-26, Chromium counts LCP from the fade's first visible frame, so a
   visible start (0.4/0.6) gained nothing (SHOP build, 4× CPU: same median). */
@keyframes settle {
  from {
    opacity: 0;
    transform: scale(1.04);
  }
}
.scrim {
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, transparent 55%, rgba(8, 20, 32, 0.72) 100%);
  pointer-events: none;
}
.visual-foot {
  position: absolute;
  left: 32px;
  right: 32px;
  bottom: 32px;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  color: #fff;
}
.foot-start {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 24px;
  min-width: 0;
}
/* On the picture's darkest part (the scrim's foot); a soft shadow keeps it clear over a light patch. */
.crest.on-photo {
  width: 396px;
  max-width: 100%;
  margin-left: auto;
  filter: drop-shadow(0 1px 6px rgba(8, 20, 32, 0.6));
}
/*
 * The steps: one list, two looks. On the picture it sits on its own dark plate, so its contrast does not depend
 * on the photo (at .68 white text stays above 4.5:1 even over a white sky; the scrim alone gave ~3.5:1 on the
 * first line). On phones it is a panel under the form, in the side's tokens.
 */
.steps {
  margin: 0;
  list-style: none;
  counter-reset: step;
  display: flex;
  flex-direction: column;
  gap: 12px;
  font-size: 15px;
  line-height: 22px;
}
.steps li {
  counter-increment: step;
  display: grid;
  grid-template-columns: 28px 1fr;
  gap: 12px;
  text-wrap: pretty;
}
.steps li::before {
  content: counter(step);
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  margin-top: -3px;
  border-radius: 50%;
  border: 1px solid var(--step-ring);
  font-size: 13px;
  font-weight: 700;
  color: var(--step-num);
}
.steps.on-photo {
  --step-ring: rgba(255, 255, 255, 0.5);
  --step-num: #fff;
  max-width: 44ch;
  padding: 20px;
  border-radius: 12px;
  background: rgba(8, 20, 32, 0.68);
  backdrop-filter: blur(8px);
  color: rgba(255, 255, 255, 0.92);
  view-transition-name: auth-note;
}
.steps.on-panel {
  --step-ring: var(--line);
  --step-num: var(--ink);
  display: none;
  padding: 16px;
  border-radius: 12px;
  background: var(--frame);
  color: var(--ink-2);
}
.caption {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(8, 20, 32, 0.55);
  backdrop-filter: blur(6px);
  font-size: 12px;
  font-weight: 600;
  color: #fff;
}
.media-btn {
  position: absolute;
  top: 16px;
  right: 16px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 0 12px;
  border-radius: 999px;
  border: 0;
  background: rgba(8, 20, 32, 0.55);
  color: #fff;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  backdrop-filter: blur(6px);
}
.media-btn:focus-visible,
.brand-link:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 3px;
}

/* The form side. */
.side-theme {
  background: var(--side) !important;
  color: var(--ink);
}
.side {
  display: grid;
  grid-template-rows: auto 1fr auto;
  padding: 32px clamp(24px, 5vw, 80px);
  min-height: 100vh;
}
.brand {
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.brand-link {
  border-radius: 4px;
  display: inline-flex;
}
.crest {
  width: 176px;
  height: auto;
  display: block;
}
.sia-brand {
  justify-content: center;
}
.sia-mark {
  width: 96px;
  height: 96px;
  display: block;
}
.brand-app {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-2);
}
/* Anchored at a fixed top offset, so heading, tabs and fields stay put between sign-up steps. */
.column {
  width: 100%;
  justify-self: center;
  align-self: start;
  padding: clamp(16px, 5vh, 56px) 0 32px;
  display: flex;
  flex-direction: column;
  gap: 32px;
}
.words {
  display: flex;
  flex-direction: column;
  gap: 8px;
  view-transition-name: auth-words;
}
.title {
  margin: 0;
  font-size: 32px;
  line-height: 40px;
  font-weight: 700;
  letter-spacing: -0.02em;
  text-wrap: balance;
}
.subtitle {
  margin: 0;
  font-size: 16px;
  line-height: 24px;
  color: var(--ink-2);
  text-wrap: pretty;
}
.form {
  view-transition-name: auth-form;
}
.foot {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 24px;
  border-top: 1px solid var(--line);
  font-size: 14px;
  line-height: 22px;
  color: var(--ink-2);
  view-transition-name: auth-foot;
}
.legal {
  margin: 0;
  font-size: 12px;
  line-height: 16px;
  color: var(--ink-2);
  text-align: center;
  text-wrap: balance;
}

/* Entrance on a direct load (and between sign-in pages without View Transitions): the column rises in. */
.arrive-load :is(.words, .form, .foot),
.arrive-plain :is(.words, .form, .foot) {
  animation: rise 640ms var(--ease-out) both;
}
.arrive-load .form,
.arrive-plain .form {
  animation-delay: 80ms;
}
.arrive-load .foot,
.arrive-plain .foot {
  animation-delay: 160ms;
}
@keyframes rise {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
}

/* Tablets and phones: the picture becomes a band on top. */
@media (max-width: 959.98px) {
  .auth {
    grid-template-columns: minmax(0, 1fr);
  }
  .visual {
    position: static;
    height: auto;
    min-height: 0;
    padding: 12px 12px 0;
  }
  .frame {
    height: 200px;
    box-shadow: none;
  }
  .steps.on-photo {
    display: none;
  }
  .steps.on-panel {
    display: flex;
  }
  .side {
    min-height: 0;
    padding: 16px 16px 32px;
  }
  .crest {
    width: 144px;
  }
  .visual-foot {
    left: 16px;
    right: 16px;
    bottom: 16px;
    gap: 12px;
  }
  .crest.on-photo {
    width: 288px;
  }
  .sia-mark {
    width: 80px;
    height: 80px;
  }
  .column {
    padding: 8px 0 24px;
    gap: 24px;
  }
  .title {
    font-size: 26px;
    line-height: 32px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .media,
  .words,
  .form,
  .foot {
    animation: none;
  }
}
</style>

<style>
/* Between sign-in pages (auth-motion.ts): the picture holds still; words lift out and settle in; the form morphs. */
::view-transition-old(root),
::view-transition-new(root) {
  animation-duration: 160ms;
}
/* The picture is the stage: it holds still. */
::view-transition-group(auth-visual),
::view-transition-new(auth-visual) {
  animation: none;
}
::view-transition-old(auth-visual) {
  display: none;
}
::view-transition-group(auth-form),
::view-transition-group(auth-foot),
::view-transition-group(auth-words) {
  animation-duration: 420ms;
  animation-timing-function: cubic-bezier(0.16, 1, 0.3, 1);
}
::view-transition-old(auth-words),
::view-transition-old(auth-form),
::view-transition-old(auth-foot),
::view-transition-old(auth-note) {
  animation: 160ms ease-in both auth-out;
}
::view-transition-new(auth-words),
::view-transition-new(auth-note) {
  animation: 440ms cubic-bezier(0.16, 1, 0.3, 1) 100ms both auth-in;
}
::view-transition-new(auth-form),
::view-transition-new(auth-foot) {
  animation: 440ms cubic-bezier(0.16, 1, 0.3, 1) 160ms both auth-in;
}
@keyframes auth-out {
  to {
    opacity: 0;
    transform: translateY(-8px);
  }
}
@keyframes auth-in {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
}
</style>
