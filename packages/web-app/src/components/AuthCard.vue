<script setup lang="ts">
/**
 * Sign-in pages (impeccable 2026-11-16, round 2: the category-standard split sign-in, owner's choice; quality bar
 * Stripe / Linear / Notion; brief packages/web-app/.impeccable/surfaces/src-components-authcard-vue.md).
 * Left: one large picture (or silent looping video) inset in a frame, with an optional `wall` slot over its foot
 * (e.g. the steps to an approved account). Right: the form column: crest + app name, heading, one line, the form,
 * footer links. SHOP is light and daytime, SIA dark and night-time, whatever theme is stored.
 * Phones: the picture becomes a band on top. Motion between sign-in pages: auth-motion.ts.
 */
import { computed, onMounted, ref } from 'vue'
import logo from '../assets/cimh-logo-blue.webp'
import logoWhite from '../assets/cimh-logo-white.webp'
import siaMark from '../assets/brand/sia-mark.svg'
import { useAppName } from '../bootstrap'
import { authMedia, takeArrival } from '../auth-motion'

defineProps<{ title: string; subtitle?: string; width?: number }>()
const sia = useAppName() === 'sia'
const media = authMedia(sia ? 'sia' : 'shop')
const arrival = takeArrival()

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
  <div class="auth" :class="[sia ? 'sia' : 'shop', `arrive-${arrival}`]">
    <aside class="visual" aria-hidden="false">
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
        <img v-else :src="media.still" alt="" class="media" :class="{ legacy: !media.generated }" decoding="async" />
        <div class="scrim" />
        <div class="visual-foot">
          <div v-if="$slots.wall" class="wall-note"><slot name="wall" /></div>
          <span class="caption">{{ media.caption }}</span>
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
    <main class="side">
      <div class="column" :style="{ maxWidth: `${width ? Math.min(width - 80, 460) : 400}px` }">
      <header class="brand">
        <router-link to="/" class="brand-link" aria-label="Home">
          <img :src="sia ? logoWhite : logo" alt="CIMH" width="176" height="55" class="crest" />
        </router-link>
        <span class="brand-app">
          <img v-if="sia" :src="siaMark" alt="" width="20" height="20" />
          {{ sia ? 'SIA · Staff app' : 'CIMH Stores' }}
        </span>
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
        <div v-if="$slots.wall" class="wall-phone"><slot name="wall" /></div>
      </div>

      <p class="legal">Caribbean Institute for Meteorology and Hydrology · Barbados</p>
    </main>
    </v-theme-provider>
  </div>
</template>

<style scoped>
.auth {
  --ink: #0f1a24;
  --ink-2: #4a5a68;
  --side: #ffffff;
  --frame: #eef3f7;
  --line: #dde5eb;
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  background: var(--side);
  color: var(--ink);
}
.auth.sia {
  --ink: #e6edf3;
  --ink-2: #9aa7b4;
  --side: #0d1117;
  --frame: #161b22;
  --line: #262d36;
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
  flex-direction: column;
  align-items: flex-start;
  gap: 24px;
  color: #fff;
}
.wall-note {
  view-transition-name: auth-note;
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
.wall-note :deep(ol) {
  color: rgba(255, 255, 255, 0.92) !important;
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
/* Same button label weight in both apps. */
.form :deep(.v-btn) {
  font-weight: 600;
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
}

/* Entrance on a direct load (and between sign-in pages without View Transitions): the column rises in. */
.wall-phone {
  display: none;
}
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
  .wall-note {
    display: none;
  }
  .wall-phone {
    display: block;
    padding: 16px;
    border-radius: 12px;
    background: var(--frame);
  }
  .wall-phone :deep(ol) {
    color: var(--ink-2) !important;
  }
  .wall-phone :deep(li::before) {
    color: var(--ink) !important;
    border-color: var(--line) !important;
  }
  .side {
    min-height: 0;
    padding: 16px 16px 32px;
  }
  .crest {
    width: 144px;
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
