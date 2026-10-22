#!/bin/bash
# ============================================================
# run-tests.sh — menjalankan pytest BPF WorkHub di HOST (v2.49.2)
# ------------------------------------------------------------
# Latar belakang (temuan audit 22/10/2026):
#   Suite hijau di CI, tapi 2 file test (test_security_headers.py &
#   test_scraper_wp_status.py) error di host karena butuh env DB
#   (SECRET_KEY & DB_PASSWORD) yang hanya disediakan CI.
#
# Pemakaian:
#   ./scripts/run-tests.sh            → suite penuh KECUALI 2 file yang
#                                       butuh DB asli (aman, default)
#   ./scripts/run-tests.sh --db       → SEMUA test, kredensial dari .env
#                                       (host MariaDB 127.0.0.1:3307);
#                                       import app menjalankan ensure-
#                                       schema "IF EXISTS" — aman tapi
#                                       jangan dipakai saat DB sibuk
#   ./scripts/run-tests.sh --db tests/test_security_headers.py
#                                     → mode --db untuk file tertentu
#   ./scripts/run-tests.sh -k kasbon  → filter pytest biasa
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

DB_TEST_FILES=(tests/test_security_headers.py tests/test_scraper_wp_status.py)

# Pemisah argumen: -q, -k, --tb dll diteruskan ke pytest apa adanya.
MANUAL_TARGETS=()
ARGS=()
for a in "$@"; do
  case "$a" in
    tests/*) MANUAL_TARGETS+=("$a") ;;
    *) ARGS+=("$a") ;;
  esac
done

if [ "${ARGS[0]:-}" = "--db" ]; then
  ARGS=("${ARGS[@]:1}")
  # Butuh .env untuk kredensial (SECRET_KEY, MYSQL_PASSWORD)
  [ -f .env ] || { echo "[run-tests] .env tidak ditemukan — cp .env.example .env dulu"; exit 1; }
  set -a
  # shellcheck disable=SC2046
  export $(grep -E '^(SECRET_KEY|MYSQL_USER|MYSQL_PASSWORD|MYSQL_DATABASE)=' .env | xargs)
  set +a
  # CI-parity env: host MariaDB via bind 127.0.0.1:3307 (docker-compose.yml)
  export DB_HOST="${DB_HOST:-127.0.0.1}" DB_PORT="${DB_PORT:-3307}" \
         DB_USER="${DB_USER:-${MYSQL_USER:-bpf_user}}" \
         DB_PASSWORD="${DB_PASSWORD:-${MYSQL_PASSWORD:?MYSQL_PASSWORD belum di-set}}" \
         DB_NAME="${DB_NAME:-${MYSQL_DATABASE:-bpf_asset_system}}"
else
  # default: skip 2 file yang butuh DB asli (import app → schema ensure)
  ARGS+=( $(printf -- '--ignore=%s ' "${DB_TEST_FILES[@]}") )
  printf "[run-tests] Mode aman: skip %d file yang butuh DB asli (pakai --db untuk semua)\n" "${#DB_TEST_FILES[@]}"
fi

# Target: path eksplisit dari user, atau seluruh folder tests/
if [ "${#MANUAL_TARGETS[@]}" -gt 0 ]; then TARGETS=("${MANUAL_TARGETS[@]}"); else TARGETS=(tests); fi

python3 -m pytest "${TARGETS[@]}" -q -p no:cacheprovider "${ARGS[@]}"
