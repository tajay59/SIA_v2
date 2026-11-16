<script setup lang="ts">
/**
 * One section of the profile (ProfileView). SHOP: an outlined card with a title. SIA: a Graphite Console
 * panel (web/sia/DESIGN.md): 1 px seam, 4 px corners, a 44 px head bar with the panel's small uppercase
 * title and its control on the right (`.console-head` / `.console-title` from web/sia/src/console.css).
 */
import { useAppName } from '../bootstrap'

defineProps<{ title: string }>()
const sia = useAppName() === 'sia'
</script>

<template>
  <section v-if="sia" class="psec">
    <header class="console-head">
      <h2 class="console-title">{{ title }}</h2>
      <slot name="action" />
    </header>
    <div class="psec-body"><slot /></div>
  </section>
  <v-card v-else>
    <v-card-title v-if="$slots.action" class="row">
      <span class="t-h3">{{ title }}</span>
      <span class="spacer" />
      <slot name="action" />
    </v-card-title>
    <v-card-title v-else class="t-h3">{{ title }}</v-card-title>
    <v-card-text><slot /></v-card-text>
  </v-card>
</template>

<style scoped>
.psec {
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
}
.psec-body {
  padding: var(--sp-4);
}
</style>
