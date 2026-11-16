<script setup lang="ts">
/**
 * Sign-in pages ("Reception desk + pass", impeccable 2026-11-16; brief packages/web-app/.impeccable/surfaces/
 * src-components-authcard-vue.md). Left: the reception wall saying where you are (CIMH crest, page title, one
 * line, and an optional `wall` slot, e.g. the steps to an approved account). Right: the pass you are handed,
 * on the page ground. SHOP issues a white visitor pass on a navy wall; SIA a navy staff card on a graphite wall,
 * so the two apps never look alike. Phones: the wall becomes a header band above the pass. No top bar on these
 * pages, so the crest links home.
 */
import logoWhite from '../assets/cimh-logo-white.webp'
import siaMark from '../assets/brand/sia-mark.svg'
import { useAppName } from '../bootstrap'

defineProps<{ title: string; subtitle?: string; width?: number }>()
const sia = useAppName() === 'sia'
</script>

<template>
  <div class="desk" :class="{ sia }">
    <section class="wall" aria-labelledby="auth-title">
      <router-link to="/" class="crest-link" aria-label="Home"><img :src="logoWhite" alt="CIMH" width="200" height="62" class="crest" /></router-link>
      <div class="wall-text">
        <h1 id="auth-title" class="wall-title">{{ title }}</h1>
        <p v-if="subtitle" class="wall-sub">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.wall" class="wall-extra"><slot name="wall" /></div>
    </section>

    <div class="ground">
      <!-- The pass carries its own theme: SHOP white visitor pass, SIA navy staff card, whatever theme is stored. -->
      <v-theme-provider :theme="sia ? 'cimhDark' : 'cimhLight'">
        <article class="pass" :class="sia ? 'v-theme--cimhDark' : 'v-theme--cimhLight'" :style="{ maxWidth: `${width ?? 460}px` }">
          <div class="stamp">
            <template v-if="sia">
              <img :src="siaMark" alt="" width="28" height="28" />
              <span class="stamp-kind">Staff card</span>
              <span class="stamp-app">SIA · CIMH Stores staff app</span>
            </template>
            <template v-else>
              <span class="stamp-kind">Visitor pass</span>
              <span class="stamp-app">CIMH Stores</span>
            </template>
          </div>
          <div class="pass-body">
            <slot />
          </div>
          <div v-if="$slots.footer" class="pass-foot">
            <slot name="footer" />
          </div>
        </article>
      </v-theme-provider>
    </div>
  </div>
</template>

<style scoped>
.desk {
  --wall: #0a2e4a;
  --wall-rule: #0084c8;
  /* Resolved here, in the page theme: the slot shows the ground through the pass whatever theme the pass has. */
  --ground: rgb(var(--v-theme-surface-variant));
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 5fr) minmax(0, 7fr);
  background: rgb(var(--v-theme-surface-variant));
}
.desk.sia {
  --wall: #0d1117;
  --wall-rule: #30363d;
}

/* The wall: where you are. */
.wall {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  background: var(--wall);
  color: #fff;
  border-right: 1px solid rgba(255, 255, 255, 0.12);
  padding: var(--sp-12, 48px) clamp(24px, 4vw, 64px);
  display: flex;
  flex-direction: column;
  gap: var(--sp-10, 40px);
}
.wall::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: -1;
  background: url('../assets/legacy/gears.webp') center bottom / 160% auto no-repeat;
  filter: invert(1);
  mix-blend-mode: screen;
  opacity: 0.2;
}
.sia .wall::before {
  opacity: 0.1;
}
.crest {
  width: 200px;
  height: auto;
  display: block;
}
.crest-link {
  align-self: flex-start;
  border-radius: 4px;
}
.crest-link:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 4px;
}
.wall-text {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.wall-title {
  font-size: clamp(30px, 3.4vw, 46px);
  line-height: 1.1;
  font-weight: 700;
  letter-spacing: -0.02em;
  margin: 0;
  max-width: 14ch;
  text-wrap: balance;
}
.wall-sub {
  margin: 0;
  max-width: 40ch;
  font-size: 17px;
  line-height: 26px;
  color: rgba(255, 255, 255, 0.84);
}
.wall-extra {
  margin-bottom: auto;
}

/* The ground and the pass you are handed. */
.ground {
  display: grid;
  place-items: center;
  padding: var(--sp-12, 48px) var(--sp-6);
}
.pass {
  position: relative;
  width: 100%;
  border-radius: 16px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  box-shadow: 0 18px 40px -20px rgba(15, 26, 36, 0.35), 0 2px 6px -2px rgba(15, 26, 36, 0.12);
  padding: 44px var(--sp-8) var(--sp-8);
}
/* The lanyard slot cut through the top of the pass. */
.pass::before {
  content: '';
  position: absolute;
  top: 16px;
  left: 50%;
  width: 56px;
  height: 8px;
  margin-left: -28px;
  border-radius: 8px;
  background: var(--ground);
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.25);
}
.sia .pass {
  background: #0a2e4a;
  border-color: #1f4b6e;
}
.stamp {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-1) var(--sp-3);
  padding-bottom: var(--sp-4);
  margin-bottom: var(--sp-6);
  border-bottom: 1px dashed rgba(var(--v-border-color), var(--v-border-opacity));
}
.sia .stamp {
  border-bottom-color: #1f4b6e;
}
.stamp-kind {
  font-size: 12px;
  line-height: 16px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 4px 8px;
  border-radius: 4px;
  background: #0a2e4a;
  color: #fff;
}
.sia .stamp-kind {
  background: #0084c8;
  color: #0d1117;
}
.stamp-app {
  font-size: 14px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.pass-foot {
  margin-top: var(--sp-6);
  padding-top: var(--sp-4);
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  font-size: 15px;
  line-height: 22px;
}
.sia .pass-foot {
  border-top-color: #1f4b6e;
}

/* Tablets and phones: the wall becomes a header band above the pass. */
@media (max-width: 959.98px) {
  .desk {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto 1fr;
  }
  .wall {
    border-right: 0;
    border-bottom: 4px solid var(--wall-rule);
    padding: var(--sp-6) var(--sp-4) var(--sp-8);
    gap: var(--sp-6);
  }
  .crest {
    width: 150px;
  }
  .wall-text {
    margin-top: 0;
  }
  .wall-extra {
    display: none;
  }
  .ground {
    place-items: start center;
    padding: var(--sp-6) var(--sp-4) var(--sp-10, 40px);
  }
}
@media (max-width: 599.98px) {
  .pass {
    padding: 40px var(--sp-4) var(--sp-6);
  }
  .wall-sub {
    font-size: 15px;
    line-height: 22px;
  }
}
</style>
