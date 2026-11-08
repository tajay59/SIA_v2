<script setup lang="ts">
/** Running list of scans on this screen, newest first: ✓ with where the unit is now, or ✗ with the reason. */
import { mdiCheckCircle, mdiCloseCircle, mdiRefresh } from '@mdi/js'

export interface ScanEntry {
  id: number
  code: string
  ok: boolean | null // null = in flight
  text: string
  retry?: () => void
}
defineProps<{ entries: ScanEntry[]; empty?: string }>()
</script>

<template>
  <div class="log" aria-live="polite">
    <p v-if="!entries.length" class="t-body muted">{{ empty ?? 'Nothing scanned yet.' }}</p>
    <ul v-else class="list">
      <li v-for="e in entries" :key="e.id" class="item" :class="{ ok: e.ok === true, bad: e.ok === false }">
        <v-progress-circular v-if="e.ok === null" indeterminate size="20" width="2" />
        <v-icon v-else :icon="e.ok ? mdiCheckCircle : mdiCloseCircle" :color="e.ok ? 'success' : 'error'" />
        <div class="body">
          <span class="t-mono code">{{ e.code }}</span>
          <span class="t-body">{{ e.text }}</span>
        </div>
        <v-btn v-if="e.ok === false && e.retry" size="small" variant="text" :prepend-icon="mdiRefresh" @click="e.retry">Retry</v-btn>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.item {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  border-radius: 8px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.item.bad {
  border-color: rgb(var(--v-theme-error));
}
.body {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1 1 auto;
}
.code {
  overflow-wrap: anywhere;
}
</style>
