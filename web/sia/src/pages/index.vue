<script setup lang="ts">
/**
 * A-01 dashboard: the legacy SIA home (statement, spares cards, search) followed by the counters. Requests:
 * new, quoting, agreements to verify, to pick, to ship, quotes expiring within 3 days; low stock; accounts.
 * Each request counter opens the desk (A-02) filtered. Counts stop at 100 ("100+": one page).
 */
import { call, identity, inventory, orders, type RequestSummary, useNotify, useSession } from '@cimh/web-app'
import aws from '@cimh/web-app/assets/legacy/hero-aws-800.webp'
import radar from '@cimh/web-app/assets/legacy/hero-radar-960.webp'
import {
  mdiAccountCheckOutline,
  mdiAccountGroupOutline,
  mdiAlertOutline,
  mdiClipboardTextOutline,
  mdiDomain,
  mdiEmailOutline,
  mdiMagnify,
} from '@mdi/js'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

definePage({ meta: { guard: 'staff', title: 'Dashboard', ownHeading: true } })

const session = useSession()
const router = useRouter()
const q = ref('')
const spares = [
  { type: 'RAD', title: 'Radar Spares', sub: 'Service parts', img: radar },
  { type: 'MET', title: 'Hydro-Met Spares', sub: 'Maintenance & service parts', img: aws },
]
const notify = useNotify()
const pending = ref<number | null>(null)
const unverified = ref<number | null>(null)

/** Count up to 100 (one page); "100+" beyond that. */
async function count(status: 'PENDING_APPROVAL' | 'PENDING_VERIFICATION'): Promise<number> {
  const res = await call(() => identity.GET('/admin/accounts', { params: { query: { status, limit: 100 } } }))
  return res.nextCursor ? 101 : res.items.length
}
const label = (n: number | null) => (n === null ? '…' : n > 100 ? '100+' : String(n))

type Counter = { key: string; title: string; status: string; n: number | null; filter?: (r: RequestSummary) => boolean }
const counters = ref<Counter[]>([
  { key: 'new', title: 'New requests', status: 'SUBMITTED', n: null },
  { key: 'quoting', title: 'Being quoted', status: 'QUOTING', n: null },
  { key: 'expiring', title: 'Quotes expiring in 3 days', status: 'QUOTED', n: null,
    filter: (r) => !!r.quoteExpiresAt && Date.parse(r.quoteExpiresAt) - Date.now() < 3 * 86_400_000 },
  { key: 'verify', title: 'Agreements to verify', status: 'ACCEPTED', n: null },
  { key: 'pick', title: 'To pick', status: 'APPROVED,PICKING,PURCHASING', n: null },
  { key: 'ship', title: 'To ship', status: 'PURCHASING,PICKING', n: null },
])
const low = ref<number | null>(null)
async function countRequests(c: Counter): Promise<number> {
  const res = (await call(() =>
    orders.GET('/requests', { params: { query: { scope: 'all', status: c.status, limit: 100 } as any } }),
  )) as { items: RequestSummary[]; nextCursor: string | null }
  const items = c.filter ? res.items.filter(c.filter) : res.items
  return res.nextCursor && !c.filter ? 101 : items.length
}

onMounted(async () => {
  void Promise.all(counters.value.map(async (c) => (c.n = await countRequests(c)))).catch((e) => notify.report(e))
  void call(() => inventory.GET('/stock/low', { params: { query: { limit: 100 } } }))
    .then((r) => (low.value = r.nextCursor ? 101 : r.items.length))
    .catch(() => undefined)
  try {
    ;[pending.value, unverified.value] = await Promise.all([count('PENDING_APPROVAL'), count('PENDING_VERIFICATION')])
  } catch (e) {
    notify.report(e)
  }
})
</script>

<template>
  <div>
    <!-- Same structure as the legacy SIA home: statement band, spares cards, "What are you looking for today?" -->
    <section class="statement">
      <div class="statement-inner">
        <p class="t-label greet">Good to see you, {{ session.account?.firstname }}</p>
        <h1 class="statement-title">The CIMH Instrumentation and Equipment <span class="accent">Spares</span></h1>
      </div>
    </section>

    <div class="page stack-lg">
      <section class="spares">
        <router-link v-for="c in spares" :key="c.type" :to="`/products?type=${c.type}`" class="spare">
          <img :src="c.img" alt="" class="spare-img" loading="lazy" />
          <div class="spare-text">
            <h2 class="t-h3">{{ c.title }}</h2>
            <p class="t-body muted">{{ c.sub }}</p>
          </div>
        </router-link>
      </section>

      <v-card class="look">
        <div class="look-text">
          <p class="t-label muted">Instruments &amp; Equipment</p>
          <h2 class="t-h1">What are you looking for today?</h2>
          <p class="t-body muted">Search by name, model number, keyword or serial number.</p>
        </div>
        <form class="look-form" role="search" @submit.prevent="router.push({ path: '/products', query: q.trim() ? { q: q.trim() } : {} })">
          <v-text-field v-model="q" data-page-search :prepend-inner-icon="mdiMagnify" label="Find a product" hide-details />
          <v-btn type="submit" color="primary" size="large">Explore products</v-btn>
        </form>
      </v-card>

      <section class="stack-sm">
        <h2 class="t-h3">Requests</h2>
        <div class="tiles">
          <v-card
            v-for="c in counters"
            :key="c.key"
            :to="{ path: '/requests', query: { status: c.status, ...(c.key === 'expiring' ? { sort: 'oldest' } : {}) } }"
            class="tile"
            :class="{ attention: (c.n ?? 0) > 0 }"
          >
            <v-icon :icon="mdiClipboardTextOutline" color="primary" />
            <span class="t-display tnum">{{ label(c.n) }}</span>
            <span class="t-label">{{ c.title }}</span>
          </v-card>
          <v-card to="/reports/stock" class="tile" :class="{ attention: (low ?? 0) > 0 }">
            <v-icon :icon="mdiAlertOutline" color="primary" />
            <span class="t-display tnum">{{ label(low) }}</span>
            <span class="t-label">Products low on stock</span>
          </v-card>
        </div>
      </section>

      <section class="stack-sm">
        <h2 class="t-h3">Accounts</h2>
        <div class="tiles">
          <v-card v-if="session.isAdmin" :to="'/admin/approvals'" class="tile" :class="{ attention: (pending ?? 0) > 0 }">
            <v-icon :icon="mdiAccountCheckOutline" color="primary" />
            <span class="t-display tnum">{{ label(pending) }}</span>
            <span class="t-label">Accounts waiting for approval</span>
          </v-card>
          <v-card :to="'/admin/accounts?status=PENDING_VERIFICATION'" class="tile">
            <v-icon :icon="mdiEmailOutline" color="primary" />
            <span class="t-display tnum">{{ label(unverified) }}</span>
            <span class="t-label">Sign-ups not yet verified</span>
          </v-card>
          <v-card to="/admin/accounts" class="tile">
            <v-icon :icon="mdiAccountGroupOutline" color="primary" />
            <span class="t-h3">Accounts</span>
            <span class="t-label muted">Find customers and staff</span>
          </v-card>
          <v-card to="/admin/organisations" class="tile">
            <v-icon :icon="mdiDomain" color="primary" />
            <span class="t-h3">Organisations</span>
            <span class="t-label muted">Met services, agencies and partners</span>
          </v-card>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.statement {
  background-color: rgb(var(--v-theme-surface));
  background-image: url('@cimh/web-app/assets/legacy/gears.webp');
  background-size: cover;
  background-position: center bottom;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.v-theme--cimhDark .statement {
  background-blend-mode: multiply;
}
.statement-inner {
  max-width: 1440px;
  margin: 0 auto;
  padding: var(--sp-12, 48px) var(--sp-6);
}
.greet {
  color: rgb(var(--v-theme-primary));
  margin-bottom: var(--sp-2);
}
.statement-title {
  font-size: clamp(28px, 3.6vw, 44px);
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.15;
  max-width: 22ch;
  margin: 0;
}
.accent {
  color: rgb(var(--v-theme-primary));
}
.stack-lg {
  display: flex;
  flex-direction: column;
  gap: var(--sp-8);
}
.spares {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: var(--sp-4);
}
.spare {
  display: grid;
  grid-template-columns: 160px 1fr;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
  overflow: hidden;
  color: inherit;
  text-decoration: none;
  background: rgb(var(--v-theme-surface));
  transition: box-shadow 160ms ease-out;
}
.spare:hover {
  box-shadow: 0 6px 18px rgba(15, 26, 36, 0.12);
}
.spare-img {
  width: 100%;
  height: 100%;
  min-height: 120px;
  object-fit: cover;
}
.spare-text {
  padding: var(--sp-4) var(--sp-5, 20px);
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
}
.look {
  padding: var(--sp-8);
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 480px);
  gap: var(--sp-6);
  align-items: center;
}
@media (max-width: 959px) {
  .look {
    grid-template-columns: minmax(0, 1fr);
  }
}
.look-form {
  display: flex;
  gap: var(--sp-3);
  align-items: center;
}
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--sp-4);
}
.tile {
  padding: var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.tile.attention {
  border-left: 3px solid rgb(var(--v-theme-warning));
}
</style>
