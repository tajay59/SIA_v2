<script setup lang="ts">
/**
 * A-01 dashboard. Request, stock and quote counters need order- and inventory-svc (P4/P5); for now the
 * identity counters that exist: pending approvals (admin) and accounts waiting for email verification.
 */
import { call, identity, useNotify, useSession } from '@cimh/web-app'
import { mdiAccountCheckOutline, mdiAccountGroupOutline, mdiDomain, mdiEmailOutline } from '@mdi/js'
import { onMounted, ref } from 'vue'

definePage({ meta: { guard: 'staff', title: 'Dashboard' } })

const session = useSession()
const notify = useNotify()
const pending = ref<number | null>(null)
const unverified = ref<number | null>(null)

/** Count up to 100 (one page); "100+" beyond that. */
async function count(status: 'PENDING_APPROVAL' | 'PENDING_VERIFICATION'): Promise<number> {
  const res = await call(() => identity.GET('/admin/accounts', { params: { query: { status, limit: 100 } } }))
  return res.nextCursor ? 101 : res.items.length
}
const label = (n: number | null) => (n === null ? '…' : n > 100 ? '100+' : String(n))

onMounted(async () => {
  try {
    ;[pending.value, unverified.value] = await Promise.all([count('PENDING_APPROVAL'), count('PENDING_VERIFICATION')])
  } catch (e) {
    notify.report(e)
  }
})
</script>

<template>
  <div class="page stack">
    <div>
      <h1 class="t-h1">Good to see you, {{ session.account?.firstname }}</h1>
      <p class="t-body muted">Requests, quoting and stock appear here as those parts of SIA go live.</p>
    </div>
    <div class="tiles">
      <v-card v-if="session.isAdmin" :to="'/admin/approvals'" class="tile" :class="{ attention: (pending ?? 0) > 0 }">
        <v-icon :icon="mdiAccountCheckOutline" color="primary" />
        <span class="t-display tnum">{{ label(pending) }}</span>
        <span class="t-label">Accounts waiting for approval</span>
      </v-card>
      <v-card :to="'/admin/accounts?status=PENDING_VERIFICATION'" class="tile">
        <v-icon :icon="mdiEmailOutline" color="primary" />
        <span class="t-display tnum">{{ label(unverified) }}</span>
        <span class="t-label">Sign-ups not yet verified</span>
      </v-card>
      <v-card to="/admin/accounts" class="tile">
        <v-icon :icon="mdiAccountGroupOutline" color="primary" />
        <span class="t-h3">Accounts</span>
        <span class="t-label muted">Find customers and staff</span>
      </v-card>
      <v-card to="/admin/organisations" class="tile">
        <v-icon :icon="mdiDomain" color="primary" />
        <span class="t-h3">Organisations</span>
        <span class="t-label muted">Met services, agencies and partners</span>
      </v-card>
    </div>
  </div>
</template>

<style scoped>
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--sp-4);
}
.tile {
  padding: var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.tile.attention {
  border-left: 3px solid rgb(var(--v-theme-warning));
}
</style>
