/**
 * Order journeys (APD §6; P5 exit criterion) through SHOP and SIA on the dev stack:
 *   J-02 browse → cart → submit (mixed cart → paid + Pro Bono requests)       S-03, S-07…S-09
 *   J-05 staff quoting (stock check, one source per line, shipping, send)    A-02, A-03, A-04
 *   J-03 customer views and signs: checks the quote, downloads the agreement,
 *        uploads it signed ("view and sign", 2026-11-17)                       S-10…S-12
 *   J-06 staff verify the signature, pick the reserved units, ship, deliver   A-03, A-10
 *   J-04 customer follows it to delivery                                        S-11
 *   J-07 Pro Bono: approve, pick, ship, deliver
 * Real infrastructure end to end: the agreement PDF comes from document-consumer, the signed copy is uploaded to
 * document-svc, reservations and file attachments travel over Kafka.
 * @req O1 O2 O3 O4 O5 O5a O6 O6a O7 O8 O9 O10 O11 O12 O14
 */
import { expect, type Page, test } from '@playwright/test'
import { SHOP, SIA } from './playwright.config'
import { auditDialog, auditPart, customerAccount, isRealPageError, mongo, onePagePdf, orderableProduct, PASSWORD, run, shot, siaGo, staffAccount, stowUnits } from './support'

const problems: string[] = []
test.beforeEach(({ page }) => {
  problems.length = 0
  page.on('pageerror', (e) => isRealPageError(e) && problems.push(`page error: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error' && /Content Security Policy/i.test(m.text())) problems.push(`CSP: ${m.text().slice(0, 160)}`)
  })
})
test.afterEach(() => expect(problems).toEqual([]))

/** In the browser: page 1 shows logo blue (#0084C8) in its top 3% and none in its bottom 5% (not mirrored). */
function blueBandAtTop(c: HTMLCanvasElement): boolean {
  const ctx = c.getContext('2d')
  if (!ctx || !c.width || !c.height) return false
  const blue = (from: number, to: number) => {
    const y = Math.floor(c.height * from)
    const d = ctx.getImageData(0, y, c.width, Math.max(1, Math.floor(c.height * to) - y)).data
    let n = 0
    for (let i = 0; i < d.length; i += 4) if (d[i] < 60 && d[i + 1] > 100 && d[i + 1] < 170 && d[i + 2] > 160) n++
    return n
  }
  return blue(0, 0.03) > c.width && blue(0.95, 1) === 0
}

const paidName = `E2E barometer ${run}`
const proName = `E2E rain gauge ${run}`
// Not in stock: quoted by a supplier, ordered by CIMH and shipped to the customer directly (its own parcel).
const supName = `E2E pyranometer ${run}`

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
  let supId = ''
  let paidUnits: string[] = []
  let proUnits: string[] = []
  let paidRequest = ''
  let proRequest = ''

  test.beforeAll(async () => {
    staff = await staffAccount('desk')
    customer = await customerAccount('buyer')
    paidId = await orderableProduct(staff, paidName, { cost: '150.00' })
    proId = await orderableProduct(staff, proName, { probono: true, cap: 2 })
    supId = await orderableProduct(staff, supName, { cost: '90.00' })
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
    await page.goto(`${SHOP}/catalogue/${supId}`)
    await page.getByRole('button', { name: 'Add to cart' }).click()
    await expect(page.getByText(`Added 1 × ${supName} to your cart`)).toBeVisible()
    await page.goto(`${SHOP}/catalogue/${proId}`)
    await page.getByRole('button', { name: 'Add to cart' }).click()
    await expect(page.getByText(`Added 1 × ${proName} to your cart`)).toBeVisible()

    await page.getByRole('link', { name: /Cart, 4 items/ }).click()
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
    // The read-back is a table: one row per item with its quantity, total at the foot.
    const items = page.getByRole('table', { name: 'Items in this request' })
    await expect(items.getByRole('row', { name: new RegExp(paidName) })).toContainText('2')
    await expect(items.getByRole('row', { name: /Total/ })).toContainText('4')
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

  test('J-05 staff start quoting and send a quote: the stock line from CIMH stock, the other from a supplier, with estimated shipping', async ({ page }) => {
    await siaLogin(page, staff)
    await siaGo(page, 'Orders')
    await page.getByRole('textbox', { name: 'Request id, customer or organisation' }).fill(paidRequest)
    // Wait for the (debounced) search: the new request is already the top row before it applies, and the list
    // re-rendering under a focused row swallowed the Enter.
    await expect(page.getByRole('listbox').getByRole('option')).toHaveCount(1)
    const row = page.getByRole('option', { name: new RegExp(paidRequest.slice(-6)) }) // the queue shows ORD…last6
    await row.focus()
    await row.press('Enter') // opens beside the list (desk) or full screen (phone)
    await expect(page.getByText('Needed for the hurricane season')).toBeVisible()
    await page.getByRole('button', { name: 'Start quoting' }).click()
    await expect(page.getByRole('cell', { name: 'Full quantity' })).toBeVisible() // 2 units on the shelf

    await page.getByRole('link', { name: 'Build quote' }).click()
    // The line is fully in stock, so it starts in CIMH stock.
    const fromStock = page.getByRole('checkbox', { name: 'From stock' })
    await expect(fromStock).toBeChecked()
    // One place per line: a supplier price takes the line out of stock; ticking From stock takes it back.
    await page.getByRole('button', { name: 'Add supplier' }).click()
    await page.getByLabel('Supplier', { exact: true }).fill('Campbell Scientific')
    await page.getByRole('button', { name: `Price ${paidName} from Campbell Scientific instead` }).click()
    await page.getByLabel(`Unit price for ${paidName}`).fill('180.00')
    await page.getByRole('tab', { name: /CIMH stock/ }).click()
    await expect(fromStock).not.toBeChecked()
    await fromStock.check()
    await page.getByRole('tab', { name: /Campbell Scientific/ }).click()
    await expect(page.getByText('From CIMH stock')).toBeVisible()
    // The item CIMH doesn't hold comes from the supplier, with the supplier's estimated shipping.
    await page.getByLabel(`Unit price for ${supName}`).fill('100.00')
    await page.getByLabel('Estimated shipping').fill('10.00')
    await page.getByRole('tab', { name: /CIMH stock/ }).click()
    await page.getByLabel('Estimated shipping').fill('20.00')
    await expect(page.getByText('Draft saved')).toBeVisible()
    // Staff see the agreement before it goes out: the real PDF, drawn from the draft and marked as a preview.
    await page.getByRole('button', { name: 'Preview agreement' }).click()
    const preview = page.getByRole('dialog')
    await expect(preview).toContainText('Agreement preview')
    await expect(preview.getByRole('img', { name: /page 1 of/ })).toBeVisible({ timeout: 20_000 })
    // Upright: the logo-blue header band is at the top of page 1. Two paints on one canvas once mirrored the page
    // (band at the bottom, text upside down) when the pane narrowed for its scrollbar mid-paint.
    await expect
      .poll(() => preview.locator('canvas[data-page="1"]').evaluate(blueBandAtTop), { timeout: 15_000 })
      .toBe(true)
    await shot(page, 'sia-agreement-preview')
    await preview.getByRole('button', { name: 'Keep editing' }).click()
    await expect(preview).toBeHidden()
    await page.getByRole('button', { name: 'Send quote' }).click()
    // Nothing is emailed before the confirm, which shows the agreement and restates the recipient and the total.
    const confirm = page.getByRole('dialog')
    await expect(confirm).toContainText('Quote version')
    await expect(confirm).toContainText('Total to sign (Estimate)')
    await expect(confirm.getByRole('img', { name: /page 1 of/ })).toBeVisible({ timeout: 20_000 })
    await auditDialog(page, 'send-quote')
    await confirm.getByRole('button', { name: 'Email the customer' }).click()
    await expect(page.getByText('Quote version 1 sent to the customer')).toBeVisible()
    await expect(page.getByText('Quoted', { exact: true }).first()).toBeVisible()
  })

  test('J-03 customer views the quote, signs the agreement and sends it', async ({ page }) => {
    await shopLogin(page, customer)
    await page.getByRole('link', { name: 'Orders', exact: true }).first().click()
    // The quote leads the list under "Waiting for you", named by the item, with its expiry.
    const waiting = page.getByRole('region', { name: 'Waiting for you' })
    await expect(waiting.getByText('Quote to sign')).toBeVisible()
    await expect(waiting.getByText(paidName)).toBeVisible()
    await expect(waiting.getByText(/valid until .* days left/)).toBeVisible()
    await shot(page, 'shop-requests-docket')
    await page.getByRole('link', { name: new RegExp(paidRequest.slice(-6)) }).click() // the list shows ORD…last6
    await expect(page.getByRole('heading', { name: paidName })).toBeVisible()
    // A hand-off while the quote waits: the total once (in the well), what the agreement is, no priced lines (they
    // are read on View and sign), one progress model (the path; dated changes folded into History).
    const well = page.getByRole('region', { name: 'Where it stands' })
    await expect(well.getByText('Your quote is ready: BBD 430.00')).toBeVisible()
    await expect(well.getByText(/The head of your organisation signs the document/)).toBeVisible()
    await expect(page.getByText('BBD 430.00')).toHaveCount(1)
    await expect(page.getByText(/Estimated shipping/)).toHaveCount(0)
    await expect(page.getByRole('list', { name: 'Request status' })).toHaveCount(0)
    await expect(page.getByText('History', { exact: true })).toBeVisible()
    // Nothing to choose: view and sign, or cancel.
    await expect(well.getByRole('button', { name: 'Cancel request' })).toBeVisible()
    // The reason dialog puts the cursor in Reason and gives focus back to Cancel request when closed.
    await well.getByRole('button', { name: 'Cancel request' }).click()
    await expect(page.getByRole('dialog').getByLabel('Reason')).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(well.getByRole('button', { name: 'Cancel request' })).toBeFocused()
    await expect(page.getByRole('radio')).toHaveCount(0)
    // Whoever comes back only with the signed copy goes straight to sending it.
    await expect(well.getByRole('link', { name: 'Send the signed copy' })).toHaveAttribute('href', new RegExp(`/requests/${paidRequest}/agreement\\?task=send$`))
    await well.getByRole('link', { name: 'View and sign' }).click()

    await expect(page.getByRole('heading', { name: 'View and sign' })).toBeVisible()
    await expect(page.getByText('CIMH stock').locator('visible=true').first()).toBeVisible()
    // Step 1 shows the quote files (the CIMH stock quote first; the page polls until document-svc has made it); the
    // agreement waits for the next step. Below 760 px a page can't be read inline (~4 px text): each document is a
    // row that opens a full-screen reader, zoomed in, and closing it returns to the row.
    const phone = (page.viewportSize()?.width ?? 1280) < 760
    const quotePreview = page.getByRole('region', { name: 'Preview of CIMH quote', exact: true })
    if (phone) {
      const row = page.getByRole('button', { name: 'Read CIMH quote full size' })
      await row.click({ timeout: 45_000 })
      const reading = page.getByRole('dialog').getByRole('region', { name: 'Reading CIMH quote' })
      await expect(reading.getByRole('img', { name: /page 1 of/ })).toBeVisible({ timeout: 20_000 })
      await expect(page.getByRole('dialog').getByRole('button', { name: /200%/ })).toBeVisible()
      await auditDialog(page, 'shop-agreement-quote-reader')
      await page.getByRole('dialog').getByRole('button', { name: 'Close' }).click()
      await expect(row).toBeFocused()
    } else await expect(quotePreview.getByRole('img', { name: /page 1 of/ })).toBeVisible({ timeout: 45_000 })
    await expect(page.getByRole('region', { name: 'Preview of Agreement to sign' })).toHaveCount(0)
    await auditPart(page, '.sign-page', 'shop-agreement-check')
    await shot(page, 'shop-agreement-check', { fullPage: false })
    await page.getByRole('button', { name: 'Continue to the agreement' }).click()
    // order.quoted → document-consumer renders the agreement → document.generated → order-consumer. Usually
    // there by now; the page polls every 3 s until the file is attached.
    const download = page.getByRole('link', { name: 'Download agreement' })
    await expect(download).toBeVisible({ timeout: 45_000 })
    // The agreement is read on the page, upright: beside the steps on wide screens, inside the task narrower, in the
    // full-screen reader on phones.
    if (phone) await page.getByRole('button', { name: 'Read Agreement to sign full size' }).click()
    const agreementDoc = page.getByRole('region', { name: phone ? 'Reading Agreement to sign' : 'Preview of Agreement to sign' })
    await expect(agreementDoc.getByRole('img', { name: /page 1 of/ })).toBeVisible({ timeout: 20_000 })
    await expect
      .poll(() => agreementDoc.locator('canvas[data-page="1"]').evaluate(blueBandAtTop), { timeout: 15_000 })
      .toBe(true)
    if (phone) {
      await page.keyboard.press('Escape')
      await expect(page.getByRole('button', { name: 'Read Agreement to sign full size' })).toBeFocused()
    }
    await expect(quotePreview).toBeHidden() // the quote preview was step 1's
    await auditPart(page, '.sign-page', 'shop-agreement-read')
    await shot(page, 'shop-agreement-read', { fullPage: false })
    // The customer may download it (document-svc asks order-svc): a real PDF, saved as a file (no new tab).
    const pdf = await page.request.get(new URL((await download.getAttribute('href')) as string, page.url()).toString())
    expect(pdf.status()).toBe(200)
    expect(pdf.headers()['content-disposition']).toMatch(/^attachment;/)
    expect((await pdf.body()).subarray(0, 5).toString()).toBe('%PDF-')
    await expect(download).not.toHaveAttribute('target', '_blank')

    // The three tasks are a list, one open at a time; the signer usually comes back later with the signed copy.
    // The address follows the open task, so a reload or a copied link opens the same one.
    await expect(page).toHaveURL(/[?&]task=sign/)
    // "Already signed?" only opens task 3: nothing on this page can know the agreement is signed, so it ticks nothing.
    await page.getByRole('button', { name: 'Already signed? Send the copy' }).click()
    await expect(page).toHaveURL(/[?&]task=send/)
    await expect(page.getByRole('button', { name: /^Get it signed\W+done/ })).toHaveCount(0)
    const sendTask = page.getByRole('button', { name: /^Send the signed copy/ })
    await expect(sendTask).toHaveAttribute('aria-expanded', 'true')
    // A reload (an interruption, or the link passed to whoever sends the signed copy) opens the same task.
    await page.reload()
    await expect(sendTask).toHaveAttribute('aria-expanded', 'true')
    await expect(page.getByRole('button', { name: /^Check the quote\W+done/ })).toHaveAttribute('aria-expanded', 'false')
    // Without a task in the address, a return visit opens the first task not done (ticks kept in this browser): the
    // quote was checked, the agreement not downloaded here, so "Get it signed".
    await page.goto(`${SHOP}/requests/${paidRequest}/agreement`)
    await expect(page.getByRole('button', { name: /^Get it signed/ })).toHaveAttribute('aria-expanded', 'true')
    await page.getByRole('button', { name: 'Already signed? Send the copy' }).click()
    await expect(sendTask).toHaveAttribute('aria-expanded', 'true')
    // Send is never disabled: without a file it says what is missing.
    await page.getByRole('button', { name: 'Send signed agreement' }).click()
    await expect(page.getByText('Choose the signed copy first')).toBeVisible()
    // The real upload: type sniffed, scanned, stored, attached at once so the quote can be accepted. The chosen file
    // is shown on the page first (read in the browser), so the customer sends the page they meant to.
    await page.locator('input[type=file]').setInputFiles({ name: 'signed.pdf', mimeType: 'application/pdf', buffer: onePagePdf('Signed agreement') })
    await expect(page.getByRole('region', { name: 'Preview of Your signed copy' })).toBeVisible()
    await auditPart(page, '.sign-page', 'shop-agreement-send')
    await page.getByRole('button', { name: 'Send signed agreement' }).click()
    // Sending accepts the quote, so it asks first: what it confirms (version, total) and that CIMH is emailed.
    const confirmSend = page.getByRole('dialog')
    await expect(confirmSend).toContainText('This accepts quote version 1 for BBD 430.00')
    await auditDialog(page, 'shop-agreement-confirm-send')
    await confirmSend.getByRole('button', { name: 'Send signed agreement' }).click()
    // Ends on the request page: a lasting banner says what CIMH does next.
    const after = page.getByRole('region', { name: 'Where it stands' }) // History repeats the words, folded
    await expect(after.getByText('Signed agreement received', { exact: true })).toBeVisible()
    await expect(after.getByText(/CIMH staff check the signature/)).toBeVisible()
    await expect(page.getByText('Accepted', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('Agreed total').locator('visible=true').first()).toBeVisible() // the quote is a record once signed
    await shot(page, 'shop-request-accepted')
    // Once signed, the papers lie on the request page as small sheets (page 1 each), never drawn at reading size; a
    // tile opens the full-size reader, and closing it returns to the tile. The invoice is a dashed sheet until delivery.
    await expect(page.getByRole('region', { name: 'Delivery', exact: true })).toBeVisible()
    await expect(page.getByRole('region', { name: 'Files', exact: true })).toHaveCount(0)
    await expect(page.getByRole('region', { name: /^Preview of/ })).toHaveCount(0)
    const papers = page.getByRole('region', { name: 'Papers', exact: true })
    for (const name of ['Signed agreement', 'Agreement', 'CIMH quote']) await expect(papers.getByRole('button', { name: new RegExp(`^Read ${name} full size`) })).toBeVisible()
    await expect(papers.getByText('Comes when the items are delivered')).toBeVisible()
    await expect(papers.locator('canvas').locator('visible=true').first()).toBeVisible({ timeout: 20_000 }) // page 1 drawn (the test's signed copy is not a real PDF: it shows the file glyph)
    await auditPart(page, '.sheet', 'shop-request-papers')
    const signedTile = papers.getByRole('button', { name: /^Read Signed agreement full size/ })
    await signedTile.click()
    await expect(page.getByRole('dialog').getByRole('region', { name: 'Reading Signed agreement' })).toBeVisible()
    await auditDialog(page, 'shop-request-paper-reader')
    await page.getByRole('dialog').getByRole('button', { name: 'Close' }).click()
    await expect(signedTile).toBeFocused()
  })

  test('J-06 staff verify, order from the supplier, pick, ship each parcel and deliver', async ({ page }) => {
    await siaLogin(page, staff)
    await page.goto(`${SIA}/requests/${paidRequest}`)
    // order.quoted → inventory reserved over Kafka when the quote was sent → stock.reserved → the line shows the units.
    await expect(async () => {
      await page.reload()
      await expect(page.getByText('Reserved', { exact: true })).toBeVisible({ timeout: 2000 })
    }).toPass({ timeout: 45_000 })
    await page.getByRole('button', { name: 'Verify and purchase' }).click()
    await page.getByLabel(/signed by an authorised person/).check()
    await page.getByLabel('PO number').fill(`PO-${run}`) // the supplier line is ordered by CIMH
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
    // One parcel per source: the request's only line comes from CIMH stock, ticked and ready (every unit picked).
    await expect(page.getByRole('dialog').getByRole('checkbox', { name: new RegExp(paidName) })).toBeChecked()
    await page.getByLabel('Hand delivery').check()
    await page.getByLabel('Delivered by / collected by').fill('Collected by Cass')
    await shot(page, 'sia-ship-dialog')
    await auditDialog(page, 'Record shipment')
    await page.getByRole('dialog').getByRole('button', { name: 'Record shipment' }).click()
    await expect(page.getByText('Shipment recorded')).toBeVisible()
    // The supplier's own parcel, shipped to the customer directly: the request is SHIPPED once every line is in one.
    await expect(page.getByRole('dialog')).toBeHidden()
    await expect(page.getByRole('button', { name: 'Mark delivered' })).toHaveCount(0)
    await page.getByRole('button', { name: 'Record shipment' }).click()
    const second = page.getByRole('dialog')
    await expect(second.getByRole('radio', { name: /Campbell Scientific/ })).toBeChecked()
    await expect(second.getByRole('checkbox', { name: new RegExp(supName) })).toBeChecked()
    await second.getByLabel('UPS').check()
    await second.getByLabel('Tracking number').fill('1Z999AA10123456784')
    await second.getByRole('button', { name: 'Record shipment' }).click()
    await expect(page.getByText('Shipment recorded').last()).toBeVisible() // the first parcel's toast may still show
    await expect(page.getByRole('region', { name: 'Shipments' }).getByRole('listitem')).toHaveCount(2)
    await page.getByRole('button', { name: 'Mark delivered' }).click()
    await page.getByLabel('Invoice number (optional)').fill(`INV-${run}`)
    await page.getByRole('dialog').getByRole('button', { name: 'Mark delivered' }).click()
    await expect(page.getByText('Marked delivered')).toBeVisible()

    // Invoice builder: every priced line, the preview drawn beside the panel, stored on the request.
    await page.getByRole('button', { name: 'Create invoice', exact: true }).click()
    const inv = page.getByRole('dialog')
    await expect(inv.locator('.line')).toHaveCount(2)
    await expect(inv.getByLabel('Invoice #')).toHaveValue(`INV-${run}`) // the number given at delivery
    // The date is a Vuetify date input: pressing it opens the v-date-picker.
    await inv.locator('.v-date-input .v-field').click()
    await expect(page.locator('.v-date-picker')).toBeVisible()
    // Whole picker inside the dialog (it once opened from the field's left edge and ran past the dialog's right side).
    const pick = (await page.locator('.v-date-picker').boundingBox())!
    const box = (await inv.locator('.v-card').first().boundingBox())!
    expect(pick.x + pick.width).toBeLessThanOrEqual(box.x + box.width + 1)
    expect(pick.x).toBeGreaterThanOrEqual(box.x - 1)
    await shot(page, 'sia-invoice-date-picker', { fullPage: false })
    await page.keyboard.press('Escape')
    await expect(page.locator('.v-date-picker')).toBeHidden()
    await expect(inv.locator('canvas.doc-page').first()).toBeVisible({ timeout: 20_000 })
    await auditDialog(page, 'Create invoice')
    await inv.getByRole('button', { name: 'Create invoice', exact: true }).click()
    await expect(page.getByText(`Invoice INV-${run} created; emailed to the customer and staff`)).toBeVisible()
    await expect(inv).toBeHidden()
    // Commercial invoice: CIMH stock only (the supplier's item shipped direct).
    await page.getByRole('button', { name: 'Create commercial invoice', exact: true }).click()
    const ci = page.getByRole('dialog')
    await expect(ci.locator('.line')).toHaveCount(1)
    await expect(ci.getByLabel('Line 1 description')).toHaveValue(new RegExp(paidName))
    await ci.getByRole('button', { name: 'Create commercial invoice', exact: true }).click()
    await expect(ci.locator('.problems')).toContainText('Enter the commercial invoice number') // marked, not disabled
    await ci.getByLabel('Commercial invoice #').fill(`CI-${run}`)
    await ci.getByLabel('Customer', { exact: true }).uncheck()
    await expect(ci.getByLabel('Customer', { exact: true })).not.toBeChecked()
    await expect(ci.locator('canvas.doc-page').first()).toBeVisible({ timeout: 20_000 })
    await ci.getByRole('button', { name: 'Create commercial invoice', exact: true }).click()
    await expect(page.getByText(`Commercial invoice CI-${run} created; emailed to staff`)).toBeVisible()
  })

  test('J-04 customer sees the request delivered', async ({ page }) => {
    await shopLogin(page, customer)
    await page.goto(`${SHOP}/requests/${paidRequest}`)
    // A delivered paid request waits for payment: the well asks for the proof.
    await expect(page.getByRole('region', { name: 'Where it stands' }).getByText(/^Payment required/)).toBeVisible()
    // One row per parcel: CIMH's stock items (hand delivered) and the supplier's direct shipment with its Track link.
    const parcels = page.getByRole('list', { name: 'Shipments' })
    await expect(parcels.getByRole('listitem')).toHaveCount(2)
    await expect(parcels.getByText('Sent by CIMH')).toBeVisible()
    await expect(parcels.getByText('Collected by Cass')).toBeVisible()
    await expect(parcels.getByText('Sent directly by Campbell Scientific')).toBeVisible()
    await expect(parcels.getByRole('link', { name: /Track 1Z999AA10123456784 with UPS/ })).toHaveAttribute('href', 'https://www.ups.com/track?tracknum=1Z999AA10123456784')
    await shot(page, 'shop-request-delivered')
    await expect(page.locator('.items li', { hasText: 'From CIMH stock' })).toBeVisible() // where the line came from
    // order.delivered → document-consumer makes the invoice → it joins the papers in place of the dashed sheet.
    await expect(async () => {
      await page.reload()
      // The invoice made at delivery and the one staff built in J-06 (invoice builder).
      await expect(page.getByRole('region', { name: 'Papers', exact: true }).getByRole('button', { name: /^Read Invoice full size/ })).toHaveCount(2, { timeout: 2000 })
    }).toPass({ timeout: 45_000 })
    await expect(page.getByText('Comes when the items are delivered')).toHaveCount(0)
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
