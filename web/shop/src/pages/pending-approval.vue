<script setup lang="ts">
/** S-15 awaiting approval: what happens now, and the one thing the visitor can do meanwhile (browse). */
import { AuthCard } from '@cimh/web-app'

definePage({ meta: { guard: 'public', title: 'Awaiting approval', layout: 'bare' } })
</script>

<template>
  <AuthCard title="Thanks, your email is verified" subtitle="An administrator will review your account.">
    <div class="stack t-body prose">
      <p>We check every new account against its organisation. You will get an email as soon as a decision is made, usually within two working days.</p>
      <p>Until then you can't log in, but you can browse the catalogue and see what CIMH holds.</p>
      <v-btn to="/catalogue" color="primary" size="large" block>Browse the catalogue</v-btn>
    </div>
    <template #footer>
      <router-link to="/">Back to the home page</router-link>
    </template>
  </AuthCard>
</template>

<style scoped>
.stack p {
  margin: 0;
}
</style>
