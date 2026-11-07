<script setup lang="ts">
/** S-10 My requests. The request list arrives with order-svc (P5); until then an honest empty state. */
import { mdiClipboardTextOutline } from '@mdi/js'

definePage({ meta: { guard: 'customer', title: 'My requests' } })
</script>

<template>
  <v-container class="page" max-width="1200">
    <div class="page-header"><h1 class="t-h1">My requests</h1></div>
    <v-card class="empty">
      <v-icon :icon="mdiClipboardTextOutline" size="40" class="muted" />
      <h2 class="t-h3">No requests yet</h2>
      <p class="t-body muted prose">Requesting items opens here soon. Your account is ready: you'll be able to add items to a request and follow quotes and deliveries on this page.</p>
    </v-card>
  </v-container>
</template>

<style scoped>
.empty {
  padding: var(--sp-12) var(--sp-6);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-3);
  text-align: center;
}
</style>
