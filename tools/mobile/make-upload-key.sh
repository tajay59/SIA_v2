#!/usr/bin/env bash
# Creates the SIA Mobile upload key (RSA 4096, 30 years) for release signing. Run ONCE, by the owner.
# Keep the .jks and both passwords in the CIMH password manager: losing them means a new app id.
# Then either write mobile/sia/keystore.properties (git-ignored):
#   storeFile=/absolute/path/sia-upload.jks
#   storePassword=...
#   keyAlias=sia-upload
#   keyPassword=...
# or set the GitHub secrets SIA_KEYSTORE_BASE64 (base64 of the .jks), SIA_KEYSTORE_PASSWORD, SIA_KEY_PASSWORD
# (alias sia-upload) so CI builds a signed internal APK.
set -euo pipefail
out="${1:?usage: make-upload-key.sh <path/to/sia-upload.jks>}"
[ -e "$out" ] && { echo "refusing to overwrite $out" >&2; exit 1; }
keytool -genkeypair -v -keystore "$out" -storetype PKCS12 -alias sia-upload \
  -keyalg RSA -keysize 4096 -validity 10950 \
  -dname "CN=SIA Mobile, OU=Stores, O=Caribbean Institute for Meteorology and Hydrology, L=Bridgetown, C=BB"
keytool -list -v -keystore "$out" -alias sia-upload | grep -E "SHA256|Valid"
