/** Display formatting: TRD TR-I18N-1 (English; dates dd MMM yyyy; money with currency code). */

export type Currency = 'BBD' | 'USD'

const MONEY_RE = /^-?\d{1,12}\.\d{2}$/

/**
 * API money is a string with 2 decimals ("1250.00"), never a float. Format without
 * converting to a float so large values keep their exact cents: "BBD 1,250.00".
 */
export function formatMoney(amount: string, currency: Currency): string {
  if (!MONEY_RE.test(amount)) throw new Error(`invalid money value: ${amount}`)
  const negative = amount.startsWith('-')
  const [whole, cents] = (negative ? amount.slice(1) : amount).split('.')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${currency} ${negative ? '-' : ''}${grouped}.${cents}`
}

const DATE_FMT = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'America/Barbados',
  day: '2-digit',
  month: 'short',
  year: 'numeric',
})
const DATETIME_FMT = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'America/Barbados',
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

function parts(fmt: Intl.DateTimeFormat, value: Date): Record<string, string> {
  return Object.fromEntries(fmt.formatToParts(value).map((p) => [p.type, p.value]))
}

/** ISO-8601 UTC -> "06 Nov 2026" in Barbados time. Date-only strings are shown as given. */
export function formatDate(iso: string): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    const p = parts(new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', day: '2-digit', month: 'short', year: 'numeric' }), new Date(`${iso}T00:00:00Z`))
    return `${p.day} ${p.month} ${p.year}`
  }
  const p = parts(DATE_FMT, new Date(iso))
  return `${p.day} ${p.month} ${p.year}`
}

/** "06 Nov 2026, 10:03" in Barbados time (UTC-4, no DST). */
export function formatDateTime(iso: string): string {
  const p = parts(DATETIME_FMT, new Date(iso))
  return `${p.day} ${p.month} ${p.year}, ${p.hour}:${p.minute}`
}
