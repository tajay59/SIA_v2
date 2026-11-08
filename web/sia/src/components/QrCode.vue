<script setup lang="ts">
/** A QR code for a barcode value (shelves, units), drawn in the browser as an image. */
import QRCode from 'qrcode'
import { ref, watchEffect } from 'vue'

const props = withDefaults(defineProps<{ value: string; size?: number; alt?: string }>(), { size: 112, alt: '' })
const src = ref('')
watchEffect(async () => {
  // Dark modules on white whatever the theme: scanners need the contrast.
  src.value = await QRCode.toDataURL(props.value, { margin: 1, width: props.size * 2, color: { dark: '#000000', light: '#FFFFFF' } })
})
</script>

<template>
  <img v-if="src" :src="src" :width="size" :height="size" :alt="alt || `QR code ${value}`" class="qr" />
</template>

<style scoped>
.qr {
  display: block;
  image-rendering: pixelated;
  border-radius: 4px;
}
</style>
