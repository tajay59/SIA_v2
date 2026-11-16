<script setup lang="ts">
/** S-13 sign up → S-14 verify: three steps beside the picture; the picture lists the way to an approved account. */
import { AuthCard, SignupForm } from '@cimh/web-app'
import { ref } from 'vue'

definePage({ meta: { guard: 'public', title: 'Sign up', layout: 'bare' } })
const step = ref(0)
</script>

<template>
  <AuthCard title="Create your account" subtitle="Request instruments and spares from CIMH." :width="520">
    <template #wall>
      <ol class="path">
        <li>Fill in the form</li>
        <li>Confirm your email with a code</li>
        <li>A CIMH administrator approves the account, usually within two working days</li>
        <li>Send requests</li>
      </ol>
    </template>
    <SignupForm v-model:step="step" />
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
  font-size: 15px;
  line-height: 22px;
  color: rgba(255, 255, 255, 0.84);
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
  border: 1px solid rgba(255, 255, 255, 0.5);
  font-size: 13px;
  font-weight: 700;
  color: #fff;
}
</style>
