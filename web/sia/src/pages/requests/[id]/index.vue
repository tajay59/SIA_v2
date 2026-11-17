<script setup lang="ts">
/**
 * A-03 request on its own page: deep links, email links and phones. On the desk (A-02) the same view opens
 * next to the queue (`?open=<id>`); both use components/RequestView.vue.
 */
import { useRoute } from 'vue-router'
import RequestView from '../../../components/RequestView.vue'
import { BTN } from '../../../request-queue'

definePage({ meta: { guard: 'staff', title: 'Request', ownHeading: true } })
const route = useRoute('/requests/[id]/')
</script>

<template>
  <div class="req-page">
    <nav class="crumbs" aria-label="Breadcrumb">
      <v-btn to="/requests" variant="text" class="m3" :prepend-icon="BTN.back">Orders</v-btn>
      <v-btn :to="{ path: '/requests', query: { open: route.params.id } }" variant="text" class="m3" :prepend-icon="BTN.list">Open beside the list</v-btn>
    </nav>
    <h1 class="sr-only">Request {{ route.params.id }}</h1>
    <div class="frame">
      <RequestView :id="route.params.id" />
    </div>
  </div>
</template>

<style scoped>
.req-page {
  width: 100%;
  max-width: 1500px;
  margin-inline: auto;
  padding: var(--sp-4) var(--sp-6) var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.crumbs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
  margin-left: -8px;
}
.frame {
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-background));
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
@media (max-width: 599.98px) {
  .req-page {
    padding: var(--sp-3) var(--sp-3) var(--sp-4);
  }
  .crumbs .v-btn:last-child {
    display: none;
  }
}
</style>
