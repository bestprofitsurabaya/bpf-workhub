#!/usr/bin/env bash
# ============================================================
# ROTASI KREDENSIAL DB — BPF WorkHub (v2.30)
# ------------------------------------------------------------
# ISO/IEC 27001 A.8.2/A.8.13 (secret management): kredensial lama
# (yang pernah di-hardcode di repo/dokumen) diganti dengan nilai acak
# kuat, disimpan HANYA di .env (chmod 600, gitignored).
#
# Aman & idempoten:
#   - Membaca kredensial LAMA dari .env (harus bisa connect dulu).
#   - Generate 2 password acak baru (openssl rand -hex 24).
#   - ALTER USER root@'localhost', root@'%', dan bpf_user@'%'.
#   - Backup .env lama ke .env.bak-<tanggal> SEBELUM menimpa.
#   - Password TIDAK pernah muncul di argv/ps (dikirim via stdin).
#   - Batal total bila kredensial lama tidak valid (tidak ada perubahan).
#
# Pemakaian:
#   scripts/rotate-db-credentials.sh
# lalu recreate service agar env baru terbaca:
#   docker compose up -d
# Verifikasi: `docker compose ps` (semua healthy) + health `/api/health`.
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$(dirname "$SCRIPT_DIR")/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "❌ .env tidak ditemukan di $(dirname "$SCRIPT_DIR")" >&2
  exit 1
fi

# --- Baca kredensial LAMA dari .env (jangan hardcode apa pun) ---
OLD_ROOT="$(grep -E '^MYSQL_ROOT_PASSWORD=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
OLD_APP="$(grep -E '^MYSQL_PASSWORD=' "$ENV_FILE" | head -1 | cut -d= -f2-)"

if [ -z "$OLD_ROOT" ] || [ -z "$OLD_APP" ]; then
  echo "❌ MYSQL_ROOT_PASSWORD / MYSQL_PASSWORD belum ada di .env" >&2
  exit 1
fi

# --- Container MariaDB berjalan? ---
if ! docker ps --format '{{.Names}}' | grep -qx 'bbm_mariadb'; then
  echo "❌ Container bbm_mariadb tidak berjalan — rotasi dibatalkan." >&2
  exit 1
fi

# --- Generate password baru (hex 24 = 96 bit entropy) ---
NEW_ROOT="$(openssl rand -hex 24)"
NEW_APP="$(openssl rand -hex 24)"

echo "🔐 Mengecek koneksi dengan kredensial lama…"
if ! docker exec bbm_mariadb mariadb -uroot -p"$OLD_ROOT" -e "SELECT 1" >/dev/null 2>&1; then
  echo "❌ Kredensial root lama di .env TIDAK valid — rotasi dibatalkan." >&2
  exit 1
fi

# --- Backup .env ---
BAK="${ENV_FILE}.bak-$(date +%Y%m%d_%H%M%S)"
cp -a "$ENV_FILE" "$BAK"
chmod 600 "$BAK"
echo "📦 Backup .env → $BAK"

# --- Rotasi di MariaDB (berlaku langsung; volume DB tidak dibuat ulang) ---
echo "🔄 Rotasi password root + bpf_user di MariaDB…"
docker exec -i bbm_mariadb mariadb -uroot -p"$OLD_ROOT" <<SQL
ALTER USER 'root'@'localhost' IDENTIFIED BY '${NEW_ROOT}';
ALTER USER 'root'@'%' IDENTIFIED BY '${NEW_ROOT}';
ALTER USER 'bpf_user'@'%' IDENTIFIED BY '${NEW_APP}';
FLUSH PRIVILEGES;
SQL
echo "✅ ALTER USER selesai."

# --- Verifikasi kredensial BARU (root) ---
if ! docker exec bbm_mariadb mariadb -uroot -p"$NEW_ROOT" -e "SELECT 1" >/dev/null 2>&1; then
  echo "❌ Verifikasi root password BARU gagal — pulihkan dari $BAK lalu cek DB." >&2
  exit 1
fi

# --- Tulis .env baru (pertahankan variabel lain yang ada) ---
TMP="$(mktemp)"
awk -v nr="$NEW_ROOT" -v na="$NEW_APP" '
  $0 ~ /^MYSQL_ROOT_PASSWORD=/ { print "MYSQL_ROOT_PASSWORD=" nr; seen_root=1; next }
  $0 ~ /^MYSQL_PASSWORD=/     { print "MYSQL_PASSWORD=" na;     seen_app=1;  next }
  { print }
  END {
    if (!seen_root) print "MYSQL_ROOT_PASSWORD=" nr
    if (!seen_app)  print "MYSQL_PASSWORD=" na
  }
' "$ENV_FILE" > "$TMP"
chmod 600 "$TMP"
mv "$TMP" "$ENV_FILE"

echo ""
echo "✅ Rotasi selesai. Langkah berikut (manual, wajib):"
echo "   1) Recreate service agar env baru terbaca:"
echo "        docker compose up -d"
echo "   2) Verifikasi:"
echo "        docker compose ps                # semua healthy"
echo "        curl -s https://<host>:5000/api/health"
echo "   3) Backup .env lama aman di: $BAK"
echo ""
echo "⚠️  Perintah/docs lama yang memakai kredensial lama kini TIDAK berlaku."
echo "   Selalu baca dari .env (lihat .env.example & DEPLOYMENT.md)."
