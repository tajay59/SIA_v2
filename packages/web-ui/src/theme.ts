/**
 * Vuetify 4 theme: DESIGN_BRIEF.md §14.1.
 *
 *   import { createVuetify } from 'vuetify'
 *   import { vuetifyOptions } from '@cimh/web-ui'
 *   createVuetify(vuetifyOptions('sia'))
 */
import { color } from './tokens'

export interface ThemeDefinition {
  dark: boolean
  colors: Record<string, string>
  variables: Record<string, string | number>
}

export const cimhLight: ThemeDefinition = {
  dark: false,
  colors: {
    primary: color.light.primary,
    'on-primary': color.light['on-primary'],
    secondary: color.light['ink-muted'],
    background: color.light.bg,
    surface: color.light.surface,
    'surface-bright': color.light.surface,
    'surface-variant': color.light['surface-2'],
    'on-surface': color.light.ink,
    'on-background': color.light.ink,
    success: color.light.success,
    warning: color.light.warning,
    error: color.light.error,
    info: color.light.info,
    'brand-logo': color.light['brand-logo'],
    'accent-probono': color.light['accent-probono'],
    'primary-subtle': color.light['primary-subtle'],
  },
  variables: { 'border-color': color.light['hairline-strong'], 'border-opacity': 1, 'medium-emphasis-opacity': 0.72 },
}

export const cimhDark: ThemeDefinition = {
  dark: true,
  colors: {
    primary: color.dark.primary,
    'on-primary': color.dark['on-primary'],
    secondary: color.dark['ink-muted'],
    background: color.dark.bg,
    surface: color.dark.surface,
    'surface-bright': color.dark['surface-2'],
    'surface-variant': color.dark['surface-2'],
    'on-surface': color.dark.ink,
    'on-background': color.dark.ink,
    success: color.dark.success,
    warning: color.dark.warning,
    error: color.dark.error,
    info: color.dark.info,
    'brand-logo': color.dark['brand-logo'],
    'accent-probono': color.dark['accent-probono'],
    'primary-subtle': color.dark['primary-subtle'],
  },
  variables: { 'border-color': color.dark['hairline-strong'], 'border-opacity': 1, 'medium-emphasis-opacity': 0.72 },
}

export type App = 'shop' | 'sia'

/** Component defaults from §14.1; SHOP density 'default', SIA 'compact'. */
export function componentDefaults(app: App): Record<string, Record<string, unknown>> {
  const density = app === 'sia' ? 'compact' : 'default'
  return {
    global: { density },
    VBtn: { rounded: 'md', variant: 'flat' },
    VTextField: { variant: 'outlined', rounded: 'md', density },
    VSelect: { variant: 'outlined', rounded: 'md', density },
    VAutocomplete: { variant: 'outlined', rounded: 'md', density },
    VTextarea: { variant: 'outlined', rounded: 'md', density },
    VCard: { rounded: 'lg', variant: 'outlined' },
    VChip: { rounded: 'sm', size: 'small' },
    VDataTable: { density },
  }
}

export function vuetifyOptions(app: App, defaultTheme: 'cimhLight' | 'cimhDark' = 'cimhLight') {
  return {
    theme: { defaultTheme, themes: { cimhLight, cimhDark } },
    defaults: componentDefaults(app),
  }
}
