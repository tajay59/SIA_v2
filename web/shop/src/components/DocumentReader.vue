<script setup lang="ts">
/**
 * A request document read full size, in a dialog (SHOP S-11 Papers, S-12 phone rows): full screen below 760 px,
 * otherwise a large centred sheet (up to 1040 px wide, 92 % of the window tall). The document's one head holds Close,
 * its name, the page in view, zoom and Download; under 600 px it opens at 200 % (a page fitted to a phone reads at
 * ~4 px). The default slot is the opener (the dialog's activator, so closing returns focus to it); it receives the
 * activator props to bind.
 */
import { DocumentViewer } from '@cimh/web-app'
import { mdiClose } from '@mdi/js'
import { useDisplay } from 'vuetify'
import { computed } from 'vue'

defineProps<{ fileId: string; mime: string; name: string }>()
const { width } = useDisplay()
const full = computed(() => width.value < 760)
const startZoom = computed(() => (width.value < 600 ? 2 : 1))
</script>

<template>
  <v-dialog :fullscreen="full" :width="full ? undefined : 'min(1040px, 94vw)'" transition="dialog-bottom-transition" :aria-label="name">
    <template #activator="{ props: a }">
      <slot :props="a" />
    </template>
    <template #default="{ isActive }">
      <div class="reader" :class="{ full }">
        <DocumentViewer :file-id="fileId" :name="name" :mime="mime" what="Reading" link="download" :start-zoom="startZoom" class="reader-doc">
          <template #title>
            <v-btn variant="text" :icon="mdiClose" size="small" aria-label="Close" class="reader-close" @click="isActive.value = false" />
            <span class="reader-name">{{ name }}</span>
          </template>
        </DocumentViewer>
      </div>
    </template>
  </v-dialog>
</template>

<style scoped>
.reader {
  height: 92vh;
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  overflow: hidden;
  background: rgb(var(--v-theme-surface));
}
.reader.full {
  height: 100%;
  border-radius: 0;
  padding-bottom: env(safe-area-inset-bottom);
}
.reader-doc {
  --doc-height: 100%;
  --doc-radius: 0;
  --doc-edge: transparent;
  --doc-page-max: 860px;
  --doc-ground: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 10%, rgb(var(--v-theme-surface)));
  flex: 1;
  min-height: 0;
}
.reader-close {
  flex: none;
  margin-left: calc(-1 * var(--sp-2));
}
.reader-name {
  min-width: 0;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
