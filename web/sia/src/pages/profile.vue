<script setup lang="ts">
/** A-21 profile. */
import { ProfileView } from '@cimh/web-app'

definePage({ meta: { guard: 'staff', title: 'Profile', ownHeading: true } })
</script>

<template>
  <div class="page"><ProfileView after-logout="/login" /></div>
</template>
