<script setup lang="ts">
/** S-18 code + new password → S-16 "Password changed" (J-11; all sessions are revoked). */
import { AuthCard, ResetForm } from '@cimh/web-app'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

definePage({ meta: { guard: 'public', title: 'Choose a new password', layout: 'bare' } })

const route = useRoute()
const router = useRouter()
/** From S-17; "Send a new code" takes it back there, so it is not typed twice. */
const email = computed(() => (typeof route.query.email === 'string' && route.query.email) || undefined)
</script>

<template>
  <AuthCard title="Choose a new password">
    <ResetForm
      :email="email"
      @done="(email: string) => router.replace({ path: '/login', query: { notice: 'password-changed', email } })"
    />
    <template #footer>
      <router-link :to="{ path: '/forgot-password', query: email ? { email } : {} }">Send a new code</router-link>
    </template>
  </AuthCard>
</template>
