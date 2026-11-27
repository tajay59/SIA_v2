/**
 * aria-invalid for every Vuetify field (audit 2026-11-26). Vuetify 4 marks a field that failed its rules or got
 * error-messages with the class `v-input--error` and links the message through aria-describedby, but never sets
 * aria-invalid, so screen readers do not say "invalid". One observer copies that state onto the field's own
 * input/textarea (never type=hidden), in both apps, for fields that exist now or mount later.
 * Six-box code fields (`v-otp-input`, reset audit 2026-11-26) are no `.v-input`: their boxes are `v-field`s that get
 * `v-field--error`, and the one real input is `.v-otp-input__input` (the boxes' own inputs are aria-hidden spacers).
 */
const FIELD = '.v-input'
const ERROR = 'v-input--error'
const CONTROLS = 'input:not([type=hidden]), textarea'
const OTP = '.v-otp-input'
const OTP_INPUT = '.v-otp-input__input'

function mark(control: Element, invalid: boolean): void {
  if (invalid) control.setAttribute('aria-invalid', 'true')
  else control.removeAttribute('aria-invalid')
}

function syncOtp(otp: Element): void {
  const input = otp.querySelector(OTP_INPUT)
  if (input) mark(input, !!otp.querySelector('.v-field--error'))
}

function sync(field: Element): void {
  const invalid = field.classList.contains(ERROR)
  field.querySelectorAll(CONTROLS).forEach((control) => {
    // Only the field's own controls: a nested field (rare) keeps its own state.
    if (control.closest(FIELD) !== field) return
    mark(control, invalid)
  })
}

export function installFieldInvalid(root: Node = document.body): void {
  if (typeof MutationObserver === 'undefined') return
  new MutationObserver((records) => {
    for (const r of records) {
      if (r.type === 'attributes') {
        const el = r.target as Element
        if (el.classList?.contains('v-input')) sync(el)
        else if (el.classList?.contains('v-field')) {
          const otp = el.closest(OTP)
          if (otp) syncOtp(otp)
        }
        continue
      }
      r.addedNodes.forEach((node) => {
        if (!(node instanceof Element)) return
        // A control can mount inside a field after the field (e.g. a slot that renders late).
        const owner = node.closest(FIELD)
        if (owner?.classList.contains(ERROR)) sync(owner)
        node.querySelectorAll(`.${ERROR}`).forEach(sync)
        const otp = node.closest(OTP)
        if (otp) syncOtp(otp)
        node.querySelectorAll(OTP).forEach(syncOtp)
      })
    }
  }).observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['class'] })
}
