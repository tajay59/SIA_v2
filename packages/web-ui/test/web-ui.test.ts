import { describe, expect, it } from 'vitest'
import {
  ACCOUNT_STATUS_TONE,
  REQUEST_STATUS_TONE,
  color,
  componentDefaults,
  contrast,
  cssVariables,
  formatDate,
  formatDateTime,
  formatMoney,
  statusLabel,
  statusTone,
  vuetifyOptions,
} from '../src'

describe('contrast (DESIGN_BRIEF §3)', () => {
  const AA = 4.5
  it.each(['light', 'dark'] as const)('%s: text tokens meet AA on surface and bg', (mode) => {
    const c = color[mode]
    for (const fg of [c.ink, c['ink-muted'], c.primary, c.success, c.warning, c.error]) {
      expect(contrast(fg, c.surface)).toBeGreaterThanOrEqual(AA)
      expect(contrast(fg, c.bg)).toBeGreaterThanOrEqual(AA)
    }
  })
  it('on-primary text on primary meets AA in both themes', () => {
    expect(contrast(color.light['on-primary'], color.light.primary)).toBeGreaterThanOrEqual(AA)
    expect(contrast(color.dark['on-primary'], color.dark.primary)).toBeGreaterThanOrEqual(AA)
  })
  it('logo blue fails AA for body text on white (so it is never used for text)', () => {
    expect(contrast(color.light['brand-logo'], '#FFFFFF')).toBeCloseTo(4.09, 1)
  })
  it('Pro Bono badge only works with ink text', () => {
    expect(contrast(color.light.ink, color.light['accent-probono'])).toBeGreaterThan(10)
    expect(contrast('#FFFFFF', color.light['accent-probono'])).toBeLessThan(AA)
  })
  it.each(['light', 'dark'] as const)('%s: the field edge is a 3:1 boundary on every ground a field sits on (WCAG 1.4.11)', (mode) => {
    const c = color[mode]
    const sia = vuetifyOptions('sia').theme.themes[mode === 'light' ? 'cimhLight' : 'cimhDark'].colors
    expect(sia['field-outline']).toBe(c['field-outline'])
    for (const ground of [c.surface, c.bg, c['surface-2'], sia.surface, sia.background, sia['surface-variant']]) {
      expect(contrast(c['field-outline'], ground)).toBeGreaterThanOrEqual(3)
    }
  })
  it('primary text on primary-subtle meets AA', () => {
    expect(contrast(color.light.primary, color.light['primary-subtle'])).toBeGreaterThanOrEqual(AA)
  })
})

describe('theme', () => {
  it('density differs per app', () => {
    expect(componentDefaults('sia').global.density).toBe('compact')
    expect(componentDefaults('shop').global.density).toBe('default')
  })
  it('exposes both themes', () => {
    const o = vuetifyOptions('shop')
    expect(Object.keys(o.theme.themes)).toEqual(['cimhLight', 'cimhDark'])
    expect(o.theme.themes.cimhDark.dark).toBe(true)
  })
  it('text on filled status colours (toasts, filled chips) meets AA in every theme', () => {
    for (const app of ['shop', 'sia'] as const) {
      for (const t of Object.values(vuetifyOptions(app).theme.themes)) {
        const c = t.colors as Record<string, string>
        for (const s of ['success', 'warning', 'error', 'info']) {
          // Vuetify picks white or black when on-<s> is unset; light themes rely on white over dark hues.
          expect(contrast(c[`on-${s}`] ?? '#FFFFFF', c[s]!), `${app} ${t.dark ? 'dark' : 'light'} ${s}`).toBeGreaterThanOrEqual(4.5)
        }
      }
    }
  })
  it('emits css variables', () => {
    const css = cssVariables('dark')
    expect(css).toContain('--cimh-primary: #5CC2FF;')
    expect(css).toContain('--cimh-space-4: 16px;')
  })
})

describe('status chips (§3.4)', () => {
  it('maps every request status', () => {
    expect(Object.keys(REQUEST_STATUS_TONE)).toHaveLength(14)
    expect(statusTone('AWAITING_AGREEMENT')).toBe('warning')
    expect(statusTone('DELIVERED')).toBe('success')
    expect(ACCOUNT_STATUS_TONE.PENDING_APPROVAL).toBe('warning')
    expect(statusTone('REJECTED')).toBe('error')
    expect(statusTone('UNKNOWN')).toBe('neutral')
  })
  it('labels are sentence case', () => {
    expect(statusLabel('AWAITING_AGREEMENT')).toBe('Awaiting agreement')
    expect(statusLabel('PENDING_VERIFICATION')).toBe('Pending verification')
    expect(statusLabel('')).toBe('')
  })
})

describe('format (TR-I18N-1)', () => {
  it('money keeps exact cents and the currency code', () => {
    expect(formatMoney('1250.00', 'BBD')).toBe('BBD 1,250.00')
    expect(formatMoney('999999999999.99', 'USD')).toBe('USD 999,999,999,999.99')
    expect(formatMoney('-5.10', 'BBD')).toBe('BBD -5.10')
    expect(() => formatMoney('1.5', 'BBD')).toThrow()
  })
  it('dates are dd MMM yyyy in Barbados time', () => {
    expect(formatDate('2026-11-07T02:30:00Z')).toBe('06 Nov 2026') // 22:30 on the 6th in Barbados
    expect(formatDate('2026-11-07')).toBe('07 Nov 2026')
    expect(formatDateTime('2026-11-06T14:03:22Z')).toBe('06 Nov 2026, 10:03')
  })
})
