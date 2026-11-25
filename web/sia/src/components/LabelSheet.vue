<script setup lang="ts">
/**
 * Printable labels, several per row. "Print" prints only this sheet (everything else on the page is hidden by the
 * print styles). Unit labels: a QR code and the short code under it. Shelf labels (items with `shelf`) follow the
 * legacy shelf label (owner, 2026-11-25): site, location and the full code top left, SHELF n top right, a large QR
 * filling the label below.
 */
import { mdiPrinterOutline } from '@mdi/js'
import { computed } from 'vue'
import QrCode from './QrCode.vue'

interface Item {
  value: string
  title: string
  subtitle?: string
  shelf?: { site?: string | null; location?: string | null; number: number }
}
const props = defineProps<{ items: Item[]; heading?: string }>()
const shelves = computed(() => props.items.some((i) => i.shelf))

function print() {
  document.body.classList.add('printing-labels')
  window.print()
  document.body.classList.remove('printing-labels')
}
</script>

<template>
  <section class="sheet-wrap">
    <div class="row no-print">
      <slot name="actions" />
      <v-btn :prepend-icon="mdiPrinterOutline" variant="outlined" @click="print">Print labels</v-btn>
    </div>
    <div class="sheet" :class="{ shelves }" :aria-label="heading ?? 'Labels'">
      <template v-for="(i, n) in items" :key="i.value">
        <figure v-if="i.shelf" class="label shelf-label" :style="{ '--i': n }">
          <figcaption class="shelf-head">
            <span class="shelf-line site">{{ i.shelf.site }}</span>
            <span class="shelf-number">Shelf {{ i.shelf.number }}</span>
            <span v-if="i.shelf.location" class="shelf-line location">{{ i.shelf.location }}</span>
            <span class="shelf-code">{{ i.value }}</span>
          </figcaption>
          <QrCode :value="i.value" :size="256" class="shelf-qr" />
        </figure>
        <figure v-else class="label" :style="{ '--i': n }">
          <QrCode :value="i.value" :size="96" />
          <figcaption>
            <span class="t-mono title">{{ i.title }}</span>
            <span v-if="i.subtitle" class="t-caption">{{ i.subtitle }}</span>
          </figcaption>
        </figure>
      </template>
    </div>
  </section>
</template>

<style scoped>
.sheet-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.sheet {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: var(--sp-3);
}
/* Shelf labels are read from across an aisle: each label up to 320 px wide (a single one does not stretch). */
.sheet.shelves {
  grid-template-columns: repeat(auto-fill, minmax(260px, 320px));
}
.label {
  margin: 0;
  padding: var(--sp-3);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-2);
  border: 1px dashed rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  background: #fff;
  color: #000;
  break-inside: avoid;
  animation: label-in 280ms var(--ease-out) both;
  animation-delay: calc(min(var(--i, 0), 12) * 24ms);
}
@keyframes label-in {
  from {
    opacity: 0;
    transform: translateY(8px) scale(0.98);
  }
}
@media (prefers-reduced-motion: reduce), print {
  .label {
    animation: none;
  }
}
.label figcaption {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}
.title {
  font-weight: 600;
}

/* Legacy shelf label: plain black on white, upper-case words, the QR as wide as the label. */
.shelf-label {
  align-items: stretch;
  gap: 4px;
  padding: 16px 16px 20px;
}
/* As on the legacy label: site beside SHELF n, location under it, the code across the whole label. */
.label figcaption.shelf-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  grid-template-areas: 'site number' 'location location' 'code code';
  column-gap: 12px;
  align-items: start;
  text-align: left;
}
.site {
  grid-area: site;
}
.location {
  grid-area: location;
}
.shelf-number {
  grid-area: number;
}
.shelf-code {
  grid-area: code;
}
.shelf-line,
.shelf-number {
  font-size: 14px;
  line-height: 18px;
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}
.shelf-line {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.shelf-number {
  flex: none;
  white-space: nowrap;
}
.shelf-code {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11px;
  line-height: 16px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.shelf-qr {
  width: 100%;
  height: auto;
  border-radius: 0;
}
</style>

<style>
/* Print only the label sheet. */
@media print {
  body.printing-labels .v-app-bar,
  body.printing-labels .no-print,
  body.printing-labels .page-title {
    display: none !important;
  }
  body.printing-labels .v-main {
    padding: 0 !important;
  }
  body.printing-labels .sheet {
    grid-template-columns: repeat(4, 1fr) !important;
  }
  body.printing-labels .sheet.shelves {
    grid-template-columns: repeat(2, 1fr) !important;
  }
}
</style>
