<script setup lang="ts">
/**
 * Page 1 of a request file as a small sheet (S-11 Papers, 2026-11-18): a PDF drawn by pdf.js at the tile's width
 * (worker from our own origin, loaded only when a tile comes near the screen), an image shown as it is. A shimmer
 * sheet while it loads; the file type's glyph when it can't be drawn. Decorative: the tile around it names the file.
 */
import { mdiFileDocumentOutline } from '@mdi/js'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { fileUrl } from '../orders'

const props = defineProps<{ fileId: string; mime: string }>()
const state = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const box = ref<HTMLElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
const isPdf = computed(() => props.mime === 'application/pdf')
const isImage = computed(() => props.mime.startsWith('image/'))
let io: IntersectionObserver | undefined
let gone = false

async function draw() {
  state.value = 'loading'
  try {
    const [lib, worker] = await Promise.all([import('pdfjs-dist'), import('pdfjs-dist/build/pdf.worker.min.mjs?url')])
    lib.GlobalWorkerOptions.workerSrc = worker.default
    const res = await fetch(fileUrl(props.fileId), { credentials: 'same-origin' })
    if (!res.ok) throw new Error(String(res.status))
    const doc = await lib.getDocument({ data: new Uint8Array(await res.arrayBuffer()) }).promise
    try {
      const page = await doc.getPage(1)
      const c = canvas.value
      if (gone || !c || !box.value) return
      const base = page.getViewport({ scale: 1 })
      const ratio = Math.min(window.devicePixelRatio || 1, 2)
      const vp = page.getViewport({ scale: (box.value.clientWidth / base.width) * ratio })
      c.width = vp.width
      c.height = vp.height
      await page.render({ canvas: c, canvasContext: c.getContext('2d')!, viewport: vp }).promise
      if (!gone) state.value = 'ready'
    } finally {
      void doc.destroy()
    }
  } catch {
    if (!gone) state.value = 'error'
  }
}

onMounted(() => {
  if (!isPdf.value) return
  io = new IntersectionObserver((seen) => {
    if (!seen.some((e) => e.isIntersecting)) return
    io?.disconnect()
    void draw()
  }, { rootMargin: '200px' })
  if (box.value) io.observe(box.value)
})
onBeforeUnmount(() => {
  gone = true
  io?.disconnect()
})
</script>

<template>
  <span ref="box" class="thumb-sheet" :class="state" aria-hidden="true">
    <img v-if="isImage" :src="fileUrl(fileId)" alt="" loading="lazy" class="thumb-img" @error="state = 'error'" />
    <canvas v-else-if="isPdf" v-show="state === 'ready'" ref="canvas" class="thumb-canvas" />
    <span v-if="isPdf && state !== 'ready' && state !== 'error'" class="thumb-skel" />
    <v-icon v-if="state === 'error' || (!isPdf && !isImage)" :icon="mdiFileDocumentOutline" size="40" class="thumb-glyph" />
  </span>
</template>

<style scoped>
/* A sheet of A4 on the page ground: white in both themes (it is the paper), a soft offset shadow. */
.thumb-sheet {
  position: relative;
  display: grid;
  place-items: center;
  aspect-ratio: 210 / 297;
  width: 100%;
  overflow: hidden;
  border-radius: 3px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.18), 0 3px 10px -3px rgba(0, 0, 0, 0.16);
}
.thumb-canvas,
.thumb-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.thumb-img {
  object-fit: cover;
  object-position: top center;
}
.thumb-skel {
  position: absolute;
  inset: 0;
  background: linear-gradient(100deg, rgba(0, 0, 0, 0.03) 30%, rgba(0, 0, 0, 0.08) 50%, rgba(0, 0, 0, 0.03) 70%) 0 0 / 200% 100%;
  animation: thumb-shimmer 1.4s linear infinite;
}
.thumb-glyph {
  color: #5b6168;
}
@keyframes thumb-shimmer {
  to {
    background-position: -200% 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .thumb-skel {
    animation: none;
  }
}
</style>
