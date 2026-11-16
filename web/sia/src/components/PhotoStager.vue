<script setup lang="ts">
/**
 * A-06 Photos section: photos chosen before the product exists. They stay in the browser (previews only)
 * until "Create product"; the page then uploads them, the primary one first. Same limits as the Images tab:
 * JPEG, PNG or WebP, up to 20 MB each, 10 per upload.
 */
import { useNotify } from '@cimh/web-app'
import { mdiArrowLeft, mdiArrowRight, mdiDeleteOutline, mdiImagePlusOutline, mdiStar, mdiStarOutline } from '@mdi/js'
import { ref } from 'vue'

export interface StagedPhoto {
  id: string
  file: File
  url: string
}
const photos = defineModel<StagedPhoto[]>({ default: () => [] })
const removeBackground = defineModel<boolean>('removeBackground', { default: false })
const notify = useNotify()

const MAX_BYTES = 20 * 1024 * 1024
const MAX_COUNT = 10
const ACCEPT = ['image/jpeg', 'image/png', 'image/webp']
const picker = ref<HTMLInputElement | null>(null)
const over = ref(false)

/** Previews are data URLs: the CSP allows img-src data: but not blob:. */
const preview = (f: File) =>
  new Promise<string>((ok, fail) => {
    const r = new FileReader()
    r.onload = () => ok(String(r.result))
    r.onerror = () => fail(r.error)
    r.readAsDataURL(f)
  })

async function add(files: FileList | File[] | null) {
  const list = Array.from(files ?? [])
  const next = [...photos.value]
  for (const f of list) {
    if (!ACCEPT.includes(f.type)) {
      notify.toast(`${f.name}: only JPEG, PNG or WebP photos`, 'error')
      continue
    }
    if (f.size > MAX_BYTES) {
      notify.toast(`${f.name} is larger than 20 MB`, 'error')
      continue
    }
    if (next.length >= MAX_COUNT) {
      notify.toast(`Up to ${MAX_COUNT} photos here; add more on the product's Images tab afterwards`, 'warning')
      break
    }
    try {
      next.push({ id: `${Date.now()}-${Math.random().toString(16).slice(2)}`, file: f, url: await preview(f) })
    } catch {
      notify.toast(`${f.name} could not be read`, 'error')
    }
  }
  photos.value = next
  if (picker.value) picker.value.value = ''
}
function remove(id: string) {
  photos.value = photos.value.filter((x) => x.id !== id)
}
/** The first photo is the primary one. */
function makePrimary(id: string) {
  const p = photos.value.find((x) => x.id === id)
  if (p) photos.value = [p, ...photos.value.filter((x) => x.id !== id)]
}
function move(id: string, d: -1 | 1) {
  const i = photos.value.findIndex((x) => x.id === id)
  const j = i + d
  if (i < 0 || j < 0 || j >= photos.value.length) return
  const next = [...photos.value]
  ;[next[i], next[j]] = [next[j]!, next[i]!]
  photos.value = next
}
function drop(e: DragEvent) {
  over.value = false
  void add(e.dataTransfer?.files ?? null)
}
const size = (b: number) => (b > 1024 * 1024 ? `${(b / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`)
</script>

<template>
  <div class="stager">
    <div
      class="drop"
      :class="{ over }"
      @dragover.prevent="over = true"
      @dragleave="over = false"
      @drop.prevent="drop"
    >
      <v-icon :icon="mdiImagePlusOutline" size="28" class="muted" />
      <div class="drop-text">
        <span class="t-label">Drop photos here, or</span>
        <span class="t-caption muted">JPEG, PNG or WebP, up to 20 MB each, {{ MAX_COUNT }} at most. Real photos on a plain background work best.</span>
      </div>
      <v-btn class="m3" variant="outlined" :prepend-icon="mdiImagePlusOutline" @click="picker?.click()">Choose photos</v-btn>
      <input ref="picker" type="file" :accept="ACCEPT.join(',')" multiple hidden aria-label="Photos to add" @change="void add(($event.target as HTMLInputElement).files)" />
    </div>
    <v-checkbox v-model="removeBackground" label="Remove the background (where the photo service supports it)" hide-details density="compact" />

    <p v-if="!photos.length" class="t-caption muted">No photos yet. You can also add them later on the product's Images tab.</p>
    <TransitionGroup v-else tag="ul" name="tile" class="grid" aria-label="Photos to upload">
      <li v-for="(p, i) in photos" :key="p.id" class="tile" :class="{ primary: i === 0 }">
        <img :src="p.url" :alt="`Photo ${i + 1}: ${p.file.name}`" />
        <div class="meta">
          <span class="t-caption name" :title="p.file.name">{{ p.file.name }}</span>
          <span class="t-caption muted console-mono">{{ size(p.file.size) }}</span>
        </div>
        <div class="bar">
          <span v-if="i === 0" class="prim"><v-icon :icon="mdiStar" size="16" />Primary</span>
          <v-btn v-else size="small" variant="text" :prepend-icon="mdiStarOutline" @click="makePrimary(p.id)">Make primary</v-btn>
          <span class="spacer" />
          <v-btn size="small" variant="text" :icon="mdiArrowLeft" :disabled="i === 0" :aria-label="`Move photo ${i + 1} earlier`" @click="move(p.id, -1)" />
          <v-btn size="small" variant="text" :icon="mdiArrowRight" :disabled="i === photos.length - 1" :aria-label="`Move photo ${i + 1} later`" @click="move(p.id, 1)" />
          <v-btn size="small" variant="text" :icon="mdiDeleteOutline" :aria-label="`Remove photo ${i + 1}`" @click="remove(p.id)" />
        </div>
      </li>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.stager {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding: var(--sp-4);
}
.drop {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-4);
  border: 1px dashed rgb(var(--v-theme-seam));
  border-radius: 4px;
  transition: border-color 150ms, background-color 150ms;
}
.drop.over {
  border-color: rgb(var(--v-theme-primary));
  background: rgb(var(--v-theme-primary-subtle));
}
.drop-text {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 200px;
}
.grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(232px, 1fr));
  gap: var(--sp-3);
}
.tile {
  display: flex;
  flex-direction: column;
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  overflow: hidden;
  background: rgb(var(--v-theme-background));
}
.tile.primary {
  border-color: rgb(var(--v-theme-primary));
}
.tile img {
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: contain;
  background: rgb(var(--v-theme-surface-variant));
}
.meta {
  display: flex;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3) 0;
}
.name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bar {
  display: flex;
  align-items: center;
  padding: var(--sp-1) var(--sp-1) var(--sp-1) var(--sp-3);
}
.prim {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 500;
  color: rgb(var(--v-theme-primary));
}
.spacer {
  flex: 1;
}
.tile-enter-active {
  transition: opacity 220ms var(--ease-out), transform 220ms var(--ease-out);
}
.tile-leave-active {
  transition: opacity 140ms ease-in, transform 140ms ease-in;
  position: absolute;
}
.tile-enter-from,
.tile-leave-to {
  opacity: 0;
  transform: scale(0.96);
}
.tile-move {
  transition: transform 280ms var(--ease-out);
}
@media (prefers-reduced-motion: reduce) {
  .tile-enter-active,
  .tile-leave-active,
  .tile-move {
    transition: opacity 120ms;
    transform: none;
  }
}
</style>
