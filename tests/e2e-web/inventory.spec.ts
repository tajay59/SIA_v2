/**
 * J-09 warehouse scanning, web parts (APD §6; P4 exit criterion). Staff register a site, a location and
 * shelves (A-08), print unit labels (A-12), stow (A-09), pick and relocate (A-10), look things up through the
 * header scan box (A-11), issue and return a unit (A-14) and read the history (A-15).
 * Scans are typed and submitted with Enter, as a handheld scanner does. @req I1 I2 I3 I4 I5 I6 I7 I8 I10
 */
import { expect, type Page, test } from '@playwright/test'
import { SIA } from './playwright.config'
import { apiProduct, mongo, PASSWORD, run, staffAccount } from './support'

const problems: string[] = []
test.beforeEach(({ page }) => {
  problems.length = 0
  page.on('console', (m) => {
    if (m.type() === 'error' && /Content Security Policy/i.test(m.text())) problems.push(`CSP: ${m.text().slice(0, 160)}`)
  })
  page.on('pageerror', (e) => problems.push(`page error: ${e.message}`))
})
test.afterEach(() => expect(problems).toEqual([]))

const siteName = `E2E site ${run}`
const bayName = `Bay ${run}`
const productName = `E2E anemometer ${run}`

async function login(page: Page, email: string) {
  await page.goto(`${SIA}/login`)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page).toHaveURL(`${SIA}/`) // the post-login redirect has happened
  await expect(page.getByRole('link', { name: 'Inventory' })).toBeVisible()
}
async function scanInto(page: Page, label: string, code: string) {
  const field = page.getByLabel(label, { exact: true })
  await field.fill(code)
  await field.press('Enter')
}

test.describe.serial('J-09 warehouse scanning (web)', () => {
  let staff = ''
  let productId = ''
  let shelves: string[] = []
  let units: string[] = []

  test.beforeAll(async () => {
    staff = await staffAccount('warehouse')
    productId = await apiProduct(staff, productName, 2)
  })

  test('register a site, a location and two shelves with QR codes (A-08)', async ({ page }) => {
    await login(page, staff)
    await page.getByRole('link', { name: 'Inventory' }).click()
    await page.getByRole('button', { name: /Location/ }).click()

    await page.getByRole('button', { name: 'Previous form' }).click() // Location → Site (legacy arrows)
    await page.getByLabel('Site name').fill(siteName)
    await page.getByRole('button', { name: 'Register site' }).click()
    await expect(page.getByText(`Site ${siteName} registered`)).toBeVisible()

    // The new site is preselected on the Location form.
    await page.getByLabel('Location name (store room, bay…)').fill(bayName)
    await page.getByRole('button', { name: 'Create location' }).click()
    await expect(page.getByText(`Location ${bayName} created`)).toBeVisible()

    await page.getByLabel('How many shelves').fill('2')
    await page.getByRole('button', { name: 'Add shelves' }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByText('Shelf 1', { exact: true })).toBeVisible()
    await expect(dialog.getByRole('img', { name: /QR code SHEL/ })).toHaveCount(2)
    await dialog.getByRole('button', { name: 'Close' }).click()

    shelves = mongo<string[]>(`
      const loc = db.misc.findOne({ kind: 'location', name: ${JSON.stringify(bayName)} });
      return db.misc.find({ kind: 'shelf', location: loc.id }).sort({ number: 1 }).toArray().map((s) => s.id);`)
    expect(shelves).toHaveLength(2)
    await page.getByRole('button', { name: new RegExp(siteName) }).click()
    await expect(page.getByText('2 shelves', { exact: true })).toBeVisible() // not the "2 shelves added" toast
  })

  test('create three unit labels for the product (A-12)', async ({ page }) => {
    await login(page, staff)
    await page.goto(`${SIA}/inventory?op=labels&product=${productId}`)
    await expect(page.getByRole('combobox', { name: 'Product' })).toHaveValue(productName)
    await page.getByLabel('Number of units').fill('3')
    await page.getByRole('button', { name: 'Create labels' }).click()
    await expect(page.getByText('3 units created')).toBeVisible()
    await expect(page.getByRole('img', { name: new RegExp(`QR code ${productId}_`) })).toHaveCount(3)
    await expect(page.getByRole('button', { name: 'Download CSV' })).toBeVisible()
    // document-svc made the label PDF (fail-soft: without it only the CSV/print path shows).
    await expect(page.getByRole('link', { name: 'Download PDF' })).toHaveAttribute('href', /\/files\/[^/]+$/)
    units = mongo<string[]>(`return db.storage.find({ product: ${JSON.stringify(productId)} }).sort({ barcode: 1 }).toArray().map((u) => u.barcode);`)
    expect(units).toHaveLength(3)
  })

  test('stow: scan a shelf, then units; wrong codes are explained (A-09)', async ({ page }) => {
    await login(page, staff)
    await page.getByRole('link', { name: 'Stow' }).click()
    await scanInto(page, 'Shelf', 'SHELnotashelf')
    await expect(page.getByText('No shelf with this code')).toBeVisible()
    await scanInto(page, 'Shelf', shelves[0]!)
    await expect(page.getByText('You have selected')).toBeVisible()
    await expect(page.getByText('Shelf 1', { exact: true })).toBeVisible()

    for (const u of units) await scanInto(page, 'Unit', u)
    await expect(page.getByText(`${productName} · ${bayName} · shelf 1`)).toHaveCount(3)
    await expect(page.getByText('3', { exact: true })).toBeVisible() // "3 stowed on this shelf"
    await scanInto(page, 'Unit', `NOPRODUCT${run}_00000000`) // <productId>_<code> of a product that does not exist
    await expect(page.getByText('No unit with this barcode')).toBeVisible()
  })

  test('pick with a reason; a second pick is refused (A-10)', async ({ page }) => {
    await login(page, staff)
    await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Pick' }).click()
    await page.getByRole('button', { name: /^Pick Take units/ }).click()
    await page.getByLabel('Reason').fill('Station repair')
    await scanInto(page, 'Unit', units[0]!)
    await expect(page.getByText(`${productName} · picked`)).toBeVisible()
    await scanInto(page, 'Unit', units[0]!)
    await expect(page.getByText('This unit was already picked')).toBeVisible()
  })

  test('header scan box → lookup; move a unit to shelf 2 (A-11)', async ({ page }) => {
    await login(page, staff)
    const box = page.getByRole('textbox', { name: 'Scan or type a unit, shelf or product code' })
    await box.fill(shelves[0]!)
    await box.press('Enter')
    await expect(page).toHaveURL(/op=lookup/)
    await expect(page.getByRole('heading', { name: `${bayName} · shelf 1` })).toBeVisible()
    await expect(page.getByText(productName, { exact: true })).toHaveCount(2) // units 2 and 3; unit 1 was picked

    await box.fill(units[1]!)
    await box.press('Enter')
    // Only the unit card has a Move button; once it shows, the shelf list (with its own chips) is gone.
    await expect(page.getByRole('button', { name: 'Move' })).toBeVisible()
    await expect(page.getByText('On shelf', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Move' }).click()
    await scanInto(page, 'New shelf', shelves[1]!)
    await expect(page.getByText(`${bayName} · shelf 2`)).toBeVisible()
  })

  test('issue a unit to a person, see it under Who has what, return it (A-14)', async ({ page }) => {
    await login(page, staff)
    await page.goto(`${SIA}/pick?op=issue`)
    await page.getByRole('combobox', { name: 'Issue to' }).fill('warehouse')
    await page.getByRole('option', { name: /warehouse/ }).first().click()
    await scanInto(page, 'Unit', units[2]!)
    await expect(page.getByText(/· with E2e warehouse/)).toBeVisible()

    await page.goto(`${SIA}/reports/assignments`)
    const row = page.getByRole('row', { name: new RegExp(units[2]!) })
    await expect(row).toContainText('E2e warehouse')
    await row.getByRole('button', { name: 'Return' }).click()
    await expect(page.getByText(/returned\. Stow it on a shelf/)).toBeVisible()
    await expect(page.getByRole('row', { name: new RegExp(units[2]!) })).toHaveCount(0)
  })

  test('history and stock reflect every scan (A-15, A-07 Stock)', async ({ page }) => {
    await login(page, staff)
    await page.goto(`${SIA}/reports/history`)
    await page.getByRole('textbox', { name: 'Unit code' }).fill(units[2]!)
    await page.getByRole('button', { name: 'Apply' }).click()
    const ops = page.locator('tbody tr td:nth-child(2)')
    await expect(ops).toHaveText(['Returned', 'Issued', 'Stowed'])

    await page.goto(`${SIA}/products/${productId}?tab=stock`)
    // unit 1 picked, unit 2 on shelf 2, unit 3 returned (off the shelf): 1 available ≤ alert at 2.
    await expect(page.getByText(/1 available · 0 reserved · 0 issued · 1 picked/)).toBeVisible()
    await expect(page.getByRole('link', { name: 'Shelf 2' })).toBeVisible()
    await page.goto(`${SIA}/reports/stock`)
    await expect(page.getByRole('link', { name: productName })).toBeVisible() // low stock
  })
})
