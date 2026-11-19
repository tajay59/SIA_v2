<script setup lang="ts">
/**
 * A request document read on the page (SHOP S-11/S-12, SIA A-04). File responses can't be framed (X-Frame-Options
 * DENY, frame-ancestors 'none'), so PDFs are drawn with pdf.js on canvases (loaded only when a document opens;
 * worker from our own origin, eval off) and images as a plain img. Pages render at the pane's width and again when
 * it changes.
 * `src` shows a PDF that is not a stored file (the agreement preview); `file` shows a local file before it is uploaded
 * (S-12: the signed copy the customer is about to send; read in the browser, nothing is sent); `what` names the region
 * ("Quote file").
 * `link` is the header action and the fallback when a file can't be drawn: open it in a new tab (staff), download
 * it (customers: nothing leaves the page) or nothing (the page has its own Download button).
 * When the server refuses (e.g. a draft that can't be priced yet), its reason is shown instead of the pages.
 * Looks: `--doc-edge`, `--doc-radius`, `--doc-ground` (SIA sets its console seams; defaults suit SHOP).
 * Size: fills its parent (`--doc-height`, default 100%); SHOP sets `--doc-height: auto` + `--doc-max-height` so a
 * one-page file isn't followed by an empty ground. Pages are drawn at most `--doc-page-max` wide (default 760 px; S-12
 * draws 860 px so an A4 page's 9.5 pt body reads at about 13 px).
 * `startZoom` opens the document zoomed in (S-12's full-screen reader on phones: a page fitted to 330 px is unreadable).
 */
import { mdiAlertCircleOutline, mdiDownload, mdiMagnifyMinusOutline, mdiMagnifyPlusOutline } from '@mdi/js'
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { fileUrl } from '../orders'

const props = withDefaults(
  defineProps<{ fileId?: string; src?: string; file?: File | null; name: string; mime: string; what?: string; link?: 'open' | 'download' | 'none'; startZoom?: 1 | 1.5 | 2 | 3 }>(),
  { fileId: '', src: '', file: null, what: 'File', link: 'open', startZoom: 1 },
)
const url = computed(() => props.src || fileUrl(props.fileId))
/** Same file, sent as an attachment: the browser saves it instead of opening another tab. */
const downloadUrl = computed(() => (props.fileId ? `${fileUrl(props.fileId)}?disposition=attachment` : url.value))
const emit = defineEmits<{ state: ['loading' | 'ready' | 'error'] }>()
const reason = ref('')

type Pdf = { numPages: number; getPage(n: number): Promise<any>; destroy(): Promise<void> }
type RenderTask = { promise: Promise<void>; cancel(): void }
const state = ref<'loading' | 'ready' | 'error'>('loading')
watch(state, (v) => emit('state', v), { immediate: true })
const pages = ref(0)
const pdf = shallowRef<Pdf | null>(null)
const host = ref<HTMLElement | null>(null)
const isPdf = () => props.mime === 'application/pdf'
/** A local image, read as a data URL (the CSP allows data: images, not blob:). */
const localImage = ref('')
const imgSrc = computed(() => (props.file ? localImage.value : url.value))
const readDataUrl = (f: File) =>
  new Promise<string>((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result))
    r.onerror = () => reject(r.error)
    r.readAsDataURL(f)
  })
let ro: ResizeObserver | undefined
let token = 0

async function open() {
  const mine = ++token
  stopDrawing()
  state.value = 'loading'
  pages.value = 0
  reason.value = ''
  await pdf.value?.destroy().catch(() => undefined)
  pdf.value = null
  localImage.value = ''
  if (!isPdf()) {
    // The img reports its own load / error; a local one is read first.
    if (!props.file) return
    const data = await readDataUrl(props.file).catch(() => '')
    if (mine !== token) return
    if (data) localImage.value = data
    else state.value = 'error'
    return
  }
  try {
    const [lib, worker] = await Promise.all([import('pdfjs-dist'), import('pdfjs-dist/build/pdf.worker.min.mjs?url')])
    lib.GlobalWorkerOptions.workerSrc = worker.default
    let bytes: ArrayBuffer
    if (props.file) bytes = await props.file.arrayBuffer()
    else {
      const res = await fetch(url.value, { credentials: 'same-origin' })
      if (!res.ok) {
        const problem = (await res.json().catch(() => ({}))) as { detail?: unknown }
        if (mine === token && typeof problem.detail === 'string') reason.value = problem.detail
        throw new Error(String(res.status))
      }
      bytes = await res.arrayBuffer()
    }
    const doc = (await lib.getDocument({ data: new Uint8Array(bytes) }).promise) as unknown as Pdf
    if (mine !== token) return void doc.destroy()
    pdf.value = doc
    pages.value = doc.numPages
    state.value = 'ready'
    await nextTick() // the canvases exist now
    draw(true)
  } catch {
    if (mine === token) state.value = 'error'
  }
}

/*
 * One paint at a time. Two renders on one canvas mirror the page: resizing a canvas resets its context, which
 * drops pdf.js's y-flip from under the render still running there (the agreement preview came out upside down when
 * the first page grew the pane a scrollbar, the pane narrowed and the ResizeObserver started a second paint). A new
 * paint cancels the page being drawn and waits for it to stop before touching any canvas.
 */
let target = 0 // the width the last requested paint draws at
let want = 0 // that paint's number; an older one stops at its next page
let task: RenderTask | null = null
let queue: Promise<void> = Promise.resolve()

function draw(force = false) {
  const width = host.value?.clientWidth ?? 0
  if (!pdf.value || !width || (!force && width === target)) return
  target = width
  const mine = ++want
  task?.cancel()
  queue = queue.then(() => paint(mine, width)).catch(() => undefined)
}

function stopDrawing() {
  want++
  target = 0
  task?.cancel()
}

async function paint(mine: number, width: number) {
  const doc = pdf.value
  const el = host.value
  if (!doc || !el) return
  const ratio = Math.min(window.devicePixelRatio || 1, 2)
  for (let n = 1; n <= doc.numPages; n++) {
    if (mine !== want) return
    const canvas = el.querySelector<HTMLCanvasElement>(`canvas[data-page="${n}"]`)
    if (!canvas) continue
    const page = await doc.getPage(n)
    if (mine !== want) return
    const base = page.getViewport({ scale: 1 })
    const vp = page.getViewport({ scale: (width / base.width) * ratio })
    canvas.width = vp.width
    canvas.height = vp.height
    canvas.style.aspectRatio = `${base.width} / ${base.height}`
    const t: RenderTask = page.render({ canvas, canvasContext: canvas.getContext('2d')!, viewport: vp })
    task = t
    try {
      await t.promise
    } catch {
      return // cancelled by a newer paint, which redraws every page
    } finally {
      if (task === t) task = null
    }
  }
}

/*
 * Zoom: 100% = the page fits the pane's width (at most `--doc-page-max`). On a phone that draws an A4 page about
 * 330 px wide, too small to read, so the reader zooms in and pans sideways inside the pane; the pages repaint at the
 * new width.
 */
const ZOOMS = [1, 1.5, 2, 3]
const zoom = ref<number>(props.startZoom)
const stepZoom = (d: 1 | -1) => (zoom.value = ZOOMS[Math.max(0, Math.min(ZOOMS.length - 1, ZOOMS.indexOf(zoom.value) + d))]!)
const zoomStyle = computed(() =>
  zoom.value === 1 ? undefined : { width: `${zoom.value * 100}%`, maxWidth: `calc(var(--doc-page-max, 760px) * ${zoom.value})` },
)
/** The page in view: the last one whose top has passed a third of the pane. */
const body = ref<HTMLElement | null>(null)
const current = ref(1)
let tracking = 0
function track() {
  if (tracking) return
  tracking = requestAnimationFrame(() => {
    tracking = 0
    const el = body.value
    const list = host.value?.querySelectorAll<HTMLCanvasElement>('canvas[data-page]')
    if (!el || !list?.length) return
    const mark = el.getBoundingClientRect().top + el.clientHeight / 3
    let n = 1
    list.forEach((c, i) => {
      if (c.getBoundingClientRect().top <= mark) n = i + 1
    })
    current.value = n
  })
}

watch([url, () => props.file], () => {
  zoom.value = props.startZoom
  current.value = 1
  void open()
}, { immediate: true })
watch(host, (el) => {
  ro?.disconnect()
  if (!el) return
  ro = new ResizeObserver(() => draw())
  ro.observe(el)
})
onBeforeUnmount(() => {
  token++
  stopDrawing()
  ro?.disconnect()
  void pdf.value?.destroy().catch(() => undefined)
})
</script>

<template>
  <div class="doc" :aria-busy="state === 'loading'">
    <header class="doc-head">
      <div class="doc-title">
        <slot name="title"><span class="doc-name" :title="name">{{ name }}</span></slot>
      </div>
      <div class="doc-tools">
      <span v-if="pages > 1" class="doc-pages tnum">Page {{ current }} of {{ pages }}</span>
      <div v-if="state === 'ready'" class="doc-zoom" role="group" :aria-label="`Zoom ${name}`">
        <button type="button" class="doc-zbtn" :disabled="zoom === ZOOMS[0]" aria-label="Zoom out" @click="stepZoom(-1)">
          <v-icon :icon="mdiMagnifyMinusOutline" size="18" />
        </button>
        <button type="button" class="doc-zpct tnum" :aria-label="`Fit to width (now ${Math.round(zoom * 100)}%)`" @click="zoom = 1">
          {{ Math.round(zoom * 100) }}%
        </button>
        <button type="button" class="doc-zbtn" :disabled="zoom === ZOOMS[ZOOMS.length - 1]" aria-label="Zoom in" @click="stepZoom(1)">
          <v-icon :icon="mdiMagnifyPlusOutline" size="18" />
        </button>
      </div>
      <a v-if="link === 'open'" :href="url" target="_blank" rel="noopener" class="doc-link">Open in a new tab</a>
      <a v-else-if="link === 'download'" :href="downloadUrl" download class="doc-link">
        <v-icon :icon="mdiDownload" size="18" />Download
      </a>
      <slot name="actions" />
      </div>
    </header>
    <!-- Focusable so keyboard users can scroll a long document (axe scrollable-region-focusable). -->
    <div ref="body" class="doc-body" tabindex="0" role="region" :aria-label="`${what} ${name}`" @scroll.passive="track">
      <template v-if="isPdf()">
        <div v-if="state === 'loading'" class="doc-msg doc-skel"><span class="doc-skel-text" role="status">Loading {{ name }}…</span></div>
        <div v-else-if="state === 'error' && reason" class="doc-msg doc-refused" role="alert">
          <v-icon :icon="mdiAlertCircleOutline" size="20" />
          <p>{{ reason }}</p>
        </div>
        <div v-else-if="state === 'error'" class="doc-msg">
          <p>This file can't be shown here.</p>
          <a v-if="link === 'open'" :href="url" target="_blank" rel="noopener" class="doc-link">Open it in a new tab</a>
          <a v-else-if="link === 'download'" :href="downloadUrl" download class="doc-link">Download it instead</a>
        </div>
        <div v-show="state === 'ready'" ref="host" class="doc-pagesbox" :style="zoomStyle">
          <canvas v-for="n in pages" :key="`${file ? `${file.name}-${file.lastModified}` : url}-${n}`" :data-page="n" class="doc-page" :aria-label="`${name}, page ${n} of ${pages}`" role="img" />
        </div>
      </template>
      <template v-else>
        <div v-if="!imgSrc && state === 'loading'" class="doc-msg doc-skel"><span class="doc-skel-text" role="status">Loading {{ name }}…</span></div>
        <img v-if="imgSrc" :key="file ? `${file.name}-${file.lastModified}` : url" :src="imgSrc" :alt="name" class="doc-img" :style="zoomStyle" @load="state = 'ready'" @error="state = 'error'" />
        <div v-if="state === 'error'" class="doc-msg">
          <v-icon :icon="mdiAlertCircleOutline" size="20" />
          <p>This file can't be shown here.</p>
          <a v-if="link === 'download'" :href="downloadUrl" download class="doc-link">Download it instead</a>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.doc {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: var(--doc-height, 100%);
  max-height: var(--doc-max-height, none);
  border: 1px solid var(--doc-edge, rgba(var(--v-border-color), var(--v-border-opacity)));
  border-radius: var(--doc-radius, 8px);
  background: rgb(var(--v-theme-surface));
}
.doc-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-3);
  min-height: 44px;
  padding: var(--sp-1) var(--sp-2) var(--sp-1) var(--sp-3);
  border-bottom: 1px solid var(--doc-edge, rgba(var(--v-border-color), var(--v-border-opacity)));
  font-size: 13px;
}
/* One head per document: its name (or the tabs a parent puts here), the page in view, zoom, the link. */
/* Narrow panes: the name (or tabs) keeps a row of its own rather than being squeezed out by the controls; a parent
   with file tabs sets `--doc-title-basis: 100%` so the tabs always own the first row. */
.doc-title {
  flex: 1 1 var(--doc-title-basis, 220px);
  min-width: 0;
  display: flex;
  align-items: center;
}
.doc-name {
  min-width: 0;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doc-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-3);
  margin-left: auto;
}
.doc-pages {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 12px;
  white-space: nowrap;
}
.doc-zoom {
  display: inline-flex;
  align-items: center;
  flex: none;
}
.doc-zbtn,
.doc-zpct {
  display: inline-grid;
  place-items: center;
  min-width: 32px;
  height: 32px;
  padding: 0 4px;
  border: 0;
  border-radius: 999px;
  background: none;
  color: inherit;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.doc-zpct {
  min-width: 44px;
  font-weight: 600;
}
.doc-zbtn:hover:not(:disabled),
.doc-zpct:hover {
  background: rgba(var(--v-theme-on-surface), 0.08);
}
.doc-zbtn:disabled {
  opacity: 0.38;
  cursor: default;
}
.doc-zbtn:focus-visible,
.doc-zpct:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 1px;
}
.doc-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 32px;
  padding: 0 var(--sp-1);
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
  white-space: nowrap;
}
/* On the grey desk ground the primary blue is 4.45:1: the message's link takes the ink colour, underlined. */
.doc-msg .doc-link {
  color: rgb(var(--v-theme-on-surface));
  text-decoration: underline;
  text-underline-offset: 3px;
}
.doc-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
  padding: var(--sp-3);
  /* Inside the frame's corners (no overflow clip on the frame: it would cut this region's focus ring). */
  border-radius: 0 0 calc(var(--doc-radius, 8px) - 1px) calc(var(--doc-radius, 8px) - 1px);
  /* Paper on a ground: the document reads as a page, not as part of the UI. */
  background: var(--doc-ground, rgb(var(--v-theme-surface-variant)));
}
/* Touch: once the document ends, the page scrolls on (no trapped finger). */
@media (pointer: coarse) {
  .doc-body {
    overscroll-behavior: auto;
  }
}
.doc-pagesbox {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
/* The pages box is what pdf.js measures, so its cap is the drawing width too. */
.doc-pagesbox,
.doc-img,
.doc-skel {
  max-width: var(--doc-page-max, 760px);
  margin-inline: auto;
}
.doc-page,
.doc-img {
  display: block;
  width: 100%;
  height: auto;
  background: #fff;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.18), 0 2px 8px -2px rgba(0, 0, 0, 0.12);
}
.doc-msg {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
  min-height: 240px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  text-align: center;
}
.doc-msg p {
  margin: 0;
  max-width: 52ch;
}
.doc-refused {
  color: rgb(var(--v-theme-error));
  font-weight: 500;
}
/* A blank sheet that shimmers while the file arrives. */
.doc-skel {
  justify-content: center;
  align-items: center;
  aspect-ratio: 210 / 297;
  min-height: 0;
  max-height: 100%;
  background: linear-gradient(100deg, rgba(var(--v-theme-on-surface), 0.04) 30%, rgba(var(--v-theme-on-surface), 0.09) 50%, rgba(var(--v-theme-on-surface), 0.04) 70%)
    0 0 / 200% 100%;
  animation: doc-shimmer 1.4s linear infinite;
}
.doc-skel-text {
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface-variant));
}
@keyframes doc-shimmer {
  to {
    background-position: -200% 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .doc-skel {
    animation: none;
  }
}
</style>
