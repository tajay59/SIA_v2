<script setup lang="ts">
/**
 * A-22 picture / background (owner 2026-11-26): pick one image → uploaded at once → media-worker prepares it
 * ("Preparing…", the chosen file shown meanwhile) → the prepared image with Replace and Remove. A failure says why
 * and offers another file. `busy` is true while an upload is not READY, so the editor can refuse to save.
 */
import { type AnnouncementImage, ApiError, uploadAnnouncementImage, waitForAnnouncementImage } from '@cimh/web-app'
import { mdiImagePlus } from '@mdi/js'
import { computed, ref } from 'vue'

const model = defineModel<AnnouncementImage | null>({ default: null })
const busy = defineModel<boolean>('busy', { default: false })
const props = defineProps<{ label: string; name: string; hint: string; wide?: boolean }>()

const MAX_BYTES = 20 * 1024 * 1024
const picker = ref<HTMLInputElement | null>(null)
const local = ref<string | null>(null) // data URL of the chosen file while it is prepared (CSP blocks blob:)
const error = ref('')
let seq = 0

const thumb = computed(() => (busy.value ? local.value : model.value ? model.value.url.replace(/\.webp$/, '@320.webp') : null))
const rules = [() => !busy.value || `Wait until the ${props.label.toLowerCase()} is ready`, () => !error.value || error.value]

function choose() {
  picker.value?.click()
}
function readLocal(file: File) {
  const r = new FileReader()
  r.onload = () => (local.value = typeof r.result === 'string' ? r.result : null)
  r.readAsDataURL(file)
}
async function picked(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  error.value = ''
  if (!/^image\/(jpeg|png|webp)$/.test(file.type)) return void (error.value = 'Use a JPEG, PNG or WebP image')
  if (file.size > MAX_BYTES) return void (error.value = 'The image is larger than 20 MB')
  const mine = ++seq
  busy.value = true
  readLocal(file)
  try {
    const up = await uploadAnnouncementImage(file)
    const done = await waitForAnnouncementImage(up.fileId)
    if (mine !== seq) return
    if (done.status === 'READY' && done.url) model.value = { fileId: done.fileId, url: done.url, w: done.w, h: done.h }
    else error.value = done.error ?? 'That image couldn’t be used'
  } catch (err) {
    if (mine !== seq) return
    error.value =
      err instanceof ApiError && err.status === 413
        ? 'The image is larger than 20 MB'
        : err instanceof ApiError && err.status === 422
          ? 'Use a JPEG, PNG or WebP image'
          : 'The upload failed. Check the connection and try again.'
  } finally {
    if (mine === seq) {
      busy.value = false
      local.value = null
    }
  }
}
function remove() {
  seq++
  busy.value = false
  local.value = null
  error.value = ''
  model.value = null
}
</script>

<template>
  <v-input :model-value="model?.fileId ?? ''" :rules="rules" :name="name" hide-details="auto" class="aif-input">
    <div :id="name" class="aif" :class="{ wide }">
      <input ref="picker" type="file" accept="image/jpeg,image/png,image/webp" class="aif-file" tabindex="-1" aria-hidden="true" @change="picked" />
      <div v-if="thumb" class="aif-thumb" :class="{ busy }">
        <img :src="thumb" alt="" />
        <span v-if="busy" class="aif-state" role="status"><v-progress-circular indeterminate size="18" width="2" /> Preparing…</span>
      </div>
      <div class="aif-side">
        <div class="aif-actions">
          <v-btn v-if="!model && !busy" class="m3" variant="tonal" size="small" :prepend-icon="mdiImagePlus" @click="choose">
            Add {{ label.toLowerCase() }}…
          </v-btn>
          <template v-else>
            <v-btn class="m3" variant="tonal" size="small" :disabled="busy" @click="choose">Replace…</v-btn>
            <v-btn class="m3" variant="text" size="small" @click="remove">{{ busy ? 'Cancel' : 'Remove' }}</v-btn>
          </template>
        </div>
        <p class="aif-hint">{{ hint }}</p>
      </div>
    </div>
  </v-input>
</template>

<style scoped>
.aif-input :deep(.v-input__control) {
  min-width: 0;
}
/* Half a form column: the image on top, its buttons and hint under it. */
.aif {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  min-width: 0;
}
.aif-file {
  display: none;
}
.aif-thumb {
  position: relative;
  height: 112px;
  border-radius: 8px;
  overflow: hidden;
  background: rgb(var(--v-theme-surface-variant));
  box-shadow: 0 0 0 1px rgb(var(--v-theme-field-outline));
}
.aif-thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
/* A background is seen cropped across the row: show it that way. */
.aif.wide .aif-thumb img {
  object-fit: cover;
}
.aif-thumb.busy img {
  opacity: 0.45;
}
.aif-state {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
}
.aif-side {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.aif-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.aif-hint {
  margin: 0;
  font-size: 12px;
  line-height: 16px;
  color: rgb(var(--v-theme-secondary));
}
</style>
