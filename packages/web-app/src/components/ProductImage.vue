<script setup lang="ts">
/**
 * Product photo in a 4:3 frame on the theme's `photo-ground` (DESIGN_BRIEF §9: real photos on white; dimmed in dark mode). Responsive WebP variants from
 * media-worker; a neutral icon when the product has no photo yet.
 */
import { mdiImageOffOutline } from '@mdi/js'
import { computed } from 'vue'
import { imageSrcset, imageVariant, type ProductPhoto } from '../catalog'

const props = withDefaults(
  defineProps<{ image?: ProductPhoto | null; alt: string; sizes?: string; eager?: boolean; small?: boolean }>(),
  { image: null, sizes: '(max-width: 600px) 50vw, 280px', eager: false, small: false },
)
const src = computed(() => (props.image ? imageVariant(props.image.url, props.small ? 320 : 800) : ''))
</script>

<template>
  <div class="frame" :class="{ empty: !image }">
    <img
      v-if="image"
      :src="src"
      :srcset="imageSrcset(image.url)"
      :sizes="sizes"
      :alt="alt"
      :loading="eager ? 'eager' : 'lazy'"
      decoding="async"
    />
    <div v-else class="none" role="img" :aria-label="`${alt}: no photo yet`">
      <v-icon :icon="mdiImageOffOutline" size="32" />
    </div>
  </div>
</template>

<style scoped>
.frame {
  aspect-ratio: 4 / 3;
  background: rgb(var(--v-theme-photo-ground));
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  mix-blend-mode: multiply; /* a photo's white background takes the ground's tone (dimmed in dark mode) */
  transition: transform 160ms ease-out;
}
/* No photo: no white ground to blend with, so the empty frame takes the quiet surface tone (a white box glared in dark). */
.frame.empty {
  background: rgb(var(--v-theme-surface-variant));
}
.none {
  color: #8a96a3;
}
</style>
