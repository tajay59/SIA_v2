/**
 * J-01 registration and approval, J-08 admin approval (with admin MFA), J-11 password reset, and the
 * global behaviours around them (APD §2). @req A1 A2 A3 A5 A6 A9 TR-AUTH-9
 */
import { expect, type Page, test } from '@playwright/test'
import { SHOP, SIA } from './playwright.config'
import { activeCimhAccount, adminAccount, claimCode, IDENTITY, isRealPageError, nextTotpWindow, PASSWORD, req, run, shopCompact, siaGo, totp } from './support'

/** Any Content-Security-Policy violation or uncaught page error fails the test (preview sends staging's CSP). */
let pageProblems: string[] = []
test.beforeEach(({ page }) => {
  pageProblems = []
  page.on('console', (m) => {
    if (m.type() === 'error' && /Content Security Policy/i.test(m.text())) pageProblems.push(`CSP: ${m.text().slice(0, 160)}`)
  })
  page.on('pageerror', (e) => isRealPageError(e) && pageProblems.push(`page error: ${e.message}`))
})
test.afterEach(() => {
  expect(pageProblems).toEqual([])
})

/** Vuetify's code input: six visual boxes over one real textbox (named by aria-label). */
async function typeCode(page: Page, code: string) {
  await page.getByRole('textbox', { name: '6-digit code' }).fill(code)
}

async function siaLogin(page: Page, email: string) {
  await page.goto(`${SIA}/login`)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Log in' }).click()
}

test.describe.serial('J-01 registration → admin approval → first login', () => {
  const member = `member.${run}@example.org`
  const org = `E2E Met Service ${run}`
  let adminEmail = ''
  let mfaKey = ''

  test('visitor signs up and verifies the email (S-13 → S-14 → S-15)', async ({ page }) => {
    await page.goto(`${SHOP}/signup`)
    // Sign-up is three steps on the visitor pass. Continue is never disabled: an empty step is marked field
    // by field and the first field gets the cursor.
    await page.getByRole('button', { name: 'Continue' }).click()
    await expect(page.getByLabel('First name')).toBeFocused()
    await expect(page).toHaveURL(/\/signup/)
    await page.getByLabel('First name').fill('Mem')
    await page.getByLabel('Last name').fill('Ber')
    await page.getByLabel('Work email').fill(member)
    await page.getByRole('button', { name: 'Continue' }).click()
    await expect(page.getByRole('heading', { name: 'Organisation' })).toBeVisible()
    // Each step opens with the cursor in its first field (it fell to <body> while the panes swapped), inside a
    // group named by the step (so the field is found by its role: the group shares its name).
    const orgField = page.getByRole('textbox', { name: 'Organisation' })
    const password = page.locator('input[name=password]')
    await expect(orgField).toBeFocused()
    await expect(page.getByRole('group', { name: 'Organisation' })).toBeVisible()
    await page.getByRole('button', { name: 'Back' }).click()
    await expect(page.getByLabel('First name')).toBeFocused()
    await page.getByRole('button', { name: 'Continue' }).click()
    await expect(orgField).toBeFocused()
    await page.getByRole('button', { name: 'Continue' }).click()
    await expect(page.getByText('Enter your organisation')).toBeVisible()
    await orgField.fill(org)
    await page.getByRole('button', { name: 'Continue' }).click()
    await expect(page.getByRole('heading', { name: 'Password' })).toBeVisible()
    await expect(password).toBeFocused()
    await page.getByRole('button', { name: 'Create account' }).click()
    await expect(page.getByText('Please accept the terms')).toBeVisible()
    await password.fill(PASSWORD)
    await page.getByLabel(/I agree/).check()
    await page.getByRole('button', { name: 'Create account' }).click()

    await expect(page).toHaveURL(/\/verify\?email=/)
    await expect(page.getByText(member)).toBeVisible()
    await typeCode(page, await claimCode(member))
    await expect(page).toHaveURL(/\/pending-approval$/)
    await expect(page.getByRole('heading', { name: /email is verified/ })).toBeVisible()
  })

  test('member cannot log in before approval (APD §2)', async ({ page }) => {
    await page.goto(`${SHOP}/login`)
    await page.getByLabel('Email').fill(member)
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page).toHaveURL(/\/pending-approval$/)
  })

  test('new admin must turn on MFA first (TR-AUTH-9)', async ({ page }) => {
    adminEmail = await adminAccount()
    await siaLogin(page, adminEmail)
    await expect(page).toHaveURL(/\/mfa-setup$/)
    mfaKey = (await page.locator('code.key').innerText()).replace(/\s/g, '')
    expect(mfaKey).toMatch(/^[A-Z2-7]{16,}$/)
    await typeCode(page, totp(mfaKey))
    await expect(page).toHaveURL(/\/login\?notice=mfa-enabled/)
    await expect(page.getByText('Two-step verification is on')).toBeVisible()
  })

  test('admin logs in with a code and approves the member, creating the organisation (A-16, J-08)', async ({ page }) => {
    await nextTotpWindow() // the confirm step used the current window; replays are refused
    await siaLogin(page, adminEmail)
    await expect(page.getByText('Enter the code from your authenticator app')).toBeVisible()
    await typeCode(page, totp(mfaKey))
    await expect(page.getByRole('heading', { name: /^Good (morning|afternoon|evening)/ })).toBeVisible()

    await siaGo(page, 'Pending accounts', 'Admin') // SIA header: account pages sit in the Admin menu
    const row = page.getByRole('listitem', { name: new RegExp(member.replace(/\./g, '\\.')) })
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: 'Approve' }).click()

    const dialog = page.getByRole('dialog')
    await expect(dialog.getByText(org)).toBeVisible()
    await dialog.getByLabel('New organisation').check()
    await expect(dialog.getByLabel('Organisation name')).toHaveValue(org)
    await dialog.getByRole('button', { name: 'Approve' }).click()
    await expect(page.getByText('Mem Ber approved')).toBeVisible()
    await expect(row).toHaveCount(0)
  })

  test('a code used a moment ago is told apart from a wrong one (2026-11-25)', async ({ page }) => {
    await nextTotpWindow()
    const code = totp(mfaKey)
    await siaLogin(page, adminEmail)
    await typeCode(page, code)
    await expect(page.getByRole('heading', { name: /^Good (morning|afternoon|evening)/ })).toBeVisible()
    // Signed out and back in with the same code (same 30 s window): refused, and the page says to wait for the next.
    await page.context().clearCookies()
    await siaLogin(page, adminEmail)
    await typeCode(page, code)
    await expect(page.getByText('That code was just used. Wait for the next code (it changes every 30 seconds).')).toBeVisible()
  })

  test('approved member logs in and reaches My requests (S-16 → S-10)', async ({ page }) => {
    await page.goto(`${SHOP}/requests`)
    await expect(page).toHaveURL(/\/login\?returnTo=(%2F|\/)requests/)
    await page.getByLabel('Email').fill(member)
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page).toHaveURL(/\/requests$/)
    await expect(page.getByRole('heading', { name: 'Orders', exact: true })).toBeVisible()
  })

  test('customers opening SIA see "staff only" (APD §2)', async ({ page }) => {
    await page.goto(`${SIA}/login`)
    await page.getByLabel('Email').fill(member)
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page.getByRole('heading', { name: 'This app is for CIMH staff' })).toBeVisible()
  })
})

test.describe('J-11 password reset', () => {
  test('forgot → code → new password → log in with it; old password refused', async ({ page }) => {
    const email = await activeCimhAccount('reset')
    const newPassword = `a brand new password ${run}`
    await page.goto(`${SHOP}/login`)
    await page.getByRole('link', { name: 'Forgot password?' }).click()
    // Sign-in pages change with a View Transition: wait for the new page before typing (else the old field gets it).
    await expect(page).toHaveURL(/\/forgot-password/)
    await page.waitForFunction(() => !document.getAnimations().some((x) => String((x.effect as KeyframeEffect | null)?.pseudoElement ?? '').startsWith('::view-transition')))
    // The SHOP route transition can still hold the leaving page's field: type until the new field keeps the address.
    await expect(async () => {
      await page.getByLabel('Email').fill(email)
      await expect(page.getByLabel('Email')).toHaveValue(email, { timeout: 500 })
    }).toPass({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Send reset code' }).click()
    await expect(page).toHaveURL(/\/reset-password\?email=/)

    await page.getByRole('textbox', { name: '6-digit code' }).fill(await claimCode(email, 'reset_password'))
    await page.getByLabel('New password', { exact: true }).fill(newPassword)
    await page.getByLabel('Repeat new password', { exact: true }).fill(newPassword)
    await page.getByRole('button', { name: 'Change password' }).click()
    await expect(page).toHaveURL(/\/login\?notice=password-changed/)
    await expect(page.getByText('Password changed')).toBeVisible()

    await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page.getByText('Email or password is incorrect.')).toBeVisible()

    await page.getByLabel('Password', { exact: true }).fill(newPassword)
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page).toHaveURL(`${SHOP}/`)
    if (shopCompact(page)) {
      await page.getByRole('button', { name: 'Menu' }).click() // phones: the account sits in the bottom-bar menu
      await expect(page.getByText('Log out')).toBeVisible()
    } else {
      await expect(page.getByRole('button', { name: 'E2e' })).toBeVisible()
    }
  })
})

test.describe('S-17 forgot password: what stops it', () => {
  // Audit 2026-11-26: a 429 was only a toast in seconds; the outage banner's Try again did nothing.
  for (const [app, base] of [['SHOP', SHOP], ['SIA', SIA]] as const) {
    test(`${app}: blank field, rate limit on the form, outage banner resends`, async ({ page }) => {
      const email = `nobody.forgot.${run}@example.org`
      await page.goto(`${base}/forgot-password`)
      const field = page.getByRole('textbox', { name: 'Email' })
      await expect(field).toBeFocused()
      await expect(field).toHaveAttribute('name', 'email')
      await expect(field).toHaveAttribute('autocomplete', 'username')
      const send = page.getByRole('button', { name: 'Send reset code' })

      await send.click()
      await expect(page.getByText('Enter your email address')).toBeVisible() // asked for, not "invalid"
      await expect(field).toBeFocused()

      await page.route('**/auth/password/forgot', (r) =>
        r.fulfill({ status: 429, headers: { 'content-type': 'application/problem+json', 'retry-after': '120' }, body: JSON.stringify({ title: 'Too many requests', code: 'RATE_LIMITED' }) }),
      )
      await field.fill(email)
      await send.click()
      await expect(page.getByRole('alert').filter({ hasText: 'Too many attempts. Try again in 2 minutes.' })).toBeVisible()
      await expect(page).toHaveURL(/\/forgot-password/)
      await expect(page.locator('.v-snackbar')).toHaveCount(0) // on the form, not a passing toast
      await page.unroute('**/auth/password/forgot')

      // Outage: the banner says nothing was sent; its Try again sends the same address again.
      let calls = 0
      await page.route('**/auth/password/forgot', (r) => (++calls === 1 ? r.abort('internetdisconnected') : r.continue()))
      await send.click()
      const banner = page.getByRole('alert').filter({ hasText: 'The service is unavailable right now. No code was sent.' })
      await expect(banner).toBeVisible()
      await expect(page.getByText('Too many attempts.')).toHaveCount(0) // the earlier message is cleared on a new press
      await banner.getByRole('button', { name: 'Try again' }).click()
      await expect(page).toHaveURL(/\/reset-password\?email=/)
      expect(calls).toBe(2)
    })
  }
})

test.describe('S-18 reset password: what stops it', () => {
  // Audit 2026-11-26: a wrong code was said at the top with the cursor on the button; a refused password used up
  // the code; too many wrong codes read as "expired"; the outage banner's Try again did nothing; a bad address
  // from the link failed silently.
  for (const [app, base] of [['SHOP', SHOP], ['SIA', SIA]] as const) {
    test(`${app}: code answers under the boxes, refused password keeps the code, outage retry`, async ({ page }) => {
      const email = await activeCimhAccount(`reset18${app.toLowerCase()}`)
      await req(`${IDENTITY}/api/identity/v1/auth/password/forgot`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      const good = await claimCode(email, 'reset_password')
      await page.goto(`${base}/reset-password?email=${encodeURIComponent(email)}`)
      const box = page.getByRole('textbox', { name: '6-digit code' })
      await expect(box).toBeFocused()
      await expect(page.getByText('It is valid for 15 minutes.')).toBeVisible()
      // Password managers get the account with the new password; "Send a new code" keeps the address.
      await expect(page.locator('input[autocomplete=username]')).toHaveValue(email)
      await expect(page.getByRole('link', { name: 'Send a new code' })).toHaveAttribute('href', `/forgot-password?email=${email}`) // vue-router leaves @ as is

      const pw = `a fresh reset password ${run}`
      await page.locator('input[name=new-password]').fill(pw)
      await page.locator('input[name=confirm-password]').fill(pw)
      const change = page.getByRole('button', { name: 'Change password' })

      // Wrong code: said under the boxes, boxes marked and emptied, cursor back in the first box.
      await box.fill(good === '000000' ? '111111' : '000000')
      await change.click()
      const message = page.getByRole('alert').filter({ hasText: 'That code is not right. Check the email and try again.' })
      await expect(message).toBeVisible()
      await expect(box).toHaveValue('')
      await expect(box).toBeFocused()
      await expect(box).toHaveAttribute('aria-invalid', 'true')
      await expect(box).toHaveAttribute('aria-describedby', (await message.getAttribute('id'))!)
      await box.pressSequentially('1')
      await expect(message).toHaveCount(0) // goes once the code changes
      await expect(box).not.toHaveAttribute('aria-invalid', 'true')

      // A breached password (dev has the breach check off: stubbed), then an outage, then the same code works.
      let calls = 0
      await page.route('**/auth/password/reset', (r) => {
        calls++
        if (calls === 1)
          return r.fulfill({
            status: 422,
            headers: { 'content-type': 'application/problem+json' },
            body: JSON.stringify({ title: 'Breached', status: 422, code: 'PASSWORD_BREACHED' }),
          })
        if (calls === 2) return r.abort('internetdisconnected')
        return r.continue()
      })
      await box.fill(good)
      await change.click()
      await expect(page.getByText('This password appears in known data breaches. Choose another one.')).toBeVisible()
      await expect(page.locator('input[name=new-password]')).toBeFocused()
      await expect(box).toHaveValue(good) // the code stays: identity checks the password before using up the code
      const next = `another fresh password ${run}`
      await page.locator('input[name=new-password]').fill(next)
      await page.locator('input[name=confirm-password]').fill(next)
      await change.click()
      const banner = page.getByRole('alert').filter({ hasText: 'The service is unavailable right now. Your password was not changed.' })
      await expect(banner).toBeVisible()
      await banner.getByRole('button', { name: 'Try again' }).click()
      await expect(page).toHaveURL(/\/login\?notice=password-changed/)
      expect(calls).toBe(3)
    })

    test(`${app}: too many wrong codes, a bad address from the link, no address`, async ({ page }) => {
      const email = await activeCimhAccount(`reset18b${app.toLowerCase()}`)
      await req(`${IDENTITY}/api/identity/v1/auth/password/forgot`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      const good = await claimCode(email, 'reset_password')
      const bad = good === '000000' ? '111111' : '000000'
      await page.goto(`${base}/reset-password?email=${encodeURIComponent(email)}`)
      const box = page.getByRole('textbox', { name: '6-digit code' })
      const pw = `a fresh reset password ${run}`
      await page.locator('input[name=new-password]').fill(pw)
      await page.locator('input[name=confirm-password]').fill(pw)
      const change = page.getByRole('button', { name: 'Change password' })
      for (let i = 0; i < 5; i++) {
        await box.fill(bad)
        await change.click()
        await expect(page.getByText('That code is not right.')).toBeVisible()
      }
      await box.fill(good) // right, but too late: five wrong codes used it up
      await change.click()
      const spent = page.getByRole('alert').filter({ hasText: 'Too many wrong codes. This one no longer works.' })
      await expect(spent).toBeVisible()
      await expect(spent.getByRole('link', { name: 'Send a new code' })).toHaveAttribute('href', `/forgot-password?email=${email}`) // vue-router leaves @ as is

      // An address the server can't read: the Email field comes back with the message and the cursor.
      await page.goto(`${base}/reset-password?email=foo`)
      await page.getByRole('textbox', { name: '6-digit code' }).fill('123456')
      await page.locator('input[name=new-password]').fill(pw)
      await page.locator('input[name=confirm-password]').fill(pw)
      await page.getByRole('button', { name: 'Change password' }).click()
      const field = page.getByRole('textbox', { name: 'Email' })
      await expect(field).toBeFocused()
      await expect(field).toHaveValue('foo')
      await expect(page.getByText('Enter a valid email address')).toBeVisible()

      // No address in the link: the cursor starts in Email, which has a name.
      await page.goto(`${base}/reset-password`)
      await expect(page.getByRole('textbox', { name: 'Email' })).toBeFocused()
      await expect(page.getByRole('textbox', { name: 'Email' })).toHaveAttribute('name', 'email')
      await expect(page.getByText('Codes are valid for 15 minutes.')).toBeVisible()
      await expect(page.getByRole('link', { name: 'Send a new code' })).toHaveAttribute('href', '/forgot-password')
    })
  }
})

test.describe('global behaviour', () => {
  test('unverified account logging in is sent to verify (APD §2)', async ({ page }) => {
    const email = `unverified.${run}@example.org`
    await req(`${IDENTITY}/api/identity/v1/auth/register`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ firstname: 'Un', lastname: 'Verified', email, password: PASSWORD, organisationText: 'X', country: 'BB' }),
    })
    await page.goto(`${SHOP}/login`)
    await page.getByLabel('Email').fill(email)
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page).toHaveURL(/\/verify\?email=/)
  })

  test('guarded SHOP page sends visitors to login with returnTo', async ({ page }) => {
    await page.goto(`${SHOP}/account`)
    await expect(page).toHaveURL(/\/login\?returnTo=(%2F|\/)account/)
  })

  test('unknown page shows Not found', async ({ page }) => {
    await page.goto(`${SHOP}/no-such-page`)
    await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible()
  })
})

test('a locked account says when it unlocks (2026-11-25)', async ({ page }) => {
  const email = await activeCimhAccount(`locked`)
  await page.goto(`${SIA}/login`)
  await page.getByLabel('Email').fill(email)
  for (let i = 0; i < 5; i++) {
    await page.getByLabel('Password', { exact: true }).fill('Not-the-password-1!')
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page.getByText('Email or password is incorrect.')).toBeVisible()
  }
  // The fifth failure locked it: now even the right password is refused, with the time left (15 min lock).
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page.getByText('Too many failed attempts. Try again in 15 minutes.')).toBeVisible()
})
