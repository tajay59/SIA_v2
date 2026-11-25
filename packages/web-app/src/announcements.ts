/**
 * Announcements (plan 2026-11-23): admin messages shown as a banner at the top of every SHOP/SIA page.
 *
 * Live feed, one per app per tab: first paint from `GET /announcements` (a reload shows them at once), then the
 * catalog-push socket (`snapshot`, then `upsert` / `remove`, `ping` every 25 s; docs/api/push.asyncapi.yaml).
 * Reconnects with backoff (1 s → 30 s + jitter); 4401 = the access token ran out → refresh, then reconnect;
 * 1013 (server full) or repeated failures → poll the list every 2 min until a socket works again. The socket is
 * closed after a minute in a hidden tab and reopened (fresh snapshot) when the tab shows again. Items are hidden
 * at `expiresAt` by the client too (server clock via `serverTime`). Information banners can be closed: remembered
 * per message + version in this browser (an edit shows it again).
 */
import { catalogClient, type CommonCatalogComponents } from '@cimh/web-api'
import { computed, reactive, ref, type Ref } from 'vue'
import { call, ifMatch, refreshSession } from './api'

type S = CommonCatalogComponents['schemas']
export type Announcement = S['Announcement']
export type AnnouncementAdmin = S['AnnouncementAdmin']
export type AnnouncementInput = S['AnnouncementInput']
export type AnnouncementPatch = S['AnnouncementPatch']
export type AnnouncementApp = 'shop' | 'sia'

const catalog = catalogClient()

// ---------------------------------------------------------------- admin API

export async function listAnnouncements(): Promise<AnnouncementAdmin[]> {
  return (await call(() => catalog.GET('/admin/announcements'))).items
}
export function createAnnouncement(body: AnnouncementInput): Promise<AnnouncementAdmin> {
  return call(() => catalog.POST('/admin/announcements', { body }))
}
export function updateAnnouncement(a: { id: string; version: number }, body: AnnouncementPatch): Promise<AnnouncementAdmin> {
  return call(() =>
    catalog.PATCH('/admin/announcements/{announcementId}', {
      params: { path: { announcementId: a.id }, header: { 'If-Match': ifMatch(a.version) } },
      body,
    }),
  )
}
export async function endAnnouncement(a: { id: string; version: number }): Promise<void> {
  await call(() =>
    catalog.DELETE('/admin/announcements/{announcementId}', {
      params: { path: { announcementId: a.id }, header: { 'If-Match': ifMatch(a.version) } },
    }),
  )
}

/** Where a banner link goes in this app: a product link opens the product's page here (SHOP /catalogue/<id>,
 *  SIA /products/<id>); a web address goes where it says. */
export function announcementHref(link: NonNullable<Announcement['link']>, app: AnnouncementApp): string | null {
  if (link.productId) return `${app === 'sia' ? '/products' : '/catalogue'}/${encodeURIComponent(link.productId)}`
  return link.url ?? null
}

/** Alerts first, then the newest start (the server's order; kept after live changes). */
export function sortAnnouncements<T extends Announcement>(items: T[]): T[] {
  return [...items].sort(
    (a, b) => Number(b.tone === 'ALERT') - Number(a.tone === 'ALERT') || b.startsAt.localeCompare(a.startsAt) || a.id.localeCompare(b.id),
  )
}

// ---------------------------------------------------------------- dismissals (this browser)

const DISMISS_KEY = 'cimh.announcements.closed'
function readClosed(): Record<string, number> {
  try {
    const v = JSON.parse(localStorage.getItem(DISMISS_KEY) ?? '{}')
    return v && typeof v === 'object' ? (v as Record<string, number>) : {}
  } catch {
    return {}
  }
}
function writeClosed(v: Record<string, number>) {
  try {
    localStorage.setItem(DISMISS_KEY, JSON.stringify(v))
  } catch {
    // storage blocked: closing lasts for this page only
  }
}

// ---------------------------------------------------------------- live feed

const POLL_MS = 120_000
const HIDDEN_CLOSE_MS = 60_000
const SILENT_MS = 70_000 // no frame (pings come every 25 s): the socket is dead
const STREAM = '/api/catalog/v1/announcements/stream'

export interface AnnouncementFeed {
  /** Live, not expired, not closed here; alerts first. */
  items: Ref<Announcement[]>
  /** Items that arrived while the page was open (for the live region); cleared by the reader. */
  arrivals: Ref<Announcement[]>
  dismiss(a: Announcement): void
  stop(): void
}

class Feed {
  readonly all = ref<Announcement[]>([])
  readonly arrivals = ref<Announcement[]>([])
  readonly closed = reactive<Record<string, number>>(readClosed())
  readonly now = ref(Date.now())
  private offset = 0 // server clock − ours
  private ws: WebSocket | null = null
  private users = 0
  private stopped = true
  private attempts = 0
  private everOpened = false
  private retryTimer: ReturnType<typeof setTimeout> | undefined
  private pollTimer: ReturnType<typeof setInterval> | undefined
  private hiddenTimer: ReturnType<typeof setTimeout> | undefined
  private silentTimer: ReturnType<typeof setTimeout> | undefined
  private tick: ReturnType<typeof setInterval> | undefined
  private loaded = false

  constructor(private readonly app: AnnouncementApp) {}

  readonly visible = computed(() =>
    this.all.value.filter(
      (a) => Date.parse(a.expiresAt) > this.now.value + this.offset && !(a.dismissible && this.closed[a.id] === a.version),
    ),
  )

  start() {
    this.users++
    if (!this.stopped) return
    this.stopped = false
    this.tick = setInterval(() => (this.now.value = Date.now()), 5_000)
    document.addEventListener('visibilitychange', this.onVisibility)
    void this.fetchList().finally(() => this.connect())
  }

  release() {
    this.users = Math.max(0, this.users - 1)
    if (this.users === 0) this.shutdown()
  }

  shutdown() {
    this.stopped = true
    clearInterval(this.tick)
    clearTimeout(this.retryTimer)
    clearTimeout(this.hiddenTimer)
    clearTimeout(this.silentTimer)
    this.stopPolling()
    document.removeEventListener('visibilitychange', this.onVisibility)
    this.closeSocket()
  }

  dismiss(a: Announcement) {
    if (!a.dismissible) return
    this.closed[a.id] = a.version
    // Forget messages that are gone, so the store stays small.
    const live = new Set(this.all.value.map((x) => x.id))
    const keep: Record<string, number> = {}
    for (const [id, v] of Object.entries(this.closed)) if (live.has(id)) keep[id] = v
    writeClosed(keep)
  }

  private async fetchList() {
    try {
      const res = await call(() => catalog.GET('/announcements', { params: { query: { app: this.app } } }), { refresh: this.app === 'sia' })
      this.replace(res.items, this.loaded)
      this.loaded = true
    } catch {
      // offline or not allowed: the socket (or the next poll) tries again
    }
  }

  private replace(items: Announcement[], announce: boolean) {
    if (announce) {
      const known = new Map(this.all.value.map((a) => [a.id, a.version]))
      const fresh = items.filter((a) => known.get(a.id) !== a.version)
      if (fresh.length) this.arrivals.value = [...this.arrivals.value, ...fresh]
    }
    this.all.value = sortAnnouncements(items)
  }

  private connect() {
    if (this.stopped || this.ws || document.visibilityState === 'hidden') return
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    let ws: WebSocket
    try {
      ws = new WebSocket(`${proto}//${location.host}${STREAM}?app=${this.app}`)
    } catch {
      this.retry()
      return
    }
    this.ws = ws
    ws.onopen = () => {
      this.everOpened = true
      this.attempts = 0
      this.stopPolling()
      this.armSilence()
    }
    ws.onmessage = (ev) => {
      this.armSilence()
      let msg: { type: string; items?: Announcement[]; item?: Announcement; id?: string; serverTime?: string }
      try {
        msg = JSON.parse(String(ev.data))
      } catch {
        return
      }
      if (msg.type === 'snapshot' && msg.items) {
        if (msg.serverTime) this.offset = Date.parse(msg.serverTime) - Date.now()
        this.replace(msg.items, this.loaded)
        this.loaded = true
      } else if (msg.type === 'upsert' && msg.item) {
        const item = msg.item
        this.replace([...this.all.value.filter((a) => a.id !== item.id), item], true)
      } else if (msg.type === 'remove' && msg.id) {
        this.all.value = this.all.value.filter((a) => a.id !== msg.id)
      }
    }
    ws.onclose = (ev) => {
      if (this.ws === ws) this.ws = null
      clearTimeout(this.silentTimer)
      if (this.stopped) return
      if (ev.code === 4403) return this.startPolling() // not staff: the list call will say so too
      if (ev.code === 4401) {
        void refreshSession().then((ok) => (ok ? this.retry(true) : this.startPolling()))
        return
      }
      if (ev.code === 1013) this.startPolling()
      this.retry()
    }
  }

  private retry(now = false) {
    if (this.stopped) return
    clearTimeout(this.retryTimer)
    this.attempts++
    if (this.attempts >= 3 || !this.everOpened) this.startPolling()
    const base = now ? 0 : Math.min(30_000, 1_000 * 2 ** Math.min(this.attempts - 1, 5))
    this.retryTimer = setTimeout(() => this.connect(), base + Math.random() * 1_000)
  }

  private armSilence() {
    clearTimeout(this.silentTimer)
    this.silentTimer = setTimeout(() => this.ws?.close(4000, 'silent'), SILENT_MS)
  }

  private closeSocket() {
    const ws = this.ws
    this.ws = null
    if (ws) {
      ws.onclose = null
      ws.close(1000)
    }
  }

  private startPolling() {
    if (this.pollTimer || this.stopped) return
    this.pollTimer = setInterval(() => void this.fetchList(), POLL_MS)
  }

  private stopPolling() {
    clearInterval(this.pollTimer)
    this.pollTimer = undefined
  }

  private onVisibility = () => {
    clearTimeout(this.hiddenTimer)
    if (document.visibilityState === 'hidden') {
      this.hiddenTimer = setTimeout(() => this.closeSocket(), HIDDEN_CLOSE_MS)
    } else if (!this.ws) {
      this.attempts = 0
      clearTimeout(this.retryTimer)
      this.connect()
    }
  }
}

const feeds = new Map<AnnouncementApp, Feed>()

/** The live announcements for this app. Call `stop()` when the banner unmounts (the feed closes with its last user). */
export function useAnnouncementFeed(app: AnnouncementApp): AnnouncementFeed {
  let feed = feeds.get(app)
  if (!feed) {
    feed = new Feed(app)
    feeds.set(app, feed)
  }
  const f = feed
  f.start()
  let released = false
  return {
    items: f.visible as unknown as Ref<Announcement[]>,
    arrivals: f.arrivals,
    dismiss: (a) => f.dismiss(a),
    stop: () => {
      if (released) return
      released = true
      f.release()
    },
  }
}
