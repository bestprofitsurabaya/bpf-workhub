#!/usr/bin/env bash
# Publikasikan APK BPF Agenda ke folder rilis WorkHub.
#
# Pemakaian:
#   ./scripts/publish-release.sh apk/dist/bpf-agenda-1.8.0-release.apk "Catatan rilis"
#
# Folder tujuan: $BPF_APK_DIR (default /srv/bpf-workhub/apk di NAS; di mesin
# build bisa diarahkan ke folder lokal). Skrip menulis:
#   <folder>/bpf-agenda-<versi>-release.apk
#   <folder>/latest.json          <- dibaca /api/app/latest
#
# Rilis wajib (tombol "Nanti" disembunyikan di aplikasi):
#   BPF_UPDATE_MANDATORY=1 ./scripts/publish-release.sh ...
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APK_ROOT="$(cd "$DIR/.." && pwd)"
CONFIG="$APK_ROOT/mobile/config.xml"

APK="${1:-}"
NOTES="${2:-}"
TARGET="${BPF_APK_DIR:-/srv/bpf-workhub/apk}"

if [ -z "$APK" ] || [ ! -f "$APK" ]; then
  echo "Pemakaian: $0 <file.apk> [catatan rilis]" >&2
  exit 2
fi
if [ ! -f "$CONFIG" ]; then
  echo "config.xml tidak ditemukan: $CONFIG" >&2
  exit 2
fi

VERSION="$(sed -n 's/.*<widget[^>]*version="\([^"]*\)".*/\1/p' "$CONFIG" | head -1)"
if [ -z "$VERSION" ]; then
  echo "Tidak bisa membaca versi dari $CONFIG" >&2
  exit 2
fi

IFS=. read -r MAJOR MINOR PATCH <<<"$VERSION"
PATCH="${PATCH%%[!0-9]*}"
CODE=$((10#$MAJOR * 10000 + 10#$MINOR * 100 + ${PATCH:-0}))
NAME="bpf-agenda-${VERSION}-release.apk"

mkdir -p "$TARGET"
cp -f "$APK" "$TARGET/$NAME"

SHA="$(sha256sum "$TARGET/$NAME" | awk '{print $1}')"
MANDATORY="false"
[ "${BPF_UPDATE_MANDATORY:-0}" = "1" ] && MANDATORY="true"
RELEASED_AT="$(date -Iseconds)"

python3 - "$TARGET/latest.json" "$VERSION" "$CODE" "$NAME" "$SHA" "$MANDATORY" "$RELEASED_AT" "$NOTES" <<'PY'
import json
import sys

path, version, code, name, sha, mandatory, released, notes = sys.argv[1:9]
data = {
    'version_name': version,
    'version_code': int(code),
    'file': name,
    'sha256': sha,
    'size': __import__('os').path.getsize(__import__('os').path.join(
        __import__('os').path.dirname(path), name)),
    'notes': notes,
    'mandatory': mandatory == 'true',
    'released_at': released,
}
with open(path, 'w', encoding='utf-8') as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)
    fh.write('\n')
print(f"manifest: {path}")
PY

echo "APK     : $TARGET/$NAME"
echo "Versi   : $VERSION (versionCode $CODE)"
echo "SHA-256 : $SHA"
echo "Wajib   : $MANDATORY"
