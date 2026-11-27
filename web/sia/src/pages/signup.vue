<script setup lang="ts">
/**
 * SIA sign up (owner, 2026-11-16): CIMH staff create their account here (@cimh.edu.bb only), confirm the email,
 * and an administrator gives the account staff access (until then SIA shows "staff only").
 */
import { AuthCard, SignupForm } from '@cimh/web-app'
import { ref } from 'vue'

definePage({ meta: { guard: 'public', title: 'Sign up', layout: 'bare' } })
const step = ref(0)
const steps = ['Fill in the form with your CIMH email', 'Confirm the email with a code', 'An administrator gives the account staff access']
</script>

<template>
  <AuthCard title="Create a staff account" subtitle="For CIMH staff with a @cimh.edu.bb address." :width="520" :steps="steps">
    <SignupForm v-model:step="step" staff />
    <template #footer>
      <span>Already have an account? <router-link to="/login">Log in</router-link></span>
    </template>
  </AuthCard>
</template>
