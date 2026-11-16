<script setup lang="ts">
/** A-07 product on its own page (deep links, phones); the same record opens beside the list in A-05. */
import { useRoute } from 'vue-router'
import ProductRecord from '../../components/ProductRecord.vue'

definePage({ meta: { guard: 'staff', title: 'Product', ownHeading: true } })
const route = useRoute('/products/[id]')
</script>

<template>
  <ProductRecord :product-id="route.params.id" />
</template>
