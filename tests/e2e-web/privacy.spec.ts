/**
 * Personal-data rights (TR-PRIV-1, BSD §8): a member downloads their data and asks to be deleted; an admin
 * finds the request, erases the account, and the old login stops working. @req TR-PRIV-1
 */
import { expect, type Page, test } from '@playwright/test'
import { SHOP, SIA } from './playwright.config'
import { activeCimhAccount, adminWithMfa, nextTotpWindow, PASSWORD, totp } from './support'

const problems: string[] = []
test.beforeEach(({ page }) => {
  problems.length = 0
  page.on('console', (m) => {
    if (m.type() === 'error' && /Content Security Policy/i.test(m.text())) problems.push(`CSP: ${m.text().slice(0, 160)}`)
  })
  page.on('pageerror', (e) => problems.push(`page error: ${e.message}`))
})
test.afterEach(() => expect(problems).toEqual([]))

async function shopLogin(page: Page, email: string) {
  await page.goto(`${SHOP}/login`)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Log in' }).click()
}

test.describe.serial('personal data: export and erasure', () => {
  let member = ''

  test('member downloads their data and asks to be deleted (S-19)', async ({ page }) => {
    member = await activeCimhAccount('erase')
    await shopLogin(page, member)
    await expect(page).toHaveURL(`${SHOP}/`)
    await page.goto(`${SHOP}/account`)

    const download = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Download' }).click()
    const file = await download
    expect(file.suggestedFilename()).toMatch(/^cimh-my-data-\d{4}-\d{2}-\d{2}\.json$/)
    const body = JSON.parse(await (await import('node:fs/promises')).readFile(await file.path(), 'utf-8'))
    expect(body.sections.identity.account.email).toBe(member)

    await page.getByRole('button', { name: 'Ask to delete' }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByLabel('Your password', { exact: true }).fill('not my password at all')
    await dialog.getByRole('button', { name: 'Ask to delete' }).click()
    await expect(dialog.getByText('Your password is not correct.')).toBeVisible()
    await dialog.getByLabel('Your password', { exact: true }).fill(PASSWORD)
    await dialog.getByRole('button', { name: 'Ask to delete' }).click()
    await expect(page.getByText('Request sent. An administrator will erase your account.')).toBeVisible()
    await expect(page.getByText(/You asked for this on/)).toBeVisible()
  })

  test('admin finds the request and erases the account (A-17)', async ({ page }) => {
    const admin = await adminWithMfa()
    await nextTotpWindow() // the confirm step used the current window
    await page.goto(`${SIA}/login`)
    await page.getByLabel('Email').fill(admin.email)
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
    await page.getByRole('button', { name: 'Log in' }).click()
    await page.getByRole('textbox', { name: '6-digit code' }).fill(totp(admin.key))
    await expect(page.getByRole('heading', { name: /Good to see you/ })).toBeVisible()

    await page.goto(`${SIA}/admin/accounts?erasure=1`)
    const row = page.getByRole('row', { name: new RegExp(member.replace(/\./g, '\.')) })
    await expect(row.getByText('Delete requested')).toBeVisible()
    await row.getByRole('link').click()
    await expect(page.getByText(/asked to be deleted on/)).toBeVisible()

    await page.getByRole('button', { name: 'Erase', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByLabel('Reason')).toHaveValue('Asked by the account holder')
    await expect(dialog.getByRole('button', { name: 'Erase account' })).toBeDisabled()
    await dialog.getByLabel('Type the email address to confirm').fill(member)
    await dialog.getByRole('button', { name: 'Erase account' }).click()
    await expect(page.getByText('Account erased')).toBeVisible()
    await expect(page).toHaveURL(/\/admin\/accounts$/)
  })

  test('the erased login no longer works', async ({ page }) => {
    await shopLogin(page, member)
    await expect(page.getByText('Email or password is incorrect.')).toBeVisible()
  })
})
