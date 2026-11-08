<script setup lang="ts">
/**
 * Sign-in pages (login, sign-up, verify, password reset), same structure as the legacy Login/Signup pages:
 * full-screen photo of a meteorological enclosure (dimmed), the CIMH logo and the page heading on the
 * left, the form in a card on the right. On phones the logo and heading sit on top of the card.
 * There is no top bar on these pages (legacy), so the logo links home.
 */
import { useDisplay } from 'vuetify'
import photo from '../assets/legacy/met-enclosure.webp'
import photoSmall from '../assets/legacy/met-enclosure-800.webp'
import logoWhite from '../assets/cimh-logo-white.webp'

defineProps<{ title: string; subtitle?: string; width?: number }>()
const { mdAndUp } = useDisplay()
</script>

<template>
  <div class="auth">
    <img class="auth-photo" :src="photo" :srcset="`${photoSmall} 800w, ${photo} 1600w`" sizes="100vw" alt="" />
    <div class="auth-shade" />
    <div class="auth-inner">
      <div class="auth-intro">
        <router-link to="/" aria-label="Home"><img :src="logoWhite" alt="CIMH" width="220" height="68" class="auth-logo" /></router-link>
        <h1 class="auth-title">{{ title }}</h1>
        <p v-if="subtitle && mdAndUp" class="auth-sub">{{ subtitle }}</p>
      </div>
      <v-card class="auth-card" :style="{ maxWidth: `${width ?? 440}px` }" variant="flat" color="surface" elevation="8">
        <p v-if="subtitle && !mdAndUp" class="t-body muted mb-4">{{ subtitle }}</p>
        <div class="auth-body">
          <slot />
        </div>
        <div v-if="$slots.footer" class="auth-foot t-body">
          <slot name="footer" />
        </div>
      </v-card>
    </div>
  </div>
</template>

<style scoped>
.auth {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  overflow: hidden;
}
.auth-photo {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.auth-shade {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, rgba(5, 12, 20, 0.78) 0%, rgba(5, 12, 20, 0.45) 55%, rgba(5, 12, 20, 0.3) 100%);
}
.auth-inner {
  position: relative;
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--sp-12, 48px) var(--sp-6);
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 460px);
  gap: var(--sp-12, 48px);
  align-items: center;
}
@media (max-width: 959px) {
  .auth-inner {
    grid-template-columns: minmax(0, 1fr);
    justify-items: center;
    gap: var(--sp-6);
    padding: var(--sp-8) var(--sp-4);
  }
}
.auth-intro {
  color: #fff;
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
@media (max-width: 959px) {
  .auth-intro {
    align-items: center;
    text-align: center;
  }
}
.auth-logo {
  width: 220px;
  height: auto;
}
.auth-title {
  font-size: clamp(30px, 4vw, 48px);
  line-height: 1.1;
  font-weight: 700;
  letter-spacing: -0.02em;
  margin: 0;
  max-width: 16ch;
}
.auth-sub {
  font-size: 18px;
  line-height: 1.55;
  max-width: 46ch;
  margin: 0;
  color: rgba(255, 255, 255, 0.86);
}
.auth-card {
  width: 100%;
  justify-self: end;
  padding: var(--sp-8) var(--sp-6);
  border-radius: 16px;
}
@media (max-width: 959px) {
  .auth-card {
    justify-self: center;
  }
}
.auth-foot {
  margin-top: var(--sp-6);
  padding-top: var(--sp-4);
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
</style>
