#!/usr/bin/env bash
# Build Wallet.apk without Gradle: aapt -> javac -> dx -> zipalign -> apksigner.
# Needs (Ubuntu): openjdk, android-sdk-platform-23, aapt, dalvik-exchange, zipalign, apksigner.
set -euo pipefail
cd "$(dirname "$0")"
SDK=/usr/lib/android-sdk/platforms/android-23/android.jar
KS="${KEYSTORE:-wallet-release.jks}"
rm -rf build && mkdir -p build/gen build/classes

python3 make_index.py
python3 make_icons.py

aapt package -f -m -J build/gen -M AndroidManifest.xml -S res -A assets -I "$SDK" \
  --min-sdk-version 21 --target-sdk-version 34 --version-code 2 --version-name 1.1 -F build/res.apk
javac --release 8 -nowarn -Xlint:-options -classpath "$SDK" -d build/classes \
  build/gen/com/aboubakr/wallet/R.java src/com/aboubakr/wallet/MainActivity.java
dalvik-exchange --dex --min-sdk-version=21 --output=build/classes.dex build/classes

# Android 11+ needs resources.arsc stored uncompressed: rebuild the zip with it STORED.
python3 - <<'PY'
import zipfile
src, dst = "build/res.apk", "build/unsigned.apk"
with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        stored = item.filename == "resources.arsc" or item.filename.endswith(".png")
        zout.writestr(item, data, compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED)
    zout.write("build/classes.dex", "classes.dex", compress_type=zipfile.ZIP_DEFLATED)
PY
zipalign -f -p 4 build/unsigned.apk build/aligned.apk

if [ ! -f "$KS" ]; then
  PASS="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"
  keytool -genkeypair -keystore "$KS" -alias wallet -keyalg RSA -keysize 2048 -validity 10000 \
    -storepass "$PASS" -keypass "$PASS" -dname "CN=Family Wallet, O=Personal, C=DZ" >/dev/null 2>&1
  echo "$PASS" > keystore.txt
fi
PASS="$(cat keystore.txt)"
apksigner sign --ks "$KS" --ks-key-alias wallet --ks-pass "pass:$PASS" --key-pass "pass:$PASS" \
  --min-sdk-version 21 --out build/Wallet.apk build/aligned.apk
apksigner verify --verbose build/Wallet.apk | head -6
ls -la build/Wallet.apk
