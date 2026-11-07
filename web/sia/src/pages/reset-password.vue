<script setup lang="ts">
import { AuthCard, ResetForm } from '@cimh/web-app'
import { useRoute, useRouter } from 'vue-router'

definePage({ meta: { guard: 'public', title: 'Choose a new password', layout: 'bare' } })
const route = useRoute()
const router = useRouter()
</script>

<template>
  <AuthCard title="Choose a new password">
    <ResetForm
      :email="typeof route.query.email === 'string' ? route.query.email : undefined"
      @done="(email: string) => router.replace({ path: '/login', query: { notice: 'password-changed', email } })"
    />
    <template #footer><router-link to="/forgot-password">Send a new code</router-link></template>
  </AuthCard>
</template>
