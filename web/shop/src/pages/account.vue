<script setup lang="ts">
/** S-19 profile. */
import { ProfileView, useSession } from '@cimh/web-app'

definePage({ meta: { guard: 'auth', title: 'Profile' } })
const session = useSession()
</script>

<template>
  <v-container class="page" max-width="1200">
    <ProfileView after-logout="/" :show-addresses="session.isCustomer" />
  </v-container>
</template>
