#!/usr/bin/env bash
# 打包平板 App：bash android/build.sh → android/build/xingce-xiuxian.apk
# 不用 Gradle，直接用 Android SDK 的 aapt2 / d8 / apksigner（GitHub 的 ubuntu 机器上自带 SDK）。
# 版本号跟 rpg/version.py 走；签名用 android/xiuxian.keystore（同一把钥匙签，平板上才能直接覆盖升级）。
set -euo pipefail
cd "$(dirname "$0")"
SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:?需要 Android SDK}}"
BT=$(ls -d "$SDK"/build-tools/* | sort -V | tail -1)
PLAT=$(ls -d "$SDK"/platforms/android-* | sort -V | tail -1)
JAR="$PLAT/android.jar"
API=${PLAT##*android-}
VER=$(sed -n 's/^VERSION = "\(.*\)"/\1/p' ../rpg/version.py)
IFS=. read -r A B C <<<"$VER"
CODE=$((A * 10000 + B * 100 + C))
echo "build-tools $BT, platform $PLAT, version $VER ($CODE)"

rm -rf build && mkdir -p build/gen/com/xingce/xiuxian build/classes build/dex
cat > build/gen/com/xingce/xiuxian/BuildInfo.java <<JAVA
package com.xingce.xiuxian;
final class BuildInfo { static final String VERSION = "$VER"; }
JAVA

"$BT/aapt2" compile --dir res -o build/res.zip
"$BT/aapt2" link -I "$JAR" --manifest AndroidManifest.xml -A assets -o build/base.apk \
  --version-code "$CODE" --version-name "$VER" --min-sdk-version 24 --target-sdk-version "$API" \
  --java build/gen build/res.zip
javac -source 1.8 -target 1.8 -bootclasspath "$JAR" -encoding UTF-8 -nowarn -d build/classes \
  $(find src build/gen -name '*.java')
"$BT/d8" --release --min-api 24 --lib "$JAR" --output build/dex $(find build/classes -name '*.class')
cp build/base.apk build/unsigned.apk
(cd build/dex && zip -q -j ../unsigned.apk classes.dex)
"$BT/zipalign" -f -p 4 build/unsigned.apk build/aligned.apk
"$BT/apksigner" sign --ks xiuxian.keystore --ks-pass pass:xiuxian2026 --ks-key-alias xiuxian \
  --out build/xingce-xiuxian.apk build/aligned.apk
"$BT/apksigner" verify build/xingce-xiuxian.apk
ls -l build/xingce-xiuxian.apk
