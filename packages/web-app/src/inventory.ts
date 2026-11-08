/**
 * Inventory API access and helpers for SIA (inventory.openapi.yaml, APD A-08…A-15).
 *
 * Scans (`/stow`, `/pick`, `/relocate`, `/assign`, `/unassign`) carry an `Idempotency-Key`: one key per
 * physical scan, so a retried request is never applied twice (the server returns the first answer).
 * Their 409s are business answers ("already stowed", "issued to …"), shown next to the scan, not as
 * edit-conflict toasts.
 */
import { type InventoryComponents, inventoryClient } from '@cimh/web-api'
import { reactive } from 'vue'
import { ApiError, call, identity } from './api'

type S = InventoryComponents['schemas']
export type Unit = S['Unit']
export type Site = S['Site']
export type Location = S['Location']
export type Shelf = S['Shelf']
export type ProductStock = S['ProductStock']
export type HistoryEntry = S['HistoryEntry']
export type Operation = S['Operation']

export const inventory = inventoryClient()

export const OPERATION_LABELS: Record<Operation, string> = {
  stow: 'Stowed',
  pick: 'Picked',
  relocate: 'Moved',
  assign: 'Issued',
  unassign: 'Returned',
  reserve: 'Reserved',
  release: 'Released',
  adjust: 'Adjusted',
}

export function newScanKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

type ScanPath = '/stow' | '/pick' | '/relocate' | '/assign' | '/unassign'

/** One scan with its own Idempotency-Key. Pass `key` to retry the same scan safely. */
export function scan(path: ScanPath, body: Record<string, unknown>, key: string = newScanKey()): Promise<Unit> {
  const params = { header: { 'Idempotency-Key': key } }
  // The body type depends on the path; the server validates it strictly.
  return call(() => inventory.POST(path as any, { params, body } as any)) as Promise<Unit>
}

/** A short, human answer for a failed scan (shown in the scan list). */
export function scanError(e: unknown): string {
  if (!(e instanceof ApiError)) return 'Something went wrong'
  if (e.isNetwork) return 'No connection: scan again'
  if (e.status === 422 && e.errors.length) return e.errors.map((x) => x.message).join(', ')
  return e.detail ?? e.message
}

export type CodeKind = 'shelf' | 'site' | 'location' | 'request' | 'unit' | 'product'

/** What a scanned code most likely is, from the legacy barcode formats (BSD §4). */
export function codeKind(raw: string): CodeKind {
  const code = raw.trim()
  if (/^SHEL[0-9a-f]{32}$/i.test(code)) return 'shelf'
  if (/^SITE[0-9a-f]{32}$/i.test(code)) return 'site'
  if (/^LOC[0-9a-f]{32}$/i.test(code)) return 'location'
  if (/^(ORD|CRT)[0-9A-Za-z]{20,}$/.test(code)) return 'request'
  if (code.includes('_')) return 'unit'
  return 'product'
}

/** "Store A · shelf 2" (or "Not on a shelf"). */
export function unitWhere(u: Pick<Unit, 'stowed' | 'locationName' | 'location' | 'shelfNumber'>): string {
  if (!u.stowed) return 'Not on a shelf'
  return `${u.locationName ?? u.location ?? 'Unknown location'} · shelf ${u.shelfNumber ?? '?'}`
}

/** Unit state in one word, for chips. */
export function unitState(u: Unit): { label: string; tone: 'success' | 'warning' | 'info' | 'neutral' } {
  if (u.picked) return { label: 'Picked', tone: 'neutral' }
  if (u.assignedTo) return { label: 'Issued', tone: 'info' }
  if (u.reservedFor) return { label: 'Reserved', tone: 'warning' }
  if (u.stowed) return { label: 'On shelf', tone: 'success' }
  return { label: 'Not placed', tone: 'neutral' }
}

// Account ids -> "First Last" (identity GET /admin/accounts/{id}, staff may read). Cached for the session.
const names = reactive(new Map<string, string>())
const pending = new Set<string>()

export function useAccountNames() {
  function load(id: string) {
    if (!id || names.has(id) || pending.has(id) || id.startsWith('svc:')) return
    pending.add(id)
    call(() => identity.GET('/admin/accounts/{accountId}', { params: { path: { accountId: id } } }))
      .then((a) => names.set(id, `${a.firstname} ${a.lastname}`.trim() || a.email))
      .catch(() => names.set(id, id))
      .finally(() => pending.delete(id))
  }
  /** The person's name once loaded; the id meanwhile (and for service ids such as svc:order). */
  function name(id: string | null | undefined): string {
    if (!id) return ''
    if (id === 'svc:order') return 'Requests (automatic)'
    load(id)
    return names.get(id) ?? id
  }
  return { name }
}

/** Legacy CSV label file: one row per unit, `barcode,CODE` (legacy getBatchCodeCSV). */
export function labelsCsv(barcodes: string[]): string {
  const rows = barcodes.map((b) => `${b},${(b.split('_').pop() ?? b).toUpperCase()}`)
  return ['barcode,code', ...rows].join('\r\n') + '\r\n'
}
