/**
 * Design tokens: DESIGN_BRIEF.md §3–§6 (the brand reference; no official CIMH brand guide exists).
 * Change values here only together with the brief, and re-run the contrast tests.
 */

export const color = {
  light: {
    'brand-logo': '#0084C8',
    primary: '#006FA8',
    'primary-hover': '#00639A',
    'primary-press': '#005A8C',
    'primary-subtle': '#E6F4FB',
    'on-primary': '#FFFFFF',
    'accent-probono': '#F5C400',
    bg: '#F5F7FA',
    surface: '#FFFFFF',
    'surface-2': '#F0F3F7',
    'surface-3': '#E6EBF1',
    hairline: '#E1E6EC',
    'hairline-strong': '#C7D0DA',
    ink: '#0F1A24',
    'ink-muted': '#53606C',
    'ink-disabled': '#8C97A3',
    success: '#1A7F37',
    'success-subtle': '#E8F5EC',
    warning: '#B54708',
    'warning-subtle': '#FDF1E7',
    error: '#B42318',
    'error-subtle': '#FDECEA',
    info: '#006FA8',
    'info-subtle': '#E6F4FB',
  },
  dark: {
    'brand-logo': '#0084C8',
    primary: '#5CC2FF',
    'primary-hover': '#7FCBF5',
    'primary-press': '#A9DCF8',
    'primary-subtle': '#0B2A3D',
    'on-primary': '#0D1117',
    'accent-probono': '#F5C400',
    bg: '#0D1117',
    surface: '#161B22',
    'surface-2': '#1C232C',
    'surface-3': '#242C36',
    hairline: '#2A323C',
    'hairline-strong': '#3A4552',
    ink: '#E6EDF3',
    'ink-muted': '#9AA7B4',
    'ink-disabled': '#5C6773',
    success: '#3FB950',
    'success-subtle': '#0F2A18',
    warning: '#F2B13A',
    'warning-subtle': '#2E2209',
    error: '#F97066',
    'error-subtle': '#2D1214',
    info: '#5CC2FF',
    'info-subtle': '#0B2A3D',
  },
} as const

export type ColorToken = keyof typeof color.light

/** 4 px grid. */
export const space = { 1: 4, 2: 8, 3: 12, 4: 16, 5: 20, 6: 24, 8: 32, 10: 40, 12: 48, 16: 64 } as const

export const radius = { sm: 4, md: 8, lg: 12, full: 9999 } as const

export const font = {
  sans: "'Inter Variable', Inter, system-ui, sans-serif",
  mono: "'JetBrains Mono Variable', 'JetBrains Mono', ui-monospace, monospace",
  features: '"cv11", "ss01"',
} as const

export const type = {
  display: { size: 36, line: 44, weight: 600, tracking: -0.5 },
  h1: { size: 28, line: 36, weight: 600, tracking: -0.3 },
  h2: { size: 22, line: 30, weight: 600, tracking: -0.2 },
  h3: { size: 18, line: 26, weight: 600, tracking: 0 },
  'body-lg': { size: 16, line: 24, weight: 400, tracking: 0 },
  body: { size: 14, line: 22, weight: 400, tracking: 0 },
  'body-strong': { size: 14, line: 22, weight: 600, tracking: 0 },
  label: { size: 13, line: 18, weight: 500, tracking: 0.1 },
  caption: { size: 12, line: 16, weight: 400, tracking: 0.1 },
  overline: { size: 11, line: 16, weight: 600, tracking: 0.6 },
  mono: { size: 13, line: 20, weight: 400, tracking: 0 },
} as const

export const elevation = {
  light: {
    0: 'none',
    1: '0 1px 2px rgba(15,26,36,.06), 0 1px 3px rgba(15,26,36,.08)',
    2: '0 8px 24px rgba(15,26,36,.12)',
    3: '0 16px 48px rgba(15,26,36,.18)',
  },
} as const

/** All tokens as CSS custom properties (`--cimh-*`) for non-Vuetify CSS and email templates. */
export function cssVariables(mode: 'light' | 'dark'): string {
  const lines = Object.entries(color[mode]).map(([k, v]) => `  --cimh-${k}: ${v};`)
  lines.push(...Object.entries(space).map(([k, v]) => `  --cimh-space-${k}: ${v}px;`))
  lines.push(...Object.entries(radius).map(([k, v]) => `  --cimh-r-${k}: ${v}px;`))
  lines.push(`  --cimh-font-sans: ${font.sans};`, `  --cimh-font-mono: ${font.mono};`)
  return lines.join('\n')
}
