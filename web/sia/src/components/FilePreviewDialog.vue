<script setup lang="ts">
/**
 * A request file read in place (signed agreement, proof of payment): the shared `DocumentViewer` in a
 * `v-dialog`, so staff never leave SIA for another tab. Download keeps a copy. Full screen on phones.
 */
import { DocumentViewer, type OrderRequest } from '@cimh/web-app'
import { mdiClose } from '@mdi/js'
import { computed, watch } from 'vue'
import { useDisplay } from 'vuetify'

const props = defineProps<{ request: OrderRequest | null; fileId: string | null; title?: string }>()
const open = defineModel<boolean>({ default: false })
const { smAndDown } = useDisplay()

const file = computed(() => (props.request?.files ?? []).find((f) => f.id === props.fileId) ?? null)
const name = computed(() => props.title ?? file.value?.name ?? 'Document')
const mime = computed(() => file.value?.mime ?? 'application/pdf')

// Opened by v-model (no activator), so Vuetify can't return focus: the button that opened it gets it back on close.
let opener: HTMLElement | null = null
watch(open, (o) => {
  if (o) opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
  else if (opener?.isConnected) {
    const el = opener
    opener = null
    setTimeout(() => el.focus(), 0)
  }
})
</script>

<template>
  <!-- One head: the viewer's (name, pages, zoom, Download) carries Close (after Download; full screen on phones at
       the start of the name row, as in a full-screen dialog, so the tools keep one row); the dialog is named after the file. -->
  <v-dialog v-model="open" :fullscreen="smAndDown" max-width="1000" scrollable :aria-label="name">
    <v-card v-if="fileId" class="preview" :class="{ full: smAndDown }">
      <DocumentViewer :key="fileId" :file-id="fileId" :name="name" :mime="mime" what="Preview of" link="download" class="console-doc">
        <template v-if="smAndDown" #title>
          <v-btn :icon="mdiClose" variant="text" size="small" aria-label="Close" class="preview-close start" @click="open = false" />
          <span class="preview-name" :title="name">{{ name }}</span>
        </template>
        <template v-else #actions>
          <v-btn :icon="mdiClose" variant="text" size="small" aria-label="Close" class="preview-close" @click="open = false" />
        </template>
      </DocumentViewer>
    </v-card>
  </v-dialog>
</template>

<style scoped>
/* The viewer is the whole dialog: its head stays put, only the document scrolls (up to the dialog's height). */
.preview {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.preview.full {
  height: 100%;
}
.console-doc {
  --doc-height: auto;
  --doc-edge: transparent;
  --doc-radius: 0;
  --doc-ground: rgb(var(--v-theme-background));
  flex: 1 1 auto;
  min-height: 0;
}
.preview-close {
  flex: none;
}
.preview-close.start {
  margin-left: calc(-1 * var(--sp-2));
}
.preview-name {
  min-width: 0;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
