// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { clearDrafts, readDraft, removeDraft, writeDraft } from '../src/draft'

describe('form drafts (APD §2)', () => {
  beforeEach(() => sessionStorage.clear())

  it('round-trips a draft and removes it', () => {
    writeDraft('product:new', { name: 'Barometer' })
    expect(readDraft('product:new')).toEqual({ name: 'Barometer' })
    removeDraft('product:new')
    expect(readDraft('product:new')).toBeNull()
  })

  it('ignores drafts older than four hours', () => {
    const now = Date.now()
    vi.spyOn(Date, 'now').mockReturnValue(now - 5 * 60 * 60 * 1000)
    writeDraft('old', { a: 1 })
    vi.spyOn(Date, 'now').mockReturnValue(now)
    expect(readDraft('old')).toBeNull()
    vi.restoreAllMocks()
  })

  it('logout clears every draft and nothing else', () => {
    writeDraft('a', 1)
    writeDraft('b', 2)
    sessionStorage.setItem('other', 'kept')
    clearDrafts()
    expect(readDraft('a')).toBeNull()
    expect(readDraft('b')).toBeNull()
    expect(sessionStorage.getItem('other')).toBe('kept')
  })

  it('survives broken stored data', () => {
    sessionStorage.setItem('cimh:draft:x', '{not json')
    expect(readDraft('x')).toBeNull()
  })
})
