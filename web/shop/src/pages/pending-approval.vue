<script setup lang="ts">
/** S-15 awaiting approval. */
import { AuthCard } from '@cimh/web-app'

definePage({ meta: { guard: 'public', title: 'Awaiting approval', layout: 'bare' } })
</script>

<template>
  <AuthCard title="Thanks, your email is verified" subtitle="An administrator will review your account.">
    <div class="stack t-body prose">
      <p>We check every new account against its organisation. You will get an email as soon as a decision is made, usually within two working days.</p>
      <p>Until then you can browse the catalogue, but you can't log in.</p>
    </div>
    <template #footer>
      <router-link to="/">Back to the home page</router-link>
    </template>
  </AuthCard>
</template>
