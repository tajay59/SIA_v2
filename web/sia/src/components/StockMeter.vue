<script setup lang="ts">
/**
 * Units available drawn against the low-stock alert level: a tick marks the alert, the fill turns amber
 * with the word "Low" at or under it. Zero is "None": red with an alert icon when an alert level is set (it ran
 * out), neutral when none is (nothing was ever expected on the shelf). No stock record at all is "Not counted":
 * no number, no track, so it can't be read as an empty shelf. Same meter in the products table, the product
 * sheet, the product page and the restock board.
 */
import { mdiAlertCircle, mdiAlertOutline } from '@mdi/js'
import { computed, onMounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    available?: number | null
    threshold?: number | null
    size?: 'row' | 'large'
    /** Mount already at its level (no fill): e.g. the same rows drawn again by a view switch. Count changes still animate. */
    still?: boolean
  }>(),
  { available: null, threshold: 0, size: 'row', still: false },
)

const t = computed(() => Math.max(0, props.threshold ?? 0))
const state = computed(() => {
  const a = props.available
  if (a === null || a === undefined) return 'unknown'
  if (a <= 0) return t.value > 0 ? 'none' : 'zero'
  if (t.value > 0 && a <= t.value) return 'low'
  return 'ok'
})
/** Scale: three times the alert level (so the tick sits a third along), or the count if larger. */
const scale = computed(() => Math.max(t.value * 3, props.available ?? 0, 1))
// Focal motion: the bar fills to its level once it is on screen (scaleX, transform only), and again whenever
// the count changes. Starts empty for one frame; the number is always shown.
const ready = ref(props.still)
onMounted(() => {
  if (!ready.value) requestAnimationFrame(() => requestAnimationFrame(() => (ready.value = true)))
})
// The count rolls only when it changes (not on first render).
const changed = ref(false)
watch(() => props.available, () => (changed.value = true))
const fill = computed(() => (ready.value ? Math.min(1, (props.available ?? 0) / scale.value) : 0))
const tick = computed(() => (t.value > 0 ? `${(t.value / scale.value) * 100}%` : null))
const label = computed(() => {
  if (state.value === 'unknown') return 'Not counted yet: no units recorded for this product'
  const base = `${props.available} available`
  if (state.value === 'none') return `${base}, none on the shelves (alert at ${t.value})`
  if (state.value === 'zero') return `${base}, none on the shelves`
  if (state.value === 'low') return `${base}, low (alert at ${t.value})`
  return t.value > 0 ? `${base}, alert at ${t.value}` : base
})
</script>

<template>
  <span class="meter" :class="[state, size]" :title="label">
    <span class="sr-only">{{ label }}</span>
    <span v-if="state === 'unknown'" class="nc t-caption" aria-hidden="true">Not counted</span>
    <template v-else>
      <span class="n console-mono" aria-hidden="true"><span :key="String(available)" :class="{ roll: changed }">{{ available }}</span></span>
      <span class="track" aria-hidden="true">
        <span class="fill" :style="{ transform: `scaleX(${fill})` }" />
        <span v-if="tick" class="tick" :style="{ left: tick }" />
      </span>
      <span v-if="state === 'low' || state === 'none'" class="word" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="14" height="14"><path :d="state === 'none' ? mdiAlertCircle : mdiAlertOutline" fill="currentColor" /></svg>
        {{ state === 'none' ? 'None' : 'Low' }}
      </span>
      <span v-else-if="state === 'zero'" class="word" aria-hidden="true">None</span>
    </template>
  </span>
</template>

<style scoped>
.meter {
  display: inline-grid;
  grid-template-columns: 3ch 56px auto;
  align-items: center;
  gap: var(--sp-2);
  white-space: nowrap;
}
.meter.large {
  grid-template-columns: auto minmax(120px, 1fr) auto;
  gap: var(--sp-3);
  width: 100%;
}
.n {
  text-align: right;
  font-size: 13px;
}
.large .n {
  font-size: 28px;
  line-height: 36px;
  font-weight: 500;
  text-align: left;
}
.track {
  position: relative;
  height: 4px;
  border-radius: 2px;
  background: rgb(var(--v-theme-seam));
}
.large .track {
  height: 6px;
  border-radius: 3px;
}
.fill {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  transform-origin: 0 50%;
  background: rgb(var(--v-theme-on-surface));
  opacity: 0.55;
  transition: transform 520ms var(--ease-out), background-color 200ms ease;
}
.tick {
  position: absolute;
  top: -3px;
  bottom: -3px;
  width: 2px;
  margin-left: -1px;
  background: rgb(var(--v-theme-secondary));
}
.low .fill {
  background: rgb(var(--v-theme-warning));
  opacity: 1;
}
.roll {
  display: inline-block;
  animation: console-roll-in 320ms var(--ease-out) both;
}
.n {
  overflow: hidden;
}
.low .word {
  color: rgb(var(--v-theme-warning));
}
.none .word,
.none .n {
  color: rgb(var(--v-theme-error));
}
/* Zero with no alert level: a plain fact, not an alarm. Dashed track = nothing to fill. */
.zero .n,
.zero .word {
  color: rgb(var(--v-theme-secondary));
  font-weight: 500;
}
.zero .track,
.none .track {
  background: none;
  border: 1px dashed rgb(var(--v-theme-seam));
}
/* No record: one phrase across the number and track columns. */
.nc {
  grid-column: 1 / span 2;
  color: rgb(var(--v-theme-secondary));
}
.word {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 12px;
  font-weight: 600;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
@media (prefers-reduced-motion: reduce) {
  .fill {
    transition: background-color 200ms ease;
  }
  .roll {
    animation-name: console-fade-in;
  }
}
</style>
