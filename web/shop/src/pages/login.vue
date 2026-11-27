<script setup lang="ts">
/** S-16 log in → `returnTo` or home. Notices: password changed, account active (from S-14 / S-18). */
import { AuthCard, AuthNotice, LoginForm, safeReturnTo } from '@cimh/web-app'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

definePage({ meta: { guard: 'public', title: 'Log in', layout: 'bare' } })

const route = useRoute()
const router = useRouter()
const NOTICES: Record<string, string> = {
  'password-changed': 'Password changed. Log in with your new password.',
  'account-active': 'Your email is verified and your account is active. Log in to continue.',
}
const notice = computed(() => NOTICES[String(route.query.notice ?? '')])

function done() {
  void router.replace(safeReturnTo(route.query.returnTo, '/'))
}
</script>

<template>
  <AuthCard title="Welcome back" subtitle="Log in to CIMH Stores to browse and request instruments and spares.">
    <AuthNotice v-if="notice" :text="notice" />
    <LoginForm
      verify-path="/verify"
      forgot-path="/forgot-password"
      pending-path="/pending-approval"
      :skip-initial-focus="!!notice"
      :initial-email="typeof route.query.email === 'string' ? route.query.email : ''"
      @success="done"
    />
    <template #footer>
      <span>New to CIMH Stores? <router-link to="/signup">Create an account</router-link></span>
      <span>Trouble logging in? Write to <a href="mailto:info@cimh.edu.bb">info@cimh.edu.bb</a>.</span>
    </template>
  </AuthCard>
</template>
