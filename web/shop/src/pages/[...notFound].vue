<script setup lang="ts">
/** S-20 not found (hidden resources look the same as missing ones). */
definePage({ meta: { guard: 'public', title: 'Page not found' } })
</script>

<template>
  <v-container class="page" max-width="720">
    <div class="stack">
      <h1 class="t-h1">Page not found</h1>
      <p class="t-body-lg muted">The page doesn't exist, or you don't have access to it.</p>
      <div class="row"><v-btn to="/" color="primary">Go to the home page</v-btn></div>
    </div>
  </v-container>
</template>
