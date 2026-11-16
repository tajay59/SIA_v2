<script setup lang="ts">
/**
 * Admin overview (new, 2026-11-13): what needs an administrator now beside the admin tools index.
 * Left: "Waiting for approval" (oldest 5) and "Asked to be deleted" (all open requests), each row opens the
 * account. Right: the admin pages with one line each. Staff see the read-only parts (accounts, organisations).
 */
import { type AccountSummary, call, identity, useSession } from '@cimh/web-app'
import { formatAge } from '@cimh/web-ui'
import {
  mdiAccountCheckOutline,
  mdiAccountMultipleOutline,
  mdiAlertOutline,
  mdiArrowRight,
  mdiCogOutline,
  mdiDeleteClockOutline,
  mdiDomain,
  mdiHistory,
} from '@mdi/js'
import { computed, onMounted, ref } from 'vue'

definePage({ meta: { guard: 'staff', title: 'Admin', ownHeading: true } })
const session = useSession()

type Box = { items: AccountSummary[]; more: boolean; loaded: boolean; failed: boolean }
const pending = ref<Box>({ items: [], more: false, loaded: false, failed: false })
const erasure = ref<Box>({ items: [], more: false, loaded: false, failed: false })

async function fill(box: typeof pending, query: Record<string, unknown>, limit: number) {
  box.value.failed = false
  try {
    const page = await call(() => identity.GET('/admin/accounts', { params: { query: { ...query, limit } } }))
    box.value = { items: page.items, more: !!page.nextCursor, loaded: true, failed: false }
  } catch {
    box.value = { ...box.value, loaded: true, failed: true }
  }
}
function load() {
  if (session.isAdmin) void fill(pending, { status: 'PENDING_APPROVAL' }, 5)
  void fill(erasure, { erasureRequested: true }, 20)
}
onMounted(load)

const DAY = 86_400_000
const overdue = (a: AccountSummary) => !!a.createdAt && Date.now() - new Date(a.createdAt).getTime() > 2 * DAY
const nameOf = (a: AccountSummary) => `${a.firstname} ${a.lastname}`.trim() || a.email
const quiet = computed(() => pending.value.loaded && erasure.value.loaded && !pending.value.items.length && !erasure.value.items.length)

const tools = computed(() =>
  [
    { to: '/admin/approvals', icon: mdiAccountCheckOutline, title: 'Pending accounts', desc: 'Approve or deny new customer sign-ups.', admin: true },
    { to: '/admin/accounts', icon: mdiAccountMultipleOutline, title: 'Accounts', desc: 'Find customers and staff; change roles, suspend, export or erase.', admin: false },
    { to: '/admin/organisations', icon: mdiDomain, title: 'Organisations', desc: 'Met services and agencies that customers belong to.', admin: false },
    { to: '/admin/audit', icon: mdiHistory, title: 'Audit log', desc: 'Admin and security actions, searchable.', admin: true },
    { to: '/admin/settings', icon: mdiCogOutline, title: 'Settings', desc: 'Admin fee, reference data and staff email lists.', admin: true },
  ].filter((t) => !t.admin || session.isAdmin),
)
</script>

<template>
  <div class="admin">
    <h1 class="t-h1">Admin</h1>

    <div class="console-panels split">
      <section class="needs" aria-labelledby="needs-h">
        <div class="console-head">
          <h2 id="needs-h" class="console-title">Needs an administrator</h2>
          <v-btn variant="text" size="small" class="m3" @click="load">Refresh</v-btn>
        </div>

        <p v-if="quiet" class="calm t-body"><v-icon :icon="mdiAccountCheckOutline" size="20" />Nothing is waiting. New sign-ups and deletion requests appear here.</p>

        <div v-if="session.isAdmin && (!pending.loaded || pending.items.length || pending.failed)" class="block">
          <h3 class="block-h">
            Waiting for approval
            <router-link to="/admin/approvals" class="more">Review all<v-icon :icon="mdiArrowRight" size="16" /></router-link>
          </h3>
          <div v-if="!pending.loaded" class="console-skel skel" />
          <p v-else-if="pending.failed" class="t-body muted">Couldn't load. <button type="button" class="console-retry" @click="load">Retry</button></p>
          <TransitionGroup v-else tag="ul" name="nrow" appear class="list">
            <li v-for="(a, i) in pending.items" :key="a.id" :style="{ '--i': i }">
              <router-link :to="`/admin/accounts?open=${a.id}`" class="item">
                <span class="who"><span class="nm">{{ nameOf(a) }}</span><span class="sub">{{ a.organisationText || 'No organisation given' }} · {{ a.email }}</span></span>
                <span class="wait" :class="{ late: overdue(a) }">
                  <v-icon v-if="overdue(a)" :icon="mdiAlertOutline" size="16" /><template v-if="overdue(a)">Overdue · </template>
                  <span class="console-mono">{{ a.createdAt ? formatAge(a.createdAt) : '' }}</span>
                </span>
              </router-link>
            </li>
            <li v-if="pending.more" class="t-caption muted tail">More are waiting; Review all shows every one.</li>
          </TransitionGroup>
        </div>

        <div v-if="!erasure.loaded || erasure.items.length || erasure.failed" class="block">
          <h3 class="block-h">
            Asked to be deleted
            <router-link to="/admin/accounts?erasure=1" class="more">In accounts<v-icon :icon="mdiArrowRight" size="16" /></router-link>
          </h3>
          <div v-if="!erasure.loaded" class="console-skel skel" />
          <p v-else-if="erasure.failed" class="t-body muted">Couldn't load. <button type="button" class="console-retry" @click="load">Retry</button></p>
          <TransitionGroup v-else tag="ul" name="nrow" appear class="list">
            <li v-for="(a, i) in erasure.items" :key="a.id" :style="{ '--i': i }">
              <router-link :to="`/admin/accounts?erasure=1&open=${a.id}`" class="item">
                <span class="who"><span class="nm">{{ nameOf(a) }}</span><span class="sub">{{ a.email }}</span></span>
                <span class="wait late"><v-icon :icon="mdiDeleteClockOutline" size="16" /><span class="console-mono">{{ a.erasureRequestedAt ? formatAge(a.erasureRequestedAt) : '' }}</span></span>
              </router-link>
            </li>
          </TransitionGroup>
        </div>
      </section>

      <nav class="tools" aria-labelledby="tools-h">
        <div class="console-head"><h2 id="tools-h" class="console-title">Admin pages</h2></div>
        <ul class="list">
          <li v-for="t in tools" :key="t.to">
            <router-link :to="t.to" class="tool">
              <v-icon :icon="t.icon" size="20" class="ti" />
              <span class="who"><span class="nm">{{ t.title }}</span><span class="sub wrap">{{ t.desc }}</span></span>
              <v-icon :icon="mdiArrowRight" size="18" class="go" />
            </router-link>
          </li>
        </ul>
      </nav>
    </div>
  </div>
</template>

<style scoped>
.admin {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
  max-width: 1400px;
  margin-inline: auto;
  padding: var(--sp-4) var(--sp-6) var(--sp-6);
  font-size: 14px;
}
.split {
  flex: none;
  grid-template-columns: minmax(0, 3fr) minmax(300px, 2fr);
  align-items: start;
}
.tools {
  border-left: 1px solid rgb(var(--v-theme-seam));
  align-self: stretch;
}
.block + .block {
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.block-h {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 0;
  padding: var(--sp-4) var(--sp-4) var(--sp-2);
  font-size: 16px;
  line-height: 22px;
  font-weight: 600;
}
.more {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
}
.more:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.more .v-icon {
  transition: transform 160ms var(--ease-out);
}
.more:hover .v-icon {
  transform: translateX(3px);
}
.calm {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin: 0;
  padding: var(--sp-6) var(--sp-4);
  color: rgb(var(--v-theme-secondary));
}
.skel {
  height: 44px;
  margin: var(--sp-2) var(--sp-4) var(--sp-4);
  border-radius: 4px;
}
.list {
  list-style: none;
  margin: 0;
  padding: 0 0 var(--sp-2);
}
.item,
.tool {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  min-height: 52px;
  padding: 6px var(--sp-4);
  color: inherit;
  text-decoration: none;
  border-top: 1px solid rgb(var(--v-theme-seam));
  transition: background-color 120ms ease;
}
.item:hover,
.tool:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.item:focus-visible,
.tool:focus-visible {
  outline-offset: -2px;
}
.who {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}
.nm {
  font-weight: 500;
}
.sub {
  font-size: 12px;
  color: rgb(var(--v-theme-secondary));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sub.wrap {
  white-space: normal;
}
.wait {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: rgb(var(--v-theme-secondary));
  white-space: nowrap;
}
.wait.late {
  color: rgb(var(--v-theme-warning));
  font-weight: 500;
}
.tail {
  padding: var(--sp-2) var(--sp-4);
}
.tools .list {
  padding: 0;
}
.tools li:first-child .tool {
  border-top: 0;
}
.ti,
.go {
  color: rgb(var(--v-theme-secondary));
}
.go {
  transition: transform 160ms var(--ease-out), color 160ms ease;
}
.tool:hover .go {
  transform: translateX(3px);
  color: rgb(var(--v-theme-primary));
}
@media (max-width: 899.98px) {
  .split {
    grid-template-columns: minmax(0, 1fr);
  }
  .tools {
    border-left: 0;
    border-top: 1px solid rgb(var(--v-theme-seam));
  }
}
@media (max-width: 599.98px) {
  .admin {
    padding: var(--sp-3) var(--sp-4) var(--sp-6);
  }
}
/* Waiting items arrive in order when the overview loads or refreshes; a handled one fades out. */
.list {
  position: relative;
}
.nrow-enter-active {
  transition: opacity 220ms var(--ease-out), transform 220ms var(--ease-out);
  transition-delay: calc(var(--i, 0) * 30ms);
}
.nrow-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.nrow-leave-active {
  position: absolute;
  width: 100%;
  transition: opacity 140ms ease-in;
}
.nrow-leave-to {
  opacity: 0;
}
.nrow-move {
  transition: transform 280ms var(--ease-out);
}
@media (prefers-reduced-motion: reduce) {
  .nrow-enter-active {
    transition: opacity 160ms ease;
    transition-delay: 0ms;
  }
  .nrow-enter-from {
    transform: none;
  }
  .nrow-move {
    transition: none;
  }
  .go,
  .more .v-icon {
    transition: none;
  }
}
</style>
