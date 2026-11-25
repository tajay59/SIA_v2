<script setup lang="ts">
/**
 * A-22 preview: the real banner row (AnnouncementRow) on top of a small sketch of each page it lands on, SHOP and
 * SIA, light and dark (owner 2026-11-23). Pages the message doesn't reach collapse to one line ("Not shown on SIA").
 * The row inside each sketch takes that page's theme, so contrast is checked where it will be read.
 */
import { type Announcement, AnnouncementRow } from '@cimh/web-app'
import { computed } from 'vue'

const props = defineProps<{ announcement: Pick<Announcement, 'message' | 'tone' | 'link' | 'dismissible' | 'audience'> }>()

const pages = computed(() =>
  (['shop', 'sia'] as const).flatMap((app) =>
    (['light', 'dark'] as const).map((mode) => ({
      app,
      mode,
      key: `${app}-${mode}`,
      title: `${app === 'shop' ? 'SHOP' : 'SIA'} · ${mode === 'light' ? 'Light' : 'Dark'}`,
      theme: mode === 'light' ? 'cimhLight' : 'cimhDark',
      reached: props.announcement.audience === 'BOTH' || props.announcement.audience === app.toUpperCase(),
    })),
  ),
)
const reached = computed(() => pages.value.filter((p) => p.reached))
const missed = computed(() => [...new Set(pages.value.filter((p) => !p.reached).map((p) => (p.app === 'shop' ? 'SHOP' : 'SIA')))])
const empty = computed(() => !props.announcement.message.trim())
const shown = computed(() => ({ ...props.announcement, message: props.announcement.message.trim() || 'Your message shows here' }))
</script>

<template>
  <div class="preview" :class="{ empty }">
    <figure v-for="p in reached" :key="p.key" class="sheet" :class="p.app">
      <figcaption class="cap">
        <span>{{ p.title }}</span>
      </figcaption>
      <v-theme-provider :theme="p.theme" with-background class="page">
        <div aria-hidden="true" :inert="true">
          <AnnouncementRow :announcement="shown" :app="p.app" preview />
          <!-- A sketch of the page under the banner: SHOP top bar, or SIA drawer + title. -->
          <div v-if="p.app === 'shop'" class="mock-shop">
            <div class="bar"><span class="logo" /><span class="nav" /><span class="nav" /><span class="cta" /></div>
            <div class="band" />
            <div class="tiles"><span v-for="i in 4" :key="i" /></div>
          </div>
          <div v-else class="mock-sia">
            <div class="drawer"><span v-for="i in 5" :key="i" /></div>
            <div class="work"><span class="title" /><span class="line" /><span class="line s" /></div>
          </div>
        </div>
      </v-theme-provider>
    </figure>
    <p v-if="missed.length" class="missed">Not shown on {{ missed.join(' or ') }}.</p>
  </div>
</template>

<style scoped>
.preview {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sp-3);
}
.sheet {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.cap {
  display: flex;
  justify-content: space-between;
  gap: var(--sp-2);
  font: 500 12px/16px 'JetBrains Mono', ui-monospace, monospace;
  color: rgb(var(--v-theme-secondary));
}
.missed {
  grid-column: 1 / -1;
  margin: 0;
  font-size: 12px;
  line-height: 16px;
  color: rgb(var(--v-theme-secondary));
}
.page {
  border: 1px solid rgb(var(--v-theme-seam));
  border-radius: 4px;
  overflow: hidden;
  /* Grows with a long message: the whole banner always shows; the page sketch below it is cut. */
  min-height: 112px;
  max-height: 220px;
  pointer-events: none;
  user-select: none;
}

/* The banner in a sketch reads at 0.86 of its size: the whole page is a thumbnail. */
.page :deep(.ann-content) {
  padding: 8px 10px;
  min-height: 0;
}
.page :deep(.ann-text) {
  font-size: 12.5px;
  line-height: 17px;
}
.empty .page :deep(.ann-msg) {
  color: rgb(var(--v-theme-on-surface-variant));
  font-style: italic;
}
.mock-shop .bar {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 30px;
  padding: 0 10px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.mock-shop .logo {
  width: 60px;
  height: 10px;
  border-radius: 2px;
  background: rgb(var(--v-theme-on-surface));
  opacity: 0.7;
}
.mock-shop .nav {
  width: 34px;
  height: 7px;
  border-radius: 2px;
  background: rgb(var(--v-theme-on-surface));
  opacity: 0.25;
}
.mock-shop .cta {
  margin-left: auto;
  width: 40px;
  height: 14px;
  border-radius: 999px;
  background: rgb(var(--v-theme-primary));
}
.mock-shop .band {
  height: 34px;
  background: #0a2e4a; /* SHOP navy band (both themes) */
}
.mock-shop .tiles {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
  padding: 8px 10px;
}
.mock-shop .tiles span {
  height: 34px;
  border-radius: 4px;
  background: rgb(var(--v-theme-on-surface));
  opacity: 0.08;
}
.mock-sia {
  display: grid;
  grid-template-columns: 52px 1fr;
  height: 100%;
}
.mock-sia .drawer {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 10px 8px;
  border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.mock-sia .drawer span {
  height: 6px;
  border-radius: 2px;
  background: rgb(var(--v-theme-on-surface));
  opacity: 0.25;
}
.mock-sia .work {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 10px;
}
.mock-sia .title {
  width: 40%;
  height: 10px;
  border-radius: 2px;
  background: rgb(var(--v-theme-on-surface));
  opacity: 0.6;
}
.mock-sia .line {
  height: 24px;
  border-radius: 4px;
  background: rgb(var(--v-theme-on-surface));
  opacity: 0.08;
}
.mock-sia .line.s {
  width: 70%;
}
@media (max-width: 599.98px) {
  .preview {
    grid-template-columns: minmax(0, 1fr);
  }
  .page {
    min-height: 104px;
  }
}
</style>
