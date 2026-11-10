/**
 * J-01 registration and approval, J-08 admin approval (with admin MFA), J-11 password reset, and the
 * global behaviours around them (APD §2). @req A1 A2 A3 A5 A6 A9 TR-AUTH-9
 */
import { expect, type Page, test } from '@playwright/test'
import { SHOP, SIA } from './playwright.config'
import { activeCimhAccount, adminAccount, claimCode, IDENTITY, nextTotpWindow, PASSWORD, req, run, shopCompact, siaGo, totp } from './support'

/** Any Content-Security-Policy violation or uncaught page error fails the test (preview sends staging's CSP). */
let pageProblems: string[] = []
test.beforeEach(({ page }) => {
  pageProblems = []
  page.on('console', (m) => {
    if (m.type() === 'error' && /Content Security Policy/i.test(m.text())) pageProblems.push(`CSP: ${m.text().slice(0, 160)}`)
  })
  page.on('pageerror', (e) => pageProblems.push(`page error: ${e.message}`))
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
    await page.getByLabel('First name').fill('Mem')
    await page.getByLabel('Last name').fill('Ber')
    await page.getByLabel('Work email').fill(member)
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
    await page.getByLabel('Organisation').fill(org)
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
    await expect(page.getByText(/Good to see you/)).toBeVisible()

    await siaGo(page, 'Pending accounts', 'Admin') // SIA header: account pages sit in the Admin menu
    const row = page.getByRole('row', { name: new RegExp(member.replace(/\./g, '\\.')) })
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: 'Approve' }).click()

    const dialog = page.getByRole('dialog')
    await expect(dialog.getByText(org)).toBeVisible()
    await dialog.getByLabel('Create a new one').check()
    await expect(dialog.getByLabel('Organisation name')).toHaveValue(org)
    await dialog.getByRole('button', { name: 'Approve' }).click()
    await expect(page.getByText('Mem Ber approved')).toBeVisible()
    await expect(row).toHaveCount(0)
  })

  test('approved member logs in and reaches My requests (S-16 → S-10)', async ({ page }) => {
    await page.goto(`${SHOP}/requests`)
    await expect(page).toHaveURL(/\/login\?returnTo=(%2F|\/)requests/)
    await page.getByLabel('Email').fill(member)
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page).toHaveURL(/\/requests$/)
    await expect(page.getByRole('heading', { name: 'My requests' })).toBeVisible()
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
    await page.getByLabel('Email').fill(email)
    await page.getByRole('button', { name: 'Send reset code' }).click()
    await expect(page).toHaveURL(/\/reset-password\?email=/)

    await page.getByLabel('6-digit code').fill(await claimCode(email, 'reset_password'))
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
