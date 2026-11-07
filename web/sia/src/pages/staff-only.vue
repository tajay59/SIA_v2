<script setup lang="ts">
/** APD §2: a customer opened SIA. */
import { AuthCard, useSession } from '@cimh/web-app'
import { useRouter } from 'vue-router'

definePage({ meta: { guard: 'public', title: 'Staff only', layout: 'bare' } })
const session = useSession()
const router = useRouter()
const shop = import.meta.env.VITE_SHOP_URL ?? 'https://store.hashiz.store'

async function logout() {
  await session.logout()
  await router.replace('/login')
}
</script>

<template>
  <AuthCard title="This app is for CIMH staff" subtitle="Customers request items in CIMH Stores.">
    <div class="stack">
      <v-btn :href="shop" color="primary" size="large" block>Go to CIMH Stores</v-btn>
      <v-btn v-if="session.isLoggedIn" variant="text" block @click="logout">Log out</v-btn>
    </div>
  </AuthCard>
</template>
