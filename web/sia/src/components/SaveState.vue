<script setup lang="ts">
/**
 * The status line in a save bar: "Unsaved changes" while edited, a check that draws itself with "Saved" right
 * after a save, then the quiet "All changes saved" (nothing when `quiet`). Announced politely.
 */
import { computed } from 'vue'

const props = defineProps<{ dirty: boolean; saved?: boolean; quiet?: boolean }>()
const state = computed(() => (props.dirty ? 'dirty' : props.saved ? 'saved' : 'clean'))
</script>

<template>
  <span class="save-state" aria-live="polite">
    <Transition name="ss" mode="out-in">
      <span v-if="state === 'dirty'" key="dirty" class="ss dirty"><span class="pip" aria-hidden="true" />Unsaved changes</span>
      <span v-else-if="state === 'saved'" key="saved" class="ss saved">
        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>Saved
      </span>
      <span v-else-if="!quiet" key="clean" class="ss clean">All changes saved</span>
    </Transition>
  </span>
</template>

<style scoped>
.save-state {
  display: inline-flex;
  min-height: 20px;
  font-size: 12px;
  line-height: 16px;
}
.ss {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: rgb(var(--v-theme-secondary));
}
.dirty {
  color: rgb(var(--v-theme-on-surface));
}
.pip {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: rgb(var(--v-theme-primary));
}
.saved {
  color: rgb(var(--v-theme-success));
  font-weight: 500;
}
.saved path {
  fill: none;
  stroke: currentColor;
  stroke-width: 2.4;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 22;
  stroke-dashoffset: 22;
  animation: ss-draw 360ms var(--ease-out) 60ms forwards;
}
@keyframes ss-draw {
  to {
    stroke-dashoffset: 0;
  }
}
.ss-enter-active {
  transition: opacity 180ms var(--ease-out), transform 180ms var(--ease-out);
}
.ss-enter-from {
  opacity: 0;
  transform: translateY(4px);
}
.ss-leave-active {
  transition: opacity 100ms ease-in;
}
.ss-leave-to {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .saved path {
    animation: none;
    stroke-dashoffset: 0;
  }
  .ss-enter-from {
    transform: none;
  }
}
</style>
