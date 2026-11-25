/**
 * What the requests desk (A-02) showed, kept for this tab while staff step into a request's own page (A-03)
 * and come back (owner 2026-11-24). The desk page is remounted on return, so its own state would be lost:
 * - `query`: the desk's last URL query (tab, filters, `?open=`), so "← Orders" returns to the same tab;
 * - `selected`: the request whose summary was shown (set by the desk, and by the request page for the request
 *   just looked at), so the queue keeps it selected instead of falling back to the first row;
 * - `seen`: the last lists per filter set, so the queue shows at once (and the view transition lands on real
 *   rows, not a skeleton) while it refreshes behind.
 */
import type { LocationQuery } from 'vue-router'

export type SeenList<T> = { items: T[]; nextCursor: string | null }

export const deskMemory = {
  query: null as LocationQuery | null,
  selected: null as string | null,
  seen: new Map<string, SeenList<unknown>>(),
}
