/**
 * Order journeys (APD §6; P5 exit criterion) through SHOP and SIA on the dev stack:
 *   J-02 browse → cart → submit (mixed cart → paid + Pro Bono requests)       S-03, S-07…S-09
 *   J-05 staff quoting (stock check, supplier price + CIMH option, send)     A-02, A-03, A-04
 *   J-03 customer chooses, downloads the agreement, uploads it signed, accepts  S-10…S-12
 *   J-06 staff verify the signature, pick the reserved units, ship, deliver   A-03, A-10
 *   J-04 customer follows it to delivery                                        S-11
 *   J-07 Pro Bono: approve, pick, ship, deliver
 * Real infrastructure end to end: the agreement PDF comes from document-consumer, the signed copy is uploaded to
 * document-svc, reservations and file attachments travel over Kafka.
 * @req O1 O2 O3 O4 O5 O5a O6 O6a O7 O8 O9 O10 O11 O12 O14
 */
import { expect, type Page, test } from '@playwright/test'
import { SHOP, SIA } from './playwright.config'
import { auditDialog, customerAccount, isRealPageError, mongo, orderableProduct, PASSWORD, run, shot, siaGo, staffAccount, stowUnits } from './support'

const problems: string[] = []
test.beforeEach(({ page }) => {
  problems.length = 0
  page.on('pageerror', (e) => isRealPageError(e) && problems.push(`page error: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error' && /Content Security Policy/i.test(m.text())) problems.push(`CSP: ${m.text().slice(0, 160)}`)
  })
})
test.afterEach(() => expect(problems).toEqual([]))

const paidName = `E2E barometer ${run}`
const proName = `E2E rain gauge ${run}`

async function shopLogin(page: Page, email: string) {
  await page.goto(`${SHOP}/login`)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page.getByRole('link', { name: 'Orders', exact: true }).first()).toBeVisible()
}
async function siaLogin(page: Page, email: string) {
  await page.goto(`${SIA}/login`)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page).toHaveURL(`${SIA}/`)
}
async function scanInto(page: Page, label: string, code: string) {
  const field = page.getByLabel(label, { exact: true })
  await field.fill(code)
  await field.press('Enter')
}

test.describe.serial('J-02…J-07 requests, quotes, agreements, fulfilment', () => {
  let staff = ''
  let customer = ''
  let paidId = ''
  let proId = ''
  let paidUnits: string[] = []
  let proUnits: string[] = []
  let paidRequest = ''
  let proRequest = ''

  test.beforeAll(async () => {
    staff = await staffAccount('desk')
    customer = await customerAccount('buyer')
    paidId = await orderableProduct(staff, paidName, { cost: '150.00' })
    proId = await orderableProduct(staff, proName, { probono: true, cap: 2 })
    paidUnits = await stowUnits(staff, paidId, 2)
    proUnits = await stowUnits(staff, proId, 1)
    // A saved address on the profile (S-19), offered at checkout.
    const addr = { line1: '1 Husbands Road', city: 'St James', country: 'BB', firstname: 'Cass', lastname: 'Tomer',
      email: customer, organisation: 'E2E Met Office' }  // prettier-ignore
    mongo(`db.accounts.updateOne({ email: ${JSON.stringify(customer)} }, { $set: { addresses: [${JSON.stringify(addr)}] } }); return true`)
  })

  test('J-02 customer adds paid and Pro Bono items and submits two requests', async ({ page }) => {
    await shopLogin(page, customer)
    await page.goto(`${SHOP}/catalogue/${paidId}`)
    await page.getByRole('button', { name: 'More' }).click() // qty 2
    await page.getByRole('button', { name: 'Add to cart' }).click()
    await expect(page.getByText(`Added 2 × ${paidName} to your cart`)).toBeVisible()
    await page.goto(`${SHOP}/catalogue/${proId}`)
    await page.getByRole('button', { name: 'Add to cart' }).click()
    await expect(page.getByText(`Added 1 × ${proName} to your cart`)).toBeVisible()

    await page.getByRole('link', { name: /Cart, 3 items/ }).click()
    await expect(page.getByText(paidName)).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Pro Bono items' })).toBeVisible()
    await expect(page.getByText('Paid and Pro Bono items become two requests.')).toBeVisible()
    await shot(page, 'shop-cart')
    await expect(page.getByText(/BBD|150\.00/)).toHaveCount(0) // no prices before the quote

    await expect(page.getByRole('heading', { name: 'Items to be quoted' })).toBeVisible()
    await page.getByRole('button', { name: 'Continue to invoice' }).click()
    await expect(page.getByRole('heading', { name: 'Who is the quote made out to?' })).toBeFocused()
    await page.getByRole('button', { name: 'Continue to delivery' }).click()
    await page.getByLabel('Notes for CIMH (optional)').fill('Needed for the hurricane season')
    await expect(page.getByText('Barbados dollars (BBD)')).toBeVisible() // every quote is in BBD
    await shot(page, 'shop-review')
    await page.getByRole('button', { name: 'Send request' }).click()
    await expect(page.getByRole('heading', { name: 'Requests sent' })).toBeVisible()
    await shot(page, 'shop-sent')
    paidRequest = (await page.locator('li', { hasText: /^\s*Request/ }).getByRole('link').textContent())!.trim()
    proRequest = (await page.locator('li', { hasText: 'Pro Bono request' }).getByRole('link').textContent())!.trim()
    expect(paidRequest).toMatch(/^ORD/)
    expect(proRequest).toMatch(/^ORD/)
    await expect(page.getByRole('link', { name: /Cart, 0 items/ })).toBeVisible()
  })

  test('J-05 staff start quoting and send a quote with a CIMH-stock option', async ({ page }) => {
    await siaLogin(page, staff)
    await siaGo(page, 'Orders')
    await page.getByRole('textbox', { name: 'Request id, customer or organisation' }).fill(paidRequest)
    const row = page.getByRole('option', { name: new RegExp(paidRequest.slice(-6)) }) // the queue shows ORD…last6
    await row.focus()
    await row.press('Enter') // opens beside the list (desk) or full screen (phone)
    await expect(page.getByText('Needed for the hurricane season')).toBeVisible()
    await page.getByRole('button', { name: 'Start quoting' }).click()
    await expect(page.getByRole('cell', { name: 'Full quantity' })).toBeVisible() // 2 units on the shelf

    await page.getByRole('link', { name: 'Build quote' }).click()
    await page.getByRole('button', { name: 'Add supplier' }).click()
    await page.getByLabel('Supplier name').fill('Campbell Scientific')
    await page.getByRole('checkbox', { name: 'Offer' }).check()
    await page.getByRole('combobox', { name: `Supplier for ${paidName}` }).click({ force: true }) // Vuetify hides the real input
    await page.getByRole('option', { name: 'Campbell Scientific' }).click()
    await page.getByLabel(`Unit price for ${paidName}`).fill('180.00')
    await expect(page.getByText('Draft saved')).toBeVisible()
    await page.getByRole('button', { name: 'Send quote' }).click()
    // Nothing is emailed before the confirm, which restates the recipient and the total.
    const confirm = page.getByRole('dialog')
    await expect(confirm).toContainText('Quote version')
    await auditDialog(page, 'send-quote')
    await confirm.getByRole('button', { name: 'Email the customer' }).click()
    await expect(page.getByText('Quote version 1 sent to the customer')).toBeVisible()
    await expect(page.getByText('Quoted', { exact: true }).first()).toBeVisible()
  })

  test('J-03 customer chooses CIMH stock, signs the agreement and accepts', async ({ page }) => {
    await shopLogin(page, customer)
    await page.getByRole('link', { name: 'Orders', exact: true }).first().click()
    // The quote leads the list under "Waiting for you", named by the item, with its expiry.
    const waiting = page.getByRole('region', { name: 'Waiting for you' })
    await expect(waiting.getByText('Quote ready')).toBeVisible()
    await expect(waiting.getByText(paidName)).toBeVisible()
    await expect(waiting.getByText(/valid until .* days left/)).toBeVisible()
    await shot(page, 'shop-requests-docket')
    await page.getByRole('link', { name: new RegExp(paidRequest.slice(-6)) }).click() // the list shows ORD…last6
    await expect(page.getByRole('heading', { name: paidName })).toBeVisible()
    // Table cells on wide screens, line cards on phones.
    await expect(page.getByText(/360\.00/).locator('visible=true').first()).toBeVisible() // supplier 2 × 180.00
    await expect(page.getByText(/300\.00/).locator('visible=true').first()).toBeVisible() // CIMH 2 × 150.00
    await page.getByRole('link', { name: 'Choose options' }).click()

    await page.getByRole('radio', { name: /300\.00/ }).check()
    await expect(page.getByText(/Total for your choices/).locator('visible=true').first()).toBeVisible()
    await shot(page, 'shop-agreement-choose')
    await page.getByRole('button', { name: 'Confirm choices' }).click()
    await expect(page.getByText('Preparing the agreement…')).toBeVisible()
    // order.agreement_requested → document-consumer renders the PDF → document.generated → order-consumer.
    // The page polls every 3 s until the file is attached.
    const download = page.getByRole('link', { name: 'Download agreement' })
    await expect(download).toBeVisible({ timeout: 45_000 })
    // The customer may download it (document-svc asks order-svc), and it is a real PDF.
    const pdf = await page.request.get(new URL((await download.getAttribute('href')) as string, page.url()).toString())
    expect(pdf.status()).toBe(200)
    expect((await pdf.body()).subarray(0, 5).toString()).toBe('%PDF-')

    // The real upload: type sniffed, scanned, stored, attached at once so the quote can be accepted.
    await page.getByRole('button', { name: 'I have signed it' }).click()
    await page.locator('input[type=file]').setInputFiles({ name: 'signed.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4 signed\n%%EOF\n') })
    await page.getByRole('button', { name: 'Accept quote' }).click()
    // Ends on the request page: a lasting banner says what CIMH does next, and the chosen option is marked.
    await expect(page.getByText('Quote accepted', { exact: true })).toBeVisible()
    await expect(page.getByText(/CIMH staff now check the signature/)).toBeVisible()
    await expect(page.getByText('Accepted', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('Chosen').locator('visible=true')).toHaveCount(1)
    await expect(page.getByText('Agreement total').locator('visible=true').first()).toBeVisible()
    await shot(page, 'shop-request-accepted')
  })

  test('J-06 staff verify, pick the reserved units, ship and deliver', async ({ page }) => {
    await siaLogin(page, staff)
    await page.goto(`${SIA}/requests/${paidRequest}`)
    // order.accepted → inventory reserves over Kafka → stock.reserved → the line shows the units.
    await expect(async () => {
      await page.reload()
      await expect(page.getByText('Reserved', { exact: true })).toBeVisible({ timeout: 2000 })
    }).toPass({ timeout: 45_000 })
    await page.getByRole('button', { name: 'Verify and purchase' }).click()
    await page.getByLabel(/signed by an authorised person/).check()
    await shot(page, 'sia-verify')
    await page.getByRole('button', { name: 'Start purchasing' }).click()
    await expect(page.getByText('Signature verified; purchasing')).toBeVisible()

    await page.getByRole('main').getByRole('link', { name: 'Pick', exact: true }).click()
    await expect(page).toHaveURL(/op=order/)
    await expect(page.getByText('0 / 2')).toBeVisible()
    for (const u of paidUnits) await scanInto(page, 'Unit', u)
    await expect(page.getByText('Everything is picked.')).toBeVisible()
    await page.getByRole('link', { name: 'Record the shipment' }).click()

    await page.getByRole('button', { name: 'Record shipment' }).click()
    await page.getByLabel('Hand delivery').check()
    await page.getByLabel('Delivered by / collected by').fill('Collected by Cass')
    await shot(page, 'sia-ship-dialog')
    await page.getByRole('dialog').getByRole('button', { name: 'Record shipment' }).click()
    await expect(page.getByText('Shipment recorded')).toBeVisible()
    await page.getByRole('button', { name: 'Mark delivered' }).click()
    await page.getByLabel('Invoice number (optional)').fill(`INV-${run}`)
    await page.getByRole('dialog').getByRole('button', { name: 'Mark delivered' }).click()
    await expect(page.getByText('Marked delivered')).toBeVisible()
  })

  test('J-04 customer sees the request delivered', async ({ page }) => {
    await shopLogin(page, customer)
    await page.goto(`${SHOP}/requests/${paidRequest}`)
    await expect(page.getByRole('region', { name: 'Where it stands' }).getByText('Delivered', { exact: true })).toBeVisible()
    await expect(page.getByText('Collected by Cass')).toBeVisible()
    await shot(page, 'shop-request-delivered')
    await expect(page.locator('.items li', { hasText: 'From CIMH stock' })).toBeVisible() // the line's choice
  })

  test('J-07 Pro Bono: approve, pick, ship with tracking, deliver', async ({ page }) => {
    await siaLogin(page, staff)
    await page.goto(`${SIA}/requests/${proRequest}`)
    await page.getByRole('button', { name: 'Approve' }).click()
    await expect(page.getByText('Approved; stock is being reserved')).toBeVisible()
    await page.getByRole('main').getByRole('link', { name: 'Pick', exact: true }).click()
    await expect(page).toHaveURL(/op=order/)
    await expect(async () => {
      await page.reload()
      await expect(page.getByText(proUnits[0]!)).toBeVisible({ timeout: 2000 })
    }).toPass({ timeout: 45_000 })
    await scanInto(page, 'Unit', proUnits[0]!)
    await expect(page.getByText('Everything is picked.')).toBeVisible()
    await page.getByRole('link', { name: 'Record the shipment' }).click()
    await page.getByRole('button', { name: 'Record shipment' }).click()
    await page.getByLabel('Tracking number').fill('JD014600006281')
    await page.getByRole('dialog').getByRole('button', { name: 'Record shipment' }).click()
    await expect(page.getByText('Shipment recorded')).toBeVisible()
    await page.getByRole('button', { name: 'Mark delivered' }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Mark delivered' }).click()
    await expect(page.getByText('Marked delivered')).toBeVisible()

    await page.context().clearCookies()
    await shopLogin(page, customer)
    await page.goto(`${SHOP}/requests/${proRequest}`)
    await expect(page.getByRole('link', { name: /JD014600006281/ })).toHaveAttribute('href', /dhl\.com/)
  })
})
