<script setup lang="ts">
definePage({ meta: { guard: 'staff', title: 'Not found', ownHeading: true } })
</script>

<template>
  <div class="page stack">
    <h1 class="t-h1">Not found</h1>
    <p class="t-body muted">The page doesn't exist, or you don't have access to it.</p>
    <div class="row"><v-btn to="/" color="primary">Back to the dashboard</v-btn></div>
  </div>
</template>
