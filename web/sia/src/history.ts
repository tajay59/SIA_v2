/**
 * A-15 movement history: shared filters, list and formatting for the /reports/history designs.
 * Day boundaries and day groups are in Barbados time (America/Barbados, UTC-4, no DST).
 */
import { type AccountSummary, call, type HistoryEntry, inventory, type Operation, OPERATION_LABELS, useAccountNames, useCursorList } from '@cimh/web-app'
import {
  mdiAccountArrowLeftOutline,
  mdiAccountArrowRightOutline,
  mdiArrowDownBoldBoxOutline,
  mdiArrowUpBoldBoxOutline,
  mdiBookmarkOffOutline,
  mdiBookmarkOutline,
  mdiSwapHorizontal,
  mdiTuneVariant,
} from '@mdi/js'
import { computed, reactive, watch } from 'vue'

export const OP_ICONS: Record<Operation, string> = {
  stow: mdiArrowDownBoldBoxOutline,
  pick: mdiArrowUpBoldBoxOutline,
  relocate: mdiSwapHorizontal,
  assign: mdiAccountArrowRightOutline,
  unassign: mdiAccountArrowLeftOutline,
  reserve: mdiBookmarkOutline,
  release: mdiBookmarkOffOutline,
  adjust: mdiTuneVariant,
}
export const OPERATIONS = Object.keys(OPERATION_LABELS) as Operation[]

const TZ = 'America/Barbados'
const dayKeyFmt = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' })
const dayLabelFmt = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
const timeFmt = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hour12: false })

/** `YYYY-MM-DD` of an instant in Barbados. */
export const dayKey = (iso: string | Date) => dayKeyFmt.format(typeof iso === 'string' ? new Date(iso) : iso)
export const timeOf = (iso: string) => timeFmt.format(new Date(iso))
export function dayLabel(key: string): string {
  const today = dayKey(new Date())
  const yesterday = dayKey(new Date(Date.now() - 864e5))
  const label = dayLabelFmt.format(new Date(`${key}T12:00:00-04:00`))
  return key === today ? `Today · ${label}` : key === yesterday ? `Yesterday · ${label}` : label
}

export type Preset = 'all' | 'today' | '7d' | '30d' | 'custom'
export const PRESETS: { value: Preset; title: string }[] = [
  { value: 'all', title: 'Any time' },
  { value: 'today', title: 'Today' },
  { value: '7d', title: '7 days' },
  { value: '30d', title: '30 days' },
  { value: 'custom', title: 'Custom' },
]


export function useMovementHistory() {
  const { name } = useAccountNames()
  const f = reactive({ unit: '', person: null as AccountSummary | null, operation: null as Operation | null, preset: 'all' as Preset, from: '', to: '' })

  const range = computed(() => {
    const today = dayKey(new Date())
    const back = (days: number) => dayKey(new Date(Date.now() - days * 864e5))
    switch (f.preset) {
      case 'today':
        return { from: today, to: today }
      case '7d':
        return { from: back(6), to: today }
      case '30d':
        return { from: back(29), to: today }
      case 'custom':
        return { from: f.from, to: f.to }
      default:
        return { from: '', to: '' }
    }
  })
  const dayStart = (d: string) => (d ? `${d}T00:00:00-04:00` : undefined)
  const dayEnd = (d: string) => (d ? `${d}T23:59:59-04:00` : undefined)

  const list = useCursorList<HistoryEntry>((cursor) =>
    call(() =>
      inventory.GET('/history', {
        params: {
          query: {
            unit: f.unit.trim() || undefined,
            user: f.person?.id,
            operation: f.operation ?? undefined,
            from: dayStart(range.value.from),
            to: dayEnd(range.value.to),
            cursor,
            limit: 50,
          },
        },
      }),
    ),
  )
  const reload = () => void list.reload()
  watch(() => [f.person, f.operation, range.value.from, range.value.to], reload)

  const active = computed(() => {
    const out: { key: string; label: string; clear: () => void }[] = []
    if (f.unit.trim()) out.push({ key: 'unit', label: `Unit ${f.unit.trim()}`, clear: () => ((f.unit = ''), reload()) })
    if (f.person) out.push({ key: 'person', label: `By ${f.person.firstname} ${f.person.lastname}`, clear: () => (f.person = null) })
    if (f.operation) out.push({ key: 'op', label: OPERATION_LABELS[f.operation], clear: () => (f.operation = null) })
    if (f.preset !== 'all' && (range.value.from || range.value.to)) {
      const p = PRESETS.find((x) => x.value === f.preset)!
      const label = f.preset === 'custom' ? `${range.value.from || '…'} to ${range.value.to || '…'}` : p.title === 'Today' ? 'Today' : `Last ${p.title}`
      out.push({ key: 'when', label, clear: () => ((f.preset = 'all'), (f.from = ''), (f.to = '')) })
    }
    return out
  })
  function clearAll() {
    f.unit = ''
    f.person = null
    f.operation = null
    f.preset = 'all'
    f.from = ''
    f.to = ''
    reload()
  }

  /** Rows grouped by Barbados day, newest first (the server's order). */
  const days = computed(() => {
    const out: { key: string; label: string; items: HistoryEntry[] }[] = []
    for (const h of list.items.value) {
      const k = dayKey(h.date)
      const last = out[out.length - 1]
      if (last?.key === k) last.items.push(h)
      else out.push({ key: k, label: dayLabel(k), items: [h] })
    }
    return out
  })

  return { f, list, reload, active, clearAll, days, name, range }
}

// Shelf names: history stores codes only, so each shelf is looked up once (inventory /shelves/{barcode}).
const shelfNames = reactive(new Map<string, string>())
const asked = new Set<string>()
function resolveShelf(code: string) {
  if (asked.has(code)) return
  asked.add(code)
  call(() => inventory.GET('/shelves/{barcode}', { params: { path: { barcode: code } } }))
    .then((s) => shelfNames.set(code, `${s.siteName ?? 'Site'} › ${s.locationName ?? 'Location'} › Shelf ${s.number}`))
    .catch(() => shelfNames.set(code, 'Unknown shelf'))
}

/** Readable place: "Site › Location › Shelf n" once the shelf is known, the shelf code until then. */
export function place(p: { site?: string | null; location?: string | null; shelf?: string | null } | null | undefined): string {
  if (!p?.shelf) return ''
  resolveShelf(p.shelf)
  return shelfNames.get(p.shelf) ?? p.shelf
}

/** Unit codes are `<TYPE><32 hex>_<8 hex>`: show "TYPE…last6_suffix"; the full code goes in the title. */
export function shortUnit(code: string): string {
  const m = /^([A-Z]+)([0-9a-f]{32})(_[0-9a-f]{8})?$/i.exec(code)
  return m ? `${m[1]}…${m[2]!.slice(-6)}${m[3] ?? ''}` : code
}

/** Who the unit went to or came back from (issue/return). */
export function personPart(h: HistoryEntry, name: (id: string) => string): string | null {
  if (!h.accountId) return null
  return `${h.operation === 'assign' ? 'to' : 'from'} ${name(h.accountId)}`
}

export const unitLink = (code: string) => ({ path: '/inventory', query: { code } })
export const requestLink = (id: string) => `/requests/${id}`

