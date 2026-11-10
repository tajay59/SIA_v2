# SIA Mobile (v2)

Android app for CIMH staff (APD §5, M-01 to M-11) on the v2 API. Kotlin, Jetpack Compose, Material 3, Android 12+
(minSdk 31). Application id `bb.edu.cimh.sia` (debug: `bb.edu.cimh.sia.debug`), so it installs next to the
legacy app (`com.google.stockinventoryapp`, kept in `AndroidStudioProjects/StockInventoryApp` until cut-over).

## What is built
| Screen / part | State |
|---|---|
| M-01 Login | Email + password; admins with MFA get a code step; customers see "This app is for CIMH staff"; admins without MFA are sent to SIA web to set it up |
| Session | Access token in memory; refresh token sealed with an AES-256-GCM key in the Android Keystore, no backups; rotated on every refresh; single-flight refresh on 401 (`RefreshAuthenticator`) |
| App lock (TR-SEC-11) | Locks after 5 min without a touch; unlock with screen lock or strong biometric; no screen lock on the device → signed out |
| Certificate pinning (TR-SEC-11) | `res/xml/network_security_config.xml`: HTTPS only; `hashiz.store` and `cimh.edu.bb` pinned to ISRG Root X1, X2 and Root YE; pin set expires 2027-12-31 (renew each release) |
| Shell | Bottom navigation Home · Lookup · Stow · Pick · Orders; overflow menu Sync queue (badge) · Log out |
| M-02 Home | Shortcuts, queue card (waiting / refused), last sync |
| M-03 Lookup | Scan a unit or shelf, or type to search the catalogue; shelf → units; product → stock by place; unit sheet with Relocate |
| M-04 Stow | Legacy order: scan the shelf (checked online; offline it is checked when sent), then units in a loop |
| M-05 Pick | Reason once (≤ 300 characters, as on SIA web), then units in a loop |
| M-06 Orders | Requests to pick or ship (paid PURCHASING, Pro Bono APPROVED/PICKING), oldest waiting first |
| M-07 Pick order | CIMH-stock and Pro Bono lines with progress; a unit goes to the first unfinished line of its product (as SIA web); picks go through the queue to order-svc `/requests/{id}/picks` |
| M-08 Ship | Carrier, tracking (typed or camera from the label), note, date, email the customer; online only (If-Match); a stale version reloads |
| M-09 Create product | Legacy order: photos (camera or gallery, ≤ 10), then the fields; v2 adds type, department, project, sellable, Pro Bono (implies sellable). Online; photos uploaded after the save (media-worker processes them); opens the product in Lookup |
| M-10 Create location | Site → location → shelves (new or existing at each step); shows the new shelf codes (labels printed on SIA web) |
| M-11 Sync queue | Queued and refused scans; Send now, Retry (new key), Discard |
| Scanning | `ui/scan`: live camera (CameraX + ML Kit, on the device) plus a text field that submits on Enter (Bluetooth/USB scanners, damaged labels; no autocorrect). Vibration + tone per result |
| Offline queue | `data/queue`: every scan goes through `ScanQueue` (Room table `scans`, schemas exported to `app/schemas`; v2 added `lineId` by auto-migration) and `SyncWorker` (WorkManager, network required). Rules in APD §5 "Offline"; `ScanQueueTest` covers them |
| M-05 Issue · Return | Same tab as Pick (as SIA web): choose a person (identity `/admin/accounts?q=`, active only), then scan units; Return scans units coming back. Both queued like every scan (schema 3 added `assignee`) |
| Theme | Design Brief §14.2: every Material 3 colour role set (light + dark), Inter for text, JetBrains Mono for codes (bundled variable fonts, OFL in `assets/licenses`) |
| Not yet | Run on the Galaxy Note 10+ with a Bluetooth scanner and camera photos (P8 exit); the real upload key (owner) |

## Build and test
Needs JDK 17 (Android Studio's `jbr` works) and the Android SDK (`local.properties` with `sdk.dir`; AGP downloads
platform 37 and build-tools itself).

```bash
cd mobile/sia
./gradlew testDebugUnitTest lintDebug assembleDebug   # what CI job `mobile` runs (plus assembleRelease)
```

Lint treats warnings as errors. Dependency versions are chosen on purpose (at least two weeks old), so version
hints are switched off.

**Against the dev stack** (`docker compose -f deploy/compose.dev.yml up -d`): the debug build talks plain HTTP to the
host from the emulator (`10.0.2.2`), one port per service: identity 18001, catalog 18002, inventory 18004, orders
18005 (`*_BASE` build fields; release uses one host). `DevIdentityContractTest` runs the same session code against
the real identity-svc:

```bash
SIA_DEV_IDENTITY=http://localhost:18001 SIA_DEV_STAFF=<staff email> SIA_DEV_CUSTOMER=<customer email> \
SIA_DEV_PASSWORD=<password> ./gradlew testDebugUnitTest --tests '*DevIdentityContractTest'
```

Accounts: register and verify through the API, then set the role in the dev DB (as `tests/e2e-web/support.ts` does).
The emulator needs a screen lock for the app lock: `adb shell locksettings set-pin 1234`.

**Emulator:** an API 31 image with Google Play (`system-images;android-31;google_apis_playstore;x86_64`). Offline
test: `adb shell svc wifi disable; adb shell svc data disable`, scan, then enable both again. `adb shell input text`
types slowly on the emulator and its Enter can overtake the code: wait until the field shows the whole code before
sending Enter.

## Release
`assembleRelease` is minified (R8). It talks to staging-lite (`https://sia.hashiz.store`, demo production) until
CIMH IT gives the production DNS name (INFRASTRUCTURE §10); then change the `*_BASE` fields in `app/build.gradle.kts`.

**Signing (upload key).** Create it once with `tools/mobile/make-upload-key.sh <path>.jks` and keep the file and both
passwords in the CIMH password manager (losing them means a new app id). Then either:
- local: `mobile/sia/keystore.properties` (git-ignored) with `storeFile`, `storePassword`, `keyAlias=sia-upload`, `keyPassword`;
- CI: GitHub secrets `SIA_KEYSTORE_BASE64` (`base64 -w0 sia-upload.jks`), `SIA_KEYSTORE_PASSWORD`, `SIA_KEY_PASSWORD`.

Without a key the release stays unsigned (PRs, forks). With the secrets set, every push to `main` builds a signed APK
(version code = CI run number) and keeps it 90 days as the artifact `sia-mobile-<run>`: the **internal release**.
Install on a staff phone with `adb install -r app-release.apk` or from a file share (allow "install unknown apps"
for the file manager). Check the signer with `apksigner verify --print-certs`.
