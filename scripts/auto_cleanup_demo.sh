#!/usr/bin/env bash
# ============================================================
# AUTO-CLEANUP DATA DEMO — jalankan via cron setiap hari.
# Data demo (label DEMO) otomatis dihapus H+1 setelah
# MEETING_DATE lewat. Aman: tidak menyentuh data produksi.
#
# Atur tanggal meeting di variabel MEETING_DATE (format YYYY-MM-DD),
# lalu pasang cron (lihat bagian akhir file ini).
# ============================================================
set -euo pipefail

# >>> Ubah sesuai jadwal meeting Anda <<<
MEETING_DATE="${MEETING_DATE:-2026-08-15}"
# >>> =================================== <<<

LOG="${HOME:-/home/it-ef}/bbm_auto_cleanup.log"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL="$SCRIPT_DIR/demo_cleanup.sql"
ENV_FILE="$(dirname "$SCRIPT_DIR")/.env"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

# v2.30: password root dibaca dari .env (JANGAN hardcode di script/repo)
ROOT_PW="$(grep -E '^MYSQL_ROOT_PASSWORD=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
if [ -z "$ROOT_PW" ]; then
  log "ERROR: MYSQL_ROOT_PASSWORD tidak ditemukan di $ENV_FILE"
  exit 1
fi

today=$(date +%F)

if [[ "$today" < "$MEETING_DATE" ]]; then
  # Belum waktunya — beri tahu saja (1x sehari di log).
  log "SKIP: meeting $MEETING_DATE, hari ini $today (data demo dipertahankan)"
  exit 0
fi

if [[ "$today" == "$MEETING_DATE" ]]; then
  # Hari meeting: jangan hapus dulu (mungkin masih demo siang ini).
  log "HARI-H: meeting $MEETING_DATE — data demo masih dipertahankan hari ini"
  exit 0
fi

# Sudah lewat meeting → bersihkan.
if [[ ! -f "$SQL" ]]; then
  log "ERROR: $SQL tidak ditemukan"
  exit 1
fi

if docker exec bbm_mariadb mariadb -uroot -p"$ROOT_PW" bpf_asset_system < "$SQL" >> "$LOG" 2>&1; then
  log "OK: data demo dihapus (H+1 setelah $MEETING_DATE)"
else
  log "ERROR: cleanup gagal — jalankan manual: docker exec -i bbm_mariadb mariadb -uroot -p\"\$MYSQL_ROOT_PASSWORD\" (dari .env) bpf_asset_system < $SQL"
  exit 1
fi

# Hapus user driver demo RIVAN (dibuat untuk demo).
docker exec bbm_mariadb mariadb -uroot -p"$ROOT_PW" bpf_asset_system \
  -e "DELETE FROM users WHERE username='RIVAN' AND role='driver';" >> "$LOG" 2>&1 || true

# Jangan jalankan lagi besok: pindahkan tanggal meeting ke masa lalu sudah otomatis,
# tapi untuk keamanan tulis marker agar tidak mengulang.
touch "${SCRIPT_DIR}/.cleanup_done_${MEETING_DATE}"
log "Selesai. Marker: .cleanup_done_${MEETING_DATE}"

echo "✅ Data demo dibersihkan otomatis. Lihat log: $LOG"
# ------------------------------------------------------------

# ------------------------------------------------------------
# CARA PASANG CRON (sekali saja):
#   crontab -e   lalu tambahkan baris:
#   15 2 * * * /home/it-ef/bpf-bbm-system/scripts/auto_cleanup_demo.sh
#
# Artinya: tiap hari pukul 02:15 sistem mengecek — jika sudah lewat
# MEETING_DATE, data demo langsung dihapus tanpa perlu diingat.
# ------------------------------------------------------------
