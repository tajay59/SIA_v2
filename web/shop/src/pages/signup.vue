<script setup lang="ts">
/** S-13 sign up → S-14 verify: three steps beside the picture; the picture lists the way to an approved account. */
import { AuthCard, SignupForm } from '@cimh/web-app'
import { ref } from 'vue'

definePage({ meta: { guard: 'public', title: 'Sign up', layout: 'bare' } })
const step = ref(0)
const steps = [
  'Fill in the form',
  'Confirm your email with a code',
  'A CIMH administrator approves the account, usually within two working days',
  'Send requests',
]
</script>

<template>
  <AuthCard title="Create your account" subtitle="Request instruments and spares from CIMH." :width="520" :steps="steps">
    <SignupForm v-model:step="step" />
    <template #footer>
      <span>Already have an account? <router-link to="/login">Log in</router-link></span>
    </template>
  </AuthCard>
</template>
