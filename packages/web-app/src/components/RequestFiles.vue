<script setup lang="ts">
/**
 * "Files" of a request: one chip per document, opened from document-svc. Documents CIMH generates are named by
 * what they are ("CIMH quote · PDF"; their file names only repeat the request id); uploads keep their own name.
 * `bare` = no card of its own (SIA puts it inside a console panel that already says "Files").
 */
import { mdiFilePdfBox, mdiFileOutline } from '@mdi/js'
import { VCard, VCardText } from 'vuetify/components'
import { FILE_KIND_LABELS, fileUrl, type FileRef } from '../orders'

withDefaults(defineProps<{ files: FileRef[]; bare?: boolean }>(), { bare: false })

const GENERATED = new Set<FileRef['kind']>(['cimh_quote', 'agreement', 'invoice', 'commercial_invoice', 'probono_invoice'])
const fileType = (f: FileRef) => (f.mime === 'application/pdf' ? 'PDF' : (f.mime.split('/')[1] ?? 'file').toUpperCase())
const label = (f: FileRef) =>
  GENERATED.has(f.kind) ? `${FILE_KIND_LABELS[f.kind]} · ${fileType(f)}` : `${FILE_KIND_LABELS[f.kind]} · ${f.name}`
</script>

<template>
  <component :is="bare ? 'div' : VCard" v-bind="bare ? {} : { subtitle: 'Files', flat: true, border: true }">
    <component :is="bare ? 'div' : VCardText">
      <v-chip-group v-if="files.length" column>
        <v-chip
          v-for="f in files"
          :key="f.id"
          :href="fileUrl(f.id)"
          target="_blank"
          rel="noopener"
          :prepend-icon="f.mime === 'application/pdf' ? mdiFilePdfBox : mdiFileOutline"
          label
          class="file"
          :title="f.name"
        >
          <span class="file-name">{{ label(f) }}</span>
        </v-chip>
      </v-chip-group>
      <p v-else class="t-caption muted">No files yet.</p>
    </component>
  </component>
</template>

<style scoped>
/* Long upload names (phone photos, scanner output) ran past the card; cut them with the full name on hover. */
.file {
  max-width: 100%;
}
.file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
