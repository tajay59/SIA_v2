import { describe, expect, it, vi } from 'vitest'

const post = vi.fn()
vi.mock('@cimh/web-api', () => ({
  identityClient: () => ({ POST: vi.fn(), GET: vi.fn() }),
  inventoryClient: () => ({ POST: post, GET: vi.fn() }),
}))

const { ApiError } = await import('../src/api')
const { codeKind, labelsCsv, scan, scanError, unitState, unitWhere } = await import('../src/inventory')

const hex = '0123456789abcdef0123456789abcdef'
const unit = (over: Record<string, unknown> = {}) =>
  ({ barcode: 'U', product: 'P', stowed: false, picked: false, ...over }) as Parameters<typeof unitState>[0]

describe('codeKind', () => {
  it('recognises the legacy barcode formats', () => {
    expect(codeKind(`SHEL${hex}`)).toBe('shelf')
    expect(codeKind(` SITE${hex} `)).toBe('site')
    expect(codeKind(`LOC${hex}`)).toBe('location')
    expect(codeKind(`MET${hex}_9f8e7d6c`)).toBe('unit')
    expect(codeKind(`ORD${hex}`)).toBe('request')
    expect(codeKind(`MET${hex}`)).toBe('product')
    expect(codeKind('SHELF-1')).toBe('product') // not a shelf barcode
  })
})

describe('unit helpers', () => {
  it('says where a unit is and what state it is in', () => {
    expect(unitWhere(unit())).toBe('Not on a shelf')
    expect(unitWhere(unit({ stowed: true, locationName: 'Store A', shelfNumber: 3 }))).toBe('Store A · shelf 3')
    expect(unitState(unit({ stowed: true })).label).toBe('On shelf')
    expect(unitState(unit({ stowed: true, reservedFor: 'ORD1' })).label).toBe('Reserved')
    expect(unitState(unit({ assignedTo: 'USR1' })).label).toBe('Issued')
    expect(unitState(unit({ picked: true })).label).toBe('Picked')
  })

  it('writes the legacy label CSV', () => {
    expect(labelsCsv([`P_ab12cd34`])).toBe('barcode,code\r\nP_ab12cd34,AB12CD34\r\n')
  })
})

describe('scan', () => {
  it('sends an Idempotency-Key and reuses the one given for a retry', async () => {
    post.mockResolvedValue({ data: { barcode: 'U' }, response: new Response(null, { status: 200 }) })
    await scan('/stow', { unit: 'U', shelf: 'S' }, 'KEY-1')
    expect(post).toHaveBeenCalledWith('/stow', { params: { header: { 'Idempotency-Key': 'KEY-1' } }, body: { unit: 'U', shelf: 'S' } })
    await scan('/pick', { unit: 'U', reason: 'x' })
    const key = post.mock.calls[1][1].params.header['Idempotency-Key']
    expect(key).toMatch(/.{8,}/)
    expect(key).not.toBe('KEY-1')
  })

  it('turns errors into a short sentence', () => {
    expect(scanError(new ApiError(409, { code: 'UNIT_ALREADY_STOWED', detail: 'Already stowed at Store A shelf 1' }))).toBe(
      'Already stowed at Store A shelf 1',
    )
    expect(scanError(new ApiError(0))).toBe('No connection: scan again')
    expect(scanError(new ApiError(422, { errors: [{ field: 'unit', message: 'required' }] }))).toBe('required')
    expect(scanError(new Error('x'))).toBe('Something went wrong')
  })
})
