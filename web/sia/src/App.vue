<script setup lang="ts">
/**
 * SIA shell, same structure as the legacy SIA AppHeader: one horizontal header with the CIMH logo on the
 * left, the work areas as links (Products; Inventory, Pick, Stow and Orders join as their phases ship),
 * an Admin menu for account and settings pages, and the theme + profile on the right. Phones: a menu
 * button opens the same links. Pages show their title as the page heading under the header (pages with
 * their own heading set `meta.ownHeading`). Bare layout (login, MFA setup…) shows no header.
 */
import { AppNotifier, useSession, useThemeMode } from '@cimh/web-app'
import logo from '@cimh/web-app/assets/cimh-logo-blue.webp'
import logoWhite from '@cimh/web-app/assets/cimh-logo-white.webp'
import { mdiAccountCircleOutline, mdiChevronDown, mdiLogout, mdiMenu, mdiWeatherNight, mdiWhiteBalanceSunny } from '@mdi/js'
import { computed, ref } from 'vue'
import { useDisplay } from 'vuetify'
import { useRoute, useRouter } from 'vue-router'

const session = useSession()
const route = useRoute()
const router = useRouter()
const { dark, toggle } = useThemeMode()
const { mdAndUp } = useDisplay()
const brand = computed(() => (dark.value ? logoWhite : logo))
const bare = computed(() => route.meta.layout === 'bare' || !session.isStaff || session.needsMfaSetup)
const drawer = ref(false)

const work = computed(() => [
  { title: 'Dashboard', to: '/', show: true },
  { title: 'Products', to: '/products', show: true },
])
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

          <nav v-if="mdAndUp" class="nav" aria-label="Main">
            <router-link v-for="n in work.filter((x) => x.show)" :key="n.to" :to="n.to" class="nav-link" :class="{ on: isActive(n.to) }">
              {{ n.title }}
            </router-link>
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
            <v-btn v-if="!mdAndUp" variant="text" :icon="mdiMenu" aria-label="Open navigation" @click="drawer = !drawer" />
          </div>
        </div>
      </v-app-bar>

      <v-navigation-drawer v-if="!mdAndUp" v-model="drawer" temporary location="right" width="280">
        <v-list nav density="comfortable" color="primary">
          <v-list-item v-for="n in work.filter((x) => x.show)" :key="n.to" :to="n.to" :title="n.title" :exact="n.to === '/'" @click="drawer = false" />
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
