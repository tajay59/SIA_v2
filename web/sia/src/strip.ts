/**
 * Sideways tab strips on phones (product tabs, settings sections): bring the chosen item fully into view, so the
 * active tab is never off-screen (critique 2026-11-14). Instant, and a no-op when the strip doesn't scroll.
 */
export function revealInStrip(strip: HTMLElement, el: HTMLElement): void {
  if (strip.scrollWidth <= strip.clientWidth) return
  const pad = 16
  const left = el.offsetLeft // the strip is the offset parent (position: relative)
  const start = strip.scrollLeft
  const end = start + strip.clientWidth
  if (left - pad < start) strip.scrollLeft = Math.max(0, left - pad)
  else if (left + el.offsetWidth + pad > end) strip.scrollLeft = left + el.offsetWidth + pad - strip.clientWidth
}
