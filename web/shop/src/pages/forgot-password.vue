<script setup lang="ts">
/** S-17 → S-18, always (no account enumeration). */
import { AuthCard, ForgotForm } from '@cimh/web-app'
import { useRoute, useRouter } from 'vue-router'

definePage({ meta: { guard: 'public', title: 'Forgot password', layout: 'bare' } })

const route = useRoute()
const router = useRouter()
</script>

<template>
  <AuthCard title="Reset your password" subtitle="We'll email you a 6-digit code.">
    <ForgotForm
      :initial-email="typeof route.query.email === 'string' ? route.query.email : ''"
      @sent="(email: string) => router.push({ path: '/reset-password', query: { email } })"
    />
    <template #footer>
      <router-link to="/login">Back to log in</router-link>
    </template>
  </AuthCard>
</template>
