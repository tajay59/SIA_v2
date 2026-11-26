/**
 * List leave motion. TransitionGroup lists take leaving items out of flow (`position: absolute`) so the rest can
 * slide into place; without a position of their own, every leaving item takes the static position the flow gives it,
 * and when several leave at once (a filter or tab change) they all pile up on the first row (owner, 2026-11-25).
 *
 * `pinLeaving` (TransitionGroup `@before-leave`) pins the item where it stands: top, left, width and height from its
 * layout, so it fades or slides out in place. The list element must be the positioning container
 * (`position: relative`), as it is the item's offsetParent.
 */
export function pinLeaving(el: Element): void {
  const item = el as HTMLElement
  const { offsetTop, offsetLeft, offsetWidth, offsetHeight } = item
  item.style.top = `${offsetTop}px`
  item.style.left = `${offsetLeft}px`
  item.style.width = `${offsetWidth}px`
  item.style.height = `${offsetHeight}px`
}
