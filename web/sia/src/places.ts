/**
 * The storeroom map behind /inventory: the sites, and each site's locations with their shelves, shared by
 * the Places tree and the record beside it. Sites load up front; a site's locations load the first time it
 * is opened (there can be hundreds of sites, so never all at once). A create refreshes only its site.
 */
import { call, inventory, type Location, type Shelf, type Site } from '@cimh/web-app'
import { reactive, ref } from 'vue'

const sites = ref<Site[]>([])
const locations = reactive<Record<string, Location[]>>({})
const pending = new Map<string, Promise<void>>()
const state = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')

async function loadSite(site: string) {
  locations[site] = (
    await call(() => inventory.GET('/sites/{site}/locations', { params: { path: { site }, query: { withShelves: true } } }))
  ).items
}
/** Load a site's locations once (concurrent callers share the request). */
function ensureSite(site: string): Promise<void> {
  if (locations[site]) return Promise.resolve()
  let p = pending.get(site)
  if (!p) {
    p = loadSite(site).finally(() => pending.delete(site))
    pending.set(site, p)
  }
  return p
}

async function load() {
  state.value = 'loading'
  try {
    sites.value = (await call(() => inventory.GET('/sites'))).items
    state.value = 'ready'
  } catch (e) {
    state.value = 'error'
    throw e
  }
}

/**
 * The site a location belongs to, when only the location code is known (a scanned or typed LOC… code: the
 * API has no lookup by location). Looks in what is loaded, then loads sites six at a time until found.
 */
async function findLocation(code: string): Promise<Location | undefined> {
  if (state.value !== 'ready') await load()
  const known = location(code)
  if (known) return known
  const rest = sites.value.map((s) => s.barcode).filter((b) => !locations[b])
  for (let i = 0; i < rest.length; i += 6) {
    await Promise.all(rest.slice(i, i + 6).map(ensureSite))
    const l = location(code)
    if (l) return l
  }
  return undefined
}

function site(code: string): Site | undefined {
  return sites.value.find((s) => s.barcode === code)
}
function location(code: string): Location | undefined {
  for (const list of Object.values(locations)) {
    const l = list.find((x) => x.barcode === code)
    if (l) return l
  }
  return undefined
}

export function shelfLabel(s: Shelf, siteName?: string, locationName?: string) {
  const site = s.siteName ?? siteName
  const location = s.locationName ?? locationName
  return {
    value: s.barcode,
    title: `Shelf ${s.number}`,
    subtitle: [site, location].filter(Boolean).join(' · '),
    // Drawn as the legacy shelf label (LabelSheet): site, location and code top left, SHELF n top right, QR below.
    shelf: { site, location, number: s.number },
  }
}

/** Link to a place on /inventory; a location carries its site so it can open without a search. */
export function placeTo(code: string, site?: string | null) {
  return { path: '/inventory', query: site ? { code, site } : { code } }
}

export function usePlaces() {
  return { sites, locations, state, load, loadSite, ensureSite, site, location, findLocation }
}
