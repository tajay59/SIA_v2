<script setup lang="ts">
/**
 * S-20 not found (hidden resources look the same as missing ones). Most broken links here are old product
 * links, so the way out is a catalogue search and the catalogue; signed-out visitors are told that logging
 * in may show the page; customers get My requests.
 */
import { useSession } from '@cimh/web-app'
import { mdiMagnify } from '@mdi/js'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

definePage({ meta: { guard: 'public', title: 'Page not found' } })
const session = useSession()
const route = useRoute()
const router = useRouter()
const q = ref('')
function search() {
  const text = q.value.trim()
  void router.push(text ? { path: '/catalogue', query: { q: text } } : '/catalogue')
}
</script>

<template>
  <v-container class="page" max-width="720">
    <div class="stack">
      <h1 class="t-h1">Page not found</h1>
      <p class="t-body-lg muted">
        The page doesn't exist, or you don't have access to it.
        <template v-if="!session.isLoggedIn">
          If it is one of your requests, <router-link :to="{ path: '/login', query: { returnTo: route.fullPath } }">log in</router-link> to see it.
        </template>
      </p>
      <form class="search" role="search" @submit.prevent="search">
        <v-text-field v-model="q" label="Search the catalogue" hint="A name, make or model number" persistent-hint :prepend-inner-icon="mdiMagnify" />
        <v-btn type="submit" color="primary" size="large">Search</v-btn>
      </form>
      <div class="row">
        <v-btn to="/catalogue" variant="outlined">Browse the catalogue</v-btn>
        <v-btn v-if="session.isCustomer" to="/requests" variant="outlined">My requests</v-btn>
        <v-btn to="/" variant="text">Home page</v-btn>
      </div>
    </div>
  </v-container>
</template>

<style scoped>
.search {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
}
.search .v-text-field {
  flex: 1;
  min-width: 0;
}
.search .v-btn {
  margin-top: 4px;
}
</style>
