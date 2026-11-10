/**
 * One way to start SHOP and SIA: Pinia, Vuetify (CIMH theme, SVG icons, density per app), the router
 * with guards. Each app passes its file-based `routes` and options.
 */
import { vuetifyOptions } from '@cimh/web-ui'
import { createPinia } from 'pinia'
import { type Component, createApp } from 'vue'
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { createVuetify } from 'vuetify'
import { aliases, mdi } from 'vuetify/iconsets/mdi-svg'
import { type GuardOptions, installGuards } from './guards'
import { storedTheme } from './theme-mode'

export interface BootOptions extends GuardOptions {
  root: Component
  routes: readonly RouteRecordRaw[]
  mount?: string
}

const RELOAD_KEY = 'cimh:chunk-reload'

/**
 * Lazy page chunks (Vite `vite:preloadError`). A CSS preload that fails because the user navigated away
 * mid-load is harmless, so it is ignored (Firefox reports it as an uncaught error). A JS chunk that fails
 * usually means a new deploy replaced the file names: reload once to fetch the new build. The
 * sessionStorage stamp stops a reload loop when the server itself is down (the error page then shows).
 */
export function handleChunkErrors(win: Window = window) {
  win.addEventListener('vite:preloadError', (event) => {
    const e = event as Event & { payload?: unknown }
    const message = e.payload instanceof Error ? e.payload.message : String(e.payload ?? '')
    if (/preload CSS/i.test(message)) {
      event.preventDefault()
      return
    }
    let last = 0
    try {
      last = Number(win.sessionStorage.getItem(RELOAD_KEY) ?? 0)
    } catch {
      /* storage blocked: still reload once per page */
    }
    if (Date.now() - last < 10_000) return // just reloaded: let the error surface
    event.preventDefault()
    try {
      win.sessionStorage.setItem(RELOAD_KEY, String(Date.now()))
    } catch {
      /* ignore */
    }
    win.location.reload()
  })
}

export function boot(opts: BootOptions) {
  handleChunkErrors()
  const app = createApp(opts.root)
  const pinia = createPinia()
  const vuetify = createVuetify({
    ...vuetifyOptions(opts.app, storedTheme()),
    icons: { defaultSet: 'mdi', aliases, sets: { mdi } },
  })
  const router = createRouter({
    history: createWebHistory(),
    routes: opts.routes as RouteRecordRaw[],
    scrollBehavior: (_to, _from, saved) => saved ?? { top: 0 },
  })
  // A page chunk that fails to load (navigation aborted it, or a deploy replaced it) rejects the route
  // ("Couldn't resolve component"). Load the target page fresh, once; then let the error page show.
  router.onError((err: unknown, to) => {
    const msg = err instanceof Error ? err.message : String(err)
    if (!/resolve component|dynamically imported module|Importing a module script failed|error loading dynamically/i.test(msg)) return
    let last = 0
    try {
      last = Number(sessionStorage.getItem(RELOAD_KEY) ?? 0)
    } catch {
      /* ignore */
    }
    if (Date.now() - last < 10_000) return
    try {
      sessionStorage.setItem(RELOAD_KEY, String(Date.now()))
    } catch {
      /* ignore */
    }
    window.location.assign(to.fullPath)
  })
  app.use(pinia).use(vuetify).use(router)
  installGuards(router, opts)
  void router.isReady().then(() => app.mount(opts.mount ?? '#app'))
  return { app, router, pinia }
}
