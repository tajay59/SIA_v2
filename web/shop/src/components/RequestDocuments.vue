<script setup lang="ts">
/**
 * A document pane that fills its column (owner, 2026-11-18): View and sign task 1 (S-12), the quote files beside
 * (or inside) "Check the quote". A tab per file (only when there is more than one) in the shared DocumentViewer's
 * head, one file always open (`selected`, v-model; the first when unset); Download saves the file without leaving
 * the page. `label` names the region, `emptyTitle` / `emptyText` say why there is nothing yet. `labels` (file id → tab
 * text, e.g. the supplier's name) keeps tabs short; the file name is the tab's tooltip. With tabs, the head gives them
 * its first row and puts the page count, zoom and Download on a second.
 */
import { DocumentViewer, FILE_KIND_LABELS, type FileRef } from '@cimh/web-app'
import { mdiFileDocumentOutline } from '@mdi/js'
import { computed } from 'vue'
import { docLabel } from '../request-docs'

const props = withDefaults(defineProps<{ files: FileRef[]; labels?: Record<string, string>; loading?: boolean; label?: string; emptyTitle?: string; emptyText?: string }>(), {
  label: 'Documents',
  emptyTitle: 'No documents yet',
  emptyText: '',
})
const selected = defineModel<string | null>('selected', { default: null })
const shown = computed(() => props.files.find((f) => f.id === selected.value) ?? props.files[0] ?? null)
const GENERATED = new Set<FileRef['kind']>(['cimh_quote', 'agreement', 'invoice', 'commercial_invoice', 'probono_invoice'])
const tab = (f: FileRef) => props.labels?.[f.id] ?? docLabel(f, props.files)
const title = (f: FileRef) => (GENERATED.has(f.kind) ? docLabel(f, props.files) : `${FILE_KIND_LABELS[f.kind]} · ${f.name}`)
</script>

<template>
  <section class="docs" :aria-label="label">
    <!-- Not keyed by file: switching tabs reopens the viewer without remounting the tabs (focus stays on them). -->
    <DocumentViewer v-if="shown" :file-id="shown.id" :name="title(shown)" :mime="shown.mime" what="Preview of" link="download" class="docs-viewer" :class="{ tabbed: files.length > 1 }">
      <!-- Several files: the tabs are the document's head (one head per document, no repeated name). -->
      <template v-if="files.length > 1" #title>
        <v-tabs
          :model-value="shown.id"
          show-arrows
          density="compact"
          color="primary"
          class="docs-tabs"
          :aria-label="`${label} of this request`"
          @update:model-value="(v: unknown) => (selected = String(v))"
        >
          <v-tab v-for="f in files" :key="f.id" :value="f.id" :title="f.name" class="docs-tab">{{ tab(f) }}</v-tab>
        </v-tabs>
      </template>
    </DocumentViewer>
    <div v-else-if="loading" class="docs-empty docs-skel" aria-busy="true" />
    <div v-else class="docs-empty">
      <v-icon :icon="mdiFileDocumentOutline" size="40" />
      <p class="docs-empty-title">{{ emptyTitle }}</p>
      <p v-if="emptyText" class="docs-empty-text">{{ emptyText }}</p>
    </div>
  </section>
</template>

<style scoped>
.docs {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  height: 100%;
  min-height: 0;
}
.docs-tabs {
  min-width: 0;
  flex: 1;
  margin-left: calc(-1 * var(--sp-3));
}
.docs-tab {
  text-transform: none;
  letter-spacing: 0;
  max-width: 260px;
}
.docs-tab :deep(.v-btn__content) {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* Tabs own the head's first row (the open file's name is never cut by the controls). */
.docs-viewer.tabbed {
  --doc-title-basis: 100%;
}
/* The viewer takes what is left of the column; its pages scroll inside it. */
.docs-viewer {
  --doc-height: auto;
  flex: 1 1 0;
}
.docs-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
  padding: var(--sp-8);
  border: 1px dashed rgba(var(--v-border-color), 0.35);
  border-radius: 8px;
  background: rgb(var(--v-theme-surface-variant));
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  text-align: center;
}
.docs-empty p {
  margin: 0;
}
.docs-empty-title {
  font-size: 17px;
  line-height: 24px;
  font-weight: 700;
  color: rgb(var(--v-theme-on-surface));
}
.docs-empty-text {
  max-width: 40ch;
  font-size: 14px;
  line-height: 20px;
  text-wrap: pretty;
}
.docs-skel {
  border-style: solid;
  background: linear-gradient(100deg, rgba(var(--v-theme-on-surface), 0.04) 30%, rgba(var(--v-theme-on-surface), 0.09) 50%, rgba(var(--v-theme-on-surface), 0.04) 70%)
    0 0 / 200% 100%;
  animation: docs-shimmer 1.4s linear infinite;
}
@keyframes docs-shimmer {
  to {
    background-position: -200% 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .docs-skel {
    animation: none;
  }
}
</style>
