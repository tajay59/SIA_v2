<script setup lang="ts">
/**
 * A supplier's quote file beside the price lines (A-04), or the agreement preview (`src`) in the review dialog:
 * the shared `DocumentViewer` (pdf.js on canvases, one paint at a time) on Graphite Console seams. Download in the
 * header saves a copy (owner 2026-11-23: request files never open another tab).
 */
import { DocumentViewer } from '@cimh/web-app'

withDefaults(defineProps<{ fileId?: string; src?: string; name: string; mime: string; what?: string }>(), {
  fileId: '',
  src: '',
  what: 'Quote file',
})
const emit = defineEmits<{ state: ['loading' | 'ready' | 'error'] }>()
</script>

<template>
  <DocumentViewer
    :file-id="fileId"
    :src="src"
    :name="name"
    :mime="mime"
    :what="what"
    link="download"
    class="console-doc"
    @state="(v: 'loading' | 'ready' | 'error') => emit('state', v)"
  />
</template>

<style scoped>
.console-doc {
  --doc-edge: rgb(var(--v-theme-seam));
  --doc-radius: 4px;
  --doc-ground: rgb(var(--v-theme-background));
}
</style>
