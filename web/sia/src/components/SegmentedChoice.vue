<script setup lang="ts" generic="T extends string | number | null">
/**
 * Material 3 segmented button for one choice out of a few (native radios: arrow keys move, one tab stop).
 * The chosen segment carries a check and the action-blue wash. One wash element slides between segments
 * (continuity, like the stage-tab ink); when the segments wrap onto two lines (phones) each segment
 * paints its own wash instead. The check wipes in from the left.
 */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import ICheck from '~icons/material-symbols/check-rounded'

const props = defineProps<{ name: string; label: string; options: { title: string; value: T }[]; scroll?: boolean }>()
const model = defineModel<T>({ required: true })

const root = ref<HTMLElement | null>(null)
const ink = ref<{ x: number; w: number } | null>(null)
const ready = ref(false) // no slide on first paint
const wrapped = ref(false)

function measure() {
  const el = root.value
  if (!el) return
  const btns = Array.from(el.querySelectorAll<HTMLElement>('.seg-btn'))
  wrapped.value = btns.length > 1 && btns.some((b) => b.offsetTop !== btns[0]!.offsetTop)
  const i = props.options.findIndex((o) => o.value === model.value)
  const b = btns[i]
  ink.value = b && !wrapped.value ? { x: b.offsetLeft, w: b.offsetWidth } : null
}
let ro: ResizeObserver | undefined
onMounted(() => {
  measure()
  requestAnimationFrame(() => (ready.value = true))
  ro = new ResizeObserver(measure)
  if (root.value) ro.observe(root.value)
})
onBeforeUnmount(() => ro?.disconnect())
watch([model, () => props.options.length], () => void nextTick(measure))
</script>

<template>
  <div ref="root" class="seg" :class="{ inked: !!ink, ready, scroll }" role="radiogroup" :aria-label="label">
    <span v-if="ink" class="seg-ink" aria-hidden="true" :style="{ transform: `translateX(${ink.x}px)`, width: `${ink.w}px` }" />
    <label v-for="o in options" :key="String(o.value)" class="seg-btn" :class="{ on: model === o.value }">
      <input v-model="model" type="radio" class="seg-input" :name="name" :value="o.value" />
      <Transition name="seg-check"><ICheck v-if="model === o.value" class="seg-check" aria-hidden="true" /></Transition>{{ o.title }}
    </label>
  </div>
</template>

<style scoped>
.seg {
  position: relative;
  display: inline-flex;
  flex-wrap: wrap;
  max-width: 100%;
  border: 1px solid rgb(var(--v-theme-field-outline));
  border-radius: 20px;
  overflow: hidden;
  isolation: isolate;
}
/* `scroll`: one row that scrolls sideways when the pane is too narrow (never a wrapped pill). */
.seg.scroll {
  flex-wrap: nowrap;
  overflow-x: auto;
  overscroll-behavior-x: contain;
  scrollbar-width: none;
}
.seg.scroll::-webkit-scrollbar {
  display: none;
}
.seg-ink {
  position: absolute;
  inset-block: 0;
  left: 0;
  z-index: -1;
  background: rgb(var(--v-theme-primary-subtle));
  pointer-events: none;
}
.seg.ready .seg-ink {
  transition:
    transform 280ms var(--ease-out),
    width 280ms var(--ease-out);
}
.seg-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 36px;
  min-width: 64px;
  padding: 0 14px;
  margin-left: -1px;
  border-left: 1px solid rgb(var(--v-theme-field-outline));
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  color: rgb(var(--v-theme-on-surface));
  cursor: pointer;
  user-select: none;
  transition: background-color 160ms ease-out;
}
.seg-btn:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}
.seg-btn.on {
  font-weight: 600;
}
/* No sliding wash (wrapped segments): the chosen segment paints its own, fading in. */
.seg:not(.inked) .seg-btn.on {
  background: rgb(var(--v-theme-primary-subtle));
}
.seg-input {
  position: absolute;
  inset: 0;
  opacity: 0;
  margin: 0;
  cursor: pointer;
}
.seg-btn:has(.seg-input:focus-visible) {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.seg-check {
  width: 16px;
  height: 16px;
  margin-left: -4px;
  color: rgb(var(--v-theme-primary));
}
/* The check wipes in from the left as the wash arrives (only on a change, never on first render). */
.seg-check-enter-active {
  transition: clip-path 220ms 80ms var(--ease-out);
}
.seg-check-enter-from {
  clip-path: inset(0 100% 0 0);
}
@media (prefers-reduced-motion: reduce) {
  .seg-btn,
  .seg.ready .seg-ink {
    transition: none;
  }
  .seg-check-enter-active {
    transition: opacity 160ms ease-out;
  }
  .seg-check-enter-from {
    clip-path: none;
    opacity: 0;
  }
}
</style>
