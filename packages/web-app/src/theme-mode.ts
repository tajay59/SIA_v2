/** Light/dark toggle, remembered per device (APD §2). Storage can be unavailable; the app works without it. */
import { useTheme } from 'vuetify'
import { computed } from 'vue'

const KEY = 'cimh.theme'
type Mode = 'cimhLight' | 'cimhDark'

/** Stored choice, else `fallback` (SIA defaults to dark), else the OS preference. */
export function storedTheme(fallback?: Mode): Mode {
  try {
    const v = localStorage.getItem(KEY)
    if (v === 'cimhLight' || v === 'cimhDark') return v
  } catch {
    // private mode / blocked storage
  }
  if (fallback) return fallback
  return typeof matchMedia !== 'undefined' && matchMedia('(prefers-color-scheme: dark)').matches ? 'cimhDark' : 'cimhLight'
}

export function useThemeMode() {
  const theme = useTheme()
  const dark = computed({
    get: () => theme.global.name.value === 'cimhDark',
    set: (on: boolean) => {
      const mode: Mode = on ? 'cimhDark' : 'cimhLight'
      theme.change(mode)
      try {
        localStorage.setItem(KEY, mode)
      } catch {
        // ignore
      }
    },
  })
  return { dark, toggle: () => (dark.value = !dark.value) }
}
