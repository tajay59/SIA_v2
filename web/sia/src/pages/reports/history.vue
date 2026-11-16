<script setup lang="ts">
/** A-15 movement history: the day ledger (filters + log grouped by Barbados day). */
import HistoryLedger from '../../components/history/HistoryLedger.vue'

definePage({ meta: { guard: 'staff', title: 'Movement history' } })
</script>

<template>
  <div class="page"><HistoryLedger /></div>
</template>

<style scoped>
.page {
  max-width: 1500px;
  width: 100%;
  margin: 0 auto;
}
</style>
