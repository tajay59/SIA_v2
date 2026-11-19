<script setup lang="ts">
/**
 * S-11 request detail on its own page (phones, links from emails, a reload). A back link to Orders, then
 * the request itself is the shared `RequestSheet` the docket on /requests shows beside the list.
 * One column at every width, with no Files section and no document preview (owner, 2026-11-18): the quote files
 * and the agreement are read on View and sign (S-12).
 */
import { mdiArrowLeft } from '@mdi/js'
import { useRoute } from 'vue-router'
import RequestSheet from '../../../components/RequestSheet.vue'

definePage({ meta: { guard: 'customer', title: 'Request' } })
const route = useRoute('/requests/[id]/')
</script>

<template>
  <div class="request-page">
    <div class="body">
      <router-link to="/requests" class="back"><v-icon :icon="mdiArrowLeft" size="18" aria-hidden="true" />Orders</router-link>
      <RequestSheet :id="route.params.id" :level="1" set-title />
    </div>
  </div>
</template>

<style scoped>
.body {
  max-width: 960px;
  margin: 0 auto;
  padding: var(--sp-4) var(--sp-4) var(--sp-12);
}
/* Back to the list: a quiet link above the request (the empty navy band it replaced said nothing else). */
.back {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-1);
  min-height: 32px;
  margin-bottom: var(--sp-3);
  font-size: 14px;
  font-weight: 500;
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
}
.back:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
/* Phones: Decline / Cancel end the page; keep them clear of the bottom bar and toasts. */
@media (max-width: 959.98px) {
  .body {
    padding-bottom: 120px;
  }
}
</style>
