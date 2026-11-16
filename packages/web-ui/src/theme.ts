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
    'on-surface-variant': color.light.ink, // solo-inverted fields take their focused text colour from here
    'on-surface': color.light.ink,
    'on-background': color.light.ink,
    success: color.light.success,
    warning: color.light.warning,
    error: color.light.error,
    info: color.light.info,
    'brand-logo': color.light['brand-logo'],
    'accent-probono': color.light['accent-probono'],
    'primary-subtle': color.light['primary-subtle'],
    // Resting edge of every input (base.css): >= 3:1 on white cards, the page ground and raised wells (WCAG 1.4.11).
    'field-outline': color.light['field-outline'],
    // Ground behind product photos; photos are multiplied onto it, so dark mode can dim it without a white box.
    'photo-ground': color.light['photo-ground'],
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
    'on-surface-variant': color.dark.ink,
    'on-surface': color.dark.ink,
    'on-background': color.dark.ink,
    success: color.dark.success,
    warning: color.dark.warning,
    error: color.dark.error,
    info: color.dark.info,
    // Dark-theme status colours are light; Vuetify would put white text on them (success = 2.54:1). Ink instead.
    'on-success': color.dark['on-primary'],
    'on-warning': color.dark['on-primary'],
    'on-error': color.dark['on-primary'],
    'on-info': color.dark['on-primary'],
    'brand-logo': color.dark['brand-logo'],
    'accent-probono': color.dark['accent-probono'],
    'primary-subtle': color.dark['primary-subtle'],
    'field-outline': color.dark['field-outline'],
    'photo-ground': color.dark['photo-ground'],
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
    // Every input is solo-inverted (owner, 2026-11-12), flat to match the panel look. At rest the field has the
    // card's own colour, so base.css draws a 1 px `field-outline` edge around it.
    VTextField: { variant: 'solo-inverted', flat: true, rounded: 'md', density },
    VSelect: { variant: 'solo-inverted', flat: true, rounded: 'md', density },
    VAutocomplete: { variant: 'solo-inverted', flat: true, rounded: 'md', density },
    VCombobox: { variant: 'solo-inverted', flat: true, rounded: 'md', density },
    VTextarea: { variant: 'solo-inverted', flat: true, rounded: 'md', density },
    VFileInput: { variant: 'solo-inverted', flat: true, rounded: 'md', density },
    VNumberInput: { variant: 'solo-inverted', flat: true, rounded: 'md', density },
    VDateInput: { variant: 'solo-inverted', flat: true, rounded: 'md', density },
    VOtpInput: { variant: 'solo-inverted' },
    VCard: { rounded: 'lg', variant: 'outlined' },
    VChip: { rounded: 'sm', size: 'small' },
    VDataTable: { density },
    // Cards default to outlined (transparent); a card inside a dialog needs its own solid surface.
    // Fields inside a dialog sit on the card's surface, so they take the raised tone to stay visible.
    VDialog: {
      VCard: { variant: 'elevated', color: 'surface' },
      ...Object.fromEntries(
        ['VTextField', 'VSelect', 'VAutocomplete', 'VCombobox', 'VTextarea', 'VFileInput', 'VNumberInput', 'VDateInput'].map((k) => [k, { bgColor: 'surface-variant' }]),
      ),
    },
  }
}

/**
 * SIA "Graphite Console" (surface brief web/sia, 2026-11-11): graphite panels separated by 1 px seams,
 * colour only for state and the primary action. Same theme names, so the light/dark toggle works unchanged.
 */
export const siaDark: ThemeDefinition = {
  dark: true,
  colors: {
    ...cimhDark.colors,
    background: '#16191D',
    surface: '#1C2026',
    'surface-bright': '#22272E',
    'surface-variant': '#22272E',
    'on-surface-variant': '#E6EDF3',
    'on-surface': '#E6EDF3',
    'on-background': '#E6EDF3',
    secondary: '#9DA7B3',
    seam: '#30363D',
    'photo-ground': '#FFFFFF', // SIA keeps product photos on white in both themes
  },
  variables: { 'border-color': '#30363D', 'border-opacity': 1, 'medium-emphasis-opacity': 0.74 },
}

export const siaLight: ThemeDefinition = {
  dark: false,
  colors: {
    ...cimhLight.colors,
    background: '#F6F8FA',
    surface: '#FFFFFF',
    'surface-bright': '#FFFFFF',
    'surface-variant': '#EEF1F4',
    'on-surface-variant': '#14191F',
    'on-surface': '#14191F',
    'on-background': '#14191F',
    secondary: '#57606A',
    seam: '#D0D7DE',
  },
  variables: { 'border-color': '#D0D7DE', 'border-opacity': 1, 'medium-emphasis-opacity': 0.74 },
}

export function vuetifyOptions(app: App, defaultTheme: 'cimhLight' | 'cimhDark' = 'cimhLight') {
  const themes = app === 'sia' ? { cimhLight: siaLight, cimhDark: siaDark } : { cimhLight, cimhDark }
  const defaults = componentDefaults(app)
  if (app === 'sia') {
    // Graphite Console: flatter, tighter corners; panels are cut by seams, not floated cards.
    defaults.VBtn = { rounded: 'sm', variant: 'flat' }
    defaults.VCard = { rounded: 'sm', variant: 'outlined' }
    for (const k of ['VTextField', 'VSelect', 'VAutocomplete', 'VCombobox', 'VTextarea', 'VFileInput', 'VNumberInput', 'VDateInput']) defaults[k] = { ...defaults[k], rounded: 'sm' }
  } else {
    // SHOP: every button is a Material 3 button (owner, 2026-11-16): full pill, 40 px; tabs keep their square ink.
    defaults.VBtn = { rounded: 'pill', variant: 'flat', class: 'm3' }
    defaults.VTab = { rounded: 0, class: '' }
  }
  return { theme: { defaultTheme, themes }, defaults }
}
