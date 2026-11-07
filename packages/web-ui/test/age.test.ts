import { describe, expect, it } from 'vitest'
import { formatAge } from '../src/format'

describe('formatAge', () => {
  const now = Date.parse('2026-11-07T12:00:00Z')
  it.each([
    ['2026-11-07T11:59:30Z', 'just now'],
    ['2026-11-07T11:48:00Z', '12 min'],
    ['2026-11-07T07:00:00Z', '5 h'],
    ['2026-11-05T13:00:00Z', '47 h'],
    ['2026-11-04T12:00:00Z', '3 days'],
    ['not a date', 'just now'],
  ])('%s -> %s', (iso, want) => expect(formatAge(iso, now)).toBe(want))
})
