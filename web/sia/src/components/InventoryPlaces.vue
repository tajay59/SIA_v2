<script setup lang="ts">
/**
 * A-08 sites and shelves (legacy Inventory → "Location" panel: arrows step between Site, Location and
 * Shelves forms). Below: every site → its locations → numbered shelves, each with a printable QR code.
 */
import { ApiError, call, countries, inventory, type Location, type Shelf, type Site, useNotify } from '@cimh/web-app'
import { mdiChevronLeft, mdiChevronRight, mdiPrinterOutline } from '@mdi/js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import LabelSheet from './LabelSheet.vue'

const emit = defineEmits<{ shelf: [barcode: string] }>()
const notify = useNotify()

const FORMS = ['Site', 'Location', 'Shelves'] as const
const form = ref<(typeof FORMS)[number]>('Location')
const step = (d: number) => (form.value = FORMS[(FORMS.indexOf(form.value) + d + FORMS.length) % FORMS.length])

const sites = ref<Site[]>([])
const locations = reactive<Record<string, Location[]>>({})
const busy = ref(false)
const errors = ref<Record<string, string>>({})

const site = reactive({ name: '', country: 'BB', address: '', description: '' })
const loc = reactive({ site: null as string | null, name: '', description: '' })
const shelves = reactive({ site: null as string | null, location: null as string | null, count: 1 })
const printing = ref<{ title: string; items: { value: string; title: string; subtitle?: string }[] } | null>(null)

const siteItems = computed(() => sites.value.map((s) => ({ title: s.name, value: s.barcode })))
const locationItems = computed(() =>
  (shelves.site ? (locations[shelves.site] ?? []) : []).map((l) => ({ title: l.name, value: l.barcode })),
)

async function loadSites() {
  try {
    sites.value = (await call(() => inventory.GET('/sites'))).items
  } catch (e) {
    notify.report(e, { retry: loadSites })
  }
}
async function loadLocations(siteCode: string) {
  try {
    locations[siteCode] = (
      await call(() => inventory.GET('/sites/{site}/locations', { params: { path: { site: siteCode }, query: { withShelves: true } } }))
    ).items
  } catch (e) {
    notify.report(e)
  }
}
onMounted(loadSites)
// Locations load when a site is opened.
const opened = ref<string[]>([])
watch(opened, (codes) => codes.filter((c) => !locations[c]).forEach((c) => void loadLocations(c)))

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
    const body = { name: site.name.trim(), country: site.country, ...(site.address.trim() ? { address: site.address.trim() } : {}),
      ...(site.description.trim() ? { description: site.description.trim() } : {}) } // prettier-ignore
    const made = await call(() => inventory.POST('/sites', { body }))
    sites.value = [...sites.value, made]
    Object.assign(site, { name: '', address: '', description: '' })
    loc.site = made.barcode
    form.value = 'Location'
    notify.toast(`Site ${made.name} registered`, 'success')
  })

const createLocation = () =>
  submit(async () => {
    const siteCode = loc.site!
    const body = { name: loc.name.trim(), ...(loc.description.trim() ? { description: loc.description.trim() } : {}) }
    const made = await call(() => inventory.POST('/sites/{site}/locations', { params: { path: { site: siteCode } }, body }))
    await loadLocations(siteCode)
    Object.assign(loc, { name: '', description: '' })
    Object.assign(shelves, { site: siteCode, location: made.barcode })
    form.value = 'Shelves'
    notify.toast(`Location ${made.name} created`, 'success')
  })

const addShelves = () =>
  submit(async () => {
    const res = await call(() =>
      inventory.POST('/locations/{location}/shelves', { params: { path: { location: shelves.location! } }, body: { count: shelves.count } }),
    )
    await loadLocations(shelves.site!)
    notify.toast(`${res.items.length} shelves added`, 'success')
    print(res.items, `New shelves`)
  })

function shelfLabel(s: Shelf) {
  return { value: s.barcode, title: `Shelf ${s.number}`, subtitle: [s.siteName, s.locationName].filter(Boolean).join(' · ') }
}
function print(list: Shelf[], title: string) {
  printing.value = { title, items: list.map(shelfLabel) }
}
async function pickSiteForShelves(code: string | null) {
  shelves.location = null
  if (code && !locations[code]) await loadLocations(code)
}
</script>

<template>
  <div class="stack">
    <v-card variant="outlined" class="pa-5 stack">
      <div class="arrows" role="group" aria-label="What to register">
        <v-btn :icon="mdiChevronLeft" variant="text" aria-label="Previous form" @click="step(-1)" />
        <h2 class="t-h3 arrow-title">{{ form === 'Site' ? 'Register a site' : form === 'Location' ? 'Create a location' : 'Add shelves' }}</h2>
        <v-btn :icon="mdiChevronRight" variant="text" aria-label="Next form" @click="step(1)" />
      </div>

      <form v-if="form === 'Site'" class="form" @submit.prevent="createSite">
        <v-text-field v-model="site.name" label="Site name" :error-messages="errors.name" />
        <v-autocomplete v-model="site.country" label="Country" :items="countries()" :error-messages="errors.country" />
        <v-text-field v-model="site.address" label="Address (optional)" />
        <v-text-field v-model="site.description" label="Description (optional)" />
        <div class="row-end"><v-btn type="submit" color="primary" :loading="busy" :disabled="!site.name.trim()">Register site</v-btn></div>
      </form>

      <form v-else-if="form === 'Location'" class="form" @submit.prevent="createLocation">
        <v-select v-model="loc.site" label="Site" :items="siteItems" no-data-text="Register a site first" />
        <v-text-field v-model="loc.name" label="Location name (store room, bay…)" :error-messages="errors.name" />
        <v-text-field v-model="loc.description" label="Description (optional)" />
        <div class="row-end"><v-btn type="submit" color="primary" :loading="busy" :disabled="!loc.site || !loc.name.trim()">Create location</v-btn></div>
      </form>

      <form v-else class="form" @submit.prevent="addShelves">
        <v-select v-model="shelves.site" label="Site" :items="siteItems" @update:model-value="pickSiteForShelves" />
        <v-select v-model="shelves.location" label="Location" :items="locationItems" :disabled="!shelves.site" no-data-text="Create a location first" />
        <v-text-field v-model.number="shelves.count" type="number" min="1" max="200" label="How many shelves" hint="Numbers continue after the existing shelves" persistent-hint />
        <div class="row-end">
          <v-btn type="submit" color="primary" :loading="busy" :disabled="!shelves.location || shelves.count < 1 || shelves.count > 200">Add shelves</v-btn>
        </div>
      </form>
    </v-card>

    <section class="stack-sm">
      <h2 class="t-h3">Sites</h2>
      <p v-if="!sites.length" class="t-body muted">No sites yet. Register one above.</p>
      <v-expansion-panels v-else v-model="opened" variant="accordion" multiple>
        <v-expansion-panel v-for="s in sites" :key="s.barcode" :value="s.barcode">
          <v-expansion-panel-title>
            <span class="t-label">{{ s.name }}</span>
            <span class="t-caption muted ml-3">{{ s.country }}<template v-if="s.address"> · {{ s.address }}</template></span>
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-progress-linear v-if="!locations[s.barcode]" indeterminate />
            <p v-else-if="!locations[s.barcode].length" class="t-body muted">No locations yet.</p>
            <div v-for="l in locations[s.barcode] ?? []" :key="l.barcode" class="loc">
              <div class="row">
                <span class="t-label">{{ l.name }}</span>
                <span class="t-caption muted">{{ l.shelfCount }} shelves</span>
                <span class="spacer" />
                <v-btn v-if="l.shelves?.length" size="small" variant="text" :prepend-icon="mdiPrinterOutline" @click="print(l.shelves, `${s.name} · ${l.name}`)">
                  Shelf QR codes
                </v-btn>
              </div>
              <div class="row">
                <v-chip v-for="sh in l.shelves ?? []" :key="sh.barcode" size="small" label @click="emit('shelf', sh.barcode)">Shelf {{ sh.number }}</v-chip>
              </div>
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </section>

    <v-dialog :model-value="!!printing" max-width="900" scrollable @update:model-value="(v: boolean) => !v && (printing = null)">
      <v-card v-if="printing">
        <v-card-title class="t-h3">{{ printing.title }}</v-card-title>
        <v-card-text><LabelSheet :items="printing.items" :heading="printing.title" /></v-card-text>
        <v-card-actions class="row-end"><v-btn variant="text" @click="printing = null">Close</v-btn></v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.arrows {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
}
.arrow-title {
  min-width: 14ch;
  text-align: center;
}
.form {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  max-width: 560px;
  margin: 0 auto;
  width: 100%;
}
.loc {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-3) 0;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.loc:last-child {
  border-bottom: 0;
}
</style>
