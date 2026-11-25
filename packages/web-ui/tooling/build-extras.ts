/**
 * Build steps for SHOP and SIA (Lighthouse fixes B and C, docs/plans/2026-11-25-lighthouse.md).
 *
 * - `preloadFonts()`: preloads the Latin Inter file in index.html. Its name is hashed, so it is only known once
 *   the bundle exists. Inter uses `font-display: swap`, so text never waits for it; the preload only saves the
 *   round trip that otherwise starts after the CSS arrives (the largest text paints in Inter sooner).
 * - `precompress()`: writes `<file>.gz` (gzip level 9) next to every text asset of 1 KB or more, so nginx serves
 *   the stored copy (`gzip_static on`) instead of compressing at level 5 on every request.
 */
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { gzipSync } from 'node:zlib'

interface Bundle {
  [fileName: string]: { type: string; fileName: string }
}

export function preloadFonts(pattern = /inter-latin-wght-normal-[^/]+\.woff2$/) {
  return {
    name: 'cimh-preload-fonts',
    apply: 'build' as const,
    transformIndexHtml: {
      order: 'post' as const,
      handler(_html: string, ctx: { bundle?: Bundle }) {
        const files = Object.values(ctx.bundle ?? {}).filter((f) => f.type === 'asset' && pattern.test(f.fileName))
        return files.map((f) => ({
          tag: 'link',
          attrs: { rel: 'preload', as: 'font', type: 'font/woff2', href: `/${f.fileName}`, crossorigin: '' },
          injectTo: 'head-prepend' as const,
        }))
      },
    },
  }
}

const TEXT = /\.(js|mjs|css|html|svg|json|txt|xml)$/  // not .map: source maps are fetched only by DevTools

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? walk(path) : [path]
  })
}

export function precompress(outDir = 'dist', minBytes = 1024) {
  return {
    name: 'cimh-precompress',
    apply: 'build' as const,
    closeBundle() {
      for (const file of walk(outDir)) {
        if (!TEXT.test(file)) continue
        const body = readFileSync(file)
        if (body.length < minBytes) continue
        const gz = gzipSync(body, { level: 9 })
        if (gz.length < body.length) writeFileSync(`${file}.gz`, gz)
      }
    },
  }
}
