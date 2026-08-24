#!/bin/sh
# ============================================================
# Overtime Photo Cleanup — dijalankan oleh cron di dalam container.
# Hapus foto overtime yang lebih lama dari 180 hari (6 bulan).
# Dipanggil via cron atau manual: docker exec bbm_web sh /app/scripts/overtime-cleanup.sh
# ============================================================

MAX_AGE_DAYS=${MAX_AGE_DAYS:-180}
FOTO_DIR="/app/uploads/overtime"
LOG_PREFIX="[overtime-cleanup]"

if [ ! -d "$FOTO_DIR" ]; then
    echo "$LOG_PREFIX Directory $FOTO_DIR tidak ditemukan, skip."
    exit 0
fi

# Hitung file yang akan dihapus (preview)
OLD_FILES=$(find "$FOTO_DIR" -type f -mtime +${MAX_AGE_DAYS} 2>/dev/null | wc -l)
TOTAL_FILES=$(find "$FOTO_DIR" -type f 2>/dev/null | wc -l)

echo "$LOG_PREFIX $(date '+%Y-%m-%d %H:%M:%S') — Total: $TOTAL_FILES files, >= ${MAX_AGE_DAYS} hari: $OLD_FILES files"

if [ "$OLD_FILES" -eq 0 ]; then
    echo "$LOG_PREFIX Tidak ada foto lama yang perlu dihapus."
    exit 0
fi

# Hapus file lama
DELETED=0
ERRORS=0
find "$FOTO_DIR" -type f -mtime +${MAX_AGE_DAYS} -print0 2>/dev/null | while IFS= read -r -d '' f; do
    if rm -f "$f" 2>/dev/null; then
        DELETED=$((DELETED + 1))
    else
        ERRORS=$((ERRORS + 1))
        echo "$LOG_PREFIX Error menghapus: $f"
    fi
done

echo "$LOG_PREFIX Selesai. Dihapus: file lama (>= ${MAX_AGE_DAYS} hari). Sisa: $((TOTAL_FILES - OLD_FILES)) files."
