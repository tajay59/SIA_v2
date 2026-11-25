/**
 * Build-time trim of Vuetify's global stylesheet (`vuetify/styles` = core + colours + utilities, ~300 KB, all of it
 * render-blocking on the first page). Lighthouse fix 3 (docs/plans/2026-11-25-lighthouse.md).
 *
 * Removed, from Vuetify's own style files only (never our CSS):
 *  - breakpoint variants of the utility classes (`ma-md-2`, `d-lg-flex`, `text-sm-center`, `hidden-sm-and-down`…):
 *    186 KB of the 234 KB of utility rules. Neither app uses one (layout is responsive in our own CSS and through
 *    `useDisplay()`), and Vuetify's components never emit them.
 *  - the Material palette classes (`bg-red-lighten-1`, `text-blue-grey`…) except white, black and transparent
 *    (`color="white"` gives `bg-white` / `text-white`). Theme colours (`primary`, `success`…) are not in that file:
 *    Vuetify's theme writes them at run time.
 *
 * If a template ever needs a breakpoint helper or a palette colour, write the rule in the app's CSS instead.
 */

const FILES = /\/vuetify\/lib\/styles\/(main|utilities|colors)\.css$/
/** A selector for a breakpoint variant: a class with -sm-/-md-/… inside or at its end, or a hidden-* helper. */
const BREAKPOINT = /\.[a-z0-9-]*-(sm|md|lg|xl|xxl)(-[a-z0-9-]+)?(?![a-z0-9-])|\.hidden-/
const PALETTE =
  /\.(bg|text|border)-(red|pink|purple|deep-purple|indigo|blue|light-blue|cyan|teal|green|light-green|lime|yellow|amber|orange|deep-orange|brown|blue-grey|grey|shades)(?![a-z])/
const KEEP_PALETTE = /white|black|transparent/

interface Node {
  type: string
  nodes?: Node[]
  selectors?: string[]
  remove(): void
}
interface Root extends Node {
  source?: { input: { file?: string } }
  walkRules(cb: (rule: Node & { selectors: string[] }) => void): void
  walkAtRules(cb: (at: Node & { name: string }) => void): void
}

export function trimVuetifyCss() {
  return {
    postcssPlugin: 'cimh-trim-vuetify-css',
    Once(root: Root) {
      const file = (root.source?.input.file ?? '').replace(/\\/g, '/')
      if (!FILES.test(file)) return
      root.walkRules((rule) => {
        const keep = rule.selectors.filter((s) => !BREAKPOINT.test(s) && !(PALETTE.test(s) && !KEEP_PALETTE.test(s)))
        if (!keep.length) rule.remove()
        else if (keep.length !== rule.selectors.length) rule.selectors = keep
      })
      // Blocks left empty (media queries, layers); `@layer a, b;` statements have no body and stay.
      let removed = true
      while (removed) {
        removed = false
        root.walkAtRules((at) => {
          if (at.nodes && at.nodes.length === 0) {
            at.remove()
            removed = true
          }
        })
      }
    },
  }
}
