/**
 * P7 exit: 0 serious/critical axe issues (WCAG 2.1 A/AA, TR-ACC-1, plus 2.2 AA rules) on every SHOP and SIA screen, light and dark.
 * Each test logs in once and visits its screens; violations are collected and reported together so one
 * run shows everything. Runs in every project (chromium, firefox, webkit, mobile). @req TR-ACC-1
 */
import AxeBuilder from '@axe-core/playwright'
import { expect, type Page, test } from '@playwright/test'
import { SHOP, SIA } from './playwright.config'
import {
  adminWithMfa,
  customerAccount,
  nextTotpWindow,
  orderableProduct,
  PASSWORD,
  run,
  staffAccount,
  totp,
} from './support'

const BLOCKING = new Set(['serious', 'critical'])

/** `prepare` brings the page to a state that only appears while typing (e.g. the password strength meter). */
async function audit(page: Page, url: string, found: string[], prepare?: (page: Page) => Promise<void>) {
  for (const theme of ['cimhLight', 'cimhDark'] as const) {
    // The apps read the remembered theme at start-up (theme-mode.ts): store it, then load the page.
    await page.addInitScript((t) => {
      try {
        localStorage.setItem('cimh.theme', t)
      } catch {
        /* ignore */
      }
    }, theme)
    await page.goto(url)
    await page.waitForLoadState('networkidle')
    if (prepare) await prepare(page)
    // Entrance motion (e.g. catalogue cards rising in) must finish first: axe reads a half-faded card as low contrast.
    await page.waitForFunction(() =>
      document.getAnimations().every((a) => a.playState !== 'running' || a.effect?.getTiming().iterations === Infinity),
    )
    const result = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
      .analyze()
    for (const v of result.violations.filter((x) => BLOCKING.has(x.impact ?? ''))) {
      const where = v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')
      const label = theme === 'cimhDark' ? 'dark' : 'light'
      const state = prepare ? ` (${prepare.name || 'prepared'})` : ''
      found.push(`${new URL(url).pathname}${state} [${label}] ${v.impact} ${v.id}: ${v.help} — ${where}`)
    }
  }
}

/** Sign-up at its last step with a password typed, so the strength meter is on the page (S-13; SIA sign-up). */
function signupPasswordStep(email: string) {
  return async function passwordTyped(page: Page) {
    await page.getByLabel('First name').fill('Axe')
    await page.getByLabel('Last name').fill('Check')
    await page.locator('input[name=email]').fill(email)
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('group', { name: /^(Organisation|Details)$/ }).waitFor()
    // By role and name: each step's group shares its name with its first field.
    const org = page.getByRole('textbox', { name: 'Organisation' })
    if (await org.isVisible()) await org.fill('Axe Met Service')
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.locator('input[name=password]').fill('weakpass')
    await expect(page.getByText(/^Strength:/)).toBeVisible()
  }
}

test.describe('accessibility (axe)', () => {
  test.describe.configure({ timeout: 300_000 })

  test('SHOP public screens', async ({ page }) => {
    const staff = await staffAccount('a11y')
    const pid = await orderableProduct(staff, `E2E a11y hygrometer ${run}`)
    const found: string[] = []
    for (const path of ['/', '/catalogue', `/catalogue/${pid}`, '/pro-bono', `/catalogue?q=hygrometer`, '/login', '/signup',
      '/verify?email=a%40example.org', '/forgot-password', '/reset-password?email=a%40example.org', '/pending-approval', '/no-such-page']) {
      await audit(page, `${SHOP}${path}`, found)
    }
    await audit(page, `${SHOP}/signup`, found, signupPasswordStep(`axe.${run}@example.org`))
    expect(found, found.join('\n')).toEqual([])
  })

  test('SHOP customer screens', async ({ page }) => {
    const staff = await staffAccount('a11yc')
    const pid = await orderableProduct(staff, `E2E a11y barograph ${run}`)
    const customer = await customerAccount('a11y')
    await page.goto(`${SHOP}/login`)
    await page.getByLabel('Email').fill(customer)
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page.getByRole('link', { name: 'Orders', exact: true }).first()).toBeVisible()
    const found: string[] = []
    await audit(page, `${SHOP}/catalogue/${pid}`, found)
    await page.getByRole('button', { name: 'Add to cart' }).click()
    for (const path of ['/cart', '/requests', '/account']) await audit(page, `${SHOP}${path}`, found)
    expect(found, found.join('\n')).toEqual([])
  })

  test('SIA staff screens', async ({ page }) => {
    const staff = await staffAccount('a11ys')
    const pid = await orderableProduct(staff, `E2E a11y psychrometer ${run}`)
    await page.goto(`${SIA}/login`)
    const found: string[] = []
    await audit(page, `${SIA}/signup`, found)
    await audit(page, `${SIA}/signup`, found, signupPasswordStep(`axe.${run}@cimh.edu.bb`))
    await page.goto(`${SIA}/login`)
    await audit(page, `${SIA}/login`, found)
    await page.getByLabel('Email').fill(staff)
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page).toHaveURL(`${SIA}/`)
    for (const path of ['/', '/requests', '/products', '/products/new', `/products/${pid}`, '/inventory',
      '/inventory?op=location', '/inventory?op=lookup', '/inventory?op=labels', '/inventory?op=site', '/pick?op=stow', '/pick', '/reports/stock', '/reports/assignments',
      '/reports/history', '/profile', '/no-such-page']) {
      await audit(page, `${SIA}${path}`, found)
    }
    expect(found, found.join('\n')).toEqual([])
  })

  test('SIA admin screens', async ({ page }) => {
    const admin = await adminWithMfa()
    await nextTotpWindow()
    await page.goto(`${SIA}/login`)
    await page.getByLabel('Email').fill(admin.email)
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
    await page.getByRole('button', { name: 'Log in' }).click()
    await page.getByRole('textbox', { name: '6-digit code' }).fill(totp(admin.key))
    await expect(page.getByRole('heading', { name: /^Good (morning|afternoon|evening)/ })).toBeVisible()
    const found: string[] = []
    for (const path of ['/admin/approvals', '/admin/accounts', '/admin/organisations', '/admin/settings', '/admin/audit', '/admin/announcements']) {
      await audit(page, `${SIA}${path}`, found)
    }
    expect(found, found.join('\n')).toEqual([])
  })
})
