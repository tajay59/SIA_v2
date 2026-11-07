/**
 * Client-side validation with Zod 4, mirroring the contract (docs/api/identity.openapi.yaml). The server
 * stays the authority: its 422 `errors[]` are shown inline too. Vuetify rules are derived from the schemas
 * so one definition drives both.
 */
import { z } from 'zod'

export const email = z.email('Enter a valid email address').max(254)
export const password = z
  .string()
  .min(12, 'At least 12 characters')
  .max(256, 'At most 256 characters')
export const code = z.string().regex(/^\d{6}$/, 'Enter the 6-digit code')
export const name = z.string().trim().min(1, 'Required').max(100, 'At most 100 characters')
export const country = z.string().regex(/^[A-Z]{2}$/, 'Choose a country')
export const phone = z.string().max(40, 'At most 40 characters')
export const reason = z.string().trim().min(3, 'At least 3 characters').max(500, 'At most 500 characters')

export const CIMH_DOMAIN = '@cimh.edu.bb'
export const isCimhEmail = (value: string): boolean => value.trim().toLowerCase().endsWith(CIMH_DOMAIN)

export const registerFields = {
  firstname: name,
  lastname: name,
  email,
  password,
  organisationText: z.string().trim().max(200, 'At most 200 characters'),
  department: z.string().max(100, 'At most 100 characters'),
  country,
  phone,
  terms: z.literal(true, 'Please accept the terms'),
}

export const register = z
  .object(registerFields)
  .refine((v) => isCimhEmail(v.email) || v.organisationText.length > 0, {
    path: ['organisationText'],
    message: 'Enter your organisation',
  })

export type Rule = (value: unknown) => true | string

/** A Vuetify rule from a Zod schema: first issue message, or true. */
export function rule(schema: z.ZodType): Rule {
  return (value: unknown) => {
    const r = schema.safeParse(value)
    return r.success ? true : (r.error.issues[0]?.message ?? 'Invalid')
  }
}

/** Rough strength meter (0–4) for the sign-up and reset forms; the breach check happens on the server. */
export function passwordStrength(pw: string): { score: number; label: string } {
  if (!pw) return { score: 0, label: '' }
  let score = 0
  if (pw.length >= 12) score++
  if (pw.length >= 16) score++
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score++
  if (/\d/.test(pw) || /[^A-Za-z0-9]/.test(pw)) score++
  if (pw.length < 12) score = Math.min(score, 1)
  const labels = ['Too short', 'Weak', 'Fair', 'Good', 'Strong']
  return { score, label: labels[score] ?? '' }
}
