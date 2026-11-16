<script setup lang="ts">
/** S-02 catalogue. */
import CatalogueBrowser from '../../components/CatalogueBrowser.vue'

definePage({ meta: { guard: 'public', title: 'Catalogue' } })
</script>

<template>
  <CatalogueBrowser
    title="Equipment and Spares"
    intro="Meteorological and radar instruments and spares. Prices are quoted when you send a request."
  />
</template>
