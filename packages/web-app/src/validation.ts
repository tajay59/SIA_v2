/**
 * Client-side validation with Zod 4, mirroring the contract (docs/api/identity.openapi.yaml). The server
 * stays the authority: its 422 `errors[]` are shown inline too. Vuetify rules are derived from the schemas
 * so one definition drives both.
 *
 * `zod/mini` (Lighthouse fix 3, 2026-11-25): the same checks as classic Zod in a tree-shakable, functional form;
 * classic Zod was the largest library on the sign-in and sign-up pages (~78 KB). Checks run in order, so
 * `z.trim()` before a length check measures the trimmed text, as classic `.trim().min()` did.
 */
import { z } from 'zod/mini'

// No compiled validators: Zod probes `new Function` to decide, and our CSP (script-src 'self', no unsafe-eval)
// blocks it, which Chrome reports as a CSP violation on every page even though Zod catches it (Lighthouse
// 2026-11-25). Interpreted parsing is plenty fast for form-sized data. Runs at module load (index re-exports
// this module), before any schema parses.
z.config({ jitless: true })

/** An empty field is asked for, not called invalid (audit 2026-11-26: "Enter a valid email address" for a blank). */
const isBlank = (input: unknown) => input == null || (typeof input === 'string' && !input.trim())
export const email = z
  .email({ error: (iss) => (isBlank(iss.input) ? 'Enter your email address' : 'Enter a valid email address') })
  .check(z.maxLength(254))
export const password = z.string().check(z.minLength(12, 'At least 12 characters'), z.maxLength(256, 'At most 256 characters'))
export const code = z.string().check(z.regex(/^\d{6}$/, 'Enter the 6-digit code'))
export const name = z.string().check(z.trim(), z.minLength(1, 'Required'), z.maxLength(100, 'At most 100 characters'))
export const country = z.string().check(z.regex(/^[A-Z]{2}$/, 'Choose a country'))
export const phone = z.string().check(z.maxLength(40, 'At most 40 characters'))
export const reason = z.string().check(z.trim(), z.minLength(3, 'At least 3 characters'), z.maxLength(500, 'At most 500 characters'))

export const CIMH_DOMAIN = '@cimh.edu.bb'
export const isCimhEmail = (value: string): boolean => value.trim().toLowerCase().endsWith(CIMH_DOMAIN)

export const registerFields = {
  firstname: name,
  lastname: name,
  email,
  password,
  organisationText: z.string().check(z.trim(), z.maxLength(200, 'At most 200 characters')),
  department: z.string().check(z.maxLength(100, 'At most 100 characters')),
  country,
  phone,
  terms: z.literal(true, 'Please accept the terms'),
}

export const register = z.object(registerFields).check(
  z.refine((v) => isCimhEmail(v.email) || v.organisationText.length > 0, {
    path: ['organisationText'],
    message: 'Enter your organisation',
  }),
)

export type Rule = (value: unknown) => true | string

/** A Vuetify rule from a Zod schema: first issue message, or true. */
export function rule(schema: z.ZodMiniType): Rule {
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
