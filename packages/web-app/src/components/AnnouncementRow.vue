<script setup lang="ts">
/**
 * One announcement as the banner shows it (AnnouncementBar) and as the admin editor previews it (A-22).
 * Tone by icon + word + colour; long text folds to two lines with More; site links and product links stay in the
 * app (a product link opens that product's page in this app: SHOP /catalogue/<id>, SIA /products/<id>), other
 * links open a new tab (said for screen readers); Close only when `dismissible` (never on an alert).
 * `app` overrides the running app (the admin preview shows SHOP rows inside SIA).
 */
import { mdiAlertCircle, mdiClose, mdiInformation, mdiOpenInNew } from '@mdi/js'
import { computed, ref } from 'vue'
import { type Announcement, type AnnouncementApp, announcementHref } from '../announcements'
import { useAppName } from '../bootstrap'

const props = withDefaults(
  defineProps<{
    announcement: Pick<Announcement, 'message' | 'tone' | 'link' | 'dismissible'>
    preview?: boolean
    app?: AnnouncementApp
  }>(),
  { preview: false, app: undefined },
)
const running = useAppName()
const emit = defineEmits<{ dismiss: [] }>()
const a = computed(() => props.announcement)
const alert = computed(() => a.value.tone === 'ALERT')
const long = computed(() => a.value.message.length > 140)
const open = ref(false)
const href = computed(() => (a.value.link ? announcementHref(a.value.link, props.app ?? running) : null))
const isSitePath = (url: string) => url.startsWith('/') && !url.startsWith('//')
</script>

<template>
  <div class="ann-row" :class="[alert ? 'is-alert' : 'is-info', `in-${props.app ?? running}`]">
    <div class="ann-content">
      <v-icon :icon="alert ? mdiAlertCircle : mdiInformation" size="20" class="ann-icon" aria-hidden="true" />
      <p class="ann-text">
        <span class="ann-word">{{ alert ? 'Alert' : 'Information' }}:</span>
        <span class="ann-msg" :class="{ clamp: long && !open }">{{ a.message || ' ' }}</span>
        <button v-if="long" type="button" class="ann-more" :aria-expanded="open" @click="open = !open">{{ open ? 'Less' : 'More' }}</button>
        <template v-if="a.link && href && a.link.label">
          <span v-if="preview" class="ann-link">{{ a.link.label }}</span>
          <router-link v-else-if="isSitePath(href)" :to="href" class="ann-link">{{ a.link.label }}</router-link>
          <a v-else :href="href" target="_blank" rel="noopener noreferrer" class="ann-link">
            {{ a.link.label }}<v-icon :icon="mdiOpenInNew" size="14" aria-hidden="true" /><span class="ann-sr"> (opens in a new tab)</span>
          </a>
        </template>
      </p>
      <v-btn
        v-if="a.dismissible && !alert"
        :icon="mdiClose"
        variant="text"
        size="small"
        density="comfortable"
        class="ann-close"
        :aria-label="`Close this information: ${a.message.slice(0, 60)}`"
        :disabled="preview"
        @click="emit('dismiss')"
      />
    </div>
  </div>
</template>

<style scoped>
.ann-sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.ann-row {
  --tone: var(--v-theme-primary);
  background: color-mix(in srgb, rgb(var(--tone)) 14%, rgb(var(--v-theme-surface)));
  border-bottom: 1px solid color-mix(in srgb, rgb(var(--tone)) 45%, rgb(var(--v-theme-surface)));
  color: rgb(var(--v-theme-on-surface));
}
.ann-row.is-alert {
  --tone: var(--v-theme-warning);
  background: color-mix(in srgb, rgb(var(--tone)) 22%, rgb(var(--v-theme-surface)));
}
/* SHOP: the header's column (max 1200 px, 16 px inset), so the icon lines up with the logo. SIA: full width. */
.ann-content {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-2);
  max-width: 1200px;
  margin: 0 auto;
  padding: 10px var(--sp-4);
  min-height: 40px;
}
.in-sia .ann-content {
  max-width: none;
}
.ann-icon {
  flex: none;
  color: rgb(var(--tone));
}
.ann-text {
  flex: 1;
  min-width: 0;
  margin: 0;
  font-size: 14px;
  line-height: 20px;
  text-wrap: pretty;
  overflow-wrap: anywhere;
}
.ann-word {
  font-weight: 700;
  margin-right: 6px;
}
.ann-msg.clamp {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.ann-more {
  border: 0;
  background: none;
  padding: 0;
  margin-left: 6px;
  font: inherit;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
  min-height: 24px;
}
.ann-link {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-left: var(--sp-2);
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
  text-decoration: underline;
  text-underline-offset: 3px;
  min-height: 24px;
}
.ann-close {
  flex: none;
  margin: -6px -8px -6px 0;
}
.ann-more:focus-visible,
.ann-link:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
  border-radius: 2px;
}
@media (max-width: 599px) {
  .ann-content {
    padding: 10px 12px;
  }
}
</style>
