<script setup lang="ts">
/** Add / edit one shipping address (common.yaml ShippingAddress = Address + Contact). */
import { reactive, ref, watch } from 'vue'
import { z } from 'zod'
import { countries } from '../countries'
import type { ShippingAddress } from '../types'
import { country as countrySchema, email as emailSchema, name as nameSchema, rule } from '../validation'


const open = defineModel<boolean>({ default: false })
const props = defineProps<{ address?: ShippingAddress | null }>()
const emit = defineEmits<{ save: [address: ShippingAddress] }>()

const blank = (): ShippingAddress => ({
  line1: '', line2: '', city: '', parish: '', country: 'BB', zip: '', organisation: '', attention: '',
  firstname: '', lastname: '', email: '', tel: '',
})
const form = reactive<ShippingAddress>(blank())
const valid = ref(false)
watch(open, (o) => {
  if (o) Object.assign(form, blank(), props.address ?? {})
})

const req = (max: number) => rule(z.string().trim().min(1, 'Required').max(max, `At most ${max} characters`))
const opt = (max: number) => rule(z.string().max(max, `At most ${max} characters`).nullable().optional())

function save() {
  const clean = Object.fromEntries(
    Object.entries(form).map(([k, v]) => [k, typeof v === 'string' ? v.trim() || null : v]),
  ) as unknown as ShippingAddress
  emit('save', clean)
  open.value = false
}
</script>

<template>
  <v-dialog v-model="open" max-width="640" scrollable>
    <v-card>
      <v-card-title class="t-h3">{{ address ? 'Edit address' : 'New address' }}</v-card-title>
      <v-card-text>
        <v-form v-model="valid" class="stack" @submit.prevent="save">
          <div class="grid-2">
            <v-text-field v-model="form.firstname" label="First name" autocomplete="given-name" :rules="[rule(nameSchema)]" />
            <v-text-field v-model="form.lastname" label="Last name" autocomplete="family-name" :rules="[rule(nameSchema)]" />
            <v-text-field v-model="form.email" label="Email" type="email" autocomplete="email" :rules="[rule(emailSchema)]" />
            <v-text-field v-model="form.tel" label="Phone (optional)" type="tel" autocomplete="tel" :rules="[opt(40)]" />
          </div>
          <v-text-field v-model="form.organisation" label="Organisation (optional)" autocomplete="organization" :rules="[opt(200)]" />
          <v-text-field v-model="form.attention" label="Attention (optional)" :rules="[opt(200)]" />
          <v-text-field v-model="form.line1" label="Address line 1" autocomplete="address-line1" :rules="[req(200)]" />
          <v-text-field v-model="form.line2" label="Address line 2 (optional)" autocomplete="address-line2" :rules="[opt(200)]" />
          <div class="grid-2">
            <v-text-field v-model="form.city" label="City / town" autocomplete="address-level2" :rules="[req(100)]" />
            <v-text-field v-model="form.parish" label="Parish / state (optional)" autocomplete="address-level1" :rules="[opt(100)]" />
            <v-autocomplete
              v-model="form.country"
              label="Country"
              :items="countries()"
              autocomplete="country"
              :rules="[rule(countrySchema)]"
            />
            <v-text-field v-model="form.zip" label="Postal code (optional)" autocomplete="postal-code" :rules="[opt(20)]" />
          </div>
        </v-form>
      </v-card-text>
      <v-card-actions class="row-end">
        <v-btn variant="text" @click="open = false">Cancel</v-btn>
        <v-btn color="primary" :disabled="!valid" @click="save">Save address</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
