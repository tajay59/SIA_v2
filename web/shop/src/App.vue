<script setup lang="ts">
/**
 * SHOP shell (DESIGN_BRIEF §8): top app bar (64 px, surface, hairline) with logo, navigation and the
 * account menu. Catalogue, Pro Bono, search and cart arrive with P3/P5; only screens that exist are linked.
 */
import { AppNotifier, useSession, useThemeMode } from '@cimh/web-app'
import logo from '@cimh/web-app/assets/cimh-logo-blue.webp'
import logoWhite from '@cimh/web-app/assets/cimh-logo-white.webp'
import { mdiAccountCircleOutline, mdiLogout, mdiWeatherNight, mdiWhiteBalanceSunny } from '@mdi/js'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const session = useSession()
const route = useRoute()
const router = useRouter()
const { dark, toggle } = useThemeMode()
const brand = computed(() => (dark.value ? logoWhite : logo))
const AUTH_PAGES = ['/signup', '/verify', '/pending-approval', '/forgot-password', '/reset-password', '/']
const loginQuery = computed(() => (AUTH_PAGES.includes(route.path) ? {} : { returnTo: route.fullPath }))

async function logout() {
  await session.logout()
  await router.push('/')
}
</script>

<template>
  <v-app>
    <a href="#main" class="skip-link">Skip to content</a>
    <v-app-bar flat border="b" height="64" color="surface">
      <div class="bar">
        <router-link to="/" class="brand" aria-label="CIMH Stores home">
          <img :src="brand" alt="CIMH" height="32" width="104" />
          <span class="t-label muted brand-name">Stores</span>
        </router-link>
        <nav v-if="session.isCustomer" class="nav" aria-label="Main">
          <v-btn to="/requests" variant="text">My requests</v-btn>
        </nav>
        <span class="spacer" />
        <v-btn
          variant="text"
          :icon="dark ? mdiWhiteBalanceSunny : mdiWeatherNight"
          :aria-label="dark ? 'Use light theme' : 'Use dark theme'"
          @click="toggle"
        />
        <template v-if="session.isLoggedIn">
          <v-menu location="bottom end">
            <template #activator="{ props }">
              <v-btn v-bind="props" variant="text" :prepend-icon="mdiAccountCircleOutline">
                {{ session.account?.firstname }}
              </v-btn>
            </template>
            <v-list density="compact" min-width="200">
              <v-list-item to="/account" title="Profile" />
              <v-list-item :prepend-icon="mdiLogout" title="Log out" @click="logout" />
            </v-list>
          </v-menu>
        </template>
        <template v-else-if="route.path !== '/login'">
          <v-btn :to="{ path: '/login', query: loginQuery }" variant="text" class="hide-xs">Log in</v-btn>
          <v-btn to="/signup" color="primary" variant="flat">Sign up</v-btn>
        </template>
      </div>
    </v-app-bar>

    <v-main id="main">
      <AppNotifier />
      <router-view />
    </v-main>
  </v-app>
</template>

<style scoped>
.bar {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 var(--sp-4);
  display: flex;
  align-items: center;
  gap: var(--sp-4);
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
.nav {
  display: flex;
  gap: var(--sp-1);
}
@media (max-width: 600px) {
  .brand-name {
    display: none;
  }
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
