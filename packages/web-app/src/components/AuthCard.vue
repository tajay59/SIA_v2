<script setup lang="ts">
/** Centred card for the public account screens (login, sign-up, verify, reset). */
import { computed } from 'vue'
import { useTheme } from 'vuetify'
import logoBlue from '../assets/cimh-logo-blue.webp'
import logoWhite from '../assets/cimh-logo-white.webp'

defineProps<{ title: string; subtitle?: string; width?: number }>()
const theme = useTheme()
const logo = computed(() => (theme.current.value.dark ? logoWhite : logoBlue))
</script>

<template>
  <div class="auth-wrap">
    <v-card class="auth-card" :style="{ maxWidth: `${width ?? 440}px` }">
      <div class="auth-head">
        <img :src="logo" alt="CIMH" width="130" height="40" class="auth-logo" />
        <h1 class="t-h2">{{ title }}</h1>
        <p v-if="subtitle" class="t-body muted prose">{{ subtitle }}</p>
      </div>
      <div class="auth-body">
        <slot />
      </div>
      <div v-if="$slots.footer" class="auth-foot t-body">
        <slot name="footer" />
      </div>
    </v-card>
  </div>
</template>

<style scoped>
.auth-wrap {
  min-height: calc(100vh - 64px);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: var(--sp-12) var(--sp-4);
}
.auth-card {
  width: 100%;
  padding: var(--sp-8) var(--sp-6);
}
.auth-head {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  margin-bottom: var(--sp-6);
}
.auth-logo {
  height: auto;
  width: 100%;
  max-width: 220px;
  margin-bottom: var(--sp-4);
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
