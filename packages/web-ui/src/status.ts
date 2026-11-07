/** Status chip mapping: DESIGN_BRIEF.md §3.4 (one mapping, used everywhere). */

export type Tone = 'neutral' | 'info' | 'warning' | 'success' | 'error'

export const REQUEST_STATUS_TONE = {
  CART: 'neutral',
  SUBMITTED: 'neutral',
  QUOTING: 'info',
  QUOTED: 'info',
  APPROVED: 'info',
  PURCHASING: 'info',
  PICKING: 'info',
  SHIPPED: 'info',
  AWAITING_AGREEMENT: 'warning',
  ACCEPTED: 'success',
  DELIVERED: 'success',
  DECLINED: 'error',
  REJECTED: 'error',
  CANCELLED: 'error',
} as const satisfies Record<string, Tone>

export const ACCOUNT_STATUS_TONE = {
  PENDING_VERIFICATION: 'neutral',
  PENDING_APPROVAL: 'warning',
  ACTIVE: 'success',
  REJECTED: 'error',
  SUSPENDED: 'error',
  EXPIRED: 'error',
} as const satisfies Record<string, Tone>

export const UNIT_STATE_TONE = {
  stowed: 'neutral',
  reserved: 'info',
  assigned: 'warning',
  picked: 'success',
} as const satisfies Record<string, Tone>

export type RequestStatus = keyof typeof REQUEST_STATUS_TONE
export type AccountStatus = keyof typeof ACCOUNT_STATUS_TONE

/** Vuetify colour name for a tone (neutral uses the muted ink). */
export const TONE_COLOR: Record<Tone, string> = {
  neutral: 'secondary',
  info: 'info',
  warning: 'warning',
  success: 'success',
  error: 'error',
}

export const TONE_ICON: Record<Tone, string> = {
  neutral: 'mdi-circle-outline',
  info: 'mdi-progress-clock',
  warning: 'mdi-alert-circle-outline',
  success: 'mdi-check-circle-outline',
  error: 'mdi-close-circle-outline',
}

/** "AWAITING_AGREEMENT" -> "Awaiting agreement" (sentence case, §4 rules). */
export function statusLabel(status: string): string {
  const words = status.toLowerCase().split('_').filter(Boolean)
  if (words.length === 0) return ''
  const sentence = words.join(' ')
  return sentence.charAt(0).toUpperCase() + sentence.slice(1)
}

export function statusTone(status: string): Tone {
  const all: Record<string, Tone> = { ...UNIT_STATE_TONE, ...ACCOUNT_STATUS_TONE, ...REQUEST_STATUS_TONE }
  return all[status] ?? 'neutral'
}
