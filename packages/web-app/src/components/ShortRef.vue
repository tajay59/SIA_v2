<script setup lang="ts">
/**
 * A record id. By default shown short ("ORD…3f9a2c", `shortRef`) with the full id in a tooltip.
 * `fit`: the full id whenever it fits without adding a line to its parent (re-checked when the parent's width
 * changes), else the short form. `copy`: a small button that copies the full id (never inside a link or button).
 */
import { mdiCheck, mdiContentCopy } from '@mdi/js'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useNotify } from '../notify'
import { shortRef } from '../orders'

const props = defineProps<{ id: string; fit?: boolean; copy?: boolean }>()

const root = ref<HTMLElement | null>(null)
const full = ref(false)
const short = computed(() => shortRef(props.id))
const shown = computed(() => (full.value ? props.id : short.value))
const copied = ref(false)
const notify = useNotify()

/** Number of line boxes the parent's text occupies. */
function lines(parent: HTMLElement): number {
  const range = document.createRange()
  range.selectNodeContents(parent)
  const tops = new Set<number>()
  for (const r of Array.from(range.getClientRects())) if (r.width > 0) tops.add(Math.round(r.top))
  return tops.size
}

/** The nearest ancestor that is not inline: its width is what the id has to fit in. */
function box(): HTMLElement | null {
  let el = root.value?.parentElement ?? null
  while (el && getComputedStyle(el).display === 'inline') el = el.parentElement
  return el
}

let lastWidth = -1
async function measure() {
  const parent = box()
  if (!props.fit || !parent) return
  if (short.value === props.id) { full.value = true; return }
  // Both layouts are measured before the browser paints (microtasks), so nothing flickers.
  full.value = false
  await nextTick()
  const base = lines(parent)
  const baseScroll = parent.scrollWidth
  full.value = true
  await nextTick()
  full.value = lines(parent) <= base && parent.scrollWidth <= Math.max(baseScroll, parent.clientWidth)
}

let ro: ResizeObserver | null = null
onMounted(() => {
  const parent = box()
  if (!props.fit || !parent || typeof ResizeObserver === 'undefined') return
  ro = new ResizeObserver((entries) => {
    const w = Math.round(entries[0]?.contentRect.width ?? 0)
    if (w === lastWidth) return
    lastWidth = w
    void measure()
  })
  ro.observe(parent)
  void document.fonts?.ready.then(() => { lastWidth = -1; void measure() })
})
onBeforeUnmount(() => ro?.disconnect())
watch(() => props.id, () => void nextTick(measure))

async function copyId() {
  try {
    await navigator.clipboard.writeText(props.id)
    copied.value = true
    notify.toast('Order id copied', 'success')
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    /* clipboard blocked: the id stays selectable */
  }
}
</script>

<template>
  <span ref="root" class="short-ref" :class="{ 'short-ref--full': full }">
    <span class="short-ref-text">{{ shown }}</span>
    <!-- role="tooltip" sits on the overlay root, so the name goes there (axe aria-tooltip-name), as in the SIA drawer. -->
    <v-tooltip v-if="!full" activator="parent" location="top" :open-delay="250" content-class="short-ref-tip" :aria-label="id">{{ id }}</v-tooltip>
    <v-btn
      v-if="copy"
      class="short-ref-copy"
      variant="text"
      size="x-small"
      density="comfortable"
      :icon="copied ? mdiCheck : mdiContentCopy"
      :aria-label="`Copy order id ${id}`"
      @click.stop.prevent="copyId"
    />
  </span>
</template>

<style>
.short-ref-tip {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px;
}
.short-ref-text {
  white-space: nowrap;
}
.short-ref-copy {
  vertical-align: middle;
  margin-inline-start: 4px;
}
</style>
