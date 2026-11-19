#!/usr/bin/env bash
# Build APK BPF Agenda (WorkHub) di workstation ini.
#   ./scripts/build-android.sh            -> APK debug
#   ./scripts/build-android.sh --release  -> APK release bertanda tangan keystore
#
# Prasyarat sekali jalan (sudah dipasang):
#   1. Node/npm + cordova CLI 13 (npm prefix user: ~/.npm-global)
#   2. JDK 17        : /home/it/android-tools/jdk/jdk-17.0.21+9
#   3. Android SDK   : /home/it/android-tools/android-sdk (platforms 34/36, build-tools 34/36)
#   4. Gradle 8.14.2 : /home/it/android-tools/gradle-8.14.2
#   5. Khusus --release: keystore + ~/.config/bpf-workhub/keystore.properties
#   Semua diset oleh scripts/android-env.sh — file ini otomatis di-source.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MODE="debug"
for arg in "$@"; do
  case "$arg" in
    --release) MODE="release" ;;
    --debug)   MODE="debug" ;;
    -h|--help)
      sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "argumen tidak dikenal: $arg" >&2; exit 2 ;;
  esac
done

# shellcheck disable=SC1091
source "$ROOT/scripts/android-env.sh"
cd "$ROOT/mobile"

if ! command -v cordova >/dev/null; then
  echo "cordova belum terpasang. Jalankan: npm config set prefix ~/.npm-global && npm i -g cordova"
  exit 1
fi

if [ ! -d platforms/android ]; then
  cordova platform add android
fi

# cordova-android menulis versionName/versionCode ke app/build.gradle hanya saat
# platform ditambahkan, jadi setelah config.xml naik versi APK bisa tetap versi
# lama. Samakan dulu dengan config.xml (idempotent).
VERSION="$(sed -n 's:.*<widget[^>]*version="\([^"]*\)".*:\1:p' config.xml | head -1)"
[ -n "$VERSION" ] || { echo "versi tidak ditemukan di config.xml"; exit 1; }
python3 - "$VERSION" <<'PY'
import re, sys
v = sys.argv[1]
parts = (v.split('.') + ['0', '0', '0'])[:3]
code = int(parts[0]) * 10000 + int(parts[1]) * 100 + int(parts[2])
p = 'platforms/android/app/build.gradle'
s = open(p, encoding='utf-8').read()
new = re.sub(r'(?m)^(\s*)versionCode \d+', lambda m: f'{m.group(1)}versionCode {code}', s, count=1)
new = re.sub(r'(?m)^(\s*)versionName "[^"]*"', lambda m: f'{m.group(1)}versionName "{v}"', new, count=1)
if new != s:
    open(p, 'w', encoding='utf-8').write(new)
    print(f'   versi build.gradle diset {v} ({code})')
PY

if [ "$MODE" = "release" ]; then
  # Rahasia tidak disimpan di repo: file ini di luar proyek, mode 600.
  PROPS="${BPF_KEYSTORE_PROPS:-$HOME/.config/bpf-workhub/keystore.properties}"
  [ -f "$PROPS" ] || {
    echo "berkas signing tidak ditemukan: $PROPS" >&2
    echo "Buat keystore dulu (keytool) lalu tulis KEYSTORE/ALIAS/STORE_PASSWORD/KEY_PASSWORD." >&2
    exit 1
  }
  # shellcheck disable=SC1090
  . "$PROPS"
  : "${KEYSTORE:?KEYSTORE kosong di $PROPS}"
  : "${ALIAS:?ALIAS kosong di $PROPS}"
  : "${STORE_PASSWORD:?STORE_PASSWORD kosong di $PROPS}"
  : "${KEY_PASSWORD:?KEY_PASSWORD kosong di $PROPS}"
  [ -f "$KEYSTORE" ] || { echo "keystore tidak ditemukan: $KEYSTORE" >&2; exit 1; }

  echo "Mode: release  (keystore: $KEYSTORE, alias: $ALIAS)"
  # --packageType=apk: cordova-android 15 menghasilkan .aab untuk --release,
  # padahal distribusi internal lewat panel admin membutuhkan APK.
  # Parameter signing diteruskan ke cordova-android -> signingConfigs.release
  cordova build android --release -- \
    --packageType=apk \
    --keystore="$KEYSTORE" \
    --storePassword="$STORE_PASSWORD" \
    --alias="$ALIAS" \
    --password="$KEY_PASSWORD"
else
  echo "Mode: debug"
  cordova build android
fi

APK="$ROOT/mobile/platforms/android/app/build/outputs/apk/$MODE/app-$MODE.apk"
[ -f "$APK" ] || { echo "APK tidak ditemukan — periksa log build di atas." >&2; exit 1; }

mkdir -p "$ROOT/dist"
if [ "$MODE" = "release" ]; then
  # Nama terpisah supaya APK debug yang sudah beredar tidak tertimpa; signature
  # release berbeda dari debug sehingga pasang-baru harus uninstall dulu.
  OUT="$ROOT/dist/bpf-agenda-${VERSION}-release.apk"
  cp -f "$APK" "$OUT"
  echo ""
  echo "APK release: $OUT"
  APKSIGNER="$(ls -d "$ANDROID_SDK_ROOT"/build-tools/*/apksigner 2>/dev/null | tail -1)"
  if [ -n "${APKSIGNER:-}" ] && [ -x "$APKSIGNER" ]; then
    "$APKSIGNER" verify --print-certs "$OUT" | grep -E "Verifies|Signer #1 certificate (DN|SHA-256)" || true
  fi
else
  cp -f "$APK" "$ROOT/dist/bpf-agenda-${VERSION}.apk"
  cp -f "$APK" "$ROOT/dist/bpf-agenda.apk"
  echo ""
  echo "APK debug: $ROOT/dist/bpf-agenda-${VERSION}.apk (juga bpf-agenda.apk)"
fi
echo "Keystore rilis wajib di-backup: tanpa itu aplikasi tidak bisa di-update lagi."
