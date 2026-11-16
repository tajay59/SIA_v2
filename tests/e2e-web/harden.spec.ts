/**
 * Critique plan step 4 (harden): submit buttons are never disabled without a reason (a press marks what is
 * missing), and actions that can't be undone ask first. The journeys cover Create product, Create account,
 * Send quote, Return and Erase; this spec covers the rest. Each open dialog is checked with axe.
 */
import { expect, test } from '@playwright/test'
import { SHOP, SIA } from './playwright.config'
import { adminWithMfa, auditDialog, customerAccount, nextTotpWindow, orderableProduct, PASSWORD, run, siaGo, staffAccount, totp } from './support'

test.describe('harden: submits explain themselves, irreversible actions ask first', () => {
  test('SHOP: empty log in, cart without an address, removing an address', async ({ page }) => {
    const staff = await staffAccount('hard')
    const pid = await orderableProduct(staff, `E2E harden anemometer ${run}`)
    const customer = await customerAccount('hard')

    await page.goto(`${SHOP}/login`)
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page.getByText('Enter your password')).toBeVisible()
    await expect(page.getByLabel('Email')).toBeFocused()
    await page.getByLabel('Email').fill(customer)
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page.getByRole('link', { name: 'My requests' }).first()).toBeVisible()

    // Cart: Continue is enabled without an invoice address and says what is missing.
    await page.goto(`${SHOP}/catalogue/${pid}`)
    await page.getByRole('button', { name: 'Add to cart' }).click()
    await page.goto(`${SHOP}/cart`)
    await page.getByRole('button', { name: 'Continue to quote details' }).click()
    await page.getByRole('button', { name: 'Continue to delivery' }).click()
    await expect(page.getByRole('alert').filter({ hasText: 'Add an invoice address to continue.' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Invoice address' })).toBeVisible() // still on step 2

    // Address dialog: Save marks the missing fields.
    await page.goto(`${SHOP}/account`)
    await page.getByRole('button', { name: 'Add address' }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByRole('button', { name: 'Save address' }).click()
    await expect(dialog.getByText('Required').first()).toBeVisible()
    await expect(dialog.getByLabel('First name')).toBeFocused()
    await dialog.getByLabel('First name').fill('Casey')
    await dialog.getByLabel('Last name').fill('Harden')
    await dialog.getByLabel('Email').fill(customer)
    await dialog.getByLabel('Address line 1').fill('1 Husbands Road')
    await dialog.getByLabel('City / town').fill('Bridgetown')
    await dialog.getByRole('button', { name: 'Save address' }).click()
    await expect(page.getByText('Address saved')).toBeVisible()

    // Removing it asks first; Keep address leaves it.
    await page.getByRole('button', { name: 'Remove address 1' }).click()
    await expect(dialog).toContainText('1 Husbands Road')
    await auditDialog(page, 'remove-address')
    await dialog.getByRole('button', { name: 'Keep address' }).click()
    await expect(page.getByText('Casey Harden')).toBeVisible()
    await page.getByRole('button', { name: 'Remove address 1' }).click()
    await dialog.getByRole('button', { name: 'Remove', exact: true }).click()
    await expect(page.getByText('Address removed')).toBeVisible()
    await expect(page.getByText('No saved addresses yet')).toBeVisible()
  })

  test('SIA settings: one Save for Reference; leaving with unsaved changes asks first', async ({ page }) => {
    const admin = await adminWithMfa()
    await nextTotpWindow()
    await page.goto(`${SIA}/login`)
    await page.getByLabel('Email').fill(admin.email)
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
    await page.getByRole('button', { name: 'Log in' }).click()
    await page.getByRole('textbox', { name: '6-digit code' }).fill(totp(admin.key))
    await expect(page.getByRole('heading', { name: /^Good (morning|afternoon|evening)/ })).toBeVisible()

    await page.goto(`${SIA}/admin/settings?tab=reference`)
    const save = page.getByRole('button', { name: 'Save reference' })
    await expect(save).toBeDisabled() // nothing changed yet, and the bar says so
    await expect(page.getByText('All changes saved')).toBeVisible()

    // Add project never sits disabled: an empty press marks both fields.
    await page.getByRole('button', { name: 'Add project' }).click()
    await expect(page.getByText('Enter a code')).toBeVisible()
    await expect(page.getByText('Enter a name')).toBeVisible()

    const dept = `E2E dept ${run}`
    await page.getByRole('combobox', { name: 'Departments' }).fill(dept)
    await page.getByRole('combobox', { name: 'Departments' }).press('Enter')
    await expect(page.getByText('Unsaved changes')).toBeVisible()

    // Leaving asks; Stay keeps the page and the edit.
    await siaGo(page, 'Products')
    const dialog = page.getByRole('dialog')
    await expect(dialog).toContainText('Reference')
    await auditDialog(page, 'settings-leave')
    await dialog.getByRole('button', { name: 'Keep editing' }).click()
    await expect(page).toHaveURL(/\/admin\/settings/)
    await expect(page.getByText(dept)).toBeVisible()

    await save.click()
    await expect(page.getByText('Reference saved')).toBeVisible()

    // Clean again: leaving is not held up.
    await siaGo(page, 'Products')
    await expect(page).toHaveURL(/\/products/)

    // Unsaved again, and this time leave: the edit is dropped.
    await page.goto(`${SIA}/admin/settings?tab=reference`)
    await page.getByRole('combobox', { name: 'Departments' }).fill(`${dept} b`)
    await page.getByRole('combobox', { name: 'Departments' }).press('Enter')
    await siaGo(page, 'Products')
    await dialog.getByRole('button', { name: 'Leave without saving' }).click()
    await expect(page).toHaveURL(/\/products/)
  })
})
