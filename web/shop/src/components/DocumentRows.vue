<script setup lang="ts">
/**
 * Phones (S-12 View and sign, below 760 px): a request's documents as ruled rows, each opening the full-size reader
 * (`DocumentReader`: full screen here, at 200 % under 600 px). A page drawn inline at phone width (~300 px) puts the
 * agreement's 9.5 pt text at about 4 px, so nothing is drawn inline. Closing returns focus to the row.
 * `docs`: id, mime, the row's name (`label`) and what it is (`kind`, e.g. "CIMH quote · PDF").
 */
import { mdiArrowExpand, mdiFileDocumentOutline, mdiFileImageOutline, mdiFilePdfBox } from '@mdi/js'
import DocumentReader from './DocumentReader.vue'

type DocRow = { id: string; mime: string; label: string; kind: string }
withDefaults(defineProps<{ docs: DocRow[]; label: string; emptyTitle?: string; emptyText?: string }>(), {
  emptyTitle: 'No documents yet',
  emptyText: '',
})
const icon = (mime: string) => (mime === 'application/pdf' ? mdiFilePdfBox : mime.startsWith('image/') ? mdiFileImageOutline : mdiFileDocumentOutline)
</script>

<template>
  <section class="rows" :aria-label="label">
    <ul v-if="docs.length" class="rows-list">
      <li v-for="d in docs" :key="d.id">
        <DocumentReader :file-id="d.id" :mime="d.mime" :name="d.label">
          <template #default="{ props: a }">
            <button type="button" class="row" v-bind="a" :aria-label="`Read ${d.label} full size`">
              <span class="row-icon" aria-hidden="true"><v-icon :icon="icon(d.mime)" size="24" /></span>
              <span class="row-text">
                <span class="row-name">{{ d.label }}</span>
                <span class="row-kind">{{ d.kind }}</span>
              </span>
              <span class="row-read" aria-hidden="true">Read<v-icon :icon="mdiArrowExpand" size="18" /></span>
            </button>
          </template>
        </DocumentReader>
      </li>
    </ul>
    <div v-else class="rows-empty">
      <p class="rows-empty-title">{{ emptyTitle }}</p>
      <p v-if="emptyText">{{ emptyText }}</p>
    </div>
  </section>
</template>

<style scoped>
.rows-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.rows-list > li {
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
/* The whole row reads the document: one target, at least 56 px tall. */
.row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  width: 100%;
  min-height: 56px;
  padding: var(--sp-2) var(--sp-1);
  background: none;
  border: 0;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  border-radius: 4px;
}
.row:hover .row-name {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.row:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
/* A sheet on the desk ground, as the documents lie on wide screens. */
.row-icon {
  flex: none;
  display: grid;
  place-items: center;
  width: 40px;
  height: 48px;
  border-radius: 4px;
  background: var(--doc-ground, rgb(var(--v-theme-surface-variant)));
  color: rgb(var(--v-theme-primary));
}
.row-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.row-name {
  font-weight: 600;
  overflow-wrap: anywhere;
}
.row-kind {
  font-size: 14px;
  line-height: 20px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.row-read {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
}
.rows-empty {
  padding: var(--sp-3) 0;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 14px;
  line-height: 20px;
}
.rows-empty p {
  margin: 0;
}
.rows-empty-title {
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
}
</style>
