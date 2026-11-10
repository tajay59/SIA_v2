/**
 * `v-scroll-region="'Requests'"` on a v-table / v-data-table: its inner `.v-table__wrapper` scrolls sideways
 * on narrow screens, so keyboard users must be able to focus it to scroll (WCAG 2.1.1, axe
 * scrollable-region-focusable). Makes the wrapper a labelled, focusable region.
 */
import type { Directive } from 'vue'

function apply(el: HTMLElement, label: string) {
  const target = el.querySelector<HTMLElement>('.v-table__wrapper') ?? el
  target.tabIndex = 0
  target.setAttribute('role', 'region')
  target.setAttribute('aria-label', label)
}

export const vScrollRegion: Directive<HTMLElement, string> = {
  mounted: (el, binding) => apply(el, binding.value),
  updated: (el, binding) => apply(el, binding.value),
}
