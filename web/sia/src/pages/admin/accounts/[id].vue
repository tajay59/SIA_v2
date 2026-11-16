<script setup lang="ts">
/** A-17 account on its own page (deep links, phones); the same record opens beside the list in /admin/accounts. */
import { useRoute, useRouter } from 'vue-router'
import AccountRecord from '../../../components/AccountRecord.vue'

definePage({ meta: { guard: 'staff', title: 'Account', ownHeading: true } })
const route = useRoute('/admin/accounts/[id]')
const router = useRouter()
</script>

<template>
  <AccountRecord :account-id="route.params.id" @erased="router.push('/admin/accounts')" />
</template>
