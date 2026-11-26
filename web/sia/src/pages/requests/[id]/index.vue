<script setup lang="ts">
/**
 * A-03 request on its own page: deep links, email links and phones. On the desk (A-02) the same view opens
 * next to the queue (`?open=<id>`); both use components/RequestView.vue.
 */
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import RequestView from '../../../components/RequestView.vue'
import { deskMemory } from '../../../desk-memory'
import { BTN } from '../../../request-queue'

definePage({ meta: { guard: 'staff', title: 'Request', ownHeading: true } })
const route = useRoute('/requests/[id]/')
const router = useRouter()

// Back on the desk, this request stays selected (owner 2026-11-24).
watch(
  () => route.params.id,
  (id) => {
    if (id) deskMemory.selected = id
  },
  { immediate: true },
)
// "Orders" returns to the desk as it was left: same tab, filters, open request (deskMemory.query).
const desk = computed(() => router.resolve({ path: '/requests', query: deskMemory.query ?? {} }))
const DESK_URL = /^\/requests\/?(\?|$)/
function toDesk(e: MouseEvent) {
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return
  e.preventDefault()
  // Came straight from the desk: step back (same as the browser's Back, no extra history entry).
  const back = (window.history.state as { back?: unknown } | null)?.back
  if (typeof back === 'string' && DESK_URL.test(back)) router.back()
  else void router.push(desk.value)
}
</script>

<template>
  <div class="req-page">
    <nav class="crumbs" aria-label="Breadcrumb">
      <v-btn :href="desk.href" variant="text" class="m3" :prepend-icon="BTN.back" @click="toDesk">Orders</v-btn>
      <v-btn :to="{ path: '/requests', query: { ...deskMemory.query, open: route.params.id } }" variant="text" class="m3" :prepend-icon="BTN.list">Open beside the list</v-btn>
    </nav>
    <h1 class="sr-only">Request {{ route.params.id }}</h1>
    <!-- No border: the request shares the page's edges. The wrapper stays, it carries the request-pane morph. -->
    <div class="frame">
      <RequestView :id="route.params.id" />
    </div>
  </div>
</template>

<style scoped>
.req-page {
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
  min-width: 0;
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
