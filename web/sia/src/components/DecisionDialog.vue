<script setup lang="ts">
/**
 * A-16 approve / deny one or several pending accounts (J-08).
 * Approve: link an organisation (suggested from the email domain or the organisation text; or create one)
 * and pick a role. Deny: a reason (emailed to the user). Several accounts → POST bulk-decision (207).
 *
 * Laid out on the dialog system (golden ratio, base.css): a plain head split φ : 1 (who, then the organisation
 * they gave), then one section per decision (Organisation, Role / Reason) with 17.8 px heads over hairlines, and a
 * footer that says who is emailed. Approve is never disabled for missing input: a press marks and focuses it.
 *
 * Motion (impeccable animate): the focal moment is the match landing. While the lookup runs the picker shows its
 * progress bar; when a match arrives the name settles into the field under a short Action Blue ring and the state
 * line beside "Organisation" swaps. On record ↔ New organisation swaps the panes out-in while the section's height
 * glides between them; the role's line swaps with the role. Reduced motion: no glide, swaps are instant.
 */
import {
  type AccountSummary,
  ApiError,
  call,
  checkForm,
  countries,
  identity,
  ifMatch,
  type Organisation,
  reason as reasonSchema,
  type Role,
  rule,
  useNotify,
} from '@cimh/web-app'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import OrganisationPicker from './OrganisationPicker.vue'
import SegmentedChoice from './SegmentedChoice.vue'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ accounts: AccountSummary[]; decision: 'approve' | 'deny' }>()
const emit = defineEmits<{ done: [okIds: string[]] }>()
const notify = useNotify()
const { xs } = useDisplay()

const formRef = ref()
const org = ref<Organisation | null>(null)
const suggested = ref<Organisation | null>(null)
const suggestedBy = ref<'domain' | 'name' | null>(null)
const looking = ref(false)
const orgMode = ref<'existing' | 'new'>('existing')
const createNew = computed(() => orgMode.value === 'new')
const newOrg = reactive({ name: '', country: 'BB', type: 'met_service' as Organisation['type'], domain: '' })
const role = ref<Role>('user')
const reason = ref('')
const busy = ref(false)
const failures = ref<{ name: string; message: string }[]>([])
/** The match just landed: drives the ring + settle on the picker; cleared when the ring ends (or the dialog reopens). */
const landed = ref(false)
/** The dialog has finished opening: a fast lookup beats the dialog's own entrance, so the ring waits for this. */
const entered = ref(false)
/** Two animation frames after a match: Vuetify floats the label one frame after the value is set, so the name
 * waits that long (in reduced motion it would otherwise paint over the unfloated label). */
const settling = ref(false)
const reduceQuery = typeof matchMedia !== 'undefined' ? matchMedia('(prefers-reduced-motion: reduce)') : null
/** Reduced motion: the swaps run without CSS (one frame, no blank between old and new) and the panes are not pinned. */
const still = ref(!!reduceQuery?.matches)
const onReduceChange = (e: MediaQueryListEvent) => (still.value = e.matches)
reduceQuery?.addEventListener('change', onReduceChange)
onBeforeUnmount(() => reduceQuery?.removeEventListener('change', onReduceChange))
function onLandEnd(e: AnimationEvent) {
  if (e.animationName.startsWith('dd-land')) landed.value = false
}

const single = computed(() => (props.accounts.length === 1 ? props.accounts[0] : null))
const domain = (email: string) => email.split('@')[1]?.toLowerCase() ?? ''
const fullName = (a: AccountSummary) => `${a.firstname} ${a.lastname}`
const ORG_TYPES = [
  { value: 'met_service', title: 'Meteorological service' },
  { value: 'hydro_service', title: 'Hydrological service' },
  { value: 'government', title: 'Government' },
  { value: 'academic', title: 'Academic' },
  { value: 'other', title: 'Other' },
]
const ORG_MODES = [
  { value: 'existing' as const, title: 'On record' },
  { value: 'new' as const, title: 'New organisation' },
]
const ROLES = [
  { value: 'user' as Role, title: 'Customer' },
  { value: 'staff' as Role, title: 'Staff' },
  { value: 'admin' as Role, title: 'Administrator' },
]
const ROLE_HINTS: Record<Role, string> = {
  user: 'Requests items in SHOP for their organisation.',
  staff: 'Works in SIA: requests, stock and products.',
  admin: 'Everything in SIA, accounts and settings included. Sets up MFA at first sign-in.',
}

async function suggest(a: AccountSummary) {
  suggested.value = null
  suggestedBy.value = null
  looking.value = true
  try {
    const byDomain = await call(() => identity.GET('/organisations', { params: { query: { emailDomain: domain(a.email), limit: 1 } } }))
    let match = byDomain.items[0]
    let by: 'domain' | 'name' = 'domain'
    if (!match && a.organisationText) {
      const byName = await call(() => identity.GET('/organisations', { params: { query: { q: a.organisationText ?? '', limit: 1 } } }))
      match = byName.items[0]
      by = 'name'
    }
    suggested.value = match ?? null
    suggestedBy.value = match ? by : null
    org.value = match ?? null
    orgMode.value = match ? 'existing' : 'new'
    if (match && open.value) {
      landed.value = true
      settling.value = true
      requestAnimationFrame(() => requestAnimationFrame(() => (settling.value = false)))
    }
  } catch (e) {
    notify.report(e)
  } finally {
    looking.value = false
  }
}

watch(open, (o) => {
  if (!o) return
  failures.value = []
  landed.value = false
  reason.value = ''
  role.value = 'user'
  org.value = null
  suggested.value = null
  suggestedBy.value = null
  const first = props.accounts[0]
  Object.assign(newOrg, { name: first?.organisationText ?? '', country: 'BB', type: 'met_service', domain: first ? domain(first.email) : '' })
  orgMode.value = 'existing'
  formRef.value?.resetValidation?.()
  if (props.decision === 'approve' && single.value) void suggest(single.value)
})

async function version(id: string): Promise<number> {
  return (await call(() => identity.GET('/admin/accounts/{accountId}', { params: { path: { accountId: id } } }))).version
}

async function organisationId(): Promise<string> {
  if (!createNew.value && org.value) return org.value.id
  const created = await call(() =>
    identity.POST('/organisations', {
      body: {
        name: newOrg.name.trim(),
        country: newOrg.country,
        type: newOrg.type,
        emailDomains: newOrg.domain.trim() ? [newOrg.domain.trim().toLowerCase()] : [],
      },
    }),
  )
  notify.toast(`Organisation “${created.name}” created`, 'success')
  return created.id
}

async function submit() {
  if (busy.value || !(await checkForm(formRef.value))) return
  busy.value = true
  failures.value = []
  try {
    const orgId = props.decision === 'approve' ? await organisationId() : undefined
    if (single.value) {
      const a = single.value
      const v = await version(a.id)
      const headers = { header: { 'If-Match': ifMatch(v) }, path: { accountId: a.id } }
      if (props.decision === 'approve')
        await call(() => identity.POST('/admin/accounts/{accountId}/approve', { params: headers, body: { organisationId: orgId!, role: role.value } }))
      else await call(() => identity.POST('/admin/accounts/{accountId}/deny', { params: headers, body: { reason: reason.value.trim() } }))
      notify.toast(`${fullName(a)} ${props.decision === 'approve' ? 'approved' : 'denied'}`, 'success')
      emit('done', [a.id])
      open.value = false
      return
    }
    const versions = await Promise.all(props.accounts.map((a) => version(a.id)))
    const res = await call(() =>
      identity.POST('/admin/accounts/bulk-decision', {
        body: {
          decisions: props.accounts.map((a, i) => ({
            accountId: a.id,
            version: versions[i]!,
            decision: props.decision,
            ...(props.decision === 'approve' ? { organisationId: orgId, role: role.value } : { reason: reason.value.trim() }),
          })),
        },
      }),
    )
    const ok = res.results.filter((r) => r.ok).map((r) => r.accountId)
    failures.value = res.results
      .filter((r) => !r.ok)
      .map((r) => {
        const a = props.accounts.find((x) => x.id === r.accountId)
        return { name: a ? fullName(a) : r.accountId, message: r.error?.detail ?? r.error?.title ?? 'Failed' }
      })
    notify.toast(`${ok.length} ${props.decision === 'approve' ? 'approved' : 'denied'}${failures.value.length ? `, ${failures.value.length} failed` : ''}`, failures.value.length ? 'warning' : 'success')
    emit('done', ok)
    if (!failures.value.length) open.value = false
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) notify.toast('One of these accounts was changed by someone else. The list has been reloaded.', 'warning')
    else notify.report(e)
    if (e instanceof ApiError && e.status === 409) emit('done', [])
  } finally {
    busy.value = false
  }
}

const approving = computed(() => props.decision === 'approve')
const title = computed(() => {
  const who = single.value ? fullName(single.value) : `${props.accounts.length} accounts`
  return `${approving.value ? 'Approve' : 'Deny'} ${who}`
})
/** Under the title: the address for one person; the names for several (three, then "and n more"). */
const sub = computed(() => {
  if (single.value) return single.value.email
  const names = props.accounts.map(fullName)
  return names.length > 3 ? `${names.slice(0, 3).join(', ')} and ${names.length - 3} more` : names.join(', ')
})
const given = computed(() => single.value?.organisationText?.trim() || '')
/** A long name (an airport address, say) would stack four lines in the narrow key column: it goes under the title. */
const longGiven = computed(() => given.value.length > 28)

/** Organisation section: where the suggestion came from, beside the head. */
const orgState = computed(() => {
  if (!single.value || createNew.value) return ''
  if (looking.value) return 'Looking for a match…'
  if (suggested.value && org.value?.id === suggested.value.id) return suggestedBy.value === 'domain' ? 'Matched by email domain' : 'Matched by name'
  if (!suggested.value) return 'No match on record'
  return ''
})
/** Why the suggestion was made, under the picker: a domain match is firm; a name match needs a look. */
const pickHint = computed(() => {
  const a = single.value
  const s = suggested.value
  if (!a || !s || org.value?.id !== s.id) return undefined
  return suggestedBy.value === 'domain'
    ? `${domain(a.email)} is on this organisation’s record.`
    : `Its name is close to “${a.organisationText}”. Check it is the same organisation.`
})
/* ---- On record ↔ New organisation: the panes cross-fade in place while the section's height glides from the old
   pane to the new one. The height is locked before Vue patches (pre-flush watch); the leaving pane is pinned where it
   stands (out of flow), so the new pane's height can be measured and tweened to. No blank beat between the two
   (an out-in swap left the box empty for ~150 ms and collapsed it before the picker came back).
   WAAPI is not cut by the global reduced-motion rule, so that path is checked here. */
const orgPane = ref<HTMLElement | null>(null)
let paneAnim: Animation | undefined
/** Stops a running glide without its handlers: a cancel event fires later and would clear the next lock. */
function stopPaneAnim() {
  if (!paneAnim) return
  paneAnim.onfinish = paneAnim.oncancel = null
  paneAnim.cancel()
  paneAnim = undefined
}
const reduced = () => still.value
watch(
  orgMode,
  () => {
    landed.value = false // leaving the picker ends its moment; coming back must not replay it
    const w = orgPane.value
    if (!w || reduced()) return
    const h = w.offsetHeight // mid-glide too: read before cancelling, or the box snaps back to the old lock
    stopPaneAnim()
    w.style.height = `${h}px`
    w.style.overflow = 'hidden'
  },
  { flush: 'pre' },
)
function pinPane(el: Element) {
  if (still.value) return
  const e = el as HTMLElement
  Object.assign(e.style, { position: 'absolute', top: `${e.offsetTop}px`, left: '0', width: `${e.offsetWidth}px` })
}
function growPane(el: Element) {
  const w = orgPane.value
  if (!w || !w.style.height) return
  const from = w.offsetHeight
  const to = (el as HTMLElement).offsetHeight
  const release = () => {
    w.style.height = ''
    w.style.overflow = ''
  }
  if (Math.abs(to - from) < 2) return release()
  paneAnim = w.animate([{ height: `${from}px` }, { height: `${to}px` }], { duration: 280, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' })
  paneAnim.onfinish = release
  paneAnim.oncancel = release
  // (stopPaneAnim drops both handlers, so a replaced glide never clears the lock of the one after it)
}

const footNote = computed(() => {
  const who = single.value ? single.value.firstname : 'each person'
  return approving.value ? `${single.value ? who : 'Each person'} is emailed that the account is active.` : `The reason goes in the email to ${who}.`
})
</script>

<template>
  <v-dialog
    v-model="open"
    max-width="600"
    content-class="dd-top"
    :fullscreen="xs"
    scrollable
    :persistent="busy"
    aria-labelledby="dd-title"
    @after-enter="entered = true"
    @after-leave="entered = false"
  >
    <v-card class="dd" :rounded="xs ? 0 : 'lg'">
      <header class="dlg-head" :class="{ solo: !given || longGiven }">
        <div class="dlg-who">
          <h2 id="dd-title" class="dlg-title">{{ title }}</h2>
          <p class="dlg-sub">{{ sub }}</p>
        </div>
        <dl v-if="given" class="dlg-key given" :class="{ long: longGiven }">
          <dt class="dlg-cap">Organisation given</dt>
          <dd class="given-name">{{ given }}</dd>
        </dl>
      </header>

      <v-card-text class="dd-body">
        <v-form ref="formRef" class="dd-form" @submit.prevent="submit">
          <template v-if="approving">
            <section class="sec" aria-labelledby="dd-org">
              <header class="sec-head">
                <h3 id="dd-org" class="sec-title">Organisation</h3>
                <!-- One live region that stays; the words inside it swap (a keyed live region would not announce). -->
                <span class="sec-state-slot" aria-live="polite">
                  <Transition name="dd-swap" mode="out-in" :css="!still">
                    <span v-if="orgState" :key="orgState" class="sec-state">{{ orgState }}</span>
                  </Transition>
                </span>
              </header>
              <div class="sec-body">
                <SegmentedChoice v-model="orgMode" name="dd-org-mode" label="Organisation on record or new" :options="ORG_MODES" />
                <div ref="orgPane" class="org-pane">
                  <Transition name="dd-pane" :css="!still" @before-leave="pinPane" @enter="growPane">
                    <div v-if="!createNew" key="existing" class="pane" :class="{ landed: landed && entered && !settling, waiting: landed && (!entered || settling) }" @animationend="onLandEnd">
                      <OrganisationPicker
                        v-model="org"
                        :busy="looking"
                        :initial-query="single?.organisationText ?? ''"
                        :rules="[(v: unknown) => !!v || 'Choose an organisation']"
                        :hint="pickHint"
                        :persistent-hint="!!pickHint"
                        hide-details="auto"
                      />
                    </div>
                    <div v-else key="new" class="pane">
                      <v-text-field v-model="newOrg.name" name="orgName" label="Organisation name" hide-details="auto" :rules="[(v: string) => !!v.trim() || 'Required']" />
                      <div class="pair">
                        <v-autocomplete v-model="newOrg.country" label="Country" hide-details :items="countries()" />
                        <v-select v-model="newOrg.type" label="Type" hide-details :items="ORG_TYPES" />
                      </div>
                      <v-text-field
                        v-model="newOrg.domain"
                        label="Email domain (optional)"
                        hide-details="auto"
                        hint="Suggests this organisation for future sign-ups from the same domain"
                        persistent-hint
                      />
                    </div>
                  </Transition>
                </div>
              </div>
            </section>

            <section class="sec" aria-labelledby="dd-role">
              <header class="sec-head">
                <h3 id="dd-role" class="sec-title">Role</h3>
              </header>
              <div class="sec-body">
                <SegmentedChoice v-model="role" name="dd-role" label="Role" :options="ROLES" />
                <p class="note role-note" aria-live="polite">
                  <Transition name="dd-swap" mode="out-in" :css="!still"><span :key="role">{{ ROLE_HINTS[role] }}</span></Transition>
                </p>
              </div>
            </section>
          </template>

          <section v-else class="sec" aria-labelledby="dd-reason">
            <header class="sec-head">
              <h3 id="dd-reason" class="sec-title">Reason</h3>
            </header>
            <div class="sec-body">
              <v-textarea v-model="reason" name="reason" label="Reason" rows="3" auto-grow counter="500" :rules="[rule(reasonSchema)]" />
            </div>
          </section>

          <Transition name="dd-swap" :css="!still">
            <v-alert v-if="failures.length" type="warning" variant="tonal" density="compact" class="fails">
              <div v-for="f in failures" :key="f.name">{{ f.name }}: {{ f.message }}</div>
            </v-alert>
          </Transition>
        </v-form>
      </v-card-text>

      <v-card-actions class="dd-foot">
        <p class="dd-note">{{ footNote }}</p>
        <div class="dd-btns">
          <v-btn variant="text" :disabled="busy" @click="open = false">Cancel</v-btn>
          <v-btn :color="approving ? 'primary' : 'error'" variant="flat" :loading="busy" @click="submit">
            {{ approving ? 'Approve' : 'Deny' }}
          </v-btn>
        </div>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style>
/* The dialog is anchored at the top instead of centred (motion review 2026-11-25): switching On record ↔ New
   organisation changes its height, and a centred dialog re-centred by ~50 px, moving the control just pressed.
   Unscoped: the overlay content is teleported. Phones are full screen and unaffected. */
.v-dialog:not(.v-dialog--fullscreen) > .v-overlay__content.dd-top {
  align-self: flex-start;
  margin-top: max(24px, 8vh);
  max-height: calc(100% - max(24px, 8vh) - 24px);
}
</style>

<style scoped>
/* Head: who φ : the organisation they gave 1. The given name is a fact to compare with the match below, so it reads
   at 17.8 px (a step under the title), right-aligned on the key line, and wraps rather than cuts. */
.given-name {
  margin: 2px 0 0;
  font-size: 17.8px;
  line-height: 1.382;
  font-weight: 600;
  overflow-wrap: anywhere;
  text-wrap: balance;
}
.given.long {
  text-align: left;
}
.given.long .given-name {
  font-size: 14px;
  line-height: 1.5;
  text-wrap: pretty;
}

.dd-body {
  padding: var(--f3) var(--f3) var(--f4);
}
.dd-form {
  display: flex;
  flex-direction: column;
}

/* Sections: a 17.8 px head over a hairline, 34 px between sections, 13 px inside. */
.sec + .sec {
  margin-top: var(--f4);
}
.sec-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 2px var(--f2);
  padding-bottom: var(--f1);
  border-bottom: 1px solid var(--dlg-rule);
}
.sec-title {
  margin: 0;
  font-size: 17.8px;
  line-height: 1.382;
  font-weight: 600;
}
.sec-state {
  font-size: 14px;
  line-height: 1.5;
  color: var(--dlg-muted);
  white-space: nowrap;
}
.sec-body {
  display: flex;
  flex-direction: column;
  gap: var(--f2);
  padding-top: var(--f2);
}
.sec-body > .seg {
  align-self: flex-start;
}
/* Country φ : type 1 would cut "Meteorological service"; the pair splits evenly, one column on phones. */
.org-pane {
  min-width: 0;
}
.pane {
  display: flex;
  flex-direction: column;
  gap: var(--f2);
}
.pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--f2);
}
.note {
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
  color: var(--dlg-muted);
}
.fails {
  margin-top: var(--f3);
}

/* Footer: who is emailed φ, the buttons 1. */
.dd-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--f2) var(--f3);
  border-top: 1px solid var(--dlg-rule);
}
.dd-note {
  flex: 1 1 0;
  min-width: 0;
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
  color: var(--dlg-muted);
}
.dd-btns {
  display: flex;
  gap: var(--f1);
  flex: none;
}

/* ---- Motion ---------------------------------------------------------------------------------------------- */
/* Small swaps (state line, role line, failures): out 90 ms ease-in, in 200 ms from 4 px below. */
.dd-swap-enter-active {
  transition:
    opacity 200ms var(--ease-out, cubic-bezier(0.16, 1, 0.3, 1)),
    transform 200ms var(--ease-out, cubic-bezier(0.16, 1, 0.3, 1));
}
.dd-swap-leave-active {
  transition:
    opacity 90ms ease-in,
    transform 90ms ease-in;
}
.dd-swap-enter-from {
  opacity: 0;
  transform: translateY(4px);
}
.dd-swap-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
.sec-state-slot,
.sec-state-slot > .sec-state,
.role-note > span {
  display: inline-block;
}
/* Pane swap (cross-fade): the old pane fades out in place in 120 ms; the new one settles in from 6 px over 240 ms,
   60 ms behind, while the height glides (280 ms), so the fields arrive into their room. */
.org-pane {
  position: relative;
}
.dd-pane-enter-active {
  transition:
    opacity 240ms 60ms var(--ease-out, cubic-bezier(0.16, 1, 0.3, 1)),
    transform 240ms 60ms var(--ease-out, cubic-bezier(0.16, 1, 0.3, 1));
}
.dd-pane-leave-active {
  transition: opacity 120ms ease-in;
}
.dd-pane-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.dd-pane-leave-to {
  opacity: 0;
}
/* Focal: the match lands. The field takes an Action Blue ring that spreads 0 → 5 px and fades (900 ms), and the
   chosen name settles in from 6 px to the left. */
.landed :deep(.v-field) {
  animation: dd-land 900ms var(--ease-out, cubic-bezier(0.16, 1, 0.3, 1)) both;
}
/* Until the dialog is open the name waits unseen, so it arrives once instead of showing, vanishing and settling. */
.waiting :deep(.v-autocomplete__selection) {
  opacity: 0;
}
.landed :deep(.v-autocomplete__selection) {
  animation: dd-settle 360ms var(--ease-out, cubic-bezier(0.16, 1, 0.3, 1)) both;
}
@keyframes dd-land {
  0% {
    box-shadow: 0 0 0 0 rgba(var(--v-theme-primary), 0.5);
  }
  35% {
    box-shadow: 0 0 0 5px rgba(var(--v-theme-primary), 0.3);
  }
  100% {
    box-shadow: 0 0 0 5px rgba(var(--v-theme-primary), 0);
  }
}
@keyframes dd-settle {
  from {
    opacity: 0;
    transform: translateX(-6px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

@media (max-width: 599.98px) {
  .dd-body {
    padding: var(--f3) var(--f2) var(--f4);
  }
  .pair {
    grid-template-columns: minmax(0, 1fr);
  }
  .dd-foot {
    flex-wrap: wrap;
  }
  .dd-note {
    flex-basis: 100%;
  }
  .dd-btns {
    margin-left: auto;
  }
  /* The given name sits under the title on phones (dlg-key turns into a baseline row there). */
  .given {
    flex-direction: column;
    align-items: flex-start;
    gap: 0;
  }
}
</style>
