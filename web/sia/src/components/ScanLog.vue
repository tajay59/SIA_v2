<script setup lang="ts">
/**
 * Running list of scans on this screen, newest first: ✓ with where the unit is now, or ✗ with the reason.
 * The newest result is shown large (a picker looks at the shelf, not the list), with a ✓/✗ tally.
 * A refusal also beeps and vibrates once and raises a short alert; the newest-result panel is a polite live region.
 */
import { mdiCheckCircle, mdiCloseCircle, mdiRefresh } from '@mdi/js'
import { computed, ref, watch } from 'vue'

export interface ScanEntry {
  id: number
  code: string
  ok: boolean | null // null = in flight
  text: string
  /** Where the scan was aimed (e.g. the shelf), shown when a log spans several places. */
  place?: string
  retry?: () => void
}
const props = defineProps<{ entries: ScanEntry[]; empty?: string }>()

const last = computed(() => props.entries[0] ?? null)
const older = computed(() => props.entries.slice(1))
const done = computed(() => props.entries.filter((e) => e.ok === true).length)
const failed = computed(() => props.entries.filter((e) => e.ok === false).length)

// The newest-result panel is a polite live region; a refusal also raises a short alert (once per scan).
const assertive = ref('')
const announced = new Map<number, boolean>()
let audio: AudioContext | null = null

function cue() {
  try {
    navigator.vibrate?.([120, 60, 120])
  } catch {
    /* not supported */
  }
  try {
    audio ??= new AudioContext()
    const osc = audio.createOscillator()
    const gain = audio.createGain()
    osc.type = 'square'
    osc.frequency.value = 220
    gain.gain.setValueAtTime(0.08, audio.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + 0.25)
    osc.connect(gain).connect(audio.destination)
    osc.start()
    osc.stop(audio.currentTime + 0.25)
  } catch {
    /* audio blocked or unavailable */
  }
}

watch(
  () => props.entries.map((e) => [e.id, e.ok] as const),
  (now) => {
    if (!now.length) announced.clear()
    for (const e of props.entries) {
      if (e.ok === null || announced.get(e.id) === e.ok) continue
      announced.set(e.id, e.ok)
      if (!e.ok) {
        // Alternate the text so a second refusal in a row is announced again.
        assertive.value = assertive.value === 'Scan refused' ? 'Scan refused.' : 'Scan refused'
        cue()
      }
    }
  },
)
</script>

<template>
  <div class="log">
    <p class="sr-only" role="alert">{{ assertive }}</p>

    <p v-if="!last" class="t-body muted">{{ empty ?? 'Nothing scanned yet.' }}</p>
    <template v-else>
      <div aria-live="polite" aria-atomic="true">
      <div :key="last.id" class="last" :class="{ ok: last.ok === true, bad: last.ok === false }">
        <v-progress-circular v-if="last.ok === null" indeterminate size="28" width="3" />
        <v-icon v-else :icon="last.ok ? mdiCheckCircle : mdiCloseCircle" size="32" />
        <div class="body">
          <span class="t-mono code">{{ last.code }}<span v-if="last.place" class="place"> → {{ last.place }}</span></span>
          <span class="t-body msg"><strong class="state">{{ last.ok === null ? 'Saving' : last.ok ? 'Done' : 'Refused' }}:</strong> {{ last.text }}</span>
        </div>
        <v-btn v-if="last.ok === false && last.retry" variant="tonal" :prepend-icon="mdiRefresh" @click="last.retry">Retry</v-btn>
      </div>
      </div>
      <p class="tally t-caption">
        <span class="tnum"><v-icon :icon="mdiCheckCircle" size="16" color="success" /> {{ done }} done</span>
        <span v-if="failed" class="tnum"><v-icon :icon="mdiCloseCircle" size="16" color="error" /> {{ failed }} refused</span>
      </p>
      <TransitionGroup v-if="older.length" tag="ul" name="log" class="list" aria-label="Earlier scans">
        <li v-for="e in older" :key="e.id" class="item" :class="{ bad: e.ok === false }">
          <v-progress-circular v-if="e.ok === null" indeterminate size="20" width="2" />
          <v-icon v-else :icon="e.ok ? mdiCheckCircle : mdiCloseCircle" :color="e.ok ? 'success' : 'error'" />
          <div class="body">
            <span class="t-mono code">{{ e.code }}<span v-if="e.place" class="place"> → {{ e.place }}</span></span>
            <span class="t-body"><strong v-if="e.ok === false">Refused: </strong>{{ e.text }}</span>
          </div>
          <v-btn v-if="e.ok === false && e.retry" size="small" variant="text" :prepend-icon="mdiRefresh" @click="e.retry">Retry</v-btn>
        </li>
      </TransitionGroup>
    </template>
  </div>
</template>

<style scoped>
.place {
  font-family: var(--font-sans, Inter, sans-serif);
  color: rgb(var(--v-theme-secondary));
}
.log {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.last {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4);
  border-radius: 4px;
  border: 1px solid rgb(var(--v-theme-seam));
  background: rgb(var(--v-theme-surface));
}
.last.ok {
  border-color: rgba(var(--v-theme-success), 0.6);
  background: rgba(var(--v-theme-success), 0.1);
}
.last.ok .v-icon,
.last.ok .state {
  color: rgb(var(--v-theme-success));
}
.last.bad {
  border-color: rgb(var(--v-theme-error));
  background: rgba(var(--v-theme-error), 0.12);
}
.last.bad .v-icon,
.last.bad .state {
  color: rgb(var(--v-theme-error));
}
.last .state {
  font-weight: 700;
}
.last .t-body {
  font-size: 1.0625rem;
  font-weight: 500;
}
.tally {
  display: flex;
  gap: var(--sp-4);
  margin: 0;
}
.tally span {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-1);
}
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
  border-radius: 4px;
  border: 1px solid rgb(var(--v-theme-seam));
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
/* ---- Motion. Each new result drops into place; a refusal adds one short sideways nudge (the result was
   "pushed back"), after the beep and vibration; earlier rows slide down instead of jumping. State colours
   cross-fade. The global reduced-motion rule (base.css) leaves only the instant colour change. */
@keyframes log-land {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }
}
@keyframes log-nudge {
  0%,
  100% {
    transform: translateX(0);
  }
  25% {
    transform: translateX(-5px);
  }
  60% {
    transform: translateX(4px);
  }
}
.last {
  animation: log-land 220ms cubic-bezier(0.16, 1, 0.3, 1);
  transition: background-color 200ms ease-out, border-color 200ms ease-out;
}
.last.bad {
  animation: log-nudge 280ms cubic-bezier(0.16, 1, 0.3, 1);
}
.list {
  position: relative;
}
.log-enter-active {
  transition: opacity 200ms cubic-bezier(0.16, 1, 0.3, 1), transform 200ms cubic-bezier(0.16, 1, 0.3, 1);
}
.log-enter-from {
  opacity: 0;
  transform: translateY(-6px);
}
.log-move {
  transition: transform 240ms cubic-bezier(0.16, 1, 0.3, 1);
}
.log-leave-active {
  display: none;
}
</style>
