/**
 * J-10 product with images (staff, APD §6) and what customers then see in SHOP (S-02/S-03/S-04/S-06):
 * Pro Bono badge and limit, photos, never a price or staff fields. @req C4 C5 C6 C7
 */
import path from 'node:path'
import { expect, test } from '@playwright/test'
import { SHOP, SIA } from './playwright.config'
import { PASSWORD, run, staffAccount } from './support'

const problems: string[] = []
test.beforeEach(({ page }) => {
  problems.length = 0
  page.on('console', (m) => {
    if (m.type() === 'error' && /Content Security Policy/i.test(m.text())) problems.push(`CSP: ${m.text().slice(0, 160)}`)
  })
  page.on('pageerror', (e) => problems.push(`page error: ${e.message}`))
})
test.afterEach(() => expect(problems).toEqual([]))

const name = `E2E rain gauge kit ${run}`
const fixtures = path.join(__dirname, 'fixtures') + path.sep

test.describe.serial('J-10 product with images → SHOP', () => {
  let productUrl = ''

  test('staff create a Pro Bono product and add photos (A-05 → A-06 → A-07)', async ({ page }) => {
    test.setTimeout(150_000)
    const staff = await staffAccount('catalogue')
    await page.goto(`${SIA}/login`)
    await page.getByLabel('Email').fill(staff)
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
    await page.getByRole('button', { name: 'Log in' }).click()
    await page.getByRole('link', { name: 'Products' }).click()
    await page.getByRole('link', { name: 'New product' }).click()

    await page.getByLabel('Name', { exact: true }).fill(name)
    await page.getByRole('combobox', { name: 'Type' }).click({ force: true }) // Vuetify keeps the real input visually hidden
    await page.getByRole('option', { name: /\(PRO\)/ }).click()
    await page.getByRole('combobox', { name: 'Department' }).fill('Hydrology')
    await page.getByLabel('Model number').fill('RG-E2E')
    await page.getByLabel('Cost (BBD, staff only)').fill('125')
    // Pro Bono has no default: the item can't be created until someone chooses (PRD C5).
    await expect(page.getByRole('button', { name: 'Create product' })).toBeDisabled()
    await page.getByRole('radio', { name: 'Yes' }).check()
    await page.getByLabel('Max per request (optional)').fill('2')
    await page.getByRole('button', { name: 'Create product' }).click()

    await expect(page).toHaveURL(/\/products\/PRO[0-9a-f]{32}\?tab=images/)
    productUrl = page.url().replace(SIA, '').split('?')[0]!
    await page.getByLabel('Photos to upload').setInputFiles([`${fixtures}photo-a.jpg`, `${fixtures}photo-b.png`])
    // Processing tiles, then the photos from media-worker (polling).
    await expect(page.getByRole('button', { name: 'Remove photo' })).toHaveCount(2, { timeout: 90_000 })
    await expect(page.getByText('Primary', { exact: true })).toHaveCount(1)
    await page.getByRole('button', { name: 'Make primary' }).click()
    await expect(page.getByRole('button', { name: 'Make primary' })).toHaveCount(1)
    await expect(page.getByRole('tab', { name: 'Images (2)' })).toBeVisible()
  })

  test('customers find it in Pro Bono and search, with photos and its limit but no price', async ({ page }) => {
    await page.goto(`${SHOP}/pro-bono`)
    const card = page.getByRole('link', { name: new RegExp(name) })
    await expect(card).toBeVisible()
    await expect(card.getByText('Pro Bono')).toBeVisible()

    await page.goto(`${SHOP}/search?q=${encodeURIComponent(name)}`)
    await page.getByRole('link', { name: new RegExp(name) }).first().click()
    await expect(page).toHaveURL(`${SHOP}/catalogue${productUrl.replace('/products', '')}`)
    await expect(page.getByRole('heading', { level: 1, name })).toBeVisible()
    await expect(page.getByText('Pro Bono · max 2 per request')).toBeVisible()
    await expect(page.getByRole('button', { name: /Photo 1 of 2/ })).toBeVisible()
    const img = page.locator('.stage-img')
    await expect(img).toHaveJSProperty('complete', true)
    expect(await img.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0)
    await expect(page.getByText(/BBD|125\.00/)).toHaveCount(0) // customers never see cost
    await expect(page.getByRole('link', { name: 'Log in to request' })).toBeVisible()
  })
})
