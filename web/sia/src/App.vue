<script setup lang="ts">
/**
 * SIA shell, same structure as the legacy SIA AppHeader: one horizontal header with the CIMH logo on the
 * left, the work areas as links in legacy order (Products, Inventory, Pick, Stow; Orders joins with P5),
 * Reports and Admin menus, then the scan box, theme and profile on the right. The scan box takes any
 * unit, shelf or product code (a handheld scanner types it and presses Enter) and opens Inventory →
 * Lookup on it (APD "global scan box"). Phones: a menu button opens the same links. Pages show their title as the page heading under the header (pages with
 * their own heading set `meta.ownHeading`). Bare layout (login, MFA setup…) shows no header.
 */
import { AppNotifier, useSession, useThemeMode } from '@cimh/web-app'
import logo from '@cimh/web-app/assets/cimh-logo-blue.webp'
import logoWhite from '@cimh/web-app/assets/cimh-logo-white.webp'
import { mdiAccountCircleOutline, mdiBarcodeScan, mdiChevronDown, mdiLogout, mdiMenu, mdiWeatherNight, mdiWhiteBalanceSunny } from '@mdi/js'
import { computed, ref } from 'vue'
import { useDisplay } from 'vuetify'
import { useRoute, useRouter } from 'vue-router'

const session = useSession()
const route = useRoute()
const router = useRouter()
const { dark, toggle } = useThemeMode()
const { lgAndUp: wide } = useDisplay()
const brand = computed(() => (dark.value ? logoWhite : logo))
const bare = computed(() => route.meta.layout === 'bare' || !session.isStaff || session.needsMfaSetup)
const drawer = ref(false)

const work = computed(() => [
  { title: 'Dashboard', to: '/', show: true },
  { title: 'Products', to: '/products', show: true },
  { title: 'Inventory', to: '/inventory', show: true },
  { title: 'Pick', to: '/pick', show: true },
  { title: 'Stow', to: '/stow', show: true },
])
const reports = [
  { title: 'Stock levels', to: '/reports/stock' },
  { title: 'Who has what', to: '/reports/assignments' },
  { title: 'Movement history', to: '/reports/history' },
]
const reportsActive = computed(() => route.path.startsWith('/reports'))

const scanCode = ref('')
function openScan() {
  const code = scanCode.value.trim()
  if (!code) return
  scanCode.value = ''
  drawer.value = false
  void router.push({ path: '/inventory', query: { op: 'lookup', code } })
}
const admin = computed(() =>
  [
    { title: 'Pending accounts', to: '/admin/approvals', show: session.isAdmin },
    { title: 'Accounts', to: '/admin/accounts', show: true },
    { title: 'Organisations', to: '/admin/organisations', show: true },
    { title: 'Audit log', to: '/admin/audit', show: session.isAdmin },
    { title: 'Settings', to: '/admin/settings', show: session.isAdmin },
  ].filter((x) => x.show),
)
const adminActive = computed(() => route.path.startsWith('/admin'))
const isActive = (to: string) => (to === '/' ? route.path === '/' : route.path.startsWith(to))

async function logout() {
  await session.logout()
  await router.push('/login')
}
</script>

<template>
  <v-app>
    <a href="#main" class="skip-link">Skip to content</a>
    <template v-if="!bare">
      <v-app-bar flat border="b" height="64" color="surface">
        <div class="bar">
          <router-link to="/" class="brand" aria-label="SIA home">
            <img :src="brand" alt="CIMH" height="32" width="104" />
            <span class="brand-name">SIA</span>
          </router-link>

          <nav v-if="wide" class="nav" aria-label="Main">
            <router-link v-for="n in work.filter((x) => x.show)" :key="n.to" :to="n.to" class="nav-link" :class="{ on: isActive(n.to) }">
              {{ n.title }}
            </router-link>
            <v-menu location="bottom start">
              <template #activator="{ props }">
                <button v-bind="props" type="button" class="nav-link" :class="{ on: reportsActive }">
                  Reports <v-icon :icon="mdiChevronDown" size="18" />
                </button>
              </template>
              <v-list density="compact" min-width="220">
                <v-list-item v-for="r in reports" :key="r.to" :to="r.to" :title="r.title" />
              </v-list>
            </v-menu>
            <v-menu location="bottom start">
              <template #activator="{ props }">
                <button v-bind="props" type="button" class="nav-link" :class="{ on: adminActive }">
                  Admin <v-icon :icon="mdiChevronDown" size="18" />
                </button>
              </template>
              <v-list density="compact" min-width="220">
                <v-list-item v-for="a in admin" :key="a.to" :to="a.to" :title="a.title" />
              </v-list>
            </v-menu>
          </nav>

          <div class="right">
            <form v-if="wide" class="scanbox" role="search" @submit.prevent="openScan">
              <v-text-field
                v-model="scanCode"
                density="compact"
                variant="outlined"
                hide-details
                placeholder="Scan a code"
                aria-label="Scan or type a unit, shelf or product code"
                :prepend-inner-icon="mdiBarcodeScan"
                autocomplete="off"
                spellcheck="false"
              />
            </form>
            <v-btn
              variant="text"
              :icon="dark ? mdiWhiteBalanceSunny : mdiWeatherNight"
              :aria-label="dark ? 'Use light theme' : 'Use dark theme'"
              @click="toggle"
            />
            <v-menu location="bottom end">
              <template #activator="{ props }">
                <v-btn v-bind="props" variant="text" :prepend-icon="mdiAccountCircleOutline">{{ session.account?.firstname }}</v-btn>
              </template>
              <v-list density="compact" min-width="220">
                <v-list-item :subtitle="session.account?.email" :title="session.displayName" />
                <v-divider />
                <v-list-item to="/profile" title="Profile" />
                <v-list-item :prepend-icon="mdiLogout" title="Log out" @click="logout" />
              </v-list>
            </v-menu>
            <v-btn v-if="!wide" variant="text" :icon="mdiMenu" aria-label="Open navigation" @click="drawer = !drawer" />
          </div>
        </div>
      </v-app-bar>

      <v-navigation-drawer v-if="!wide" v-model="drawer" temporary location="right" width="280">
        <v-list nav density="comfortable" color="primary">
          <form class="pa-2" role="search" @submit.prevent="openScan">
            <v-text-field v-model="scanCode" density="compact" hide-details placeholder="Scan a code" aria-label="Scan or type a unit, shelf or product code" :prepend-inner-icon="mdiBarcodeScan" />
          </form>
          <v-list-item v-for="n in work.filter((x) => x.show)" :key="n.to" :to="n.to" :title="n.title" :exact="n.to === '/'" @click="drawer = false" />
          <v-list-subheader>Reports</v-list-subheader>
          <v-list-item v-for="r in reports" :key="r.to" :to="r.to" :title="r.title" @click="drawer = false" />
          <v-list-subheader>Admin</v-list-subheader>
          <v-list-item v-for="a in admin" :key="a.to" :to="a.to" :title="a.title" @click="drawer = false" />
        </v-list>
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
.bar {
  width: 100%;
  max-width: 1440px;
  margin: 0 auto;
  padding: 0 var(--sp-4);
  display: flex;
  align-items: center;
  gap: var(--sp-8);
}
.brand {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  text-decoration: none;
  color: inherit;
}
.brand img {
  height: 32px;
  width: auto;
}
.brand-name {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.06em;
  opacity: 0.72;
}
.nav {
  display: flex;
  align-items: center;
  gap: var(--sp-6);
  height: 100%;
}
.nav-link {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  height: 64px;
  padding: 0 2px;
  font: inherit;
  font-size: 15px;
  font-weight: 500;
  color: rgb(var(--v-theme-on-surface));
  text-decoration: none;
  background: none;
  border: 0;
  cursor: pointer;
}
.nav-link:hover {
  color: rgb(var(--v-theme-primary));
}
.nav-link.on {
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
}
.nav-link.on::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 3px;
  border-radius: 3px 3px 0 0;
  background: rgb(var(--v-theme-primary));
}
.scanbox {
  width: 200px;
}
.right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--sp-1);
}
.page-title {
  max-width: 1440px;
  margin: 0 auto;
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
