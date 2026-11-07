<script setup lang="ts">
/** A-21 profile. */
import { ProfileView } from '@cimh/web-app'

definePage({ meta: { guard: 'staff', title: 'Profile' } })
</script>

<template>
  <div class="page"><ProfileView after-logout="/login" /></div>
</template>
