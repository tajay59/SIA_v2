import { describe, expect, it } from 'vitest'
import { addCents, customerActionNeeded, type OrderRequest, quoteRows, statusSteps } from '../src/orders'

const line = (lineId: string, qty = 1) =>
  ({ lineId, productId: `P${lineId}`, qty, product: { name: lineId, type: 'MET', probono: false } }) as OrderRequest['lines'][number]

describe('orders helpers', () => {
  it('adds money in cents (no float drift)', () => {
    expect(addCents('0.10', '0.20')).toBe('0.30')
    expect(addCents('199.99', null, undefined, '0.01')).toBe('200.00')
  })

  it('pairs supplier and CIMH options per line from the latest quote only', () => {
    const r = {
      lines: [line('L1', 2), line('L2')],
      quotes: [
        { id: 'Q1', version: 1, lines: [{ lineId: 'L1', unitPrice: '9.00', total: '18.00' }], total: '18.00', expiresAt: '' },
        { id: 'Q2', version: 2, lines: [{ lineId: 'L1', unitPrice: '8.00', total: '16.00' }], total: '16.00', expiresAt: '' },
      ],
      cimhQuote: { version: 2, lines: [{ lineId: 'L2', unitPrice: '5.00', total: '5.00' }], total: '5.00' },
    } as unknown as OrderRequest
    const { version, rows } = quoteRows(r)
    expect(version).toBe(2)
    expect(rows[0]!.supplier?.total).toBe('16.00')
    expect(rows[0]!.cimh).toBeNull()
    expect(rows[1]!.supplier).toBeNull()
    expect(rows[1]!.cimh?.total).toBe('5.00')
  })

  it('flags what the customer must do and the steps of each flow', () => {
    expect(customerActionNeeded({ status: 'QUOTED' })).toBe('Quote ready')
    expect(customerActionNeeded({ status: 'AWAITING_AGREEMENT' })).toBe('Agreement to sign')
    expect(customerActionNeeded({ status: 'QUOTING' })).toBeNull()
    expect(statusSteps('PROBONO')).toEqual(['SUBMITTED', 'APPROVED', 'PICKING', 'SHIPPED', 'DELIVERED'])
    expect(statusSteps('PAID')).toContain('AWAITING_AGREEMENT')
  })
})
