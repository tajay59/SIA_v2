<script setup lang="ts">
/** Admins must turn on two-step verification before anything else (TR-AUTH-9). */
import { AuthCard, MfaSetup, useSession } from '@cimh/web-app'
import { useRouter } from 'vue-router'

definePage({ meta: { guard: 'staff', title: 'Two-step verification', layout: 'bare' } })
const session = useSession()
const router = useRouter()

async function enabled() {
  // The current token predates MFA; log in again so the new token carries it.
  const email = session.account?.email ?? ''
  await session.logout()
  await router.replace({ path: '/login', query: { notice: 'mfa-enabled', email } })
}
</script>

<template>
  <AuthCard title="Turn on two-step verification" subtitle="Administrators sign in with a password and a code from an authenticator app." :width="520">
    <MfaSetup @enabled="enabled" />
    <template #footer>
      <v-btn variant="text" class="align-self-start" @click="session.logout().then(() => router.replace('/login'))">Log out</v-btn>
    </template>
  </AuthCard>
</template>
