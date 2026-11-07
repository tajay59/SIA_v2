/**
 * Focus a field once, when the form mounts. Vuetify's `autofocus` focuses from an IntersectionObserver
 * callback, which can fire after the user has already clicked into another field and steal focus
 * mid-typing (seen in the browser tests). This runs before the first paint, then never again.
 */
import { nextTick, onMounted, type Ref } from 'vue'

export function useInitialFocus(target: Ref<{ focus: () => void } | null | undefined>): void {
  onMounted(() => {
    void nextTick(() => {
      if (typeof document !== 'undefined' && document.activeElement && document.activeElement !== document.body) return
      target.value?.focus()
    })
  })
}
