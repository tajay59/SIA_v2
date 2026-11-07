<script setup lang="ts">
/** S-04 Pro Bono items: free items from CIMH projects; some have a limit per request. */
import CatalogueBrowser from '../components/CatalogueBrowser.vue'

definePage({ meta: { guard: 'public', title: 'Pro Bono items' } })
</script>

<template>
  <CatalogueBrowser
    probono
    title="Pro Bono items"
    intro="Items CIMH supplies free of charge through its projects. Request them like any other item; some have a limit per request."
  />
</template>
