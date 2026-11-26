<script setup lang="ts">
/**
 * A-07 Images tab (J-10): upload JPEG/PNG/WebP (optional background removal) -> "processing" tiles while
 * media-worker works -> photos appear (polling) -> make one primary, remove.
 */
import { ApiError, call, catalog, type ProductStaff, ProductImage, useNotify } from '@cimh/web-app'
import { mdiDeleteOutline, mdiImagePlusOutline, mdiStar, mdiStarOutline } from '@mdi/js'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { pinLeaving } from '../list-motion'

/** expect: total photos once uploads made elsewhere (the new-product page) finish processing. */
const props = defineProps<{ product: ProductStaff; expect?: number; level?: 2 | 3 }>()
const hs = computed(() => `h${props.level ?? 2}`)
const emit = defineEmits<{ updated: [p: ProductStaff] }>()
const notify = useNotify()

const MAX_BYTES = 20 * 1024 * 1024
const ACCEPT = ['image/jpeg', 'image/png', 'image/webp']
const removeBackground = ref(false)
const uploading = ref(false)
const processing = ref(0)
const busy = ref<string | null>(null)
const picker = ref<HTMLInputElement | null>(null)
let poll: ReturnType<typeof setTimeout> | undefined
onBeforeUnmount(() => clearTimeout(poll))
onMounted(() => {
  const left = (props.expect ?? 0) - props.product.images.length
  if (left > 0) {
    processing.value = left
    watchJobs(props.expect!, Date.now() + 90_000)
  }
})

async function refresh(): Promise<ProductStaff> {
  const p = (await call(() => catalog.GET('/products/{productId}', { params: { path: { productId: props.product.id } } }))) as ProductStaff
  emit('updated', p)
  return p
}

function watchJobs(expected: number, until: number) {
  clearTimeout(poll)
  poll = setTimeout(async () => {
    try {
      const p = await refresh()
      const left = expected - p.images.length
      processing.value = Math.max(0, left)
      if (left > 0 && Date.now() < until) watchJobs(expected, until)
      else if (left > 0) notify.toast('Some photos are still processing or could not be used. Refresh later to check.', 'warning')
    } catch {
      if (Date.now() < until) watchJobs(expected, until)
    }
  }, 2000)
}

async function upload(files: FileList | null) {
  const list = Array.from(files ?? [])
  if (!list.length) return
  const bad = list.find((f) => !ACCEPT.includes(f.type))
  if (bad) return notify.toast(`${bad.name}: only JPEG, PNG or WebP photos`, 'error')
  const big = list.find((f) => f.size > MAX_BYTES)
  if (big) return notify.toast(`${big.name} is larger than 20 MB`, 'error')
  if (list.length > 10) return notify.toast('Up to 10 photos at a time', 'error')
  const form = new FormData()
  for (const f of list) form.append('files', f)
  form.append('removeBackground', String(removeBackground.value))
  uploading.value = true
  try {
    const res = await call(() =>
      catalog.POST('/products/{productId}/images', {
        params: { path: { productId: props.product.id } },
        body: form as never,
        bodySerializer: (b: unknown) => b as FormData,
      }),
    )
    processing.value = res.jobIds.length
    watchJobs(props.product.images.length + res.jobIds.length, Date.now() + 90_000)
  } catch (e) {
    if (e instanceof ApiError && e.status === 413) notify.toast('The upload is too large. Send fewer or smaller photos at a time.', 'error')
    else notify.report(e)
  } finally {
    uploading.value = false
    if (picker.value) picker.value.value = ''
  }
}

// Photos dropped on the slot go the same way as chosen ones.
const over = ref(false)
function dropped(e: DragEvent) {
  over.value = false
  if (!uploading.value) void upload(e.dataTransfer?.files ?? null)
}

async function makePrimary(fileId: string) {
  busy.value = fileId
  try {
    const p = await call(() =>
      catalog.PATCH('/products/{productId}/images/{fileId}', {
        params: { path: { productId: props.product.id, fileId } },
        body: { primary: true },
      }),
    )
    emit('updated', p as ProductStaff)
  } catch (e) {
    notify.report(e, { retry: () => void refresh() })
  } finally {
    busy.value = null
  }
}

const removing = ref<{ fileId: string; primary: boolean } | null>(null)
const removeOpen = computed({ get: () => !!removing.value, set: (v: boolean) => !v && (removing.value = null) })
async function confirmRemove() {
  const r = removing.value
  removing.value = null
  if (r) await remove(r.fileId)
}

async function remove(fileId: string) {
  busy.value = fileId
  try {
    await call(() => catalog.DELETE('/products/{productId}/images/{fileId}', { params: { path: { productId: props.product.id, fileId } } }))
    await refresh()
    notify.toast('Photo removed', 'success')
  } catch (e) {
    notify.report(e, { retry: () => void refresh() })
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <div class="ip">
    <section class="sec" aria-labelledby="ip-add-h">
      <component :is="hs" id="ip-add-h" class="sec-title">Add photos</component>
      <div
        class="slot"
        :class="{ over, busy: uploading }"
        @dragenter.prevent="over = true"
        @dragover.prevent="over = true"
        @dragleave.self="over = false"
        @drop.prevent="dropped"
      >
        <v-icon :icon="mdiImagePlusOutline" size="34" class="slot-icon" />
        <div class="slot-text">
          <p class="slot-title">Drop photos here, or choose them</p>
          <p class="slot-sub">JPEG, PNG or WebP, up to 20 MB each and 10 at a time. Real photos on a plain background work best.</p>
        </div>
        <v-btn class="m3" color="primary" :loading="uploading" @click="picker?.click()">Choose photos</v-btn>
        <input ref="picker" type="file" :accept="ACCEPT.join(',')" multiple hidden aria-label="Photos to upload" @change="upload(($event.target as HTMLInputElement).files)" />
      </div>
      <v-checkbox v-model="removeBackground" class="bg" label="Remove the background from new uploads (where the photo service supports it)" hide-details density="compact" />
    </section>

    <section class="sec" aria-labelledby="ip-photos-h">
      <div class="sec-h">
        <component :is="hs" id="ip-photos-h" class="sec-title">Photos</component>
        <span v-if="product.images.length" class="sec-aside">Customers see the primary photo first</span>
      </div>
      <p v-if="!product.images.length && !processing" class="none">No photos yet. Customers see a placeholder until one is added.</p>
      <TransitionGroup tag="ul" name="tile" class="grid" @before-leave="pinLeaving" aria-live="polite">
        <li v-for="img in product.images" :key="img.fileId" class="tile" :class="{ primary: img.primary }">
          <div class="plate"><ProductImage :image="img" :alt="product.name" small sizes="200px" /></div>
          <div class="tile-bar">
            <span v-if="img.primary" class="is-primary"><v-icon :icon="mdiStar" size="16" />Primary</span>
            <v-btn v-else size="small" variant="text" class="m3 mp" :prepend-icon="mdiStarOutline" :loading="busy === img.fileId" title="Make primary" @click="makePrimary(img.fileId)"><span class="mp-text">Make primary</span></v-btn>
            <span class="spacer" />
            <v-btn size="small" variant="text" :icon="mdiDeleteOutline" aria-label="Remove photo" title="Remove photo" :disabled="busy === img.fileId" @click="removing = { fileId: img.fileId, primary: !!img.primary }" />
          </div>
        </li>
        <li v-for="i in processing" :key="`p${i}`" class="tile">
          <div class="processing"><v-progress-circular indeterminate size="28" color="primary" /><span>Processing…</span></div>
        </li>
      </TransitionGroup>
    </section>

    <v-dialog v-model="removeOpen" max-width="440">
      <v-card>
        <v-card-title>Remove this photo?</v-card-title>
        <v-card-text>
          <p class="t-body">
            It is deleted for good.<template v-if="removing?.primary"> It is the primary photo: the next one becomes the photo customers see first.</template>
          </p>
        </v-card-text>
        <v-card-actions class="row-end">
          <v-btn class="m3" variant="text" @click="removing = null">Keep photo</v-btn>
          <v-btn class="m3 m3-danger" variant="outlined" @click="confirmRemove">Remove photo</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
/* Golden-ratio system, as the product record: 17.8 px heads, 14 px text, 8 · 13 · 21 · 34. */
.ip {
  --rule: rgb(var(--v-theme-seam));
  --muted: rgb(var(--v-theme-secondary));
}
.sec + .sec {
  margin-top: 13px;
  padding-top: 21px;
  border-top: 1px solid var(--rule);
}
.sec-h {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 13px;
  margin-bottom: 13px;
}
.sec-title {
  margin: 0 0 13px;
  font-size: 17.8px;
  line-height: 1.382;
  font-weight: 600;
}
.sec-h .sec-title {
  margin: 0;
}
.sec-aside {
  font-size: 14px;
  color: var(--muted);
}
.slot {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 21px;
  padding: 21px;
  border: 1px dashed rgb(var(--v-theme-field-outline));
  border-radius: 4px;
  transition: background-color 150ms ease, border-color 150ms ease;
}
.slot.over {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.08);
}
.slot-icon {
  color: var(--muted);
}
.slot p {
  margin: 0;
}
.slot-title {
  font-size: 14px;
  font-weight: 600;
}
.slot-sub {
  margin-top: 2px !important;
  font-size: 14px;
  color: var(--muted);
  text-wrap: pretty;
}
.bg {
  margin-top: 8px;
}
.bg :deep(.v-label) {
  padding-inline-start: 9px; /* 13 px from the box to its words */
  opacity: 1;
}
.none {
  margin: 0;
  color: var(--muted);
}
.grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(178px, 1fr));
  gap: 21px;
  position: relative; /* leaving items are pinned inside it (list-motion.ts) */
}
.plate {
  border: 1px solid var(--rule);
  border-radius: 4px;
  overflow: hidden;
  background: #fff;
}
.tile.primary .plate {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.tile-bar {
  display: flex;
  align-items: center;
  min-height: 34px;
  margin-top: 8px;
}
.spacer {
  flex: 1;
}
.tile-bar .v-btn--icon {
  width: 34px;
  height: 34px;
}
.tile-bar {
  min-width: 0;
}
.is-primary {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
}
.processing {
  aspect-ratio: 4 / 3;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--muted);
  border: 1px dashed var(--rule);
  border-radius: 4px;
}
@media (max-width: 599.98px) {
  .slot {
    grid-template-columns: minmax(0, 1fr);
    justify-items: start;
    gap: 13px;
    padding: 13px;
  }
  .grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 13px;
  }
  .mp {
    min-width: 34px !important;
    padding-inline: 8px !important;
  }
  .mp :deep(.v-btn__prepend) {
    margin-inline-end: 0;
  }
  .mp-text {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }
}
</style>
<style scoped>
/* Photos arrive (processing tile → photo) and leave in place; the rest close the gap. */
.tile-enter-active {
  transition: opacity 240ms var(--ease-out), transform 240ms var(--ease-out);
}
.tile-enter-from {
  opacity: 0;
  transform: scale(0.96);
}
.tile-leave-active {
  position: absolute;
  transition: opacity 140ms ease-in, transform 140ms ease-in;
}
.tile-leave-to {
  opacity: 0;
  transform: scale(0.96);
}
.tile-move {
  transition: transform 280ms var(--ease-out);
}
@media (prefers-reduced-motion: reduce) {
  .tile-enter-from,
  .tile-leave-to {
    transform: none;
  }
}
</style>
