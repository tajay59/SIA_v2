<script setup lang="ts">
/**
 * SIA shell (DESIGN_BRIEF §8): left side nav 248 px (collapsible to icons), top bar with the page title and
 * user menu. Bare layout (login, MFA setup…) shows only the card. Nav items appear as their phases ship.
 */
import { AppNotifier, useSession, useThemeMode } from '@cimh/web-app'
import logo from '@cimh/web-app/assets/cimh-logo-blue.webp'
import logoWhite from '@cimh/web-app/assets/cimh-logo-white.webp'
import {
  mdiAccountCheckOutline,
  mdiAccountCircleOutline,
  mdiAccountGroupOutline,
  mdiDomain,
  mdiHistory,
  mdiLogout,
  mdiMenu,
  mdiViewDashboardOutline,
  mdiWeatherNight,
  mdiWhiteBalanceSunny,
} from '@mdi/js'
import { computed, ref } from 'vue'
import { useDisplay } from 'vuetify'
import { useRoute, useRouter } from 'vue-router'

const session = useSession()
const route = useRoute()
const router = useRouter()
const { dark, toggle } = useThemeMode()
const { mdAndUp } = useDisplay()
const drawer = ref<boolean | null>(null)
const rail = ref(false)
const brand = computed(() => (dark.value ? logoWhite : logo))
const bare = computed(() => route.meta.layout === 'bare' || !session.isStaff || session.needsMfaSetup)

const nav = computed(() => [
  { title: 'Dashboard', to: '/', icon: mdiViewDashboardOutline, show: true },
  { header: 'Accounts', show: true },
  { title: 'Pending accounts', to: '/admin/approvals', icon: mdiAccountCheckOutline, show: session.isAdmin },
  { title: 'Accounts', to: '/admin/accounts', icon: mdiAccountGroupOutline, show: true },
  { title: 'Organisations', to: '/admin/organisations', icon: mdiDomain, show: session.isStaff },
  { title: 'Audit log', to: '/admin/audit', icon: mdiHistory, show: session.isAdmin },
])

async function logout() {
  await session.logout()
  await router.push('/login')
}
</script>

<template>
  <v-app>
    <a href="#main" class="skip-link">Skip to content</a>
    <template v-if="!bare">
      <v-navigation-drawer v-model="drawer" :rail="rail && mdAndUp" width="248" border="e">
        <div class="drawer-brand">
          <img :src="brand" alt="CIMH" height="28" width="91" />
          <span v-if="!rail" class="t-label muted">SIA</span>
        </div>
        <v-list nav density="compact" color="primary">
          <template v-for="item in nav.filter((n) => n.show)" :key="item.title ?? item.header">
            <v-list-subheader v-if="item.header && !rail">{{ item.header }}</v-list-subheader>
            <v-list-item
              v-else-if="item.to"
              :to="item.to"
              :prepend-icon="item.icon"
              :title="item.title"
              :exact="item.to === '/'"
              rounded="md"
            />
          </template>
        </v-list>
      </v-navigation-drawer>

      <v-app-bar flat border="b" height="56" color="surface">
        <v-btn
          variant="text"
          :icon="mdiMenu"
          :aria-label="mdAndUp ? 'Collapse navigation' : 'Open navigation'"
          @click="mdAndUp ? (rail = !rail) : (drawer = !drawer)"
        />
        <v-app-bar-title class="t-h3">{{ route.meta.title ?? '' }}</v-app-bar-title>
        <v-btn
          variant="text"
          :icon="dark ? mdiWhiteBalanceSunny : mdiWeatherNight"
          :aria-label="dark ? 'Use light theme' : 'Use dark theme'"
          @click="toggle"
        />
        <v-menu location="bottom end">
          <template #activator="{ props }">
            <v-btn v-bind="props" variant="text" :prepend-icon="mdiAccountCircleOutline" class="mr-2">
              {{ session.account?.firstname }}
            </v-btn>
          </template>
          <v-list density="compact" min-width="200">
            <v-list-item :subtitle="session.account?.email" :title="session.displayName" />
            <v-divider />
            <v-list-item to="/profile" title="Profile" />
            <v-list-item :prepend-icon="mdiLogout" title="Log out" @click="logout" />
          </v-list>
        </v-menu>
      </v-app-bar>
    </template>

    <v-main id="main">
      <AppNotifier />
      <router-view />
    </v-main>
  </v-app>
</template>

<style scoped>
.drawer-brand {
  height: 56px;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: 0 var(--sp-4);
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.drawer-brand img {
  height: 28px;
  width: auto;
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
