<script setup lang="ts">
/**
 * A-18 organisations, list beside record: search, the organisation list, and the open organisation
 * (`?open=<id>`, `?open=new` to create) beside it on wide screens; narrow screens show the record alone with a
 * way back. Admins edit, create and merge; staff read.
 */
import { call, countryName, identity, type Organisation, useCursorList, useSession } from '@cimh/web-app'
import { mdiArrowLeft, mdiMagnify, mdiPlus } from '@mdi/js'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useRoute, useRouter } from 'vue-router'
import OrganisationRecord from '../../components/OrganisationRecord.vue'
import { orgTypeTitle } from '../../organisations'
import { pinLeaving } from '../../list-motion'

definePage({ meta: { guard: 'staff', title: 'Organisations', ownHeading: true } })

const route = useRoute()
const router = useRouter()
const display = useDisplay()
const session = useSession()
const str = (v: unknown) => (typeof v === 'string' && v ? v : null)
const q = ref(str(route.query.q) ?? '')
const openId = computed(() => str(route.query.open))
const isNew = computed(() => openId.value === 'new')

const list = useCursorList<Organisation>((cursor) =>
  call(() => identity.GET('/organisations', { params: { query: { q: q.value.trim() || undefined, cursor, limit: 50 } } })),
)
onMounted(list.reload)

function queryFor(open: string | null) {
  const query: Record<string, string> = {}
  if (q.value.trim()) query.q = q.value.trim()
  if (open) query.open = open
  return query
}
let timer: ReturnType<typeof setTimeout> | undefined
// A pending debounce must not fire after the page is left (router.replace would navigate back here).
onBeforeUnmount(() => clearTimeout(timer))
watch(q, () => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    void router.replace({ query: queryFor(openId.value) })
    void list.reload()
  }, 250)
})

const wide = computed(() => display.width.value >= 1280)
const open = (id: string) => void router.replace({ query: queryFor(id) })
const close = () => void router.replace({ query: queryFor(null) })
function onRowKey(e: KeyboardEvent, i: number) {
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
  e.preventDefault()
  const items = list.items.value
  const next = items[Math.max(0, Math.min(items.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))]
  if (!next) return
  document.getElementById(`orow-${next.id}`)?.focus()
  if (wide.value && openId.value) open(next.id)
}
function onSaved(o: Organisation, created: boolean) {
  const i = list.items.value.findIndex((x) => x.id === o.id)
  if (i >= 0) list.items.value.splice(i, 1, { ...o, memberCount: o.memberCount ?? list.items.value[i]!.memberCount })
  else list.items.value = [o, ...list.items.value]
  if (created) open(o.id)
}
function onMerged() {
  close()
  void list.reload()
}
const summary = computed(() => {
  if (!list.loaded.value) return 'Loading…'
  const n = list.items.value.length
  return `${n}${list.nextCursor.value ? '+' : ''} ${n === 1 ? 'organisation' : 'organisations'}`
})
</script>

<template>
  <div class="orgs" :class="{ alone: !wide && openId }">
    <div class="top">
      <h1 class="t-h1">Organisations</h1>
    </div>

    <div class="strip">
      <v-text-field
        v-model="q"
        data-page-search
        :prepend-inner-icon="mdiMagnify"
        label="Search organisations"
        clearable
        hide-details
        class="search"
        @click:clear="q = ''"
      />
      <!-- In the search strip, not the title row: at 360 px the title + button pushed the page sideways. -->
      <span class="spacer" />
      <v-btn v-if="session.isAdmin" class="m3 new-org" color="primary" variant="flat" :prepend-icon="mdiPlus" @click="open('new')">New organisation</v-btn>
    </div>

    <div class="console-panels panels" :class="{ split: wide && openId }">
      <section v-if="wide || !openId" class="olist" aria-label="Organisations">
        <div class="console-head">
          <h2 class="console-title" aria-live="polite">{{ summary }}</h2>
        </div>
        <div class="console-scroll">
          <div v-if="!list.loaded.value && list.loading.value" class="skel-rows">
            <div v-for="i in 8" :key="i" class="console-skel skel-row" />
          </div>
          <div v-else-if="list.loaded.value && !list.items.value.length" class="empty">
            <p class="t-body">{{ q.trim() ? `No organisation matches “${q.trim()}”.` : 'No organisations yet.' }}</p>
            <div class="row">
              <v-btn v-if="q.trim()" class="m3" variant="outlined" @click="q = ''">Clear search</v-btn>
              <v-btn v-if="session.isAdmin" class="m3" variant="outlined" :prepend-icon="mdiPlus" @click="open('new')">New organisation</v-btn>
            </div>
          </div>
          <TransitionGroup v-else tag="ul" name="orow" class="rows" @before-leave="pinLeaving">
            <li v-if="!(wide && openId)" key="head" class="row-h" aria-hidden="true">
              <span>Name</span>
              <span class="c-type">Type</span>
              <span class="c-country">Country</span>
              <span class="c-dom">Email domains</span>
              <span class="c-n">Members</span>
            </li>
            <li v-for="(o, i) in list.items.value" :key="o.id" :style="{ '--i': Math.min(i, 12) }">
              <a
                :id="`orow-${o.id}`"
                :href="`/admin/organisations?open=${o.id}`"
                class="orow"
                :class="{ on: openId === o.id, off: o.active === false }"
                :aria-current="openId === o.id ? 'true' : undefined"
                @click.prevent="open(o.id)"
                @keydown="onRowKey($event, i)"
              >
                <span class="c-name">
                  <span class="oname">{{ o.name }}<span v-if="o.active === false" class="inactive">Inactive</span></span>
                  <span v-if="o.aliases?.length" class="sub">Also: {{ o.aliases.join(', ') }}</span>
                  <span v-if="wide && openId" class="sub">{{ countryName(o.country) }}</span>
                </span>
                <span class="c-type">{{ orgTypeTitle(o.type) }}</span>
                <span class="c-country">{{ countryName(o.country) }}</span>
                <span class="c-dom console-mono">{{ (o.emailDomains ?? []).join(', ') || '—' }}</span>
                <span class="c-n console-mono">{{ o.memberCount ?? 0 }}</span>
              </a>
            </li>
          </TransitionGroup>
          <div v-if="list.nextCursor.value" class="load-more">
            <v-btn class="m3" variant="outlined" :loading="list.loading.value" @click="list.loadMore">Load more</v-btn>
          </div>
        </div>
      </section>

      <section v-if="openId" class="record" :aria-label="isNew ? 'New organisation' : 'Selected organisation'">
        <div class="console-head">
          <v-btn v-if="!wide" variant="text" size="small" class="m3" :prepend-icon="mdiArrowLeft" @click="close">All organisations</v-btn>
          <h2 v-else class="console-title">{{ isNew ? 'New organisation' : 'Selected organisation' }}</h2>
          <v-btn v-if="wide" variant="text" size="small" class="m3" @click="close">Close</v-btn>
        </div>
        <div class="console-scroll">
          <OrganisationRecord :key="openId" :organisation-id="isNew ? null : openId" @saved="onSaved" @merged="onMerged" />
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.orgs {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  max-width: 1600px;
  margin-inline: auto;
  padding: var(--sp-4) var(--sp-6) var(--sp-6);
  font-size: 14px;
}
@media (min-width: 1280px) {
  .orgs {
    height: 100dvh;
    min-height: 560px;
  }
  .orgs > :not(.panels) {
    flex-shrink: 0;
  }
}
.top {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}
.spacer {
  flex: 1;
}
.strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-3);
}
.search {
  flex: 1 1 240px;
  max-width: 480px;
}
.alone .strip {
  display: none;
}
.panels {
  grid-template-columns: minmax(0, 1fr);
}
.panels.split {
  grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
}
.record {
  background: rgb(var(--v-theme-background));
  min-width: 0;
}
.split .record {
  border-left: 1px solid rgb(var(--v-theme-seam));
}
.rows {
  list-style: none;
  position: relative;
  margin: 0;
  padding: 0;
}
.row-h,
.orow {
  display: grid;
  grid-template-columns: minmax(220px, 2.4fr) minmax(150px, 1.2fr) minmax(110px, 1fr) minmax(140px, 1.4fr) 80px;
  align-items: center;
  gap: var(--sp-3);
  padding: 0 var(--sp-4);
}
.split .orow {
  grid-template-columns: minmax(0, 1fr) auto;
}
.split .c-type,
.split .c-country,
.split .c-dom {
  display: none;
}
.row-h {
  position: sticky;
  top: 0;
  z-index: 1;
  height: 36px;
  font-size: 12px;
  font-weight: 500;
  color: rgb(var(--v-theme-secondary));
  background: rgb(var(--v-theme-surface));
  border-bottom: 1px solid rgb(var(--v-theme-seam));
}
.orow {
  min-height: 52px;
  padding-block: 8px;
  color: inherit;
  text-decoration: none;
  border-bottom: 1px solid rgb(var(--v-theme-seam));
  transition: background-color 120ms ease;
}
.orow:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.orow.on {
  background: rgba(var(--v-theme-primary), 0.14);
  box-shadow: inset 2px 0 rgb(var(--v-theme-primary));
}
.orow:focus-visible {
  outline-offset: -2px;
}
.orow.off .oname {
  color: rgb(var(--v-theme-secondary));
}
.c-name {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.oname {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-weight: 500;
  line-height: 20px;
}
.inactive {
  font-size: 11px;
  font-weight: 500;
  line-height: 18px;
  padding: 0 6px;
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 8px;
  color: rgb(var(--v-theme-secondary));
}
.sub,
.c-type,
.c-country,
.c-dom {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sub {
  font-size: 12px;
  color: rgb(var(--v-theme-secondary));
}
.c-dom {
  font-size: 12px;
  color: rgb(var(--v-theme-secondary));
}
.c-n {
  justify-self: end;
  font-size: 13px;
}
.skel-rows {
  padding: var(--sp-2) var(--sp-4);
}
.skel-row {
  height: 36px;
  margin: 12px 0;
  border-radius: 4px;
}
.empty {
  padding: var(--sp-8) var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.load-more {
  display: flex;
  justify-content: center;
  padding: var(--sp-4);
}
@media (max-width: 1099.98px) {
  .row-h,
  .orow {
    grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) 72px;
  }
  .c-type,
  .c-dom {
    display: none;
  }
}
@media (max-width: 599.98px) {
  .orgs {
    padding: var(--sp-3) var(--sp-4) var(--sp-6);
  }
  .row-h,
  .orow {
    grid-template-columns: minmax(0, 1fr) 56px;
  }
  .c-country {
    display: none;
  }
  .search {
    max-width: none;
  }
  .strip .spacer {
    display: none;
  }
}
.orow-enter-active {
  transition: opacity 220ms var(--ease-out), transform 220ms var(--ease-out);
  transition-delay: calc(var(--i, 0) * 24ms);
}
.orow-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.orow-leave-active {
  position: absolute;
  transition: opacity 140ms ease-in;
}
.orow-leave-to {
  opacity: 0;
}
.orow-move {
  transition: transform 280ms var(--ease-out);
}
@media (prefers-reduced-motion: reduce) {
  .orow-enter-active {
    transition: opacity 160ms ease;
    transition-delay: 0ms;
  }
  .orow-enter-from {
    transform: none;
  }
  .orow-move {
    transition: none;
  }
}
</style>
