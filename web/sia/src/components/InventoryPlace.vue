<script setup lang="ts">
/**
 * A-08 places, the record beside the Places tree on /inventory:
 *   new site   (`?op=site`): register a site;
 *   a site     (`?code=SITE…`): its locations, and the form to add one;
 *   a location (`?code=LOC…`): its shelves with their QR labels, and the form to add shelves.
 * Every create refreshes the tree and opens what was made, so the next step is right there.
 */
import { ApiError, call, countries, inventory, useNotify } from '@cimh/web-app'
import { mdiChevronRight, mdiPrinterOutline } from '@mdi/js'
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { placeTo, shelfLabel, usePlaces } from '../places'
import LabelSheet from './LabelSheet.vue'

const props = defineProps<{ kind: 'new-site' | 'site' | 'location'; code?: string; site?: string | null }>()
const router = useRouter()
const notify = useNotify()
const places = usePlaces()

const busy = ref(false)
const errors = ref<Record<string, string>>({})
const siteForm = reactive({ name: '', country: 'BB', address: '', description: '' })
const locForm = reactive({ name: '', description: '' })
const shelfCount = ref(1)
const printAll = ref(false)
const fresh = ref<string[]>([]) // shelves just added: shown on the label sheet straight away

const site = computed(() => (props.kind === 'site' && props.code ? places.site(props.code) : undefined))
const location = computed(() => (props.kind === 'location' && props.code ? places.location(props.code) : undefined))
const siteOfLocation = computed(() => (location.value ? places.site(location.value.site) : undefined))
// The site whose locations this record needs: the site itself, or the location's site (from the link).
const siteCode = computed(() => (props.kind === 'site' ? props.code : props.kind === 'location' ? props.site : null) ?? null)
const loadFailed = ref(false)
const notFound = ref(false)
watch(
  [() => props.code, siteCode],
  ([, sc]) => {
    errors.value = {}
    printAll.value = false
    fresh.value = []
    loadFailed.value = false
    notFound.value = false
    if (sc) places.ensureSite(sc).catch((e) => ((loadFailed.value = true), notify.report(e)))
    // A location opened by its code alone: find its site, then open it properly (site in the URL, tree marked).
    else if (props.kind === 'location' && props.code) {
      const code = props.code
      places
        .findLocation(code)
        .then((l) => {
          if (props.code !== code) return
          if (l) void router.replace(placeTo(code, l.site))
          else notFound.value = true
        })
        .catch((e) => ((loadFailed.value = true), notify.report(e)))
    }
  },
  { immediate: true },
)
const missing = computed(() => {
  if (loadFailed.value) return 'This place could not be loaded.'
  if (props.kind === 'location' && !props.site) return notFound.value ? 'No location has this code.' : 'Finding this location…'
  if (places.state.value !== 'ready' || (siteCode.value && !places.locations[siteCode.value])) return 'Loading…'
  return props.kind === 'site' ? 'No site has this code.' : 'No location has this code.'
})

async function submit(fn: () => Promise<void>) {
  busy.value = true
  errors.value = {}
  try {
    await fn()
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) errors.value = e.fieldErrors()
    notify.report(e)
  } finally {
    busy.value = false
  }
}

const createSite = () =>
  submit(async () => {
    const t = (s: string) => s.trim()
    const body = { name: t(siteForm.name), country: siteForm.country, ...(t(siteForm.address) ? { address: t(siteForm.address) } : {}),
      ...(t(siteForm.description) ? { description: t(siteForm.description) } : {}) } // prettier-ignore
    const made = await call(() => inventory.POST('/sites', { body }))
    places.sites.value = [...places.sites.value, made]
    places.locations[made.barcode] = []
    Object.assign(siteForm, { name: '', address: '', description: '' })
    notify.toast(`Site ${made.name} registered`, 'success')
    void router.replace({ query: { code: made.barcode } })
  })

const createLocation = () =>
  submit(async () => {
    const s = site.value!
    const body = { name: locForm.name.trim(), ...(locForm.description.trim() ? { description: locForm.description.trim() } : {}) }
    const made = await call(() => inventory.POST('/sites/{site}/locations', { params: { path: { site: s.barcode } }, body }))
    await places.loadSite(s.barcode)
    Object.assign(locForm, { name: '', description: '' })
    notify.toast(`Location ${made.name} created`, 'success')
    void router.replace(placeTo(made.barcode, s.barcode))
  })

const addShelves = () =>
  submit(async () => {
    const l = location.value!
    const res = await call(() =>
      inventory.POST('/locations/{location}/shelves', { params: { path: { location: l.barcode } }, body: { count: shelfCount.value } }),
    )
    await places.loadSite(l.site)
    fresh.value = res.items.map((s) => s.barcode)
    printAll.value = false
    shelfCount.value = 1
    notify.toast(`${res.items.length} shelves added. Print their labels below.`, 'success')
  })

const shelves = computed(() => location.value?.shelves ?? [])
const sheet = computed(() => {
  const l = location.value
  if (!l) return []
  const list = printAll.value ? shelves.value : shelves.value.filter((s) => fresh.value.includes(s.barcode))
  return list.map((s) => shelfLabel(s, siteOfLocation.value?.name, l.name))
})
const to = (code: string, site?: string) => placeTo(code, site)
</script>

<template>
  <div class="place">
    <!-- Register a site -->
    <template v-if="kind === 'new-site'">
      <header class="pad">
        <h2 class="t-h3">Register a site</h2>
        <p class="t-body muted">A site is a building or station. Locations (store rooms, bays) and their shelves go under it.</p>
      </header>
      <form class="pad form" @submit.prevent="createSite">
        <v-text-field v-model="siteForm.name" label="Site name" :error-messages="errors.name" />
        <v-autocomplete v-model="siteForm.country" label="Country" :items="countries()" :error-messages="errors.country" />
        <v-text-field v-model="siteForm.address" label="Address (optional)" />
        <v-text-field v-model="siteForm.description" label="Description (optional)" />
        <div class="actions">
          <v-btn class="m3" variant="text" :to="{ path: '/inventory' }">Cancel</v-btn>
          <v-btn class="m3" type="submit" color="primary" :loading="busy" :disabled="!siteForm.name.trim()">Register site</v-btn>
        </div>
      </form>
    </template>

    <!-- A site: its locations -->
    <template v-else-if="kind === 'site'">
      <p v-if="!site" class="pad t-body muted">{{ missing }}</p>
      <template v-else>
        <header class="pad">
          <h2 class="t-h3">{{ site.name }}</h2>
          <p class="t-caption muted">
            {{ site.country }}<template v-if="site.address"> · {{ site.address }}</template> · <span class="console-mono">{{ site.barcode }}</span>
          </p>
          <p v-if="site.description" class="t-body">{{ site.description }}</p>
        </header>
        <div class="console-head sub"><h3 class="console-title">Locations</h3><span class="console-mono t-caption muted">{{ places.locations[site.barcode]?.length ?? 0 }}</span></div>
        <p v-if="!places.locations[site.barcode]?.length" class="pad t-body muted">No locations yet. Add the first one below.</p>
        <ul v-else class="rows" role="list">
          <li v-for="l in places.locations[site.barcode]" :key="l.barcode">
            <router-link class="rowlink" :to="to(l.barcode, site.barcode)">
              <span class="nm">{{ l.name }}</span>
              <span class="console-mono t-caption muted">{{ l.shelfCount ?? 0 }} shelves</span>
              <v-icon :icon="mdiChevronRight" size="18" class="muted" />
            </router-link>
          </li>
        </ul>
        <div class="console-head sub"><h3 class="console-title">Add a location</h3></div>
        <form class="pad form" @submit.prevent="createLocation">
          <v-text-field v-model="locForm.name" label="Location name (store room, bay…)" :error-messages="errors.name" />
          <v-text-field v-model="locForm.description" label="Description (optional)" />
          <div class="actions">
            <v-btn class="m3" type="submit" color="primary" :loading="busy" :disabled="!locForm.name.trim()">Create location</v-btn>
          </div>
        </form>
      </template>
    </template>

    <!-- A location: its shelves -->
    <template v-else>
      <p v-if="!location" class="pad t-body muted">{{ missing }}</p>
      <template v-else>
        <header class="pad hd">
          <div>
            <h2 class="t-h3">{{ location.name }}</h2>
            <p class="t-caption muted">
              <router-link v-if="siteOfLocation" :to="to(siteOfLocation.barcode)">{{ siteOfLocation.name }}</router-link>
              · <span class="console-mono">{{ location.barcode }}</span>
            </p>
            <p v-if="location.description" class="t-body">{{ location.description }}</p>
          </div>
          <v-btn
            v-if="shelves.length"
            class="m3"
            variant="outlined"
            :prepend-icon="mdiPrinterOutline"
            :aria-expanded="printAll"
            @click="printAll = !printAll"
          >
            {{ printAll ? 'Hide shelf QR codes' : 'Shelf QR codes' }}
          </v-btn>
        </header>

        <div class="console-head sub"><h3 class="console-title">Shelves</h3><span class="console-mono t-caption muted">{{ location.shelfCount ?? shelves.length }}</span></div>
        <p v-if="!shelves.length" class="pad t-body muted">No shelves yet. Add them below; each gets a QR label to print.</p>
        <ul v-else class="grid" role="list">
          <li v-for="s in shelves" :key="s.barcode">
            <router-link
              class="cell"
              :class="{ fresh: fresh.includes(s.barcode) }"
              :style="fresh.includes(s.barcode) ? { '--i': fresh.indexOf(s.barcode) } : undefined"
              :to="to(s.barcode)"
            >
              <span class="t-caption muted">Shelf</span>
              <span class="console-mono num">{{ s.number }}</span>
            </router-link>
          </li>
        </ul>

        <div v-if="sheet.length" class="pad sheet">
          <LabelSheet :items="sheet" :heading="printAll ? `${location.name} shelf labels` : 'New shelves'" />
        </div>

        <div class="console-head sub"><h3 class="console-title">Add shelves</h3></div>
        <form class="pad form row-form" @submit.prevent="addShelves">
          <v-text-field
            v-model.number="shelfCount"
            type="number"
            min="1"
            max="200"
            label="How many shelves"
            hint="Numbers continue after the existing shelves"
            persistent-hint
            :error-messages="errors.count"
          />
          <v-btn class="m3" type="submit" color="primary" :loading="busy" :disabled="shelfCount < 1 || shelfCount > 200">Add shelves</v-btn>
        </form>
      </template>
    </template>
  </div>
</template>

<style scoped>
.place {
  animation: console-swap-in 220ms var(--ease-out);
}
.pad {
  padding: var(--sp-4);
}
header.pad {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}
.hd {
  flex-direction: row !important;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--sp-3) !important;
}
.sub {
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.form {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  max-width: 560px;
}
.row-form {
  flex-direction: row;
  align-items: flex-start;
  gap: var(--sp-3);
}
.row-form .v-input {
  max-width: 260px;
}
.row-form .v-btn {
  margin-top: 2px;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
}
.rows {
  list-style: none;
  margin: 0;
  padding: 0;
}
.rowlink {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  min-height: 44px;
  padding: 0 var(--sp-4);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
  color: rgb(var(--v-theme-on-surface));
  text-decoration: none;
}
.rowlink:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.nm {
  flex: 1;
  min-width: 0;
}
.grid {
  list-style: none;
  margin: 0;
  padding: var(--sp-4);
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(88px, 1fr));
  gap: var(--sp-2);
}
.cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  color: rgb(var(--v-theme-on-surface));
  text-decoration: none;
  transition: border-color 120ms, background-color 120ms;
}
.cell:hover {
  border-color: rgb(var(--v-theme-primary));
}
.cell.fresh {
  background: rgb(var(--v-theme-primary-subtle));
  border-color: rgb(var(--v-theme-primary));
  animation: fresh-in 420ms var(--ease-out) both;
  animation-delay: calc(min(var(--i, 0), 10) * 30ms);
}
.num {
  font-size: 20px;
  line-height: 28px;
  font-weight: 600;
}
.sheet {
  border-top: 1px solid rgb(var(--v-theme-seam));
}
@keyframes fresh-in {
  from {
    opacity: 0;
    transform: scale(0.94);
  }
}
@media (max-width: 599px) {
  .row-form {
    flex-direction: column;
    align-items: stretch;
  }
  .row-form .v-input {
    max-width: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .cell.fresh {
    animation: none;
  }
}
</style>
