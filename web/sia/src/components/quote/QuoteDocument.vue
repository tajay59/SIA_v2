<script setup lang="ts">
/**
 * A supplier's quote file shown beside the price lines (A-04). File responses can't be framed (X-Frame-Options DENY,
 * frame-ancestors 'none'), so PDFs are drawn with pdf.js on canvases (loaded only here; worker from our own origin,
 * eval off) and images as a plain img. Pages render at the pane's width and again when it changes.
 */
import { fileUrl } from '@cimh/web-app'
import { onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { BTN } from '../../request-queue'

const props = defineProps<{ fileId: string; name: string; mime: string }>()

type Pdf = { numPages: number; getPage(n: number): Promise<any>; destroy(): Promise<void> }
const state = ref<'loading' | 'ready' | 'error'>('loading')
const pages = ref(0)
const pdf = shallowRef<Pdf | null>(null)
const host = ref<HTMLElement | null>(null)
const isPdf = () => props.mime === 'application/pdf'
let ro: ResizeObserver | undefined
let drawn = 0
let token = 0

async function open() {
  const mine = ++token
  state.value = 'loading'
  pages.value = 0
  await pdf.value?.destroy().catch(() => undefined)
  pdf.value = null
  if (!isPdf()) return // the img reports its own load / error
  try {
    const [lib, worker] = await Promise.all([import('pdfjs-dist'), import('pdfjs-dist/build/pdf.worker.min.mjs?url')])
    lib.GlobalWorkerOptions.workerSrc = worker.default
    const res = await fetch(fileUrl(props.fileId), { credentials: 'same-origin' })
    if (!res.ok) throw new Error(String(res.status))
    const doc = (await lib.getDocument({ data: new Uint8Array(await res.arrayBuffer()) }).promise) as unknown as Pdf
    if (mine !== token) return void doc.destroy()
    pdf.value = doc
    pages.value = doc.numPages
    state.value = 'ready'
    await draw()
  } catch {
    if (mine === token) state.value = 'error'
  }
}

async function draw() {
  const doc = pdf.value
  const el = host.value
  if (!doc || !el) return
  const width = el.clientWidth
  if (!width || width === drawn) return
  drawn = width
  const ratio = Math.min(window.devicePixelRatio || 1, 2)
  for (let n = 1; n <= doc.numPages; n++) {
    const canvas = el.querySelector<HTMLCanvasElement>(`canvas[data-page="${n}"]`)
    if (!canvas) continue
    const page = await doc.getPage(n)
    const base = page.getViewport({ scale: 1 })
    const vp = page.getViewport({ scale: (width / base.width) * ratio })
    canvas.width = vp.width
    canvas.height = vp.height
    canvas.style.aspectRatio = `${base.width} / ${base.height}`
    await page.render({ canvas, canvasContext: canvas.getContext('2d')!, viewport: vp }).promise
  }
}

watch(() => props.fileId, () => { drawn = 0; void open() }, { immediate: true }) // prettier-ignore
watch(host, (el) => {
  ro?.disconnect()
  if (!el) return
  ro = new ResizeObserver(() => void draw())
  ro.observe(el)
})
watch(pages, () => requestAnimationFrame(() => { drawn = 0; void draw() })) // prettier-ignore
onBeforeUnmount(() => {
  token++
  ro?.disconnect()
  void pdf.value?.destroy().catch(() => undefined)
})
</script>

<template>
  <div class="doc" :aria-busy="state === 'loading'">
    <header class="doc-head">
      <span class="doc-name" :title="name">{{ name }}</span>
      <span v-if="pages > 1" class="doc-pages console-mono">{{ pages }} pages</span>
      <a :href="fileUrl(fileId)" target="_blank" rel="noopener" class="doc-open">Open in a new tab</a>
    </header>
    <!-- Focusable so keyboard users can scroll a long quote (axe scrollable-region-focusable). -->
    <div class="doc-body" tabindex="0" role="region" :aria-label="`Quote file ${name}`">
      <template v-if="isPdf()">
        <div v-if="state === 'loading'" class="doc-msg console-skel" />
        <div v-else-if="state === 'error'" class="doc-msg">
          <p>This file can't be shown here.</p>
          <a :href="fileUrl(fileId)" target="_blank" rel="noopener" class="doc-open">Open it in a new tab</a>
        </div>
        <div v-show="state === 'ready'" ref="host" class="doc-pagesbox">
          <canvas v-for="n in pages" :key="`${fileId}-${n}`" :data-page="n" class="doc-page" :aria-label="`${name}, page ${n} of ${pages}`" role="img" />
        </div>
      </template>
      <template v-else>
        <img
          :key="fileId"
          :src="fileUrl(fileId)"
          :alt="name"
          class="doc-img"
          @load="state = 'ready'"
          @error="state = 'error'"
        />
        <div v-if="state === 'error'" class="doc-msg">
          <v-icon :icon="BTN.reject" size="20" />
          <p>This file can't be shown here.</p>
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
  height: 100%;
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
}
.doc-head {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  border-bottom: 1px solid rgb(var(--v-theme-seam));
  font-size: 13px;
}
.doc-name {
  flex: 1;
  min-width: 0;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doc-pages {
  color: rgb(var(--v-theme-secondary));
  font-size: 12px;
}
.doc-open {
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
  white-space: nowrap;
}
.doc-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
  padding: var(--sp-3);
  /* Paper on the console ground: the document reads as a page, not as part of the UI. */
  background: rgb(var(--v-theme-background));
}
.doc-pagesbox {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
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
  color: rgb(var(--v-theme-secondary));
  text-align: center;
}
.doc-msg p {
  margin: 0;
}
</style>
