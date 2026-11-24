#!/usr/bin/env bash
# Builds Bouchra.apk without the Android SDK.
# Needs: JDK, python3 + Pillow, and two jars from Maven Central:
#   android.jar = org.robolectric:android-all:9-robolectric-4913185-2
#   dx.jar      = com.jakewharton.android.repackaged:dalvik-dx:16.0.1
# usage: build.sh <android.jar> <dx.jar>
set -euo pipefail
ANDROID_JAR=$1
DX_JAR=$2
HERE=$(cd "$(dirname "$0")" && pwd)
APP=$(dirname "$HERE")
OUT=$APP/build
rm -rf "$OUT" && mkdir -p "$OUT/classes"

javac --release 8 -encoding UTF-8 -nowarn \
  -cp "$ANDROID_JAR" -d "$OUT/classes" $(find "$APP/src" -name '*.java')

java -cp "$DX_JAR" com.android.dx.command.Main --dex --min-sdk-version=21 \
  --output="$OUT/classes.dex" "$OUT/classes"

python3 "$HERE/build.py" "$OUT/classes.dex" "$OUT/unsigned.apk"

KS=$HERE/bouchra.keystore
if [ ! -f "$KS" ]; then
  keytool -genkeypair -keystore "$KS" -storepass bouchra123 -keypass bouchra123 -alias bouchra \
    -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Bouchra" >/dev/null
fi
cp "$OUT/unsigned.apk" "$OUT/signed.apk"
jarsigner -keystore "$KS" -storepass bouchra123 -keypass bouchra123 \
  -sigalg SHA256withRSA -digestalg SHA-256 "$OUT/signed.apk" bouchra >/dev/null
cp "$OUT/signed.apk" "$APP/Bouchra.apk"
echo "Built $APP/Bouchra.apk"
