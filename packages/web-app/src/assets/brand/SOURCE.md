# Brand marks

Supplied by the owner on 2026-11-12 in `logos/` (`sia.svg`, `stores.svg`). The originals carry a C2PA manifest
(content credentials), i.e. they were made with a generative tool; the manifest is kept in `logos/`.

Derived here by `logos.mjs` (one-off script, run 2026-11-12; logic recorded in the CLAUDE.md log):
- full-canvas background shape removed, C2PA metadata stripped, viewBox cropped to the artwork;
- wordmark: the "o" and "e" counters, painted in the background colour in the original, are cut with
  `fill-rule="evenodd"`; two stray light specks removed;
- `stores-wordmark-dark.svg`: "CIMH" in #E6E8EB, "Stores" in the dark-theme primary #5CC2FF.

Used by: SIA drawer/app bar + `web/sia/public/favicon.svg` (`sia-mark.svg`); SHOP top bar (wordmarks).
The CIMH institute crest (`../cimh-logo-*.webp`) stays where it stands for the institute (SHOP home logo
band, sign-in pages).
