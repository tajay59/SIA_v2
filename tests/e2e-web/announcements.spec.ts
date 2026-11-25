/**
 * Announcements (plan 2026-11-23, A-22): an admin posts a message that appears at once, without a reload, at the
 * top of every SHOP page (catalog-push WebSocket), stays after a reload (stored), links to the product it is
 * about, can be closed when it is information, never when it is an alert, and leaves every page on End now.
 * axe on the banner and on A-22.
 */
import { expect, type Page, test } from '@playwright/test'
import { SHOP, SIA } from './playwright.config'
import { adminWithMfa, auditDialog, auditPart, CATALOG, IDENTITY, mongo, nextTotpWindow, siaCompact, orderableProduct, PASSWORD, req, run, shot, staffAccount, totp } from './support'

async function siaAdmin(page: Page): Promise<{ email: string }> {
  const admin = await adminWithMfa()
  await nextTotpWindow()
  await page.goto(`${SIA}/login`)
  await page.getByLabel('Email').fill(admin.email)
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Log in' }).click()
  await page.getByRole('textbox', { name: '6-digit code' }).fill(totp(admin.key))
  await expect(page.getByRole('heading', { name: /^Good (morning|afternoon|evening)/ })).toBeVisible()
  return admin
}

const banner = (page: Page) => page.getByRole('region', { name: 'Announcements' })
const row = (page: Page, text: string) => banner(page).locator('li', { hasText: text })

// A run that fails half-way must not leave its messages on every page of later specs.
test.afterEach(() => {
  mongo(`db.announcements.deleteMany({ message: { $regex: ${JSON.stringify(run)} } }); return true`)
})

test.describe('announcements: live banner on every page', () => {
  test('post, see it live on SHOP, product link, close, alert, end now', async ({ page, browser }) => {
    const staff = await staffAccount('ann')
    const pid = await orderableProduct(staff, `E2E banner radar ${run}`)
    await siaAdmin(page)

    // A visitor already has SHOP open (signed out): the banner must arrive without a reload.
    const visitorCtx = await browser.newContext({ viewport: page.viewportSize() ?? undefined })
    const shop = await visitorCtx.newPage()
    await shop.goto(`${SHOP}/catalogue`)
    await expect(shop.locator('#main')).toBeVisible()
    await shop.waitForLoadState('networkidle')

    await page.goto(`${SIA}/admin/announcements`)
    await expect(page.getByRole('heading', { name: 'Announcements', level: 1 })).toBeVisible()
    await page.getByRole('button', { name: 'New announcement' }).first().click()

    // Submit, then mark: Publish with nothing written says what is missing.
    await page.getByRole('button', { name: 'Publish' }).click()
    await expect(page.getByText('Write the message')).toBeVisible()

    const message = `New radar spares in stock ${run}`
    await page.getByRole('textbox', { name: 'Message', exact: true }).fill(message)
    // Choices are native radios inside segmented rows that may scroll sideways: click the visible segment.
    const choose = (group: string, option: string) => page.getByRole('radiogroup', { name: group }).locator('label', { hasText: option }).click()
    await choose('Shown on', 'SHOP')
    await choose('Link', 'A product')
    const picker = page.getByRole('combobox', { name: 'Product it is about' })
    await picker.fill(`banner radar ${run}`)
    await page.getByRole('option', { name: new RegExp(`E2E banner radar ${run}`) }).click()
    // The preview shows the row as SHOP will (four-up: SHOP light + dark reached, SIA dimmed).
    await expect(page.getByText(message).first()).toBeVisible()
    await expect(page.getByText('Not shown on SIA.')).toBeVisible()
    await shot(page, 'a22-editor')
    // Nothing wider than the screen (360 px: the save bar, then the record head, widened the layout viewport, so a
    // phone zoomed the page out; scrollWidth alone can't see that, the layout viewport's width can).
    const vw = page.viewportSize()!.width
    expect(await page.evaluate(() => [window.innerWidth, document.documentElement.scrollWidth])).toEqual([vw, vw])

    await page.getByRole('button', { name: 'Publish' }).click()
    const confirm = page.getByRole('dialog', { name: 'Publish to everyone now?' })
    await expect(confirm).toBeVisible()
    await auditDialog(page, 'announcement publish confirm')
    await confirm.getByRole('button', { name: 'Publish now' }).click()
    await expect(page.getByText('Published: everyone sees it now')).toBeVisible()
    // In the Live now list (narrow screens show the record alone: back to the list, then reopen it).
    if (siaCompact(page)) await page.getByRole('button', { name: 'All announcements' }).click()
    await expect(page.getByRole('link', { name: new RegExp(message) })).toBeVisible()
    await shot(page, 'a22-list')
    if (siaCompact(page)) await page.getByRole('link', { name: new RegExp(message) }).click()

    // SHOP, no reload: the banner arrives over the socket, with the product as its link.
    await expect(banner(shop).getByText(message)).toBeVisible({ timeout: 15_000 })
    await expect(row(shop, message).getByText('Information:')).toBeVisible()
    await auditPart(shop, 'section[aria-label="Announcements"]', 'banner (information)')
    await shot(shop, 'banner-shop', { fullPage: false })
    // Reload: still there (stored, first paint from the list).
    await shop.reload()
    await expect(banner(shop).getByText(message)).toBeVisible()
    // The link opens the product on SHOP.
    await row(shop, message).getByRole('link', { name: /E2E banner radar/ }).click()
    await expect(shop).toHaveURL(new RegExp(`/catalogue/${pid}$`))
    // Information can be closed, and stays closed after a reload.
    await row(shop, message).getByRole('button', { name: /^Close this information/ }).click()
    await expect(row(shop, message)).toHaveCount(0)
    await shop.reload()
    await expect(row(shop, message)).toHaveCount(0)

    // Turned into an alert (an edit): back for everyone, without a close button.
    await page.getByRole('radiogroup', { name: 'Tone' }).locator('label', { hasText: 'Alert' }).click()
    await expect(page.getByLabel(/alerts always stay/)).toBeDisabled()
    const save = page.getByRole('button', { name: 'Save changes' })
    await save.click()
    await page.getByRole('dialog', { name: 'Save for everyone now?' }).getByRole('button', { name: 'Save changes' }).click()
    await expect(row(shop, message).getByText('Alert:')).toBeVisible({ timeout: 15_000 })
    await expect(row(shop, message).getByRole('button', { name: /^Close/ })).toHaveCount(0)
    await auditPart(shop, 'section[aria-label="Announcements"]', 'banner (alert)')

    // End now: red confirm, and it leaves the open SHOP page.
    await page.getByRole('button', { name: 'End now…' }).click()
    await auditDialog(page, 'announcement end confirm')
    await page.getByRole('dialog', { name: 'End this announcement now?' }).getByRole('button', { name: 'End now' }).click()
    await expect(page.getByText('Ended: it has left every open page')).toBeVisible()
    await expect(row(shop, message)).toHaveCount(0, { timeout: 15_000 })
    await visitorCtx.close()
  })

  test('SIA-only message: staff see it, SHOP does not; ending it removes it live', async ({ page }) => {
    const admin = await adminWithMfa()
    await nextTotpWindow() // the MFA confirm spent this window's code
    const login = await req(`${IDENTITY}/api/identity/v1/auth/login`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ email: admin.email, password: PASSWORD, client: 'mobile', totp: totp(admin.key) }),
    })
    expect(login.status).toBe(200)
    const token = ((await login.json()) as { accessToken: string }).accessToken
    const auth = { Authorization: `Bearer ${token}`, 'content-type': 'application/json' }
    const message = `Stocktake Friday ${run}`
    const r = await req(`${CATALOG}/api/catalog/v1/admin/announcements`, {
      method: 'POST',
      headers: auth,
      body: JSON.stringify({ message, tone: 'INFO', audience: 'SIA', ttl: { preset: '1h' } }),
    })
    expect(r.status).toBe(201)
    const created = (await r.json()) as { id: string; version: number }

    await page.goto(`${SHOP}/`)
    await expect(page.locator('#main')).toBeVisible()
    await expect(row(page, message)).toHaveCount(0)

    const staff = await staffAccount('annsia')
    await page.goto(`${SIA}/login`)
    await page.getByLabel('Email').fill(staff)
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(row(page, message)).toBeVisible()
    await auditPart(page, 'section[aria-label="Announcements"]', 'SIA banner')
    await shot(page, 'banner-sia', { fullPage: false })

    // Ended through the API: the open SIA page drops it.
    const end = await req(`${CATALOG}/api/catalog/v1/admin/announcements/${created.id}`, {
      method: 'DELETE',
      headers: { ...auth, 'If-Match': `"${created.version}"` },
    })
    expect(end.status).toBe(204)
    await expect(row(page, message)).toHaveCount(0, { timeout: 15_000 })
  })
})
