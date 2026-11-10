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
| M-02 Home | Placeholder with account and log out. Bottom navigation, scanning, offline queue: P8 with inventory (P4) and orders (P5) |

## Build and test
Needs JDK 17 (Android Studio's `jbr` works) and the Android SDK (`local.properties` with `sdk.dir`; AGP downloads
platform 37 and build-tools itself).

```bash
cd mobile/sia
./gradlew testDebugUnitTest lintDebug assembleDebug   # what CI job `mobile` runs (plus assembleRelease)
```

Lint treats warnings as errors. Dependency versions are chosen on purpose (at least two weeks old), so version
hints are switched off.

**Against the dev stack** (`docker compose -f deploy/compose.dev.yml up -d`): the debug build talks plain HTTP to
`http://10.0.2.2:18001` (the host from the emulator). `DevIdentityContractTest` runs the same session code against
the real identity-svc:

```bash
SIA_DEV_IDENTITY=http://localhost:18001 SIA_DEV_STAFF=<staff email> SIA_DEV_CUSTOMER=<customer email> \
SIA_DEV_PASSWORD=<password> ./gradlew testDebugUnitTest --tests '*DevIdentityContractTest'
```

Accounts: register and verify through the API, then set the role in the dev DB (as `tests/e2e-web/support.ts` does).
The emulator needs a screen lock for the app lock: `adb shell locksettings set-pin 1234`.

## Release
`assembleRelease` is minified and unsigned. Signing (keystore from the CIMH password manager), distribution to
staff devices and the production `API_BASE` come with the internal release in P8.
