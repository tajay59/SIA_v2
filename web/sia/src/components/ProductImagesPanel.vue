<script setup lang="ts">
/**
 * A-07 Images tab (J-10): upload JPEG/PNG/WebP (optional background removal) -> "processing" tiles while
 * media-worker works -> photos appear (polling) -> make one primary, remove.
 */
import { ApiError, call, catalog, type ProductStaff, ProductImage, useNotify } from '@cimh/web-app'
import { mdiDeleteOutline, mdiStar, mdiStarOutline, mdiUpload } from '@mdi/js'
import { onBeforeUnmount, ref } from 'vue'

const props = defineProps<{ product: ProductStaff }>()
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
  <div class="stack">
    <v-card class="pa-4 stack-sm">
      <div class="row">
        <div class="stack-sm">
          <span class="t-label">Add photos</span>
          <span class="t-body muted">JPEG, PNG or WebP, up to 20 MB each and 10 at a time. Real photos on a plain background work best.</span>
        </div>
        <span class="spacer" />
        <v-btn color="primary" :prepend-icon="mdiUpload" :loading="uploading" @click="picker?.click()">Choose photos</v-btn>
        <input ref="picker" type="file" :accept="ACCEPT.join(',')" multiple hidden aria-label="Photos to upload" @change="upload(($event.target as HTMLInputElement).files)" />
      </div>
      <v-checkbox v-model="removeBackground" label="Remove the background (where the photo service supports it)" hide-details density="compact" />
    </v-card>

    <p v-if="!product.images.length && !processing" class="t-body muted">No photos yet. Customers see a placeholder until one is added.</p>
    <ul class="grid" aria-live="polite">
      <li v-for="img in product.images" :key="img.fileId" class="tile">
        <ProductImage :image="img" :alt="product.name" small sizes="200px" />
        <div class="row tile-bar">
          <v-chip v-if="img.primary" size="small" color="primary" variant="tonal" :prepend-icon="mdiStar" label>Primary</v-chip>
          <v-btn v-else size="small" variant="text" :prepend-icon="mdiStarOutline" :loading="busy === img.fileId" @click="makePrimary(img.fileId)">Make primary</v-btn>
          <span class="spacer" />
          <v-btn size="small" variant="text" :icon="mdiDeleteOutline" aria-label="Remove photo" :disabled="busy === img.fileId" @click="remove(img.fileId)" />
        </div>
      </li>
      <li v-for="i in processing" :key="`p${i}`" class="tile">
        <div class="processing"><v-progress-circular indeterminate size="28" color="primary" /><span class="t-caption muted">Processing…</span></div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--sp-4);
}
.tile {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
  padding: var(--sp-2);
}
.tile-bar {
  margin-top: var(--sp-2);
  min-height: 36px;
}
.processing {
  aspect-ratio: 4 / 3;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  align-items: center;
  justify-content: center;
}
</style>
