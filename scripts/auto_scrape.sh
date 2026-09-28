#!/bin/bash
# auto_scrape.sh — Auto-scrape new articles and upload to WordPress
# Runs via cron (e.g., every 4 hours during business hours)
# Log output: /app/data/news_scraper/auto_scrape.log
#
# v2.45.1: logika python dipindah ke auto_scrape.py (testable + pre-filter
# duplikat paginasi penuh, sinkron dengan routes.py). PATH cron diperluas —
# image python-slim menaruh python3 di /usr/local/bin yang DI LUAR PATH
# default cron (/usr/bin:/bin) → dulu selalu 'python3: not found'.

set -e
cd /app
LOG="/app/data/news_scraper/auto_scrape.log"
LOCK="/tmp/auto_scrape.lock"

# PATH cron hanya /usr/bin:/bin — python3 image resmi ada di /usr/local/bin.
export PATH="/usr/local/bin:$PATH"

# Prevent overlapping runs
if [ -f "$LOCK" ]; then
    pid=$(cat "$LOCK" 2>/dev/null)
    if kill -0 "$pid" 2>/dev/null; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] SKIP: previous run still active (PID $pid)" >> "$LOG"
        exit 0
    fi
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting auto-scrape..." >> "$LOG"

python3 -u /app/scripts/auto_scrape.py >> "$LOG" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Auto-scrape finished" >> "$LOG"
