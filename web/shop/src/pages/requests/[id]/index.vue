<script setup lang="ts">
/**
 * S-11 request detail on its own page (phones, links from emails, a reload). The navy band names the place
 * ("Requests"), the request itself is the shared `RequestSheet` the docket on /requests shows beside the list.
 */
import { mdiArrowLeft } from '@mdi/js'
import { useRoute } from 'vue-router'
import RequestSheet from '../../../components/RequestSheet.vue'

definePage({ meta: { guard: 'customer', title: 'Request' } })
const route = useRoute('/requests/[id]/')
</script>

<template>
  <div class="request-page">
    <div class="band">
      <div class="band-in">
        <v-btn to="/requests" variant="text" :prepend-icon="mdiArrowLeft" class="back">Orders</v-btn>
      </div>
    </div>
    <div class="body">
      <RequestSheet :id="route.params.id" :level="1" set-title />
    </div>
  </div>
</template>

<style scoped>
.band {
  background: #0a2e4a;
  color: #fff;
  border-bottom: 4px solid #0084c8;
}
.band-in {
  max-width: 960px;
  margin: 0 auto;
  padding: var(--sp-3) var(--sp-4);
}
.back {
  color: #fff;
  margin-left: calc(-1 * var(--sp-3));
}
.body {
  max-width: 960px;
  margin: 0 auto;
  padding: var(--sp-6) var(--sp-4) var(--sp-12);
}
/* Phones: Decline / Cancel end the page; keep them clear of the bottom bar and toasts. */
@media (max-width: 959.98px) {
  .body {
    padding-bottom: 120px;
  }
}
</style>
