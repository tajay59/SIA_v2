<script setup lang="ts">
/** Verify email (as S-14), for staff who log in before verifying. */
import { AuthCard, VerifyForm } from '@cimh/web-app'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

definePage({ meta: { guard: 'public', title: 'Verify your email', layout: 'bare' } })

const route = useRoute()
const router = useRouter()
const email = computed(() => (typeof route.query.email === 'string' ? route.query.email : ''))
</script>

<template>
  <AuthCard title="Check your email" subtitle="Enter the code we sent to your address.">
    <VerifyForm
      :email="email || undefined"
      :editable-email="!email"
      @verified="(_s: string, address: string) => router.replace({ path: '/login', query: { notice: 'account-active', email: address } })"
    />
  </AuthCard>
</template>
