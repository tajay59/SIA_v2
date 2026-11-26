# Sign-in pictures (AuthCard)

The owner generates these (2026-11-16). Drop the files here with these exact names; `auth-motion.ts` picks them up
at build time. Until `shop.webp` / `sia.webp` exist, the legacy enclosure photo stands in.

| File | What | Size |
|---|---|---|
| `shop.webp` | SHOP still (daylight) | 1536 × 2048 (3:4 portrait), WebP, < 400 KB |
| `sia.webp` | SIA still (night) | 1536 × 2048 (3:4 portrait), WebP, < 400 KB |
| `shop-800.webp`, `sia-800.webp`, … (optional) | Smaller copies of a still (`<app>-<width>.webp`), used for phones' 200 px band via `srcset` | e.g. 800 and 1024 wide |
| `shop.mp4` (optional) | SHOP silent loop, first frame = the still | 1080 × 1440 (3:4), 6–10 s, H.264, no audio, < 4 MB |
| `sia.mp4` (optional) | SIA silent loop | same |

Rules (Design Brief §7): no text, logos, faces or recognisable brands; must not show or imply a specific catalogue
product (so: an invented, unbranded device, never a real instrument from the catalogue). The picture is cropped to
fill a tall panel on desktop and a 200 px band on phones, so keep the subject in the middle third.

## Prompts

Written for an image model such as **FLUX.1 [pro]** on OpenArt.ai (portrait 3:4; 2:3 also works). For video, use the still as the
start frame in an image-to-video model (e.g. Kling or Runway) with the motion prompt.

Owner direction (2026-11-16): futuristic technology, not a weather station.

**SHOP (light, daytime)**
> Futuristic environmental sensing technology, clean high-end product render: a sleek white and pale-silver
> sensor module with smooth curved surfaces and fine machined seams floats above a soft white floor, thin rings
> of translucent glass orbit it, faint cyan light lines trace airflow and rain data around it like a hologram,
> bright diffused daylight studio, soft shadows, lots of white space, colour palette white, silver, ocean blue
> #0084C8 and a touch of cyan. Minimal, precise, optimistic, Apple-style industrial design, sharp focus,
> subject in the middle third, empty space above. No people, no text, no logos.

Negative: text, letters, numbers, watermark, logo, people, faces, brand names, cluttered, dark, grungy, neon pink,
purple, cartoon, low detail.

**SIA (dark, night)**
> Futuristic control and logistics technology in darkness: a sleek matte-graphite sensor core with precise
> machined edges stands on a dark reflective floor, a slow ring of thin cyan light scans around it, fine glowing
> data lines and small light points rise from it like a holographic map of the Caribbean sky, deep navy and
> graphite tones, cool cyan #5CC2FF highlights, cinematic low-key lighting, light haze, high-end product render,
> sharp focus, subject in the middle third. No people, no text, no logos.

Negative: same as SHOP, plus: bright background, warm orange light, red.

**Motion prompt (both)**
> Locked-off camera. The light rings orbit slowly, data lines drift gently upward, a soft glow pulses once every
> few seconds. No camera movement, no zoom, no cuts. Seamless loop.

## Provenance (fill in when delivered)

| Item | SHOP | SIA |
|---|---|---|
| Tool / model | | |
| Prompt used (if changed) | | |
| Licence (commercial use allowed?) | | |
| Date | | |
