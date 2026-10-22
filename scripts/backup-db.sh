#!/bin/sh
# ============================================================
# Backup DB otomatis — BPF WorkHub (v2.21)
# ------------------------------------------------------------
# - Dump SEMUA database MySQL (master + tiap cabang) via mysqldump
# - Nama file: bpf_backup_<tanggal>_<jam>.sql (gzip)
# - Retensi: hapus backup lebih lama dari BACKUP_RETENTION_DAYS
# - Tulis status terakhir ke /backups/last-backup.txt (untuk monitoring)
# ============================================================
set -e

HOST="${MYSQL_HOST:-db}"
ROOT_PW="${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD wajib}"
RETENTION="${BACKUP_RETENTION_DAYS:-30}"
OUT_DIR="/backups"
STAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$OUT_DIR"

# 1. Dump semua database (kecuali sistem MySQL)
DUMPED=""
for DB in $(mysql -h "$HOST" -uroot -p"$ROOT_PW" -N -e "SHOW DATABASES" 2>/dev/null \
  | grep -vE '^(information_schema|performance_schema|mysql|sys)$'); do
  mysqldump -h "$HOST" -uroot -p"$ROOT_PW" \
    --single-transaction --routines --triggers --skip-lock-tables \
    "$DB" > "${OUT_DIR}/bpf_${DB}_${STAMP}.sql" 2>/dev/null
  gzip -f "${OUT_DIR}/bpf_${DB}_${STAMP}.sql"
  DUMPED="${DUMPED}${DB} "
done

# 2. Retensi — hapus backup lebih lama dari N hari
find "$OUT_DIR" -name 'bpf_*.sql.gz' -mtime "+${RETENTION}" -delete 2>/dev/null || true

# 3. Status untuk monitoring
{
  echo "last_backup: $(date -Iseconds)"
  echo "databases: ${DUMPED:-<none>}"
  echo "file_count: $(find "$OUT_DIR" -name 'bpf_*.sql.gz' | wc -l)"
  echo "oldest: $(find "$OUT_DIR" -name 'bpf_*.sql.gz' -printf '%T+ %f\n' 2>/dev/null | sort | head -1)"
} > "$OUT_DIR/last-backup.txt"

echo "[backup] OK $(date -Iseconds) — DB: ${DUMPED:-none}"

# 4. Verifikasi integritas + freshness (v2.49.2 audit fix)
#    - Uji gzip -t tiap file dump HARI INI (ketahuan korup di hari yang sama,
#      bukan saat restore butuh di t+30 hari)
#    - Heartbeat/alert Uptime Kuma bila BACKUP_KUMA_HEARTBEAT/KUMA_ALERT_URL di-set
if [ -x /usr/local/bin/backup-freshness-check.sh ]; then
  if ! /usr/local/bin/backup-freshness-check.sh; then
    echo "[backup] FRESHNESS CHECK GAGAL — lihat output di atas"
    exit 1
  fi
fi
