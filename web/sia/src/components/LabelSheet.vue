<script setup lang="ts">
/**
 * Printable labels: a QR code and the short code under it, several per row. "Print" prints only this
 * sheet (everything else on the page is hidden by the print styles). Used for unit labels and shelf QR codes.
 */
import { mdiPrinterOutline } from '@mdi/js'
import QrCode from './QrCode.vue'

defineProps<{ items: { value: string; title: string; subtitle?: string }[]; heading?: string }>()

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
    <div class="sheet" :aria-label="heading ?? 'Labels'">
      <figure v-for="i in items" :key="i.value" class="label">
        <QrCode :value="i.value" :size="96" />
        <figcaption>
          <span class="t-mono title">{{ i.title }}</span>
          <span v-if="i.subtitle" class="t-caption">{{ i.subtitle }}</span>
        </figcaption>
      </figure>
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
}
</style>
