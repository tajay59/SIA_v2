<script setup lang="ts">
/**
 * SHOP shell, same structure as the legacy SHOP (App.vue, TopAppBar, BottomNavBar, Footer):
 * desktop = top bar (brand left, main navigation centred, account + theme right); phones = no top bar,
 * bottom navigation (Menu, Catalogue, Pro Bono, Requests); footer on every page. The sign-in pages
 * (login, sign-up, verify, password) have no top bar, as in legacy. Customers get the cart (with a count)
 * in both bars, as in legacy.
 */
import { AppNotifier, useCart, useSession, useThemeMode } from '@cimh/web-app'
import logo from '@cimh/web-app/assets/cimh-logo-blue.webp'
import logoWhite from '@cimh/web-app/assets/cimh-logo-white.webp'
import {
  mdiAccountCircleOutline,
  mdiCartOutline,
  mdiClipboardTextOutline,
  mdiGiftOutline,
  mdiHomeOutline,
  mdiLogin,
  mdiLogout,
  mdiMenu,
  mdiViewGridOutline,
  mdiWeatherNight,
  mdiWhiteBalanceSunny,
} from '@mdi/js'
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useRoute, useRouter } from 'vue-router'
import ShopFooter from './components/ShopFooter.vue'

const session = useSession()
const route = useRoute()
const router = useRouter()
const { mdAndUp } = useDisplay()
const { dark, toggle } = useThemeMode()
const brand = computed(() => (dark.value ? logoWhite : logo))
const SIGN_IN_PAGES = ['/login', '/signup', '/verify', '/pending-approval', '/forgot-password', '/reset-password']
const signInPage = computed(() => SIGN_IN_PAGES.includes(route.path))
const loginQuery = computed(() => (route.path === '/' || signInPage.value ? {} : { returnTo: route.fullPath }))
const menu = ref(false)
const cart = useCart()
watch(
  () => session.isCustomer,
  (yes) => (yes ? void cart.load().catch(() => undefined) : cart.reset()),
  { immediate: true },
)

const nav = computed(() => [
  { to: '/catalogue', title: 'Catalogue', icon: mdiViewGridOutline, show: true },
  { to: '/pro-bono', title: 'Pro Bono', icon: mdiGiftOutline, show: true },
  { to: '/requests', title: 'My requests', short: 'Requests', icon: mdiClipboardTextOutline, show: session.isCustomer },
])

async function logout() {
  menu.value = false
  await session.logout()
  await router.push('/')
}
</script>

<template>
  <v-app>
    <a href="#main" class="skip-link">Skip to content</a>
    <v-app-bar v-if="mdAndUp && !signInPage" flat border="b" height="72" color="surface">
      <div class="bar">
        <router-link to="/" class="brand" aria-label="CIMH Stores home">
          <img :src="brand" alt="CIMH" height="36" width="117" />
          <span class="brand-name">Stores</span>
        </router-link>
        <nav class="nav" aria-label="Main">
          <router-link v-for="n in nav.filter((x) => x.show)" :key="n.to" :to="n.to" class="nav-link">{{ n.title }}</router-link>
        </nav>
        <div class="right">
          <v-btn v-if="session.isCustomer" to="/cart" variant="text" icon :aria-label="`Cart, ${cart.count} items`">
            <v-badge :model-value="cart.count > 0" :content="cart.count" color="primary">
              <v-icon :icon="mdiCartOutline" />
            </v-badge>
          </v-btn>
          <v-btn
            variant="text"
            :icon="dark ? mdiWhiteBalanceSunny : mdiWeatherNight"
            :aria-label="dark ? 'Use light theme' : 'Use dark theme'"
            @click="toggle"
          />
          <v-menu v-if="session.isLoggedIn" location="bottom end">
            <template #activator="{ props }">
              <v-btn v-bind="props" variant="text" :prepend-icon="mdiAccountCircleOutline">{{ session.account?.firstname }}</v-btn>
            </template>
            <v-list density="compact" min-width="200">
              <v-list-item to="/account" title="Profile" :prepend-icon="mdiAccountCircleOutline" />
              <v-list-item :prepend-icon="mdiLogout" title="Log out" @click="logout" />
            </v-list>
          </v-menu>
          <template v-else>
            <v-btn :to="{ path: '/login', query: loginQuery }" variant="text">Log in</v-btn>
            <v-btn to="/signup" color="primary" variant="flat">Sign up</v-btn>
          </template>
        </div>
      </div>
    </v-app-bar>

    <v-main id="main">
      <AppNotifier />
      <router-view />
      <ShopFooter />
    </v-main>

    <v-bottom-navigation v-if="!mdAndUp" grow height="64" border="t" color="primary" aria-label="Main">
      <v-menu v-model="menu" location="top start" :close-on-content-click="false">
        <template #activator="{ props }">
          <v-btn v-bind="props" :prepend-icon="mdiMenu" stacked>Menu</v-btn>
        </template>
        <v-card min-width="240">
          <v-list density="comfortable">
            <v-list-item v-if="session.isLoggedIn" :title="session.displayName" :subtitle="session.account?.email" />
            <v-list-item to="/" title="Home" :prepend-icon="mdiHomeOutline" @click="menu = false" />
            <v-list-item v-if="session.isLoggedIn" to="/account" title="Profile" :prepend-icon="mdiAccountCircleOutline" @click="menu = false" />
            <v-list-item :title="dark ? 'Light theme' : 'Dark theme'" :prepend-icon="dark ? mdiWhiteBalanceSunny : mdiWeatherNight" @click="toggle" />
            <v-list-item v-if="session.isLoggedIn" title="Log out" :prepend-icon="mdiLogout" @click="logout" />
            <template v-else>
              <v-list-item :to="{ path: '/login', query: loginQuery }" title="Log in" :prepend-icon="mdiLogin" @click="menu = false" />
              <v-list-item to="/signup" title="Sign up" :prepend-icon="mdiAccountCircleOutline" @click="menu = false" />
            </template>
          </v-list>
        </v-card>
      </v-menu>
      <v-btn v-for="n in nav.filter((x) => x.show)" :key="n.to" :to="n.to" :prepend-icon="n.icon" stacked>{{ n.short ?? n.title }}</v-btn>
      <v-btn v-if="session.isCustomer" to="/cart" stacked>
        <v-badge :model-value="cart.count > 0" :content="cart.count" color="primary"><v-icon :icon="mdiCartOutline" /></v-badge>
        Cart
      </v-btn>
    </v-bottom-navigation>
  </v-app>
</template>

<style scoped>
.bar {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 var(--sp-4);
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: var(--sp-4);
}
.brand {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  text-decoration: none;
  color: inherit;
  justify-self: start;
}
.brand img {
  height: 36px;
  width: auto;
}
.brand-name {
  font-size: 14px;
  font-weight: 600;
  opacity: 0.72;
}
.nav {
  display: flex;
  gap: var(--sp-6);
}
.nav-link {
  position: relative;
  padding: 8px 2px;
  font-size: 15px;
  font-weight: 500;
  color: rgb(var(--v-theme-on-surface));
  text-decoration: none;
}
.nav-link:hover {
  color: rgb(var(--v-theme-primary));
}
.nav-link.router-link-active {
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
}
.nav-link.router-link-active::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -2px;
  height: 2px;
  border-radius: 2px;
  background: rgb(var(--v-theme-primary));
}
.right {
  justify-self: end;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
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
