/*
 * "Only the table scrolls" (owner, 2026-11-26; /reports/history, /admin/approvals, /admin/audit, the /pick queue):
 * the page stays still and one box fills the window from its top down to `gap` px above the window's foot,
 * scrolling on its own. Its height is re-measured when the box appears (tabs, v-if), when anything above it changes
 * size (filters wrap, Custom adds dates, a bulk bar appears) and when the window does. A very short window keeps
 * `min` px. Below `minWidth` (a layout that stacks) the box keeps its natural height.
 */
import { onBeforeUnmount, onMounted, ref, type Ref, watch } from 'vue'

export function useFitToWindow(
  box: Ref<HTMLElement | null>,
  above: Ref<HTMLElement | null>[] = [],
  { gap = 24, min = 240, minWidth = 0 } = {},
) {
  const height = ref<number | null>(null)
  let ro: ResizeObserver | null = null
  function fit() {
    const el = box.value
    if (!el || window.innerWidth < minWidth) {
      height.value = null
      return
    }
    const top = el.getBoundingClientRect().top + window.scrollY
    height.value = Math.max(min, Math.floor(window.innerHeight - top - gap))
  }
  onMounted(() => {
    fit()
    ro = new ResizeObserver(() => fit())
    for (const a of above) if (a.value) ro.observe(a.value)
    window.addEventListener('resize', fit, { passive: true })
  })
  watch(box, () => requestAnimationFrame(fit))
  onBeforeUnmount(() => {
    ro?.disconnect()
    window.removeEventListener('resize', fit)
  })
  /** Bind as `:style` on the box. */
  const style = () => (height.value ? { height: `${height.value}px` } : undefined)
  return { height, fit, style }
}
