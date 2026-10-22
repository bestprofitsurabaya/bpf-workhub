#!/bin/sh
# ============================================================
# Backup freshness & integrity check — BPF WorkHub (v2.49.2)
# ------------------------------------------------------------
# Dipanggil otomatis di akhir backup-db.sh, tapi juga bisa jalan
# mandiri (cron/manual) untuk audit backup literal:
#
#   docker exec bbm_backup /bin/sh /usr/local/bin/backup-freshness-check.sh
#
# Pengecekan:
#   1. File backup TERBARU berumur <= BACKUP_MAX_AGE_HOURS (default 30 —
#      backup harian 03:00 + toleransi satu hari)
#   2. Semua dump dibuat HARI INI lulus uji gzip -t (tidak korup)
#   3. /backups/last-backup.txt ada & mencantumkan setidaknya 1 database
#
# Integrasi Uptime Kuma:
#   BACKUP_KUMA_HEARTBEAT  = URL push monitor ("Heartbeat") → di-curl saat OK
#   BACKUP_KUMA_ALERT_URL  = URL push monitor → di-curl saat GAGAL (?status=down)
#   Kedua variabel opsional; kosong = tidak ada notifikasi (hanya exit code).
# Exit code: 0 = semua OK; 1..4 = kode kesalahan (lihat output)
# ============================================================

OUT_DIR="/backups"
MAX_AGE_H="${BACKUP_MAX_AGE_HOURS:-30}"

fail() {
  echo "[freshness] GAGAL: $1"
  [ -n "$BACKUP_KUMA_ALERT_URL" ] && \
    curl -fsS -m 10 "${BACKUP_KUMA_ALERT_URL}?status=down&msg=$(echo "$1" | head -c 80 | tr ' ' '+')" >/dev/null 2>&1 \
    || true
  exit "$2"
}

notify_ok() {
  [ -n "$BACKUP_KUMA_HEARTBEAT" ] && curl -fsS -m 10 "$BACKUP_KUMA_HEARTBEAT" >/dev/null 2>&1 || true
  echo "[freshness] OK $(date -Iseconds)"
}

[ -d "$OUT_DIR" ] || fail "folder $OUT_DIR tidak ada" 1

# --- 1. Freshness: file terbaru harus cukup segar ---------------------------
LATEST=$(find "$OUT_DIR" -name 'bpf_*.sql.gz' -printf '%T@ %T+\n' 2>/dev/null | sort -rn | head -1)
[ -n "$LATEST" ] || fail "tidak ada file bpf_*.sql.gz di $OUT_DIR" 2
LATEST_EPOCH=$(echo "$LATEST" | awk '{print int($1)}')
NOW_EPOCH=$(date +%s)
AGE_H=$(( (NOW_EPOCH - LATEST_EPOCH) / 3600 ))
if [ "$AGE_H" -gt "$MAX_AGE_H" ]; then
  fail "backup terbaru berumur ${AGE_H} jam (batas ${MAX_AGE_H} jam)" 3
fi

# --- 2. Integritas gzip: semua dump hari ini pakai gzip -t ------------------
BAD=""
for f in $(find "$OUT_DIR" -name 'bpf_*.sql.gz' -newermt "today" 2>/dev/null); do
  gzip -t "$f" 2>/dev/null || BAD="${BAD} $(basename "$f")"
done
[ -z "$BAD" ] || fail "dump korup: ${BAD}" 4

# --- 3. Status sizing: last-backup.txt punya minimal 1 database -------------
if [ -f "$OUT_DIR/last-backup.txt" ]; then
  grep -q "databases: .[a-zA-Z]" "$OUT_DIR/last-backup.txt" || \
    fail "last-backup.txt tidak mencantumkan database mana pun" 4
else
  fail "last-backup.txt belum dibuat" 2
fi

notify_ok
