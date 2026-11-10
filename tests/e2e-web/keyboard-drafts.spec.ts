/**
 * P7: SIA keyboard shortcuts (Design Brief: `/` search, `s` scan box, `g r` Requests) and unsaved form
 * data surviving a session expiry (APD §2: kept in session storage, restored after logging back in).
 */
import { expect, type Page, test } from '@playwright/test'
import { SIA } from './playwright.config'
import { isRealPageError, PASSWORD, run, staffAccount } from './support'

const problems: string[] = []
test.beforeEach(({ page }) => {
  problems.length = 0
  page.on('pageerror', (e) => isRealPageError(e) && problems.push(`page error: ${e.message}`))
})
test.afterEach(() => expect(problems).toEqual([]))

async function login(page: Page, email: string, from = `${SIA}/login`) {
  if (from) await page.goto(from)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Log in' }).click()
}

test.describe('SIA keyboard and drafts', () => {
  let staff = ''
  test.beforeAll(async () => {
    staff = await staffAccount('keys')
  })

  test('shortcuts: g r opens Requests, / focuses its search, s the scan box', async ({ page }, info) => {
    test.skip(info.project.name === 'mobile', 'phones have no hardware keyboard')
    await login(page, staff)
    await expect(page).toHaveURL(`${SIA}/`)
    await page.locator('body').click({ position: { x: 5, y: 300 } }) // focus the page, not a field
    await page.keyboard.press('g')
    await page.keyboard.press('r')
    await expect(page).toHaveURL(/\/requests/)
    await page.keyboard.press('/')
    await expect(page.getByRole('textbox', { name: 'Request id, customer or organisation' })).toBeFocused()
    // Typing in a field never triggers shortcuts.
    await page.keyboard.type('gr s')
    await expect(page).toHaveURL(/\/requests/)
    await page.keyboard.press('Escape')
    await page.locator('h1').first().click()
    await page.keyboard.press('s')
    await expect(page.getByRole('textbox', { name: 'Scan or type a unit, shelf or product code' })).toBeFocused()
  })

  test('a new product survives the session ending; logout clears it', async ({ page, context }) => {
    const name = `E2E draft thermometer ${run}`
    await login(page, staff)
    await expect(page).toHaveURL(`${SIA}/`)
    await page.goto(`${SIA}/products/new`)
    await page.getByLabel('Name', { exact: true }).fill(name)
    await page.getByLabel('Model number').fill('TH-DRAFT')
    await page.waitForTimeout(500) // the draft is written 300 ms after typing stops

    await context.clearCookies() // the session ends (refresh token gone)
    await page.reload()
    await expect(page).toHaveURL(/\/login\?returnTo=/)
    await login(page, staff, '')
    await expect(page).toHaveURL(`${SIA}/products/new`)
    await expect(page.getByText('Your unsaved changes were restored.')).toBeVisible()
    await expect(page.getByLabel('Name', { exact: true })).toHaveValue(name)
    await expect(page.getByLabel('Model number')).toHaveValue('TH-DRAFT')

    const left = await page.evaluate(() => Object.keys(sessionStorage).filter((k) => k.startsWith('cimh:draft:')))
    expect(left).toEqual(['cimh:draft:product:new'])
    await page.getByRole('button', { name: /E2e/ }).click()
    await page.getByText('Log out').click()
    await expect(page).toHaveURL(/\/login/)
    const after = await page.evaluate(() => Object.keys(sessionStorage).filter((k) => k.startsWith('cimh:draft:')))
    expect(after).toEqual([])
  })
})
