<script setup lang="ts">
/** "Files" card of a request (legacy order page): one chip per document, opened from document-svc. */
import { mdiFilePdfBox, mdiFileOutline } from '@mdi/js'
import { FILE_KIND_LABELS, fileUrl, type FileRef } from '../orders'

defineProps<{ files: FileRef[] }>()
</script>

<template>
  <v-card subtitle="Files" flat border>
    <v-card-text>
      <v-chip-group v-if="files.length" column>
        <v-chip
          v-for="f in files"
          :key="f.id"
          :href="fileUrl(f.id)"
          target="_blank"
          rel="noopener"
          :prepend-icon="f.mime === 'application/pdf' ? mdiFilePdfBox : mdiFileOutline"
          label
        >
          {{ FILE_KIND_LABELS[f.kind] }} · {{ f.name }}
        </v-chip>
      </v-chip-group>
      <p v-else class="t-caption muted">No files yet.</p>
    </v-card-text>
  </v-card>
</template>
