/**
 * Submit, then mark (critique plan step 4): submit buttons stay enabled; the handler runs every rule, each
 * missing or wrong field shows its message, and the cursor goes to the first one. A disabled button could
 * not say which field was missing.
 */
export interface FormLike {
  validate: () => Promise<{ valid: boolean; errors: { id: number | string; errorMessages: string[] }[] }>
}

/** Run a `v-form`'s rules. False = something is marked; the first marked field has the focus. */
export async function checkForm(form: FormLike | null | undefined): Promise<boolean> {
  if (!form) return true
  const { valid, errors } = await form.validate()
  if (valid) return true
  const first = errors[0]
  // Vuetify reports a field by its `name` when it has one, otherwise by the input's id.
  const key = first ? String(first.id) : ''
  const el =
    first && typeof document !== 'undefined'
      ? (document.getElementById(key) ?? document.querySelector<HTMLElement>(`[name="${CSS.escape(key)}"]`))
      : null
  if (el) {
    // A radio group or checkbox reports its wrapper: the cursor goes to the first control inside.
    const control = el.matches('input, textarea, select, button') ? el : (el.querySelector<HTMLElement>('input, textarea, select, button') ?? el)
    el.scrollIntoView({ block: 'center' })
    control.focus({ preventScroll: true })
  }
  return false
}
