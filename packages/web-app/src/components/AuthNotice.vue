<script setup lang="ts">
/**
 * The one-line notice a sign-in page opens with ("Password changed…", "Your account is active…"). It is on the
 * page from the first render, where role=alert is often not announced, and the form would otherwise take the
 * cursor first: so the notice takes focus once (tabindex -1) and the next Tab lands in the form.
 * Pair with the form's `skip-initial-focus`.
 */
import { nextTick, onMounted, ref } from 'vue'

defineProps<{ text: string }>()
const el = ref<HTMLElement | null>(null)
onMounted(() => {
  void nextTick(() => {
    if (document.activeElement && document.activeElement !== document.body) return
    el.value?.focus({ preventScroll: true })
  })
})
</script>

<template>
  <div ref="el" class="auth-notice" tabindex="-1" role="status">
    <!-- role none: the wrapper is the one status; v-alert's own role=alert would make it two. -->
    <v-alert type="success" variant="tonal" density="compact" role="none">{{ text }}</v-alert>
  </div>
</template>

<style scoped>
.auth-notice {
  margin-bottom: 16px;
  border-radius: 4px;
  outline: none;
}
.auth-notice:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
</style>
