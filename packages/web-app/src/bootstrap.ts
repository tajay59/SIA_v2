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

export function boot(opts: BootOptions) {
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
  app.use(pinia).use(vuetify).use(router)
  installGuards(router, opts)
  void router.isReady().then(() => app.mount(opts.mount ?? '#app'))
  return { app, router, pinia }
}
