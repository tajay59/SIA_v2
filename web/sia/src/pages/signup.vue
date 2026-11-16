<script setup lang="ts">
/**
 * SIA sign up (owner, 2026-11-16): CIMH staff create their account here (@cimh.edu.bb only), confirm the email,
 * and an administrator gives the account staff access (until then SIA shows "staff only").
 */
import { AuthCard, SignupForm } from '@cimh/web-app'
import { ref } from 'vue'

definePage({ meta: { guard: 'public', title: 'Sign up', layout: 'bare' } })
const step = ref(0)
</script>

<template>
  <AuthCard title="Create a staff account" subtitle="For CIMH staff with a @cimh.edu.bb address." :width="520">
    <template #wall>
      <ol class="path">
        <li>Fill in this card with your CIMH email</li>
        <li>Confirm the email with a code</li>
        <li>An administrator gives the account staff access</li>
      </ol>
    </template>
    <SignupForm v-model:step="step" staff />
    <template #footer>
      <span>Already have an account? <router-link to="/login">Log in</router-link></span>
    </template>
  </AuthCard>
</template>

<style scoped>
.path {
  margin: 0;
  padding: 0;
  list-style: none;
  counter-reset: p;
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  max-width: 36ch;
  font-size: 14px;
  line-height: 22px;
  color: rgba(255, 255, 255, 0.8);
}
.path li {
  counter-increment: p;
  display: grid;
  grid-template-columns: 28px 1fr;
  gap: var(--sp-3);
}
.path li::before {
  content: counter(p);
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.4);
  font-size: 13px;
  font-weight: 700;
  color: #fff;
}
</style>
