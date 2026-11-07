<script setup lang="ts">
/** S-13 sign up → S-14 verify. The API answers 202 whether or not the email exists (no enumeration). */
import {
  ApiError,
  AuthCard,
  call,
  countries,
  identity,
  isCimhEmail,
  PasswordField,
  register,
  registerFields,
  rule,
  useNotify,
} from '@cimh/web-app'
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

definePage({ meta: { guard: 'public', title: 'Sign up', layout: 'bare' } })

const router = useRouter()
const notify = useNotify()
const form = reactive({
  firstname: '',
  lastname: '',
  email: '',
  password: '',
  organisationText: '',
  department: '',
  country: 'BB',
  phone: '',
  terms: false,
})
const valid = ref(false)
const busy = ref(false)
const errors = ref<Record<string, string>>({})
const cimh = computed(() => isCimhEmail(form.email))

const field = (k: keyof typeof registerFields) => rule(registerFields[k])

async function submit() {
  const parsed = register.safeParse(form)
  if (!parsed.success) {
    errors.value = Object.fromEntries(parsed.error.issues.map((i) => [String(i.path[0]), i.message]))
    return
  }
  busy.value = true
  errors.value = {}
  try {
    await call(
      () =>
        identity.POST('/auth/register', {
          body: {
            firstname: form.firstname.trim(),
            lastname: form.lastname.trim(),
            email: form.email.trim(),
            password: form.password,
            organisationText: form.organisationText.trim(),
            country: form.country,
            department: form.department.trim() || null,
            phone: form.phone.trim() || null,
          },
        }),
      { refresh: false },
    )
    await router.push({ path: '/verify', query: { email: form.email.trim() } })
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) {
      errors.value = e.fieldErrors()
      if (e.code === 'PASSWORD_BREACHED')
        errors.value.password = 'This password appears in known data breaches. Choose another one.'
      if (!Object.keys(errors.value).length) notify.report(e)
    } else notify.report(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthCard title="Create your account" subtitle="Request instruments and supplies from CIMH." :width="560">
    <v-form v-model="valid" class="stack" @submit.prevent="submit">
      <div class="grid-2">
        <v-text-field v-model="form.firstname" label="First name" autocomplete="given-name" :rules="[field('firstname')]" :error-messages="errors.firstname" />
        <v-text-field v-model="form.lastname" label="Last name" autocomplete="family-name" :rules="[field('lastname')]" :error-messages="errors.lastname" />
      </div>
      <v-text-field
        v-model="form.email"
        label="Work email"
        type="email"
        autocomplete="email"
        :rules="[field('email')]"
        :error-messages="errors.email"
        :hint="cimh ? 'CIMH accounts are active once the email is verified. They can browse but not submit requests.' : undefined"
        persistent-hint
      />
      <PasswordField v-model="form.password" autocomplete="new-password" strength :rules="[field('password')]" :error-messages="errors.password" />
      <v-text-field
        v-if="!cimh"
        v-model="form.organisationText"
        label="Organisation"
        autocomplete="organization"
        hint="For example: Barbados Meteorological Services. An administrator links it when approving your account."
        persistent-hint
        :rules="[(v: string) => !!v.trim() || 'Enter your organisation']"
        :error-messages="errors.organisationText"
      />
      <div class="grid-2">
        <v-text-field v-model="form.department" label="Department (optional)" :error-messages="errors.department" />
        <v-autocomplete v-model="form.country" label="Country" :items="countries()" autocomplete="country" :rules="[field('country')]" :error-messages="errors.country" />
      </div>
      <v-text-field v-model="form.phone" label="Phone (optional)" type="tel" autocomplete="tel" :error-messages="errors.phone" />
      <v-checkbox v-model="form.terms" color="primary" hide-details="auto" :rules="[(v: boolean) => v || 'Please accept the terms']" :error-messages="errors.terms">
        <template #label>
          <span class="t-body">I agree that CIMH stores my details to handle my requests (Barbados Data Protection Act 2019).</span>
        </template>
      </v-checkbox>
      <v-btn type="submit" color="primary" size="large" block :loading="busy" :disabled="!valid">Create account</v-btn>
    </v-form>
    <template #footer>
      <span>Already have an account? <router-link to="/login">Log in</router-link></span>
    </template>
  </AuthCard>
</template>
