import { describe, expect, it } from 'vitest'
import { addCents, currentAgreement, customerActionNeeded, type OrderRequest, pricedQuote, statusSteps } from '../src/orders'

const line = (lineId: string, qty = 1, extra: Record<string, unknown> = {}) =>
  ({ lineId, productId: `P${lineId}`, qty, product: { name: lineId, type: 'MET', probono: false }, ...extra }) as OrderRequest['lines'][number]

describe('orders helpers', () => {
  it('adds money in cents (no float drift)', () => {
    expect(addCents('0.10', '0.20')).toBe('0.30')
    expect(addCents('199.99', null, undefined, '0.01')).toBe('200.00')
  })

  it('prices every line once from the latest quote, with shipping per source and the signed total', () => {
    const r = {
      lines: [line('L1', 2, { source: 'SUPPLIER', supplier: 'Vaisala' }), line('L2', 1, { source: 'CIMH' })],
      adminFee: '25.00',
      quotes: [
        { id: 'Q1', version: 1, supplier: 'Vaisala', lines: [{ lineId: 'L1', unitPrice: '9.00', total: '18.00' }], total: '18.00', shippingEstimate: '4.00', expiresAt: '' },
        { id: 'Q2', version: 2, supplier: 'Vaisala', lines: [{ lineId: 'L1', unitPrice: '8.00', total: '16.00' }], total: '16.00', shippingEstimate: '3.00', expiresAt: '' },
      ],
      cimhQuote: { version: 2, lines: [{ lineId: 'L2', unitPrice: '5.00', total: '5.00' }], total: '5.00', shippingEstimate: '2.00' },
      agreement: { quoteVersion: 2, total: '51.00' },
    } as unknown as OrderRequest
    const q = pricedQuote(r)
    expect(q.version).toBe(2)
    expect(q.rows.map((x) => [x.source, x.supplier, x.total])).toEqual([['SUPPLIER', 'Vaisala', '16.00'], ['CIMH', null, '5.00']])
    expect(q.shipping).toEqual([
      { source: 'CIMH', label: 'CIMH stock', amount: '2.00' },
      { source: 'SUPPLIER', label: 'Vaisala', amount: '3.00' },
    ])
    expect([q.items, q.fee, q.total]).toEqual(['21.00', '25.00', '51.00'])
    expect(currentAgreement(r)?.total).toBe('51.00')
    // An agreement made for an earlier version is void: the total is the sum of the parts.
    const old = { ...r, agreement: { quoteVersion: 1, total: '99.00' } } as unknown as OrderRequest
    expect(currentAgreement(old)).toBeNull()
    expect(pricedQuote(old).total).toBe('51.00')
  })

  it('flags what the customer must do and the steps of each flow', () => {
    expect(customerActionNeeded({ status: 'QUOTED' })).toBe('Quote to sign')
    expect(customerActionNeeded({ status: 'QUOTING' })).toBeNull()
    expect(statusSteps('PROBONO')).toEqual(['SUBMITTED', 'APPROVED', 'PICKING', 'SHIPPED', 'DELIVERED'])
    expect(statusSteps('PAID')).toEqual(['SUBMITTED', 'QUOTING', 'QUOTED', 'ACCEPTED', 'PURCHASING', 'SHIPPED', 'DELIVERED'])
  })
})
