<script setup lang="ts">
/**
 * "Files" of a request: one square tile per document (big type icon, what it is, file type or name), opened from
 * document-svc in a new tab. Documents CIMH generates are named by what they are ("CIMH quote", PDF; their file
 * names only repeat the request id); uploads keep their own name under the kind.
 * `bare` = no card of its own (SIA puts it inside a console panel that already says "Files").
 */
import { mdiFileImageOutline, mdiFileOutline, mdiFilePdfBox } from '@mdi/js'
import { VCard, VCardText } from 'vuetify/components'
import { FILE_KIND_LABELS, fileUrl, type FileRef } from '../orders'

withDefaults(defineProps<{ files: FileRef[]; bare?: boolean }>(), { bare: false })

const GENERATED = new Set<FileRef['kind']>(['cimh_quote', 'agreement', 'invoice', 'commercial_invoice', 'probono_invoice'])
const fileType = (f: FileRef) => (f.mime === 'application/pdf' ? 'PDF' : (f.mime.split('/')[1] ?? 'file').toUpperCase())
const detail = (f: FileRef) => (GENERATED.has(f.kind) ? fileType(f) : f.name)
const icon = (f: FileRef) =>
  f.mime === 'application/pdf' ? mdiFilePdfBox : f.mime.startsWith('image/') ? mdiFileImageOutline : mdiFileOutline
</script>

<template>
  <component :is="bare ? 'div' : VCard" v-bind="bare ? {} : { subtitle: 'Files', flat: true, border: true }">
    <component :is="bare ? 'div' : VCardText">
      <ul v-if="files.length" class="files">
        <li v-for="f in files" :key="f.id">
          <a
            :href="fileUrl(f.id)"
            target="_blank"
            rel="noopener"
            class="tile"
            :title="f.name"
            :aria-label="`${FILE_KIND_LABELS[f.kind]}, ${detail(f)} (opens in a new tab)`"
          >
            <v-icon :icon="icon(f)" size="64" class="tile-icon" />
            <span class="tile-kind">{{ FILE_KIND_LABELS[f.kind] }}</span>
            <span class="tile-detail">{{ detail(f) }}</span>
          </a>
        </li>
      </ul>
      <p v-else class="t-caption muted">No files yet.</p>
    </component>
  </component>
</template>

<style scoped>
.files {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
}
.tile {
  aspect-ratio: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgb(var(--v-theme-surface-variant));
  color: rgb(var(--v-theme-on-surface-variant));
  text-decoration: none;
  text-align: center;
  transition:
    border-color 150ms ease,
    transform 150ms ease;
}
.tile:hover {
  border-color: rgb(var(--v-theme-primary));
}
.tile:active {
  transform: scale(0.98);
}
.tile:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.tile-icon {
  color: rgb(var(--v-theme-primary));
  margin-bottom: 4px;
}
.tile-kind {
  font-weight: 600;
  font-size: 0.875rem;
  line-height: 1.25;
  color: rgb(var(--v-theme-on-surface));
}
/* Long upload names (phone photos, scanner output) are cut; the full name shows on hover. */
.tile-detail {
  max-width: 100%;
  font-size: 0.75rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
@media (prefers-reduced-motion: reduce) {
  .tile {
    transition: none;
  }
}
</style>
