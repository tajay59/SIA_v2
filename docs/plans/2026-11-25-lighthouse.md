# Lighthouse: results, fixes done, fixes to come

Date: 2026-11-25 · Status: **all fixes built: 1, 2, 4, 5 (#55), edge (#56), 6 (#57), 3 (#58), C + B + D (branch `perf/lighthouse-c-b-d`, §5.3); honest phone numbers measured (§5.3)** · Owner request 2026-11-25

Working plan, not part of the manual. Picks up where the session left off: read §6 first.

## 1. What was run

- **Lighthouse CLI 12.6.0** (`npx --yes lighthouse@12.6.0`), headless Chrome, one fresh Chrome per audit, run one at a time (parallel runs skew performance scores).
- **Production preview builds** of SHOP (`http://localhost:15291`) and SIA (`http://localhost:15292`) against the dev stack, not the Vite dev servers (dev serves unbundled modules: performance numbers mean nothing there). The preview server does **not** compress, so compression (fix 1) only shows on staging/production.
- **38 audits:** SHOP 10 pages × phone + desktop (6 signed out: home, catalogue, product, Pro Bono, login, signup; 4 as a customer: cart, requests, request, account); SIA 18 pages at desktop (10 as staff, 7 as an admin with MFA, the sign-in page).
- **Signed-in pages:** Playwright signs in with its own browser, writes the session cookies to a JSON header file, and Lighthouse sends it with `--extra-headers`. (Attaching Lighthouse to a Chrome that Playwright controls over CDP hung every audit until its timeout.) Every signed-in audit was checked: none was bounced to `/login`.
- HTML + JSON reports of the first run were in the session scratchpad (may be gone); the spec that produced them is in §7.

## 2. Results before the fixes

| | Performance | Accessibility | Best practices | SEO |
|---|---|---|---|---|
| SHOP, phone (10 pages) | **37–58** (LCP 7.2–8.5 s) | 100 | 93 | 82–83 |
| SHOP, desktop (10 pages) | 72–93 (LCP 1.3–1.5 s) | 100 | 93 | 83 |
| SIA, desktop (18 pages) | 75–91 | 100 | 93 | 83 |

Per page (LCP = main content shown, CLS = layout shift, TBT = main thread blocked):

| App | Page | Size | Perf | A11y | Best pr. | SEO | LCP | CLS | TBT |
|---|---|---|---|---|---|---|---|---|---|
| SHOP | home | mobile | 51 | 100 | 93 | 83 | 8.5 s | 0 | 340 ms |
| SHOP | home | desktop | 91 | 100 | 93 | 83 | 1.5 s | 0.001 | 50 ms |
| SHOP | catalogue | mobile | 56 | 100 | 93 | 83 | 8.2 s | 0.003 | 180 ms |
| SHOP | catalogue | desktop | 92 | 100 | 93 | 83 | 1.5 s | 0.002 | 10 ms |
| SHOP | product | mobile | 37 | 100 | 93 | 83 | 7.4 s | 0.531 | 120 ms |
| SHOP | product | desktop | 72 | 100 | 93 | 83 | 1.4 s | 0.469 | 0 ms |
| SHOP | pro-bono | mobile | 56 | 100 | 93 | 82 | 7.9 s | 0 | 190 ms |
| SHOP | pro-bono | desktop | 92 | 100 | 93 | 83 | 1.5 s | 0 | 10 ms |
| SHOP | login | mobile | 53 | 100 | 93 | 83 | 8.1 s | 0 | 290 ms |
| SHOP | login | desktop | 93 | 100 | 93 | 83 | 1.5 s | 0 | 0 ms |
| SHOP | signup | mobile | 57 | 100 | 93 | 83 | 7.7 s | 0 | 190 ms |
| SHOP | signup | desktop | 93 | 100 | 93 | 83 | 1.5 s | 0.002 | 50 ms |
| SHOP | cart | mobile | 58 | 100 | 93 | 82 | 7.7 s | 0.016 | 120 ms |
| SHOP | cart | desktop | 92 | 100 | 93 | 83 | 1.4 s | 0.007 | 0 ms |
| SHOP | requests | mobile | 51 | 100 | 93 | 82 | 7.9 s | 0 | 330 ms |
| SHOP | requests | desktop | 91 | 100 | 93 | 83 | 1.5 s | 0.002 | 0 ms |
| SHOP | request | mobile | 54 | 100 | 93 | 82 | 7.8 s | 0.01 | 240 ms |
| SHOP | request | desktop | 90 | 100 | 93 | 83 | 1.4 s | 0.088 | 0 ms |
| SHOP | account | mobile | 58 | 100 | 93 | 82 | 7.2 s | 0 | 160 ms |
| SHOP | account | desktop | 93 | 100 | 93 | 83 | 1.3 s | 0.009 | 20 ms |
| SIA | home | desktop | 75 | 100 | 93 | 83 | 1.7 s | 0 | 300 ms |
| SIA | requests | desktop | 76 | 100 | 93 | 83 | 1.9 s | 0.002 | 240 ms |
| SIA | request | desktop | 87 | 100 | 93 | 83 | 1.8 s | 0 | 50 ms |
| SIA | products | desktop | 88 | 100 | 93 | 83 | 1.7 s | 0.026 | 20 ms |
| SIA | product | desktop | 89 | 100 | 93 | 83 | 1.6 s | 0 | 20 ms |
| SIA | inventory | desktop | 88 | 100 | 93 | 83 | 1.6 s | 0.006 | 30 ms |
| SIA | pick | desktop | 89 | 100 | 93 | 83 | 1.6 s | 0 | 20 ms |
| SIA | reports-stock | desktop | 89 | 100 | 93 | 83 | 1.5 s | 0 | 10 ms |
| SIA | reports-history | desktop | 83 | 100 | 93 | 83 | 1.6 s | 0.125 | 50 ms |
| SIA | profile | desktop | 91 | 100 | 93 | 83 | 1.5 s | 0 | 40 ms |
| SIA | admin | desktop | 89 | 100 | 93 | 83 | 1.6 s | 0.029 | 70 ms |
| SIA | accounts | desktop | 89 | 100 | 93 | 83 | 1.6 s | 0 | 20 ms |
| SIA | approvals | desktop | 89 | 100 | 93 | 83 | 1.6 s | 0 | 10 ms |
| SIA | organisations | desktop | 86 | 100 | 93 | 83 | 1.7 s | 0 | 100 ms |
| SIA | audit | desktop | 88 | 100 | 93 | 83 | 1.7 s | 0.001 | 10 ms |
| SIA | settings | desktop | 89 | 100 | 93 | 83 | 1.7 s | 0 | 20 ms |
| SIA | announcements | desktop | 87 | 100 | 93 | 83 | 1.7 s | 0 | 70 ms |
| SIA | login | desktop | 90 | 100 | 93 | 83 | 1.6 s | 0 | 0 ms |

## 3. What caused the scores

1. **No compression anywhere.** Neither `deploy/nginx/templates/sites.conf.template` nor `deploy/staging-lite/gateway.conf` had gzip/brotli: about 1.2 MB of JS + CSS per first visit, uncompressed. Main reason phones waited ~8 s.
2. **SHOP product page layout shift 0.47 (desktop) / 0.53 (phone)** (poor is > 0.1). Not the photo (the band has a fixed height): while the product loaded, `v-skeleton-loader type="image, article"` was short, so the **footer** sat in view; when the product arrived the footer jumped off screen. Found with a `PerformanceObserver('layout-shift')` probe (sources: `FOOTER.footer` from y 338 to off screen).
3. **Large first-load code:** main JS ~660 KB (SHOP `index-*.js` 661 KB, ~395 KB unused on the first page; SIA ~658 KB, ~366 KB unused) and render-blocking CSS 370 KB (SHOP) / 415 KB (SIA), probably all of Vuetify's styles.
4. **SEO 83:** no `<meta name="description">`, and `robots.txt` was invalid (the SPA fallback served `index.html` for it).
5. **Best practices 93:** console errors and DevTools issues on every page:
   - "Note that 'script-src' was not explicitly set": the CSP had only `default-src`. **Second cause found later:** Zod 4 probes `new Function` to decide whether to compile validators; the CSP blocks it and Chrome reports a `securitypolicyviolation` (`blocked: eval`) on every page, although Zod catches it.
   - Two 401s on every signed-out page load: the "am I signed in?" check (`GET /api/identity/v1/me`) and the refresh attempt (`POST /auth/refresh`).
6. Minor: API JSON responses uncompressed (small; deliberately left so, see fix 1).

## 4. Fixes done (PR #55, branch `perf/lighthouse-fixes`, commit `1b1ef3b`)

| # | Fix | Files | Verified |
|---|---|---|---|
| 1 | **gzip for the web app files only** (JS, CSS, HTML, JSON, SVG, fonts; level 5, ≥ 1 KB, `gzip_vary`), switched on in the 4 SPA locations (SIA + SHOP, `/assets/` + `/`) of the production template and of the staging gateway. **Not on `/api/`**: responses carrying tokens next to user-supplied text invite BREACH, and API answers are small. | `deploy/nginx/templates/sites.conf.template`, `deploy/staging-lite/gateway.conf` | `deploy/nginx/test-config.sh` OK; `nginx -t` on the staging gateway in a throwaway `nginx:1.27-alpine`; local nginx with the gateway config: `/assets/app.js` **661 → 225 KB** with `Content-Encoding: gzip` + `Vary`, `/api/` not compressed |
| 2 | **Product page loading shape:** the placeholder is the page's own shape (crumb, `.band` as tall as the real one, the bar) and `.page { min-height: 100dvh }`, so the footer stays below the fold until the product arrives. | `web/shop/src/pages/catalogue/[id].vue` | Layout-shift probe: 0.53 → 0.03 (calc(100dvh − 64px)) → **0** (100dvh); Lighthouse phone: CLS 0, perf 37 → 52 (before compression) |
| 4 | **robots.txt + description:** SHOP `public/robots.txt` (allow all; disallow `/api/`, `/cart`, `/requests`, `/account`, `/verify`, `/reset-password`) + `<meta name="description">`; SIA `public/robots.txt` (`Disallow: /`) + `<meta name="robots" content="noindex, nofollow">` (staff app). | `web/shop/index.html`, `web/shop/public/robots.txt`, `web/sia/index.html`, `web/sia/public/robots.txt` | SHOP SEO **83 → 100**; SIA SEO 58 **on purpose** (not crawlable) |
| 5 | **CSP:** `script-src 'self'` named explicitly (production snippet, staging `$csp` map, both Vite preview configs) and **Zod `z.config({ jitless: true })`** at module load of `packages/web-app/src/validation.ts` (both apps), so Zod never probes `new Function`. | `deploy/nginx/snippets/security-headers.conf`, `deploy/staging-lite/gateway.conf`, `web/shop/vite.config.ts`, `web/sia/vite.config.ts`, `packages/web-app/src/validation.ts` | Playwright `securitypolicyviolation` probe: none on SHOP home and SIA sign-in (was `script-src` / `eval` on both) |

Docs updated in the same PR: INFRASTRUCTURE (caching/compression + robots), SECURITY T-10 (CSP), APD S-03 (loading shape), manual ch. 6/11/14 (rebuilt), CLAUDE.md log.

Tests run before the PR: web typecheck + unit (22 + 32), SHOP + SIA builds, Playwright catalogue + a11y (chromium + 360 px, 12 passed), identity + keyboard-drafts + catalogue (chromium, 16 passed).

Re-measured on previews after the fixes (no compression on previews):

| Page | Before | After |
|---|---|---|
| SHOP product, phone | Perf 37 · CLS 0.53 · SEO 83 | Perf 52 · CLS 0 · SEO 100 |
| SHOP home, phone | Perf 51 · SEO 83 · CSP violation | Perf 49–54 · SEO 100 · no CSP violation |
| SIA sign-in, desktop | Perf 90 · SEO 83 · CSP violation | Perf 90 · SEO 58 (noindex, on purpose) · no CSP violation |

Best practices stays 93 after the fixes: only the two 401s are left (fix 6).

## 5. Recommended fixes to come

| # | Fix | Why | Size / risk |
|---|---|---|---|
| A | **Done 2026-11-25 (§5.1).** ~~Merge #55, then re-run Lighthouse on staging's public pages~~ (`https://store.hashiz.store/`, `/catalogue`, a product, `/pro-bono`; `https://sia.hashiz.store/login`). Read-only page loads only; never sign up or create data there (it holds the real legacy data). | Compression only shows once nginx serves the files: this is the real phone performance number. | Small. Merging deploys the new gateway config to staging (CI reloads the gateway after `nginx -t`). |
| 6 | **Built 2026-11-25** (no contract change: with no `csrf_token` cookie the web apps skip `/me` and `/auth/refresh`, which could only answer 401; identity refuses a web refresh without it; signed-out SHOP/SIA pages load with no failed request and no console error). ~~No 401s for signed-out visitors:~~ e.g. an identity endpoint that answers 200 `{ account: null }` for "am I signed in?" (or skip `/auth/refresh` when no session is known), so the console stays clean. | Last item keeping Best practices at 93 on every page. | Small; contract change (identity OpenAPI) + web-app `session.ts`/`api.ts`. |
| 3 | **Built 2026-11-25 (§5.2).** ~~Smaller first load:~~ check whether all of Vuetify's CSS ships (`vuetify/styles` vs per-component styles with `vite-plugin-vuetify` `autoImport` + `styles: 'sass'`/`configFile`), split rarely used code out of the main chunk (pdf.js is already separate; check what else lands in `index-*.js`, e.g. via `rollup-plugin-visualizer`), lazy-load heavy components below the fold. | Main JS ~60 % unused on the first page; 370–415 KB render-blocking CSS. The biggest remaining phone cost once compression is on. | Medium; touches build config and possibly the look (verify with the Playwright suite + screenshots). Decide after A. |
| B | **Built 2026-11-25 (§5.3; gzip only, no brotli).** ~~Brotli / precompressed assets:~~ build `.gz`/`.br` next to each asset (e.g. `vite-plugin-compression`) and serve them with `gzip_static` (brotli needs an nginx module not in the stock image). | A further ~15–20 % below gzip, and no compression CPU per request. | Small–medium. Optional after A. |
| C | **Built 2026-11-25 (§5.3).** ~~Font and hero image:~~ check `font-display` and preload of Inter (SHOP home LCP), and the 110 KB `gears-*.webp` on SHOP home. | Small LCP gains on phones. | Small. |
| D | **Built 2026-11-25 (§5.3).** ~~Lighthouse in CI (optional):~~ run the §7 spec against previews on PRs touching `web/`, failing on accessibility < 100 or CLS > 0.1 (performance too noisy on CI runners to gate). | Keeps the 100 accessibility and the layout-shift fix from regressing. | Medium (CI time ~15 min; could audit a subset). |

SIA's SEO score (58) is correct for a staff app and should stay.

### 5.1 Staging after #55 (5-A, 2026-11-25)

Read-only page loads of the public pages, Lighthouse 12.6.0, one at a time.

| Page | Phone: Perf · BP · SEO · FCP · LCP · CLS | Desktop: Perf · BP · SEO · LCP · CLS |
|---|---|---|
| SHOP home | 59 · 96 · 100 · 6.3 s · 7.2 s · 0 | 91 · 96 · 100 · 1.4 s · 0.001 |
| SHOP catalogue | 60 · 96 · 100 · 6.4 s · 7.7 s · 0 | 90 · 96 · 100 · 1.4 s · 0 |
| SHOP product | 60 · 96 · 100 · 6.0 s · 6.8 s · 0 | 93 · 96 · 100 · 1.2 s · 0.014 |
| SHOP Pro Bono | 59 · 96 · 100 · 6.4 s · 6.9 s · 0 | 91 · 96 · 100 · 1.3 s · 0.011 |
| SIA sign-in | n/a | 90 · 96 · 58 · 1.4 s · 0 |

Accessibility 100 everywhere. Best practices 96: only the two 401s (fix 6) remain.

- **Compression works on staging:** a real Chromium receives the SHOP main JS as 225 KB (660 KB raw) and the CSS as 59 KB (369 KB raw), `Content-Encoding: gzip` + `Vary`.
- **The phone performance scores above are pessimistic, because this PC's ESET SSL filter interferes.** It intercepts HTTPS from any Chrome that `chrome-launcher` starts (installed Chrome 157 and Playwright's Chromium 158 alike; certificate issuer "ESET SSL Filter CA") and hands the page the files **uncompressed**, so Lighthouse loads 660 + 369 KB and simulates the phone on that. Chromium started by Playwright itself is not filtered (gzip arrives); Lighthouse could not attach to that one (hangs, as in §1). Honest phone numbers need a machine without ESET (or ESET's SSL filtering off for chrome.exe), or PageSpeed Insights (sends the public URL to Google: owner to decide).
- What the reports still show, whatever the encoding: the 369 KB CSS blocks rendering (est. 1.95 s on a phone), ~386 KB of the main JS is unused on the first page, and the LCP image (home slide) is found only after the JS runs. These are fix 3 (and C), unchanged.
- **Found: the shared staging edge gzips API answers.** `printit-nginx` (not ours) sets `gzip on; gzip_proxied any` at the http level for every site, so `/api/` JSON left staging gzipped (BREACH, the thing fix 1 avoided), before and after #55. Production is not affected (gzip is switched on only in the SPA locations; off by default elsewhere). Fix: `gzip off;` in our edge site's 443 server (`deploy/staging-lite/edge-site.conf`, branch `fix/staging-edge-no-api-gzip`); sia-gateway's own gzip of the web app files passes through untouched. Installing it touches the shared edge (backup, `nginx -t`, reload; no certbot): owner to approve.

### 5.2 Fix 3: smaller first load (2026-11-25, branch `perf/smaller-first-load`)

What the first page loaded, found with `source-map-explorer` on the SHOP entry chunk (644 KB): classic Zod 78 KB, qrcode 21 KB (MFA setup only), every shared web-app component 34 KB, Vuetify components no first page uses (OTP input, autocomplete, select, date composables…). Cause: `@cimh/web-app` declared no `sideEffects`, so its barrel (`index.ts`) pulled every module into the entry. Vuetify components were already imported one by one (`autoImport`); `vuetify/styles` (301 KB) was core 20 KB + palette classes 41 KB + utilities 240 KB, of which 186 KB are breakpoint variants no template uses.

Changes:
1. `packages/web-app/package.json` `"sideEffects": ["**/*.css"]`: pages pull only what they use (the only import-time code, `bootstrap.ts` and `z.config` in `validation.ts`, runs whenever those modules are used).
2. `packages/web-ui/tooling/trim-vuetify-css.ts`, a PostCSS step in both Vite configs, removes from Vuetify's own style files only: breakpoint utility variants and `hidden-*`, and the Material palette classes except white/black/transparent. Checked: no template, script or Vuetify component uses them; `bg-white`, `rounded-pill`, `elevation-*`, `d-flex`, `ma-2` stay.
3. `zod/mini` instead of classic Zod (validation.ts, AddressDialog, ProductForm; same checks and messages).

SHOP first load, JS / CSS compressed (gzip 6), signed out, measured in a browser on preview builds:

| Page | Before | After |
|---|---|---|
| Home | 229 / 60 KB | 164 / 31 KB |
| Catalogue | 226 / 59 KB | 187 / 39 KB |
| Product | 225 / 59 KB | 166 / 33 KB |
| Login | 219 / 54 KB | 178 / 32 KB |
| Sign-up | 219 / 54 KB | 197 / 37 KB |

Entry stylesheet 360 → 110 KB (SHOP), 415 → 113 KB (SIA). Pages now load 30–40 small files instead of ~10 (HTTP/2, cheap). Lighthouse phone on previews (uncompressed, so pessimistic): home 49–54 → 55, catalogue 56 → 62, product 52 → 64, login 53 → 61; SIA sign-in desktop 90 → 94. Whole Playwright suite (Chromium + 360 px) passes.

Still in every first load: Vue (~80 KB raw), vue-router (23 KB), Vuetify core, the shell (lists, menus, snackbar), Vuetify's date adapter (11.5 KB, created by `createVuetify` whatever the page). Further steps would be per-page (lazy-load below-the-fold parts) with smaller returns.

### 5.3 C, B, D and honest phone numbers (2026-11-25, branch `perf/lighthouse-c-b-d`)

- **C:** Inter (Latin) preloaded from index.html (`preloadFonts()` in `packages/web-ui/tooling/build-extras.ts`; the file name is hashed, so it is written at build); the first hero slide gets `fetchpriority="high"`; `gears.webp` (decorative, shown at 22 % opacity) re-encoded at WebP quality 45: 107 → 59 KB, no visible change.
- **B:** the build stores a level-9 `.gz` next to every text asset ≥ 1 KB (`precompress()`; not source maps) and the SPA locations have `gzip_static on` (production template + staging gateway; both pass `nginx -t`; the official nginx image has the module). The SHOP main script goes out at 63 KB (180 KB raw). No brotli: it needs an nginx module the stock image does not have.
- **D:** `tools/perf/lighthouse-gate.mjs` runs at the end of the CI e2e job against the production builds (SHOP home, catalogue, a product, login at phone size; SIA sign-in): fails on accessibility below 100 or CLS above 0.1; all scores go to the job summary, HTML reports to the `lighthouse-reports` artifact. Performance is reported, not gated.
- **Honest phone numbers.** ESET also intercepts plain HTTP from Chrome that Lighthouse starts, so measuring from Windows is skewed even against localhost. Measured instead with Lighthouse in a Linux container on the same Docker network as an nginx container serving the production builds with this gzip/gzip_static setup (traffic never touches the Windows network stack; Lighthouse's simulated slow 4G still applies):

| Page | Phone perf | FCP | LCP | TBT | CLS |
|---|---|---|---|---|---|
| SHOP home | 68 | 2.9 s | 4.0 s | 560 ms | 0 |
| SHOP catalogue | 81 | 3.0 s | 4.0 s | 120 ms | 0.002 |
| SHOP product | 80 | 2.8 s | 3.8 s | 210 ms | 0 |
| SHOP login | 82 | 2.8 s | 3.5 s | 220 ms | 0 |
| SIA sign-in (desktop) | 99 | 0.7 s | 0.8 s | 0 ms | 0 |

Before the fixes, staging measured 37–58 on phones (ESET-skewed, so not directly comparable). Next lever if wanted: SHOP home's 560 ms of main-thread blocking (the hero carousel and the masthead start together).

How to repeat the honest measurement: serve `web/*/dist` from `nginx:1.27-alpine` with the gateway's gzip lines (`/api/*` proxied to the dev stack through `host.docker.internal`), put it and a `node:22-bookworm-slim` container (apt `chromium`, `CHROME_PATH=/usr/bin/chromium`) on one Docker network, and run `npx lighthouse@12.6.0 http://<nginx>:<port>/ --chrome-flags="--headless=new --no-sandbox" --form-factor=mobile` in the node container.

## 6. State at the end of the session (2026-11-25, second session)

- **#55 merged** (squash) and deployed to staging; this plan is on `main` with it. 5-A done (§5.1).
- **#56 merged and the edge file installed on kw-server by hand** (backup `/srv/edge-sites/cimh-stores-staging.conf.bak`, `nginx -t`, reload): `/api/` answers now leave uncompressed, web app files still gzip, the other sites on the edge answer as before (`printitdesigns.com` without `www.` has a certificate that doesn't name it: pre-existing, not ours).
- **Fix 6 built** on branch `fix/signed-out-console-and-pick-queue` (with SIA/SHOP UI work from the same session).
- **#57 merged** (fix 6 + SIA pick/desk UI). **Fix 3 built** on `perf/smaller-first-load` (§5.2).
- **C, B, D built** on `perf/lighthouse-c-b-d` (stacked on #58; rebase onto `main` once #58 merges). Honest phone numbers in §5.3.
- **Next (optional):** SHOP home main-thread blocking (560 ms); check staging after the deploys (Best practices 100 expected once #57 is live).
- PR #54 (announcements + invoice CRUD) is merged and on staging: order-svc's `invoices` upgrade made 35 records, 0 number clashes; the staging edge site is installed (announcement WebSocket 101 on both hosts, a foreign Origin gets 403).
- Preview servers were running on 15291 (SHOP) / 15292 (SIA) from `web/*/dist` built on this branch. **Gotcha:** stopping a background `npx vite preview` task leaves its `node` process holding the port; kill the listener (PowerShell `Get-NetTCPConnection -LocalPort 15291 -State Listen` → `Stop-Process`) before restarting, and restart previews after editing `vite.config.ts` (the CSP header is read at start).
- **Never run `deploy/staging-lite/deploy.sh --edge` from a tree with unmerged changes:** it rebuilds and ships the local tree before installing the edge file.

## 7. How to run it again

1. Dev stack up (`docker compose -f deploy/compose.dev.yml --profile kafka up -d`), then fresh previews on free ports (15291/15292 here; 15195/15196 and 15184 were taken by stale servers):
   ```bash
   npm run build -w @cimh/shop -w @cimh/sia
   (cd web/shop && npx vite preview --port 15291 --strictPort) &
   (cd web/sia && npx vite preview --port 15292 --strictPort) &
   ```
2. Copy the spec below to `tests/e2e-web/lighthouse.local.spec.ts` (Playwright only finds specs in its `testDir`; **delete it afterwards, never commit it**) and run:
   ```bash
   LH_OUT=<scratch dir> SHOP_URL=http://localhost:15291 SIA_URL=http://localhost:15292 \
     npx playwright test -c tests/e2e-web lighthouse.local.spec.ts --project=chromium --reporter=list
   ```
   About 15 minutes for the 38 audits; `summary.json` and one HTML report per page land in `LH_OUT`. It creates test accounts (staff, customer, admin with MFA), a product and a request in the **dev** database only.
3. **On this PC, HTTPS pages (staging) come back uncompressed in Lighthouse because of ESET (§5.1)**; local previews (plain HTTP) are not affected.
4. A single public page by hand: `npx --yes lighthouse@12.6.0 http://localhost:15291/catalogue --form-factor=mobile --view` (or `--preset=desktop`). In Chrome DevTools: Lighthouse tab, Incognito; for signed-in pages sign in first and untick "Clear storage" under the gear.

Helper probes used (recreate as throwaway specs when needed): a `PerformanceObserver({ type: 'layout-shift', buffered: true })` recording `sources[].node` and previous/current rects, and a `securitypolicyviolation` listener recording `violatedDirective`, `blockedURI`, `sourceFile`.

### The spec

```ts
/**
 * THROWAWAY (not committed): Lighthouse over every main SHOP and SIA page, signed in where the page needs it.
 * Playwright signs in and hands the session cookies to Lighthouse as an extra Cookie header; Lighthouse starts its
 * own Chrome for every audit (it could not drive a Chrome that Playwright was attached to). Reports go to LH_OUT.
 */
import { expect, test, type Browser } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { SHOP, SIA } from './playwright.config'
import { adminWithMfa, bearer, customerAccount, mongo, nextTotpWindow, ORDERS, orderableProduct, PASSWORD, req, staffAccount, totp } from './support'

const OUT = process.env.LH_OUT!
type Row = { app: string; page: string; form: string; perf: number; a11y: number; bp: number; seo: number; lcp: string; cls: string; tbt: string }
const results: Row[] = []

function lighthouse(app: string, name: string, url: string, form: 'mobile' | 'desktop', headers?: string) {
  const base = join(OUT, `${app}-${name}-${form}`)
  const args = ['--yes', 'lighthouse@12.6.0', url, '--quiet', '--chrome-flags="--headless=new"', '--output=json', '--output=html',
    `--output-path="${base}"`, ...(form === 'desktop' ? ['--preset=desktop'] : ['--form-factor=mobile']), ...(headers ? [`--extra-headers="${headers}"`] : [])]
  try {
    execFileSync('npx', args, { stdio: 'pipe', shell: true, timeout: 150_000 })
  } catch (e) {
    console.log(`lighthouse failed for ${app} ${name} ${form}: ${String((e as { stderr?: Buffer }).stderr ?? e).slice(0, 300)}`)
    return
  }
  const r = JSON.parse(readFileSync(`${base}.report.json`, 'utf8'))
  const s = (k: string) => Math.round((r.categories[k]?.score ?? 0) * 100)
  const a = (k: string) => r.audits[k]?.displayValue ?? ''
  results.push({ app, page: name, form, perf: s('performance'), a11y: s('accessibility'), bp: s('best-practices'), seo: s('seo'),
    lcp: a('largest-contentful-paint'), cls: a('cumulative-layout-shift'), tbt: a('total-blocking-time') })
  writeFileSync(join(OUT, 'summary.json'), JSON.stringify(results, null, 1))
  console.log(`done ${results.length}: ${app} ${name} ${form}`)
}

/** Sign in in a fresh context and write the session cookies as a Lighthouse header file. */
async function signIn(browser: Browser, app: 'shop' | 'sia', email: string, key?: string): Promise<string> {
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  await page.goto(`${app === 'shop' ? SHOP : SIA}/login`)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Log in' }).click()
  if (key) {
    await nextTotpWindow()
    await page.getByRole('textbox', { name: '6-digit code' }).fill(totp(key))
  }
  await expect(page).not.toHaveURL(/\/login/, { timeout: 20_000 })
  const cookies = (await ctx.cookies()).map((c) => `${c.name}=${c.value}`).join('; ')
  await ctx.close()
  const file = join(OUT, `headers-${app}-${key ? 'admin' : 'user'}.json`)
  writeFileSync(file, JSON.stringify({ Cookie: cookies }))
  return file
}

test('lighthouse over SHOP and SIA', async ({ browser }) => {
  test.setTimeout(90 * 60_000)
  rmSync(OUT, { recursive: true, force: true })
  mkdirSync(OUT, { recursive: true })

  // Data: a customer with one request, staff, an admin with MFA, a product on SHOP.
  const staff = await staffAccount('lh')
  const customer = await customerAccount('lhbuyer')
  const admin = await adminWithMfa()
  const pid = await orderableProduct(staff, 'Lighthouse barometer', { cost: '150.00' })
  const auth = { authorization: `Bearer ${await bearer(customer)}`, 'content-type': 'application/json' }
  expect((await req(`${ORDERS}/api/orders/v1/cart/lines/${pid}`, { method: 'PUT', headers: auth, body: JSON.stringify({ qty: 2 }) })).status).toBe(200)
  const shipTo = { line1: '1 Husbands Road', city: 'St James', country: 'BB', firstname: 'Cass', lastname: 'Tomer', email: customer }
  const sub = await req(`${ORDERS}/api/orders/v1/requests`, { method: 'POST', headers: auth, body: JSON.stringify({ shipTo }) })
  expect(sub.status).toBe(201)
  const rid = ((await sub.json()) as { requests: { id: string }[] }).requests[0]!.id
  const shopProduct = mongo<string>(`return db.product.findOne({ active: true, sellable: true, type: 'MET', 'images.0': { $exists: true } }, { id: 1 })?.id ?? ${JSON.stringify(pid)}`)

  // SHOP signed out.
  for (const [name, path] of [['home', '/'], ['catalogue', '/catalogue'], ['product', `/catalogue/${shopProduct}`], ['pro-bono', '/pro-bono'], ['login', '/login'], ['signup', '/signup']] as const)
    for (const form of ['mobile', 'desktop'] as const) lighthouse('shop', name, `${SHOP}${path}`, form)
  // SHOP as the customer.
  let h = await signIn(browser, 'shop', customer)
  for (const [name, path] of [['cart', '/cart'], ['requests', '/requests'], ['request', `/requests/${rid}`], ['account', '/account']] as const)
    for (const form of ['mobile', 'desktop'] as const) lighthouse('shop', name, `${SHOP}${path}`, form, h)
  // SIA as staff (a desk app: desktop).
  h = await signIn(browser, 'sia', staff)
  for (const [name, path] of [['home', '/'], ['requests', '/requests'], ['request', `/requests/${rid}`], ['products', '/products'], ['product', `/products/${pid}`],
    ['inventory', '/inventory'], ['pick', '/pick'], ['reports-stock', '/reports/stock'], ['reports-history', '/reports/history'], ['profile', '/profile']] as const)
    lighthouse('sia', name, `${SIA}${path}`, 'desktop', h)
  // SIA as an admin with MFA.
  h = await signIn(browser, 'sia', admin.email, admin.key)
  for (const [name, path] of [['admin', '/admin'], ['accounts', '/admin/accounts'], ['approvals', '/admin/approvals'], ['organisations', '/admin/organisations'],
    ['audit', '/admin/audit'], ['settings', '/admin/settings'], ['announcements', '/admin/announcements']] as const)
    lighthouse('sia', name, `${SIA}${path}`, 'desktop', h)
  // SIA sign-in page, signed out.
  lighthouse('sia', 'login', `${SIA}/login`, 'desktop')
})
```
