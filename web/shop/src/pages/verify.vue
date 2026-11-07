<script setup lang="ts">
/** S-14 verify email → S-15 awaiting approval (members) or S-16 with "account active" (@cimh.edu.bb). */
import { type AccountStatus, AuthCard, VerifyForm } from '@cimh/web-app'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

definePage({ meta: { guard: 'public', title: 'Verify your email', layout: 'bare' } })

const route = useRoute()
const router = useRouter()
const email = computed(() => (typeof route.query.email === 'string' ? route.query.email : ''))

function verified(status: AccountStatus, address: string) {
  if (status === 'ACTIVE') void router.replace({ path: '/login', query: { notice: 'account-active', email: address } })
  else void router.replace('/pending-approval')
}
</script>

<template>
  <AuthCard title="Check your email" subtitle="Enter the code we sent to finish creating your account.">
    <VerifyForm :email="email || undefined" :editable-email="!email" @verified="verified" />
    <template #footer>
      <span>Wrong address? <router-link to="/signup">Sign up again</router-link></span>
    </template>
  </AuthCard>
</template>
