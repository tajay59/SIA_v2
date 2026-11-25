#!/usr/bin/env node
/**
 * Lighthouse gate (Lighthouse plan fix D, docs/plans/2026-11-25-lighthouse.md): audits a few signed-out pages of
 * the production builds and fails when accessibility drops below 100 or the layout shift (CLS) goes above 0.1.
 * Performance is reported but never gated (too noisy on shared CI runners).
 *
 * Usage: node tools/perf/lighthouse-gate.mjs   (SHOP_URL, SIA_URL, CATALOG_URL, LH_OUT optional)
 * CI runs it in the e2e job after the browser journeys, against `vite preview` of both apps on the dev stack.
 */
import { execFileSync } from 'node:child_process'
import { appendFileSync, mkdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const SHOP = process.env.SHOP_URL ?? 'http://localhost:15173'
const SIA = process.env.SIA_URL ?? 'http://localhost:15174'
const CATALOG = process.env.CATALOG_URL ?? 'http://localhost:18002'
const OUT = process.env.LH_OUT ?? 'lighthouse-reports'
const LIGHTHOUSE = 'lighthouse@12.6.0'
mkdirSync(OUT, { recursive: true })

async function productPath() {
  try {
    const r = await fetch(`${CATALOG}/api/catalog/v1/products?limit=1`)
    const id = (await r.json()).items?.[0]?.id
    return id ? `/catalogue/${id}` : null
  } catch {
    return null
  }
}

const pages = [
  ['shop-home', `${SHOP}/`, 'mobile'],
  ['shop-catalogue', `${SHOP}/catalogue`, 'mobile'],
  ['shop-login', `${SHOP}/login`, 'mobile'],
  ['sia-login', `${SIA}/login`, 'desktop'],
]
const product = await productPath()
if (product) pages.splice(2, 0, ['shop-product', `${SHOP}${product}`, 'mobile'])

const rows = []
const failures = []
for (const [name, url, form] of pages) {
  const base = join(OUT, name)
  const args = ['--yes', LIGHTHOUSE, url, '--quiet', '--chrome-flags=--headless=new --no-sandbox', '--output=json', '--output=html',
    `--output-path=${base}`, form === 'desktop' ? '--preset=desktop' : '--form-factor=mobile']
  try {
    // Windows: npx is npx.cmd, which Node only starts through a shell (arguments quoted by hand there).
    if (process.platform === 'win32') execFileSync(['npx', ...args.map((a) => `"${a}"`)].join(' '), { shell: true, stdio: ['ignore', 'ignore', 'pipe'], timeout: 180_000 })
    else execFileSync('npx', args, { stdio: ['ignore', 'ignore', 'pipe'], timeout: 180_000 })
  } catch (e) {
    failures.push(`${name}: Lighthouse did not finish (${String(e.stderr ?? e).slice(0, 200)})`)
    continue
  }
  const r = JSON.parse(readFileSync(`${base}.report.json`, 'utf8'))
  const score = (k) => Math.round((r.categories[k]?.score ?? 0) * 100)
  const cls = r.audits['cumulative-layout-shift']?.numericValue ?? 0
  const row = { name, form, perf: score('performance'), a11y: score('accessibility'), bp: score('best-practices'), seo: score('seo'),
    lcp: r.audits['largest-contentful-paint']?.displayValue ?? '', cls: cls.toFixed(3) }
  rows.push(row)
  if (row.a11y < 100) {
    const failed = r.categories.accessibility.auditRefs.filter((a) => r.audits[a.id]?.score === 0).map((a) => a.id)
    failures.push(`${name}: accessibility ${row.a11y} (${failed.join(', ')})`)
  }
  if (cls > 0.1) failures.push(`${name}: layout shift ${row.cls} (> 0.1)`)
  console.log(`${name} ${form}: perf ${row.perf} · a11y ${row.a11y} · best practices ${row.bp} · SEO ${row.seo} · LCP ${row.lcp} · CLS ${row.cls}`)
}

if (process.env.GITHUB_STEP_SUMMARY) {
  const table = ['| Page | Form | Perf | A11y | Best pr. | SEO | LCP | CLS |', '|---|---|---|---|---|---|---|---|',
    ...rows.map((r) => `| ${r.name} | ${r.form} | ${r.perf} | ${r.a11y} | ${r.bp} | ${r.seo} | ${r.lcp} | ${r.cls} |`)]
  appendFileSync(process.env.GITHUB_STEP_SUMMARY, `### Lighthouse (gate: accessibility 100, CLS ≤ 0.1)\n\n${table.join('\n')}\n\n${failures.map((f) => `- ❌ ${f}`).join('\n')}\n`)
}
if (failures.length) {
  console.error(`Lighthouse gate failed:\n- ${failures.join('\n- ')}`)
  process.exit(1)
}
