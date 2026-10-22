#!/bin/sh
# ============================================================
# Restore drill — BPF WorkHub (v2.49.2, temuan audit no. 6)
# ------------------------------------------------------------
# Buktikan bahwa .sql.gz backup benar-benar bisa di-restore,
# bukan hanya terbuat. Kegunaan ISO 27001 A.8.13.
#
# Cara pakai (dari host):
#   docker exec bpf-workhub-backup /bin/sh /usr/local/bin/restore-test.sh
#   ⚡ buat uji restore di DB SEMENTARA, tidak menyentuh DB asli
#   ⚡ keluar 0 bila verifikasi restore OK; 1..3 bila gagal
# ============================================================
set -eu

HOST="${MYSQL_HOST:-db}"
ROOT_PW="${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD wajib}"
OUT_DIR="/backups"
SCRATCH_DB="restore_dr_tmp"

# --- Deteksi file uji — pilih dump TERBARU dari DB master -------------------
TEST_FILE=$(find "$OUT_DIR" -name 'bpf_bpf_asset_system_*.sql.gz' -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
if [ -z "$TEST_FILE" ]; then
  echo "[restore-test] GAGAL: tidak ada bpf_bpf_asset_system_*.sql.gz"
  exit 2
fi
echo "[restore-test] File uji: $(basename "$TEST_FILE")"

# 1. Integritas arsip --------------------------------------------------------
gzip -t "$TEST_FILE" && echo "[restore-test] gzip -t OK"

# 2. Restore ke DB sementara -------------------------------------------------
mysql -h "$HOST" -uroot -p"$ROOT_PW" -e "DROP DATABASE IF EXISTS $SCRATCH_DB; CREATE DATABASE $SCRATCH_DB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci" 2>/dev/null
gunzip -c "$TEST_FILE" | mysql -h "$HOST" -uroot -p"$ROOT_PW" "$SCRATCH_DB" 2>/dev/null

# 3. Verifikasi row terbaca — non-sample table utama masuk log -----------------
N_USERS=$(mysql -h "$HOST" -uroot -p"$ROOT_PW" -N -e "SELECT COUNT(*) FROM $SCRATCH_DB.users" 2>/dev/null || echo 0)
N_TX=$(mysql -h "$HOST" -uroot -p"$ROOT_PW" -N -e "SELECT COUNT(*) FROM $SCRATCH_DB.transactions" 2>/dev/null || echo 0)

# 4. Bersih-bersih ------------------------------------------------------------
mysql -h "$HOST" -uroot -p"$ROOT_PW" -e "DROP DATABASE $SCRATCH_DB" 2>/dev/null

[ "$N_USERS" -gt 0 ] || { echo "[restore-test] GAGAL: users = 0 rows"; exit 1; }
echo "[restore-test] OK — users=$N_USERS transactions=$N_TX — DB dril di-drop"
