<script setup lang="ts">
/**
 * SIA shell, "Graphite Console" (surface brief web/sia): a left navigation drawer replaces the top bar
 * (owner, 2026-11-11). Drawer = brand, Work / Stock / Reports / Admin groups with live counts, then the scan
 * box, theme and profile at its foot. The scan box takes any unit, shelf or product code (a handheld scanner
 * types it and presses Enter) and opens Inventory → Lookup on it (APD "global scan box").
 * ≥ 1280 px the drawer is permanent; below, a slim top bar opens it ("Open navigation").
 * Pages show their title as the page heading (pages with their own heading set `meta.ownHeading`).
 * Bare layout (login, MFA setup…) shows no shell.
 */
import { AnnouncementBar, AppNotifier, useSession, useThemeMode } from '@cimh/web-app'
import siaMark from '@cimh/web-app/assets/brand/sia-mark.svg'
import { markRaw } from 'vue'
// Filled Material Symbols via Iconify (unplugin-icons): compiled in, nothing fetched at runtime.
import IDashboard from '~icons/material-symbols/dashboard-rounded'
import IRequests from '~icons/material-symbols/assignment-rounded'
import IPick from '~icons/material-symbols/unarchive-rounded'
import IStow from '~icons/material-symbols/archive-rounded'
import IProducts from '~icons/material-symbols/category-rounded'
import IInventory from '~icons/material-symbols/inventory-2-rounded'
import IStockLevels from '~icons/material-symbols/bar-chart-rounded'
import IWhoHas from '~icons/material-symbols/assignment-ind-rounded'
import IHistory from '~icons/material-symbols/history-rounded'
import IApprovals from '~icons/material-symbols/how-to-reg-rounded'
import IAccounts from '~icons/material-symbols/group-rounded'
import IOrgs from '~icons/material-symbols/corporate-fare-rounded'
import IAudit from '~icons/material-symbols/policy-rounded'
import ISettings from '~icons/material-symbols/settings-rounded'
import ICampaign from '~icons/material-symbols/campaign-rounded'
import ICollapse from '~icons/material-symbols/left-panel-close-rounded'
import IExpand from '~icons/material-symbols/left-panel-open-rounded'
import IScan from './icons/QrScan.vue'
import IAccount from '~icons/material-symbols/account-circle'
import ILight from '~icons/material-symbols/light-mode-rounded'
import IDark from '~icons/material-symbols/dark-mode-rounded'
import ILogout from '~icons/material-symbols/logout-rounded'
import IMenu from '~icons/material-symbols/menu-rounded'

const i = {
  dashboard: markRaw(IDashboard),
  requests: markRaw(IRequests),
  pick: markRaw(IPick),
  stow: markRaw(IStow),
  products: markRaw(IProducts),
  inventory: markRaw(IInventory),
  stockLevels: markRaw(IStockLevels),
  whoHas: markRaw(IWhoHas),
  history: markRaw(IHistory),
  approvals: markRaw(IApprovals),
  accounts: markRaw(IAccounts),
  orgs: markRaw(IOrgs),
  audit: markRaw(IAudit),
  settings: markRaw(ISettings),
  announce: markRaw(ICampaign),
  collapse: markRaw(ICollapse),
  expand: markRaw(IExpand),
  scan: markRaw(IScan),
  account: markRaw(IAccount),
  light: markRaw(ILight),
  dark: markRaw(IDark),
  logout: markRaw(ILogout),
  menu: markRaw(IMenu),
}
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import type { IconValue } from 'vuetify/lib/composables/icons.mjs'
import { installRequestMotion } from './request-motion'
import { pageSearch, shortcutHandler } from './shortcuts'
import { type CountKey, countLabel, useWorkCounts } from './work-counts'

const session = useSession()
const route = useRoute()
const router = useRouter()
onBeforeUnmount(installRequestMotion(router))
const { dark, toggle } = useThemeMode()
const { lgAndUp: wide } = useDisplay()
const bare = computed(() => route.meta.layout === 'bare' || !session.isStaff || session.needsMfaSetup)
const open = ref(false)
const drawer = computed({
  get: () => wide.value || open.value,
  set: (v: boolean) => (open.value = v),
})
const { counts, refresh } = useWorkCounts()

// Desktop: the drawer collapses to an icon rail; the choice is remembered per device (storage may be blocked).
const RAIL_KEY = 'sia.drawer.rail'
const readRail = () => {
  try {
    return localStorage.getItem(RAIL_KEY) === '1'
  } catch {
    return false
  }
}
const railPref = ref(readRail())
const rail = computed(() => wide.value && railPref.value)
function toggleRail() {
  railPref.value = !railPref.value
  try {
    localStorage.setItem(RAIL_KEY, railPref.value ? '1' : '0')
  } catch {
    // ignore
  }
}

type Link = { title: string; to: string; icon: IconValue; desc: string; count?: CountKey; show?: boolean }
const groups = computed<{ title: string; links: Link[] }[]>(() => [
  {
    title: 'Work',
    links: [
      { title: 'Dashboard', to: '/', icon: i.dashboard, desc: 'What needs staff now, and requests counted by status.' },
      { title: 'Orders', to: '/requests', icon: i.requests, desc: 'The order desk: filter, quote, approve and track every request.', count: 'new' },
      { title: 'Pick', to: '/pick', icon: i.pick, desc: 'Pick units for requests; stow and relocate, issue and return items.', count: 'fulfil' },
    ],
  },
  {
    title: 'Stock',
    links: [
      { title: 'Inventory', to: '/products', icon: i.products, desc: 'Every product: details, photos, stock and Pro Bono limits.', count: 'low' },
      { title: 'Locations', to: '/inventory', icon: i.inventory, desc: 'Sites, locations and shelves, labels, and a lookup for any unit or shelf.' },
    ],
  },
  {
    title: 'Reports',
    links: [
      { title: 'Stock levels', to: '/reports/stock', icon: i.stockLevels, desc: 'Available, reserved and low stock for each product.' },
      { title: 'Who has what', to: '/reports/assignments', icon: i.whoHas, desc: 'Units issued to people and not yet returned.' },
      { title: 'Movement history', to: '/reports/history', icon: i.history, desc: 'Every stow, pick, move and issue: who and when.' },
    ],
  },
  {
    title: 'Admin',
    links: ([
      { title: 'Admin overview', to: '/admin', icon: i.dashboard, desc: 'What needs an administrator now, and every admin page.' },
      { title: 'Pending accounts', to: '/admin/approvals', icon: i.approvals, desc: 'Approve or reject new customer sign-ups.', count: 'approvals', show: session.isAdmin },
      { title: 'Accounts', to: '/admin/accounts', icon: i.accounts, desc: 'Find customers and staff; suspend, export or erase.' },
      { title: 'Organisations', to: '/admin/organisations', icon: i.orgs, desc: 'Met services and agencies that customers belong to.' },
      { title: 'Announcements', to: '/admin/announcements', icon: i.announce, desc: 'The banner at the top of every SHOP and SIA page.', show: session.isAdmin },
      { title: 'Audit log', to: '/admin/audit', icon: i.audit, desc: 'Admin and security actions, searchable.', show: session.isAdmin },
      { title: 'Settings', to: '/admin/settings', icon: i.settings, desc: 'Admin fee, reference data and staff email lists.', show: session.isAdmin },
    ] as Link[]).filter((l) => l.show !== false),
  },
])
const isActive = (to: string) => (to === '/' || to === '/admin' ? route.path.replace(/(.)\/$/, '$1') === to : route.path.startsWith(to))
const badge = (k?: CountKey) => {
  if (!k) return ''
  const c = counts[k]
  return c.failed || !c.n ? '' : countLabel(c)
}

const SCAN = 'input[aria-label="Scan or type a unit, shelf or product code"]'
async function focusScan() {
  if (rail.value) {
    toggleRail()
    await nextTick()
  }
  if (!wide.value) {
    open.value = true
    await nextTick()
  }
  document.querySelector<HTMLInputElement>(SCAN)?.focus()
}
// Shortcuts (Design Brief): `/` page search (else the scan box), `s` scan box, `g r` Requests.
const onKey = shortcutHandler({
  focusSearch: () => {
    const field = pageSearch()
    if (field) field.focus()
    else void focusScan()
  },
  focusScan: () => void focusScan(),
  go: (path) => void router.push(path),
})
const onKeyShell = (e: KeyboardEvent) => !bare.value && onKey(e) // not on login, MFA setup or staff-only
let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  window.addEventListener('keydown', onKeyShell)
  timer = setInterval(() => !bare.value && document.visibilityState === 'visible' && void refresh(), 120_000)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyShell)
  clearInterval(timer)
})
watch(bare, (b) => !b && void refresh(), { immediate: true })
watch(() => route.path, () => (open.value = false))
// A page that refuses to be left (unsaved settings → "Keep editing") keeps its path: close the phone drawer too.
router.afterEach((_to, _from, failure) => {
  if (failure) open.value = false
})

const scanCode = ref('')
function openScan() {
  const code = scanCode.value.trim()
  if (!code) return
  scanCode.value = ''
  open.value = false
  void router.push({ path: '/inventory', query: { op: 'lookup', code } })
}

async function logout() {
  await session.logout()
  await router.push('/login')
}
</script>

<template>
  <v-app>
    <a href="#main" class="skip-link">Skip to content</a>
    <!-- Announcements (plan 2026-11-23): signed-in staff only (D2), on every page. -->
    <AnnouncementBar app="sia" :enabled="session.isStaff && !session.needsMfaSetup" />
    <template v-if="!bare">
      <v-app-bar v-if="!wide" flat border="b" height="56" color="surface">
        <v-btn variant="text" :icon="i.menu" aria-label="Open navigation" @click="open = !open" />
        <router-link to="/" class="brand compact" aria-label="SIA home">
          <img :src="siaMark" alt="" height="32" width="36" />
          <span class="brand-name">SIA</span>
        </router-link>
      </v-app-bar>

      <v-navigation-drawer
        v-model="drawer"
        :permanent="wide"
        :temporary="!wide"
        :rail="rail"
        width="240"
        rail-width="64"
        color="surface"
        class="shell-drawer"
        :class="{ 'is-rail': rail }"
      >
        <div class="drawer-col">
          <div v-if="wide" class="brand-row">
            <router-link to="/" class="brand" aria-label="SIA home">
              <img :src="siaMark" alt="" height="32" width="36" />
              <span v-if="!rail" class="brand-name">SIA</span>
            </router-link>
            <v-btn
              v-if="!rail"
              variant="text"
              size="small"
              :icon="i.collapse"
              aria-label="Collapse navigation"
              @click="toggleRail"
            />
          </div>
          <v-btn
            v-if="rail"
            variant="text"
            size="small"
            class="expand"
            :icon="i.expand"
            aria-label="Expand navigation"
            @click="toggleRail"
          />

          <nav aria-label="Main" class="nav">
            <v-list v-for="g in groups" :key="g.title" nav density="compact" bg-color="transparent" class="grp" role="group" :aria-label="g.title">
              <v-list-subheader class="grp-title console-title" :class="{ 'sr-only': rail }">{{ g.title }}</v-list-subheader>
              <v-list-item
                v-for="l in g.links"
                :key="l.to"
                :to="l.to"
                :active="isActive(l.to)"
                active-class="on"
                :aria-current="isActive(l.to) ? 'page' : undefined"
                :aria-label="rail ? l.title : undefined"
                class="nav-item"
                rounded="0"
              >
                <template #prepend>
                  <v-icon :icon="l.icon" size="20" class="nav-icon" />
                </template>
                <v-list-item-title class="nav-text">{{ l.title }}</v-list-item-title>
                <template v-if="badge(l.count)" #append>
                  <span class="count" aria-hidden="true">{{ badge(l.count) }}</span>
                </template>
                <!-- Title + description. role="tooltip" sits on the overlay root, so the name goes there (axe aria-tooltip-name). -->
                <v-tooltip
                  activator="parent"
                  location="end"
                  :offset="rail ? 10 : 14"
                  :open-delay="rail ? 120 : 450"
                  transition="nav-tip"
                  content-class="nav-tip"
                  :aria-label="`${l.title}: ${l.desc}`"
                  max-width="260"
                >
                  <span class="nav-tip-title">{{ l.title }}<span v-if="badge(l.count)" class="nav-tip-count">{{ badge(l.count) }}</span></span>
                  <span class="nav-tip-desc">{{ l.desc }}</span>
                </v-tooltip>
              </v-list-item>
            </v-list>
          </nav>

          <div class="foot">
            <v-btn
              v-if="rail"
              variant="text"
              :icon="i.scan"
              aria-label="Scan a code"
              title="Scan a code (s)"
              @click="focusScan"
            />
            <form v-else role="search" @submit.prevent="openScan">
              <v-text-field
                v-model="scanCode"
                hide-details
                placeholder="Scan a code"
                aria-label="Scan or type a unit, shelf or product code"
                :prepend-inner-icon="i.scan"
                autocomplete="off"
                spellcheck="false"
              >
                <template #append-inner><kbd class="kbd" aria-hidden="true">s</kbd></template>
              </v-text-field>
            </form>
            <div class="me" :class="{ stacked: rail }">
              <v-menu location="top start">
                <template #activator="{ props }">
                  <v-btn v-if="rail" v-bind="props" variant="text" :icon="i.account" :aria-label="`Account: ${session.account?.firstname ?? ''}`" />
                  <v-btn v-else v-bind="props" variant="text" class="me-btn" :prepend-icon="i.account">
                    {{ session.account?.firstname }}
                  </v-btn>
                </template>
                <v-list density="compact" min-width="220">
                  <v-list-item :subtitle="session.account?.email" :title="session.displayName" />
                  <v-divider />
                  <v-list-item to="/profile" title="Profile" />
                  <v-list-item :prepend-icon="i.logout" title="Log out" @click="logout" />
                </v-list>
              </v-menu>
              <v-btn
                variant="text"
                size="small"
                :icon="dark ? i.light : i.dark"
                :aria-label="dark ? 'Use light theme' : 'Use dark theme'"
                @click="toggle"
              />
            </div>
          </div>
        </div>
      </v-navigation-drawer>
    </template>

    <v-main id="main">
      <AppNotifier />
      <div v-if="!bare && !route.meta.ownHeading && route.meta.title" class="page-title">
        <h1 class="t-h1">{{ route.meta.title }}</h1>
      </div>
      <router-view />
    </v-main>
  </v-app>
</template>

<style scoped>
.shell-drawer {
  border-right: 1px solid rgb(var(--v-theme-seam)) !important;
}
.drawer-col {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  padding: var(--sp-4) 0 var(--sp-3);
}
.brand {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: 0 var(--sp-4) var(--sp-4);
  text-decoration: none;
  color: inherit;
}
.brand.compact {
  padding: 0 var(--sp-2);
}
.brand img {
  height: 32px;
  width: auto;
}
.brand-name {
  font: 500 13px/1 'JetBrains Mono', ui-monospace, monospace;
  letter-spacing: 0.08em;
  color: rgb(var(--v-theme-secondary));
}
.nav {
  flex: 1;
}
/* v-list nav, restyled to the Graphite Console drawer: flat rows, no rounded pills, no Vuetify active
   overlay; the active row gets the surface-variant ground, a blue icon and a 2 px blue bar on its RIGHT edge
   (in the rail: to the right of the icon button). */
.grp {
  padding: 0;
}
.grp + .grp {
  margin-top: var(--sp-3);
}
.grp-title {
  min-height: 0 !important;
  padding: var(--sp-2) var(--sp-4) var(--sp-1) !important;
  opacity: 1; /* type from .console-title */
}
.nav-item.v-list-item {
  min-height: 32px !important;
  margin: 0 !important;
  padding: 0 var(--sp-4) !important;
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface));
  transition:
    background-color 120ms ease-out,
    box-shadow 160ms cubic-bezier(0.16, 1, 0.3, 1);
}
.nav-item :deep(.v-list-item__overlay) {
  display: none;
}
.nav-item :deep(.v-list-item__prepend) {
  width: auto;
}
.nav-item :deep(.v-list-item__prepend > .v-icon ~ .v-list-item__spacer) {
  width: var(--sp-3);
}
.nav-item:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.nav-item.on {
  background: rgb(var(--v-theme-surface-variant));
  box-shadow: inset -2px 0 0 rgb(var(--v-theme-primary));
}
.nav-item.on .nav-text {
  font-weight: 600;
}
.nav-icon {
  flex: none;
  color: rgb(var(--v-theme-secondary));
  opacity: 1 !important;
}
.nav-item.on .nav-icon {
  color: rgb(var(--v-theme-primary));
}
.nav-text {
  font-size: 14px !important;
  line-height: 20px;
  font-weight: 400;
  letter-spacing: 0;
}
.nav-item :deep(.v-list-item__append) {
  padding-left: var(--sp-2);
}
.brand-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: var(--sp-2);
}
.brand-row .brand {
  padding-bottom: 0;
}
.brand-row {
  padding-bottom: var(--sp-3);
}
.expand {
  align-self: center;
  margin-bottom: var(--sp-2);
}
/* Collapsed rail: icons only, centred; counts become a dot; group titles stay for screen readers. */
.is-rail .brand {
  justify-content: center;
  padding: 0 0 var(--sp-2);
  width: 100%;
}
.is-rail .brand-row {
  justify-content: center;
  padding: 0;
}
.is-rail .grp + .grp {
  margin-top: var(--sp-2);
  padding-top: var(--sp-2);
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.is-rail .nav-item.v-list-item {
  position: relative;
  justify-content: center;
  min-height: 40px !important;
  padding: 0 !important;
  grid-template-columns: 1fr;
}
.is-rail .nav-item :deep(.v-list-item__prepend) {
  justify-content: center;
}
.is-rail .nav-item :deep(.v-list-item__prepend .v-list-item__spacer),
.is-rail .nav-item :deep(.v-list-item__content) {
  display: none;
}
.is-rail .nav-item :deep(.v-list-item__append) {
  position: absolute;
  inset: 0;
  padding: 0;
  pointer-events: none;
}
.is-rail .count {
  position: absolute;
  top: 7px;
  right: 14px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: rgb(var(--v-theme-primary));
  font-size: 0;
}
.is-rail .foot {
  align-items: center;
  padding: var(--sp-2) 0 0;
}
.me.stacked {
  flex-direction: column;
  gap: var(--sp-1);
}
.sr-only {
  position: absolute !important;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
.count {
  font: 500 12px/1 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--v-theme-secondary));
}
.foot {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-3) 0;
  border-top: 1px solid rgb(var(--v-theme-seam));
  margin-top: var(--sp-4);
}
.me {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.me-btn {
  text-transform: none;
  letter-spacing: 0;
}
.kbd {
  font: 500 11px/1 'JetBrains Mono', ui-monospace, monospace;
  padding: 2px 5px;
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 3px;
  color: rgb(var(--v-theme-secondary));
}
.page-title {
  max-width: 1440px;
  padding: var(--sp-6) var(--sp-6) 0;
}
.skip-link {
  position: absolute;
  left: -9999px;
  top: 8px;
  z-index: 2000;
  background: rgb(var(--v-theme-surface));
  padding: 8px 12px;
  border-radius: 4px;
}
.skip-link:focus {
  left: 8px;
}
</style>

<style>
/* Drawer tooltips (teleported, so not scoped): title + one-line description, slides in from the drawer. */
.v-tooltip > .v-overlay__content.nav-tip {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 12px;
  border-radius: 4px;
  background: rgb(var(--v-theme-surface-bright));
  color: rgb(var(--v-theme-on-surface));
  border: 1px solid rgb(var(--v-theme-seam));
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.28);
  font-size: 13px;
  line-height: 1.4;
}
.nav-tip-title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-weight: 600;
}
.nav-tip-count {
  font: 500 12px 'JetBrains Mono', ui-monospace, monospace;
  color: rgb(var(--v-theme-primary));
}
.nav-tip-desc {
  color: rgb(var(--v-theme-secondary));
}
.nav-tip-enter-active {
  transition: opacity 160ms cubic-bezier(0.16, 1, 0.3, 1), transform 220ms cubic-bezier(0.16, 1, 0.3, 1);
}
.nav-tip-leave-active {
  transition: opacity 90ms ease-in, transform 90ms ease-in;
}
.nav-tip-enter-from,
.nav-tip-leave-to {
  opacity: 0;
  transform: translateX(-6px) scale(0.98);
}
</style>
