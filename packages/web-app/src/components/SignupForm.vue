<script setup lang="ts">
/**
 * Sign up (S-13; SIA sign-up for CIMH staff), in three short steps: You · Organisation (CIMH
 * emails: Details) · Password. Each Continue checks only its own step (`checkForm`: marks every field, focuses
 * the first); nothing is ever disabled for missing input. A 422 from the server jumps to the step holding the
 * first bad field. The API answers 202 whether or not the email exists (no enumeration), then → /verify.
 * `staff` (SIA): only @cimh.edu.bb addresses; an administrator then gives the account staff access.
 */
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError, call, identity } from '../api'
import { useNotify } from '../notify'
import { countries } from '../countries'
import { checkForm, type FormLike } from '../form'
import { isCimhEmail, register, registerFields, rule } from '../validation'
import PasswordField from './PasswordField.vue'

const props = withDefaults(defineProps<{ staff?: boolean; loginPath?: string }>(), { staff: false, loginPath: '/login' })
const step = defineModel<number>('step', { default: 0 })

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
const forms = [ref<FormLike | null>(null), ref<FormLike | null>(null), ref<FormLike | null>(null)]
const busy = ref(false)
const errors = ref<Record<string, string>>({})
const cimh = computed(() => isCimhEmail(form.email))
const field = (k: keyof typeof registerFields) => rule(registerFields[k])
const staffEmail = (v: string) => !props.staff || !v.trim() || isCimhEmail(v) || 'Use your @cimh.edu.bb address'

const STEP_OF: Record<string, number> = {
  firstname: 0, lastname: 0, email: 0,
  organisationText: 1, department: 1, country: 1, phone: 1,
  password: 2, terms: 2,
} // prettier-ignore
const titles = computed(() => ['You', cimh.value ? 'Details' : 'Organisation', 'Password'])
defineExpose({ titles })

// The step pane takes the cursor when it changes (screen readers hear its heading).
const paneHead = ref<HTMLElement | null>(null)
// Panes slide in the direction of travel: forward from the right, Back from the left.
const dir = ref<'fwd' | 'back'>('fwd')
watch(step, (n, o) => {
  dir.value = n < o ? 'back' : 'fwd'
  void nextTick(() => paneHead.value?.focus())
})

async function next() {
  if (!(await checkForm(forms[step.value].value))) return
  step.value = Math.min(step.value + 1, 2)
}

async function submit() {
  if (busy.value) return
  if (!(await checkForm(forms[2].value))) return
  const parsed = register.safeParse(form)
  if (!parsed.success) {
    errors.value = Object.fromEntries(parsed.error.issues.map((i) => [String(i.path[0]), i.message]))
    step.value = Math.min(...Object.keys(errors.value).map((k) => STEP_OF[k] ?? 0))
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
      if (e.code === 'PASSWORD_BREACHED') errors.value.password = 'This password appears in known data breaches. Choose another one.'
      if (Object.keys(errors.value).length) step.value = Math.min(...Object.keys(errors.value).map((k) => STEP_OF[k] ?? 0))
      else notify.report(e)
    } else notify.report(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="signup">
    <ol class="dots" :aria-label="`Step ${step + 1} of 3`" :style="{ '--step': step }">
      <li v-for="(t, i) in titles" :key="i" :class="{ on: i === step, done: i < step }">
        <button v-if="i < step" type="button" class="dot-btn" @click="step = i">{{ i + 1 }}. {{ t }}</button>
        <span v-else :aria-current="i === step ? 'step' : undefined">{{ i + 1 }}. {{ t }}</span>
      </li>
      <li class="ink" aria-hidden="true" />
    </ol>

    <div class="panes">
      <Transition :name="`pane-${dir}`" mode="out-in">
        <div :key="step" class="pane">
          <h2 ref="paneHead" tabindex="-1" class="pane-title sr-only">{{ titles[step] }}</h2>

          <v-form v-show="step === 0" :ref="(el) => (forms[0].value = el as unknown as FormLike)" class="stack" @submit.prevent="next">
            <div class="grid-2">
              <v-text-field v-model="form.firstname" name="firstname" label="First name" autocomplete="given-name" :rules="[field('firstname')]" :error-messages="errors.firstname" />
              <v-text-field v-model="form.lastname" name="lastname" label="Last name" autocomplete="family-name" :rules="[field('lastname')]" :error-messages="errors.lastname" />
            </div>
            <v-text-field
              v-model="form.email"
              name="email"
              :label="staff ? 'CIMH email' : 'Work email'"
              type="email"
              autocomplete="email"
              :rules="[field('email'), staffEmail]"
              :error-messages="errors.email"
              :hint="
                staff
                  ? 'An administrator gives the account staff access after you verify the email.'
                  : cimh
                    ? 'CIMH accounts are active once the email is verified. They can browse but not send requests.'
                    : 'A CIMH administrator approves new accounts, usually within two working days.'
              "
              persistent-hint
            />
            <v-btn type="submit" color="primary" size="large" block>Continue</v-btn>
          </v-form>

          <v-form v-show="step === 1" :ref="(el) => (forms[1].value = el as unknown as FormLike)" class="stack" @submit.prevent="next">
            <v-text-field
              v-if="!cimh"
              v-model="form.organisationText"
              name="organisationText"
              label="Organisation"
              autocomplete="organization"
              hint="For example: Barbados Meteorological Services. An administrator links it when approving your account."
              persistent-hint
              :rules="[(v: string) => !!v.trim() || 'Enter your organisation']"
              :error-messages="errors.organisationText"
            />
            <div class="grid-2">
              <v-text-field v-model="form.department" name="department" label="Department (optional)" :error-messages="errors.department" />
              <v-autocomplete v-model="form.country" name="country" label="Country" :items="countries()" autocomplete="country" :rules="[field('country')]" :error-messages="errors.country" />
            </div>
            <v-text-field v-model="form.phone" name="phone" label="Phone (optional)" type="tel" autocomplete="tel" :error-messages="errors.phone" />
            <v-btn type="submit" color="primary" size="large" block>Continue</v-btn>
            <v-btn variant="text" class="back" @click="step = 0">Back</v-btn>
          </v-form>

          <v-form v-show="step === 2" :ref="(el) => (forms[2].value = el as unknown as FormLike)" class="stack" @submit.prevent="submit">
            <PasswordField v-model="form.password" name="password" autocomplete="new-password" strength :rules="[field('password')]" :error-messages="errors.password" />
            <v-checkbox v-model="form.terms" name="terms" color="primary" hide-details="auto" :rules="[(v: boolean) => v || 'Please accept the terms']" :error-messages="errors.terms">
              <template #label>
                <span class="terms">I agree that CIMH stores my details to handle my requests (Barbados Data Protection Act 2019).</span>
              </template>
            </v-checkbox>
            <v-btn type="submit" color="primary" size="large" block :loading="busy">Create account</v-btn>
            <v-btn variant="text" class="back" @click="step = 1">Back</v-btn>
          </v-form>
        </div>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.dots {
  position: relative;
  list-style: none;
  margin: 0 0 var(--sp-4);
  padding: 0;
  display: flex;
  gap: var(--sp-2);
  font-size: 13px;
  font-weight: 600;
}
.dots li:not(.ink) {
  flex: 1;
  padding-top: var(--sp-2);
  border-top: 3px solid rgba(var(--v-border-color), var(--v-border-opacity));
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  transition: border-color 250ms cubic-bezier(0.16, 1, 0.3, 1), color 250ms ease-out;
}
.dots li.done {
  border-top-color: rgba(var(--v-theme-primary), 0.5);
}
/* One indicator slides along the track to the current step. */
.dots .ink {
  position: absolute;
  top: 0;
  left: 0;
  width: calc((100% - 2 * var(--sp-2)) / 3);
  height: 3px;
  background: rgb(var(--v-theme-primary));
  border-radius: 3px;
  transform: translateX(calc(var(--step) * (100% + var(--sp-2))));
  transition: transform 420ms cubic-bezier(0.16, 1, 0.3, 1);
}
.dots li.on {
  border-top-color: rgba(var(--v-theme-primary), 0.18);
  color: rgb(var(--v-theme-on-surface));
}
.dot-btn {
  font: inherit;
  color: rgb(var(--v-theme-primary));
  background: none;
  border: 0;
  padding: 0;
  min-height: 24px;
  cursor: pointer;
  text-decoration: none;
  text-underline-offset: 3px;
}
.dot-btn:hover,
.dot-btn:focus-visible {
  text-decoration: underline;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
.back {
  align-self: center;
}
/* Field hints: readable, never hyphenated mid-word. */
.signup :deep(.v-messages),
.signup :deep(.v-messages__message) {
  min-height: 0;
  overflow: visible;
  font-size: 13px;
  line-height: 18px;
  letter-spacing: normal;
  hyphens: manual;
}
.pane-title {
  font-size: 20px;
  line-height: 28px;
  font-weight: 700;
  margin: 0 0 var(--sp-4);
  outline: none;
}
.row-2 {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--sp-3);
}
.terms {
  font-size: 14px;
  line-height: 20px;
}
/* Steps slide in the direction of travel (exit faster than entry). */
.pane-fwd-enter-active,
.pane-back-enter-active {
  transition: opacity 280ms ease-out, transform 360ms cubic-bezier(0.16, 1, 0.3, 1);
}
.pane-fwd-leave-active,
.pane-back-leave-active {
  transition: opacity 120ms ease-in, transform 120ms ease-in;
}
.pane-fwd-enter-from {
  opacity: 0;
  transform: translateX(32px);
}
.pane-fwd-leave-to {
  opacity: 0;
  transform: translateX(-16px);
}
.pane-back-enter-from {
  opacity: 0;
  transform: translateX(-32px);
}
.pane-back-leave-to {
  opacity: 0;
  transform: translateX(16px);
}
@media (prefers-reduced-motion: reduce) {
  .pane-fwd-enter-from,
  .pane-fwd-leave-to,
  .pane-back-enter-from,
  .pane-back-leave-to {
    transform: none;
  }
  .dots .ink {
    transition: none;
  }
}
</style>
