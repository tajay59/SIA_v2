<script setup lang="ts">
/** S-02 catalogue. */
import CatalogueBrowser from '../../components/CatalogueBrowser.vue'

definePage({ meta: { guard: 'public', title: 'Catalogue' } })
</script>

<template>
  <CatalogueBrowser
    title="Equipment and Spares"
    intro="Meteorological, radar and hydrological instruments, spares and supplies. Prices are quoted when you send a request."
  />
</template>
