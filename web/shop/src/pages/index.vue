<script setup lang="ts">
/**
 * S-01 home. Featured products and the Pro Bono teaser need the catalogue (P3); the hero photo comes
 * from the owner (DESIGN_BRIEF §7). Until then: what the store is, how requesting works, sign-up.
 */
import { useSession } from '@cimh/web-app'
import { mdiClipboardCheckOutline, mdiFileDocumentEditOutline, mdiTruckDeliveryOutline } from '@mdi/js'

definePage({ meta: { guard: 'public', title: 'Home' } })
const session = useSession()

const steps = [
  { icon: mdiClipboardCheckOutline, title: 'Request', text: 'Choose instruments, spares or supplies and send one request. Prices are never shown up front.' },
  { icon: mdiFileDocumentEditOutline, title: 'Review the quote', text: 'CIMH quotes each line from its own stock or a supplier. You pick the options, then sign the agreement.' },
  { icon: mdiTruckDeliveryOutline, title: 'Receive', text: 'Follow your request through purchasing and shipping, with tracking, until it is delivered.' },
]
</script>

<template>
  <div>
    <section class="hero">
      <v-container max-width="1200" class="hero-inner">
        <p class="t-label eyebrow">Caribbean Institute for Meteorology and Hydrology</p>
        <h1 class="t-display">Instruments and supplies for the region's weather and water services</h1>
        <p class="t-body-lg muted prose">
          CIMH Stores supplies meteorological, radar and hydrological equipment to national services and partners
          across the Caribbean, from CIMH stock or trusted suppliers.
        </p>
        <div class="row">
          <template v-if="!session.isLoggedIn">
            <v-btn to="/signup" color="primary" size="large">Create an account</v-btn>
            <v-btn to="/login" variant="outlined" size="large">Log in</v-btn>
          </template>
          <v-btn v-else-if="session.isCustomer" to="/requests" color="primary" size="large">My requests</v-btn>
        </div>
      </v-container>
    </section>

    <v-container max-width="1200" class="page stack">
      <h2 class="t-h2">How requesting works</h2>
      <div class="steps">
        <v-card v-for="(s, i) in steps" :key="s.title" class="step">
          <div class="row">
            <v-icon :icon="s.icon" color="primary" size="28" />
            <span class="t-label muted">Step {{ i + 1 }}</span>
          </div>
          <h3 class="t-h3">{{ s.title }}</h3>
          <p class="t-body muted">{{ s.text }}</p>
        </v-card>
      </div>
      <p v-if="session.isCimh" class="t-body muted prose">
        You're signed in with a CIMH account: you can browse, but CIMH staff can't submit requests.
      </p>
    </v-container>
  </div>
</template>

<style scoped>
.hero {
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgb(var(--v-theme-surface));
}
.hero-inner {
  padding: var(--sp-16, 64px) var(--sp-4) var(--sp-12);
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.hero-inner .t-display {
  max-width: 22ch;
}
.eyebrow {
  color: rgb(var(--v-theme-primary));
}
.steps {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: var(--sp-4);
}
.step {
  padding: var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
@media (max-width: 600px) {
  .hero-inner .t-display {
    font-size: 28px;
    line-height: 36px;
  }
}
</style>
