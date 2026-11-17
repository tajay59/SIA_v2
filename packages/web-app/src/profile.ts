/**
 * Account/profile state and actions shared by SIA `ProfileView` (A-21) and the SHOP account page (S-19):
 * personal details (If-Match), addresses (max 10), change email (code to the new address), change password
 * (other sessions are signed out), data export, erasure request, log out. Submit handlers never rely on disabled
 * buttons: each form is checked on a press (`checkForm`).
 */
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError, call, identity, ifMatch } from './api'
import { downloadJson, exportFilename } from './download'
import { checkForm, type FormLike } from './form'
import { useNotify } from './notify'
import { useSession } from './session'
import type { ShippingAddress } from './types'

export const MAX_ADDRESSES = 10

export function useProfile(afterLogout: string) {
  const session = useSession()
  const notify = useNotify()
  const router = useRouter()

  const account = computed(() => session.account)
  const details = reactive({ firstname: '', lastname: '', phone: '', department: '', country: '' })
  const detailsForm = ref<FormLike | null>(null)
  const saving = ref(false)
  const errors = ref<Record<string, string>>({})

  function fill() {
    const a = account.value
    if (!a) return
    Object.assign(details, {
      firstname: a.firstname,
      lastname: a.lastname,
      phone: a.phone ?? '',
      department: a.department ?? '',
      country: a.country ?? '',
    })
  }
  watch(account, fill, { immediate: true })
  /** True when the details form differs from the saved account. */
  const detailsDirty = computed(() => {
    const a = account.value
    if (!a) return false
    return (
      details.firstname !== a.firstname ||
      details.lastname !== a.lastname ||
      details.phone !== (a.phone ?? '') ||
      details.department !== (a.department ?? '') ||
      details.country !== (a.country ?? '')
    )
  })

  async function patch(body: Record<string, unknown>, okText: string): Promise<boolean> {
    const a = account.value
    if (!a) return false
    saving.value = true
    errors.value = {}
    try {
      const updated = await call(() =>
        identity.PATCH('/me', { params: { header: { 'If-Match': ifMatch(a.version) } }, body: body as never }),
      )
      session.set(updated)
      notify.toast(okText, 'success')
      return true
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) errors.value = e.fieldErrors()
      notify.report(e, { retry: () => void session.load(true) })
      return false
    } finally {
      saving.value = false
    }
  }

  async function saveDetails(): Promise<boolean> {
    if (saving.value || !(await checkForm(detailsForm.value))) return false
    return patch(
      {
        firstname: details.firstname.trim(),
        lastname: details.lastname.trim(),
        phone: details.phone.trim() || null,
        department: details.department.trim() || null,
        country: details.country || null,
      },
      'Profile saved',
    )
  }

  // ---- addresses
  const addresses = computed<ShippingAddress[]>(() => (account.value?.addresses ?? []) as ShippingAddress[])
  const addrOpen = ref(false)
  const addrIndex = ref<number | null>(null)
  function editAddress(i: number | null) {
    addrIndex.value = i
    addrOpen.value = true
  }
  function saveAddress(a: ShippingAddress) {
    const list = [...addresses.value]
    if (addrIndex.value === null) list.push(a)
    else list[addrIndex.value] = a
    void patch({ addresses: list }, 'Address saved')
  }
  /** Index of the address waiting for a confirm. */
  const removing = ref<number | null>(null)
  async function removeAddress() {
    const i = removing.value
    if (i === null || saving.value) return
    await patch({ addresses: addresses.value.filter((_, j) => j !== i) }, 'Address removed')
    removing.value = null
  }

  // ---- email change
  const emailOpen = ref(false)
  const emailStep = ref<'request' | 'verify'>('request')
  const newEmail = ref('')
  const emailPassword = ref('')
  const emailForm = ref<FormLike | null>(null)
  const emailBusy = ref(false)
  const emailError = ref<string | null>(null)
  function openEmail() {
    emailStep.value = 'request'
    newEmail.value = ''
    emailPassword.value = ''
    emailError.value = null
    emailOpen.value = true
  }
  async function requestEmail() {
    if (emailBusy.value || !(await checkForm(emailForm.value))) return
    emailBusy.value = true
    emailError.value = null
    try {
      await call(() => identity.POST('/me/email', { body: { newEmail: newEmail.value.trim(), password: emailPassword.value } }))
      emailStep.value = 'verify'
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) emailError.value = 'Your password is not correct.'
      else if (e instanceof ApiError && e.status === 422) emailError.value = e.message
      else notify.report(e)
    } finally {
      emailBusy.value = false
    }
  }
  async function emailVerified() {
    emailOpen.value = false
    await session.load(true)
    notify.toast('Email address changed', 'success')
  }

  // ---- password change
  const pwOpen = ref(false)
  const pw = reactive({ current: '', next: '', confirm: '' })
  const pwForm = ref<FormLike | null>(null)
  const pwBusy = ref(false)
  const pwErrors = ref<Record<string, string>>({})
  function openPassword() {
    Object.assign(pw, { current: '', next: '', confirm: '' })
    pwErrors.value = {}
    pwOpen.value = true
  }
  async function changePassword() {
    if (pwBusy.value || !(await checkForm(pwForm.value))) return
    pwBusy.value = true
    pwErrors.value = {}
    try {
      await call(() => identity.POST('/me/password', { body: { currentPassword: pw.current, newPassword: pw.next } }))
      pwOpen.value = false
      notify.toast('Password changed. Your other sessions were signed out.', 'success')
    } catch (e) {
      if (e instanceof ApiError && e.status === 401 && e.code === 'INVALID_CREDENTIALS')
        pwErrors.value = { currentPassword: 'Your current password is not correct.' }
      else if (e instanceof ApiError && e.status === 422)
        pwErrors.value =
          e.code === 'PASSWORD_BREACHED'
            ? { newPassword: 'This password appears in known data breaches. Choose another one.' }
            : e.fieldErrors()
      else notify.report(e)
    } finally {
      pwBusy.value = false
    }
  }

  // ---- your data (TR-PRIV-1)
  const exporting = ref(false)
  async function downloadMyData() {
    exporting.value = true
    try {
      const body = await call(() => identity.GET('/me/export'))
      downloadJson(body, exportFilename('cimh-my-data', body.generatedAt))
    } catch (e) {
      notify.report(e)
    } finally {
      exporting.value = false
    }
  }
  const eraseOpen = ref(false)
  const erasePassword = ref('')
  const eraseForm = ref<FormLike | null>(null)
  const eraseBusy = ref(false)
  const eraseError = ref<string | null>(null)
  function openErase() {
    erasePassword.value = ''
    eraseError.value = null
    eraseOpen.value = true
  }
  async function requestErasure() {
    if (eraseBusy.value || !(await checkForm(eraseForm.value))) return
    eraseBusy.value = true
    eraseError.value = null
    try {
      await call(() => identity.POST('/me/erasure-request', { body: { password: erasePassword.value } }))
      eraseOpen.value = false
      await session.load(true)
      notify.toast('Request sent. An administrator will erase your account.', 'success')
    } catch (e) {
      if (e instanceof ApiError && e.status === 401 && e.code === 'INVALID_CREDENTIALS') eraseError.value = 'Your password is not correct.'
      else notify.report(e)
    } finally {
      eraseBusy.value = false
    }
  }

  async function logout() {
    await session.logout()
    await router.push(afterLogout)
  }

  const organisation = computed(() => {
    const a = account.value
    if (!a) return ''
    if (a.organisationId) return a.organisationName ?? a.organisationText ?? 'Linked'
    if (a.organisationText) return `${a.organisationText} (waiting to be linked by an administrator)`
    return a.isCimh ? 'CIMH' : 'Not set'
  })
  const roleLabel = computed(() => {
    const r = account.value?.role
    return r === 'user' ? 'Customer' : r === 'staff' ? 'Staff' : 'Administrator'
  })

  return {
    session,
    account,
    details,
    detailsForm,
    detailsDirty,
    saving,
    errors,
    fill,
    saveDetails,
    addresses,
    addrOpen,
    addrIndex,
    editAddress,
    saveAddress,
    removing,
    removeAddress,
    emailOpen,
    emailStep,
    newEmail,
    emailPassword,
    emailForm,
    emailBusy,
    emailError,
    openEmail,
    requestEmail,
    emailVerified,
    pwOpen,
    pw,
    pwForm,
    pwBusy,
    pwErrors,
    openPassword,
    changePassword,
    exporting,
    downloadMyData,
    eraseOpen,
    erasePassword,
    eraseForm,
    eraseBusy,
    eraseError,
    openErase,
    requestErasure,
    logout,
    organisation,
    roleLabel,
  }
}
