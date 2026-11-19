<script setup lang="ts">
/**
 * "Files" of a request: one square tile per document (big type icon, what it is, file type or name). Documents
 * CIMH generates are named by what they are ("CIMH quote", PDF; their file names only repeat the request id);
 * uploads keep their own name under the kind.
 * Opening a file: by default a new tab from document-svc (SIA). `preview` (SHOP, owner 2026-11-18: customers stay
 * on the page) keeps a pane open under the tiles instead, always showing one file: `selected` (v-model; the first
 * file when unset or gone), a tile press shows another. Download saves the file (attachment) without leaving the
 * page.
 * `bare` = no card of its own (SIA puts it inside a console panel that already says "Files").
 */
import { mdiFileImageOutline, mdiFileOutline, mdiFilePdfBox } from '@mdi/js'
import { computed, nextTick, ref, useId } from 'vue'
import { VCard, VCardText } from 'vuetify/components'
import { FILE_KIND_LABELS, fileUrl, type FileRef } from '../orders'
import DocumentViewer from './DocumentViewer.vue'

const props = withDefaults(defineProps<{ files: FileRef[]; bare?: boolean; preview?: boolean }>(), { bare: false, preview: false })
const selected = defineModel<string | null>('selected', { default: null })

const GENERATED = new Set<FileRef['kind']>(['cimh_quote', 'agreement', 'invoice', 'commercial_invoice', 'probono_invoice'])
const fileType = (f: FileRef) => (f.mime === 'application/pdf' ? 'PDF' : (f.mime.split('/')[1] ?? 'file').toUpperCase())
const detail = (f: FileRef) => (GENERATED.has(f.kind) ? fileType(f) : f.name)
const icon = (f: FileRef) =>
  f.mime === 'application/pdf' ? mdiFilePdfBox : f.mime.startsWith('image/') ? mdiFileImageOutline : mdiFileOutline
/** The pane's title: what it is, plus the name for uploads (generated names only repeat the request id). */
const title = (f: FileRef) => (GENERATED.has(f.kind) ? FILE_KIND_LABELS[f.kind] : `${FILE_KIND_LABELS[f.kind]} · ${f.name}`)

// ---- preview pane (always open while there is a file)
const paneId = useId()
const pane = ref<HTMLElement | null>(null)
// A file that leaves the list (deleted by staff) gives way to the first one.
const shown = computed(() => props.files.find((f) => f.id === selected.value) ?? props.files[0] ?? null)

async function show(f: FileRef) {
  selected.value = f.id
  await nextTick()
  // Pane below the fold (tiles at the foot of the screen, phones): bring it up; otherwise leave the page be.
  const el = pane.value
  if (el && el.getBoundingClientRect().top > window.innerHeight * 0.6) {
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    el.scrollIntoView({ block: 'start', behavior: still ? 'auto' : 'smooth' })
  }
}
</script>

<template>
  <component :is="bare ? 'div' : VCard" v-bind="bare ? {} : { subtitle: 'Files', flat: true, border: true }">
    <component :is="bare ? 'div' : VCardText">
      <div>
        <ul v-if="files.length" class="files">
          <li v-for="f in files" :key="f.id">
            <button
              v-if="preview"
              type="button"
              class="tile"
              :class="{ open: f.id === shown?.id }"
              :title="f.name"
              :aria-pressed="f.id === shown?.id"
              :aria-controls="paneId"
              :aria-label="`${FILE_KIND_LABELS[f.kind]}, ${detail(f)}`"
              @click="show(f)"
            >
              <v-icon :icon="icon(f)" size="64" class="tile-icon" />
              <span class="tile-kind">{{ FILE_KIND_LABELS[f.kind] }}</span>
              <span class="tile-detail">{{ detail(f) }}</span>
            </button>
            <a
              v-else
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

        <div v-if="preview && shown" :id="paneId" ref="pane" class="pane">
          <DocumentViewer :key="shown.id" :file-id="shown.id" :name="title(shown)" :mime="shown.mime" what="Preview of" link="download" />
        </div>
      </div>
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
  width: 100%;
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
  font: inherit;
  text-decoration: none;
  text-align: center;
  cursor: pointer;
  transition:
    border-color 150ms ease,
    box-shadow 150ms ease,
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
/* The file in the pane: a 2 px primary edge (drawn inside, so the grid doesn't shift) on a faint primary wash. */
.tile.open {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: inset 0 0 0 1px rgb(var(--v-theme-primary));
  background: linear-gradient(rgba(var(--v-theme-primary), 0.08), rgba(var(--v-theme-primary), 0.08)), rgb(var(--v-theme-surface-variant));
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
/* The pane: as tall as the document, at most a page at a time, so the page around it stays in reach. */
.pane {
  --doc-height: auto;
  --doc-max-height: clamp(360px, 75vh, 1000px);
  margin-top: 12px;
  scroll-margin-top: 80px;
  animation: pane-in 220ms cubic-bezier(0.16, 1, 0.3, 1);
}
@keyframes pane-in {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }
}
@media (prefers-reduced-motion: reduce) {
  .tile {
    transition: none;
  }
  .pane {
    animation-name: pane-fade;
  }
}
@keyframes pane-fade {
  from {
    opacity: 0;
  }
}
</style>
