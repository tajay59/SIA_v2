<script setup lang="ts">
/**
 * Status chip (DESIGN_BRIEF status mapping): colour + icon + text, never colour alone.
 * Material 3 chip anatomy: 8 px corners, 18 px leading icon, label-large type (500, +0.1 px tracking),
 * 8/12 px padding, tonal container with a 1 px outline in the same hue. Neutral uses outline only (M3 assist
 * chip), so "nothing to do yet" reads quieter than states that need attention. Status is not interactive:
 * no hover/ripple, it is a label, not a button. `iconOnly` = the icon alone, its label in a tooltip (and the
 * accessible name). `label`/`tone`/`icon` override the status words (e.g. "Payment required").
 */
import { mdiAlertCircle, mdiCashClock, mdiCheckCircle, mdiCircleOutline, mdiCloseCircle, mdiProgressClock } from '@mdi/js'
import { statusLabel, statusTone, TONE_COLOR } from '@cimh/web-ui'
import { computed } from 'vue'

type Tone = ReturnType<typeof statusTone>
const props = defineProps<{ status: string; iconOnly?: boolean; label?: string; tone?: Tone; icon?: 'cash' }>()
const tone = computed(() => props.tone ?? statusTone(props.status))
const label = computed(() => props.label ?? statusLabel(props.status))
const path = computed(() => (props.icon === 'cash' ? mdiCashClock : ICONS[tone.value]))
const ICONS = {
  neutral: mdiCircleOutline,
  info: mdiProgressClock,
  warning: mdiAlertCircle,
  success: mdiCheckCircle,
  error: mdiCloseCircle,
} as const
</script>

<template>
  <v-tooltip v-if="iconOnly" :text="label" location="top">
    <template #activator="{ props: tip }">
      <span
        v-bind="tip"
        class="m3-status icon-only"
        :class="`tone-${tone}`"
        :style="{ '--chip': `var(--v-theme-${TONE_COLOR[tone]})` }"
        role="img"
        :aria-label="label"
        tabindex="0"
      >
        <svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path :d="path" /></svg>
      </span>
    </template>
  </v-tooltip>
  <span v-else class="m3-status" :class="`tone-${tone}`" :style="{ '--chip': `var(--v-theme-${TONE_COLOR[tone]})` }" :title="label">
    <svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path :d="path" /></svg>
    <span class="label">{{ label }}</span>
  </span>
</template>

<style scoped>
.m3-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  height: 28px;
  padding: 0 12px 0 8px;
  border-radius: 8px;
  border: 1px solid rgba(var(--chip), 0.32);
  background: rgba(var(--chip), 0.08);
  /* M3 on-container: the label is the hue deepened toward the ink (AA on the tint); the icon keeps the pure hue. */
  color: color-mix(in srgb, rgb(var(--chip)) 72%, rgb(var(--v-theme-on-surface)));
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.1px;
  line-height: 1;
  white-space: nowrap;
  vertical-align: middle;
}
.m3-status.icon-only {
  width: 28px;
  padding: 0;
  justify-content: center;
}
.icon {
  flex: none;
  width: 18px;
  height: 18px;
  fill: rgb(var(--chip));
}
.label {
  overflow: hidden;
  text-overflow: ellipsis;
}
/* Neutral = outlined assist chip: no fill, ink label, muted icon. */
.tone-neutral {
  background: transparent;
  border-color: rgb(var(--v-theme-seam, var(--v-border-color)));
  color: rgb(var(--v-theme-on-surface));
}
.tone-neutral .icon {
  fill: rgb(var(--v-theme-secondary));
  color: rgb(var(--v-theme-secondary));
}
</style>
