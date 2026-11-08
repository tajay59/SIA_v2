<script setup lang="ts">
/** /search?q= (links and bookmarks): search lives on the catalogue page, as in legacy. */
definePage({
  meta: { guard: 'public', title: 'Search' },
  redirect: (to) => ({ path: to.query.probono === 'true' ? '/pro-bono' : '/catalogue', query: { q: to.query.q } }),
})
</script>

<template><div /></template>
