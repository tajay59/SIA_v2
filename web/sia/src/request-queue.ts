/**
 * Shared wording and icons for request queues (A-01 dashboard "Needs you now", A-02 desk) and the request
 * detail panel. Colour marks state only: amber = verify, red = quote about to expire; everything else is
 * neutral text + icon so a state is never colour alone.
 */
import type { RequestStatus, RequestSummary } from '@cimh/web-app'
import { statusLabel } from '@cimh/web-ui'
import { markRaw } from 'vue'
import IUrgent from '~icons/material-symbols/error-rounded'
import IAct from '~icons/material-symbols/arrow-circle-right-rounded'
import IFulfil from '~icons/material-symbols/package-2-rounded'
import IExpiring from '~icons/material-symbols/timer-rounded'
import IWait from '~icons/material-symbols/hourglass-top-rounded'
import IClosed from '~icons/material-symbols/check-circle-rounded'
import IQuote from '~icons/material-symbols/calculate-rounded'
import IDraft from '~icons/material-symbols/edit-document-rounded'
import IVerify from '~icons/material-symbols/task-rounded'
import ISigned from '~icons/material-symbols/signature-rounded'
import IShip from '~icons/material-symbols/local-shipping-rounded'
import IDeliver from '~icons/material-symbols/done-all-rounded'
import IStow from '~icons/material-symbols/shelves-rounded'
import IScan from '~icons/material-symbols/barcode-scanner-rounded'
import IRefresh from '~icons/material-symbols/refresh-rounded'
import IReject from '~icons/material-symbols/cancel-rounded'
import ISearch from '~icons/material-symbols/search-rounded'
import IFilter from '~icons/material-symbols/tune-rounded'
import IMore from '~icons/material-symbols/expand-more-rounded'
import IBack from '~icons/material-symbols/arrow-back-rounded'
import IList from '~icons/material-symbols/view-sidebar-rounded'
import IDelete from '~icons/material-symbols/delete-rounded'
import IAdd from '~icons/material-symbols/add-rounded'
import IAttach from '~icons/material-symbols/attach-file-rounded'

export const DAY = 86_400_000
export const ALL_STATUS: RequestStatus[] = ['SUBMITTED', 'QUOTING', 'QUOTED', 'ACCEPTED',
  'PURCHASING', 'APPROVED', 'PICKING', 'SHIPPED', 'DELIVERED', 'DECLINED', 'REJECTED', 'CANCELLED']  // prettier-ignore
export const CLOSED_STATUS: RequestStatus[] = ['DELIVERED', 'DECLINED', 'REJECTED', 'CANCELLED']
export const OPEN_STATUS: RequestStatus[] = ALL_STATUS.filter((s) => !CLOSED_STATUS.includes(s))

export const expiresSoon = (r: RequestSummary) =>
  !!r.quoteExpiresAt && Date.parse(r.quoteExpiresAt) - Date.now() < 3 * DAY
export const fmtDate = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : ''
/** Days in the current status (order-svc `waitingDays`). */
export const waited = (r: RequestSummary) => {
  const d = r.waitingDays ?? 0
  return d === 0 ? 'Since today' : d === 1 ? '1 day' : `${d} days`
}

export type Tone = 'urgent' | 'expiring' | 'act' | 'fulfil' | 'wait' | 'closed'
/** The next move on a request, in staff words. */
export function why(r: RequestSummary): { text: string; tone: Tone } {
  switch (r.status) {
    case 'SUBMITTED':
      return { text: r.type === 'PROBONO' ? 'Approve or reject' : 'Start quoting', tone: 'act' }
    case 'QUOTING':
      return { text: 'Build and send the quote', tone: 'act' }
    case 'QUOTED':
      return expiresSoon(r)
        ? { text: `Quote expires ${fmtDate(r.quoteExpiresAt)}`, tone: 'expiring' }
        : { text: 'Customer signs the agreement or cancels', tone: 'wait' }
    case 'ACCEPTED':
      return { text: 'Check the signed agreement', tone: 'urgent' }
    case 'PURCHASING':
      return { text: 'Purchase, pick and ship', tone: 'fulfil' }
    case 'APPROVED':
    case 'PICKING':
      return { text: 'Pick and ship', tone: 'fulfil' }
    case 'SHIPPED':
      return { text: 'Mark delivered', tone: 'fulfil' }
    default:
      return { text: statusLabel(r.status), tone: 'closed' }
  }
}

export const TONE_ICON = {
  urgent: markRaw(IUrgent),
  expiring: markRaw(IExpiring),
  act: markRaw(IAct),
  fulfil: markRaw(IFulfil),
  wait: markRaw(IWait),
  closed: markRaw(IClosed),
} as const

/** Button icons: Material Symbols, filled, rounded. */
export const BTN = {
  quote: markRaw(IQuote),
  draft: markRaw(IDraft),
  approve: markRaw(IClosed),
  verify: markRaw(IVerify),
  signed: markRaw(ISigned),
  pick: markRaw(IFulfil),
  ship: markRaw(IShip),
  deliver: markRaw(IDeliver),
  stow: markRaw(IStow),
  scan: markRaw(IScan),
  retry: markRaw(IRefresh),
  reject: markRaw(IReject),
  search: markRaw(ISearch),
  filter: markRaw(IFilter),
  more: markRaw(IMore),
  back: markRaw(IBack),
  list: markRaw(IList),
  remove: markRaw(IDelete),
  add: markRaw(IAdd),
  attach: markRaw(IAttach),
} as const
