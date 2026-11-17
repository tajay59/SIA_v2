<script setup lang="ts">
/**
 * A record id shown short ("ORD…3f9a2c", `shortRef`) with the full id in a tooltip on hover (and on focus when
 * the ref sits in a focusable parent such as a queue row link).
 */
import { shortRef } from '../orders'

defineProps<{ id: string }>()
</script>

<template>
  <span class="short-ref">
    {{ shortRef(id) }}
    <!-- role="tooltip" sits on the overlay root, so the name goes there (axe aria-tooltip-name), as in the SIA drawer. -->
    <v-tooltip activator="parent" location="top" :open-delay="250" content-class="short-ref-tip" :aria-label="id">{{ id }}</v-tooltip>
  </span>
</template>

<style>
.short-ref-tip {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px;
}
</style>
