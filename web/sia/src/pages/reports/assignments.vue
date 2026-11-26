<script setup lang="ts">
/**
 * A-14 who has what (Graphite Console): units issued to people, one panel per person (most units first), each
 * unit a row with its own Return. Filter by one person. Return asks first: one stray click must not take a
 * unit off someone's name. Every row keeps Return on screen at 360 px (the row wraps, the button stays).
 */
import { type AccountSummary, call, inventory, newScanKey, scan, scanError, type Unit, useAccountNames, useCursorList, useNotify } from '@cimh/web-app'
import { formatDateTime } from '@cimh/web-ui'
import { mdiAccountArrowLeftOutline } from '@mdi/js'
import { computed, onMounted, ref, watch } from 'vue'
import PersonPicker from '../../components/PersonPicker.vue'
import { shortUnit } from '../../history'

definePage({ meta: { guard: 'staff', title: 'Who has what' } })
const notify = useNotify()
const { name } = useAccountNames()
const person = ref<AccountSummary | null>(null)
const returning = ref<string | null>(null)
const asking = ref<Unit | null>(null)

const list = useCursorList<Unit>((cursor) =>
  call(() => inventory.GET('/assignments', { params: { query: { accountId: person.value?.id, cursor, limit: 100 } } })),
)
onMounted(list.reload)
watch(person, () => void list.reload())

/** People with their units, most units first, then by name. */
const groups = computed(() => {
  const by = new Map<string, Unit[]>()
  for (const u of list.items.value) {
    const k = u.assignedTo ?? ''
    by.set(k, [...(by.get(k) ?? []), u])
  }
  return [...by.entries()]
    .map(([id, units]) => ({ id, who: name(id), units }))
    .sort((a, b) => b.units.length - a.units.length || a.who.localeCompare(b.who))
})

async function giveBack(u: Unit) {
  if (returning.value) return
  returning.value = u.barcode
  try {
    await scan('/unassign', { unit: u.barcode }, newScanKey())
    list.items.value = list.items.value.filter((x) => x.barcode !== u.barcode)
    notify.toast(`${u.productName ?? u.barcode} returned. Stow it on a shelf.`, 'success')
  } catch (e) {
    notify.toast(scanError(e), 'error')
  } finally {
    returning.value = null
    asking.value = null
  }
}
</script>

<template>
  <div class="page stack">
    <div class="strip">
      <PersonPicker v-model="person" class="finder" label="Person" placeholder="Everyone" persistent-placeholder clearable hide-details />
      <span v-if="list.loaded.value" class="console-mono t-caption muted">
        {{ list.items.value.length }}{{ list.nextCursor.value ? '+' : '' }} {{ list.items.value.length === 1 ? 'unit' : 'units' }}
        · {{ groups.length }} {{ groups.length === 1 ? 'person' : 'people' }}
      </span>
    </div>

    <v-skeleton-loader v-if="!list.loaded.value && list.loading.value" type="table-row@4" />
    <div v-else-if="list.loaded.value && !list.items.value.length" class="panel empty">
      <h2 class="t-h3">Nothing is out</h2>
      <p class="t-body muted">
        No units are issued{{ person ? ` to ${person.firstname} ${person.lastname}` : '' }}. Units are issued under
        <router-link :to="{ path: '/pick', query: { op: 'issue' } }">Pick → Issue / Return</router-link>.
      </p>
    </div>

    <TransitionGroup v-else tag="div" name="grp" class="groups">
      <section v-for="g in groups" :key="g.id" class="panel" :aria-labelledby="`p-${g.id}`">
        <header class="console-head">
          <h2 :id="`p-${g.id}`" class="person">{{ g.who }}</h2>
          <span class="console-mono t-caption muted">{{ g.units.length }} {{ g.units.length === 1 ? 'unit' : 'units' }}</span>
        </header>
        <TransitionGroup tag="ul" name="row" class="rows" role="list">
          <li v-for="u in g.units" :key="u.barcode" class="row">
            <div class="what">
              <router-link class="nm" :to="`/products/${u.product}`">{{ u.productName ?? u.product }}</router-link>
              <span class="meta t-caption muted">
                <span class="console-mono" :title="u.barcode">{{ shortUnit(u.barcode) }}</span>
                <template v-if="u.serial"> · serial <span class="console-mono">{{ u.serial }}</span></template>
                <template v-if="u.stowDate"> · last on a shelf {{ formatDateTime(u.stowDate) }}</template>
              </span>
            </div>
            <v-btn class="m3 ret" variant="outlined" :prepend-icon="mdiAccountArrowLeftOutline" :loading="returning === u.barcode" @click="asking = u">
              Return
            </v-btn>
          </li>
        </TransitionGroup>
      </section>
    </TransitionGroup>
    <v-btn v-if="list.nextCursor.value" class="m3 more" variant="text" :loading="list.loading.value" @click="list.loadMore">Load more</v-btn>

    <v-dialog :model-value="!!asking" max-width="480" :persistent="!!returning" @update:model-value="(v: boolean) => !v && (asking = null)">
      <v-card v-if="asking">
        <v-card-title class="t-h3">Return this unit?</v-card-title>
        <v-card-subtitle><span class="t-mono" :title="asking.barcode">{{ shortUnit(asking.barcode) }}</span></v-card-subtitle>
        <v-divider />
        <v-card-text>
          <p class="t-body">
            <strong>{{ asking.productName ?? asking.product }}</strong> comes off {{ name(asking.assignedTo) }}'s name. Do this when the unit
            is back in your hands; it then has to be stowed on a shelf.
          </p>
        </v-card-text>
        <v-card-actions class="row-end">
          <v-btn class="m3" variant="text" :disabled="!!returning" @click="asking = null">Keep issued</v-btn>
          <v-btn class="m3" color="primary" variant="flat" :loading="!!returning" @click="giveBack(asking)">Return unit</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
/* A person, not a place: their name in title style (was the uppercase panel eyebrow). */
.person {
  margin: 0;
  font-size: 16px;
  line-height: 22px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-3) var(--sp-4);
}
.finder {
  flex: 0 1 420px;
  min-width: 0;
}
/* Graphite Console panel: 1 px seam, 4 px corners. */
.panel {
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
}
.empty {
  padding: var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.groups {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.rows {
  list-style: none;
  margin: 0;
  padding: 0;
}
.row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4);
  border-top: 1px solid rgb(var(--v-theme-seam));
}
.what {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.nm {
  font-weight: 600;
}
.meta {
  overflow-wrap: anywhere;
}
.ret {
  flex: none;
}
.more {
  align-self: center;
}
/* Phones: Return drops under the text, full row width stays tappable. */
@media (max-width: 599px) {
  .row {
    flex-wrap: wrap;
  }
  .ret {
    margin-left: auto;
  }
}
/* A returned unit leaves its row; a person with nothing left leaves the list (reduced motion: instant). */
.row-leave-active,
.grp-leave-active {
  transition: opacity 160ms ease-in;
}
.row-leave-to,
.grp-leave-to {
  opacity: 0;
}
.row-move,
.grp-move {
  transition: transform 240ms var(--ease-out);
}
</style>
