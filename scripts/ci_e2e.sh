#!/usr/bin/env bash
# ============================================================
# E2E lokal/CI — alur kritis driver → GA → Finance.
#
# Script ini TIDAK PERNAH memakai produksi:
#   - koneksi DB wajib loopback (127.0.0.1 / localhost / ::1);
#   - FLASK_ENV dipaksa development (app.py menolak server dev di production);
#   - kredensial di bawah adalah kredensial throwaway service CI.
#
# Urutan: seed DB uji → build SPA → start Flask → tunggu /api/health →
#         npm run e2e → matikan Flask (trap).
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)

# --- Guard anti-produksi -------------------------------------------------
case "${DB_HOST:-127.0.0.1}" in
  127.0.0.1|localhost|::1) ;;
  *) echo "[e2e] DITOLAK: DB_HOST=${DB_HOST} bukan loopback — E2E hanya untuk DB uji." >&2; exit 1 ;;
esac

# --- Environment CI (bisa dioverride untuk verifikasi lokal) ------------
export FLASK_ENV=development
export SECRET_KEY="${SECRET_KEY:-ci-e2e-secret-key}"
export SESSION_COOKIE_SECURE='false'
export DB_HOST="${DB_HOST:-127.0.0.1}"
export DB_PORT="${DB_PORT:-3306}"
export DB_USER="${DB_USER:-bpf_user}"
export DB_PASSWORD="${DB_PASSWORD:-ci_app_pass_x9}"
export DB_NAME="${DB_NAME:-bpf_asset_system}"
export DB_POOL_SIZE="${DB_POOL_SIZE:-2}"
export BRANCH_POOL_SIZE="${BRANCH_POOL_SIZE:-1}"
export DB_POOL_RETRIES="${DB_POOL_RETRIES:-1}"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
export E2E_BASE_URL="${E2E_BASE_URL:-http://127.0.0.1:5000}"
case "$E2E_BASE_URL" in
  http://127.0.0.1:*|http://localhost:*|http://[::1]:*) ;;
  *) echo "[e2e] DITOLAK: E2E_BASE_URL=${E2E_BASE_URL} bukan loopback." >&2; exit 1 ;;
esac
PYTHON="${PYTHON:-python}"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

# --- 1. Seed database uji (skema + data minimal) -------------------------
echo "[e2e] Seed database uji ${DB_NAME} di ${DB_HOST}:${DB_PORT} ..."
"$PYTHON" - <<'PY'
import os

import mysql.connector

cfg = dict(
    host=os.environ['DB_HOST'],
    port=int(os.environ['DB_PORT']),
    user=os.environ['DB_USER'],
    password=os.environ['DB_PASSWORD'],
    database=os.environ['DB_NAME'],
    autocommit=True,
    use_pure=True,  # CMySQLCursor tidak mendukung execute(..., multi=True)
)
conn = mysql.connector.connect(**cfg)
cur = conn.cursor()

# Skema lengkap dari manifest (CREATE TABLE IF NOT EXISTS / INSERT IGNORE).
# init.sql hanya berisi DDL/INSERT tanpa DELIMITER atau ';' di dalam string,
# jadi pemecahan per ';' aman (mysql-connector 9.x tidak punya execute multi).
with open(os.path.join(os.getcwd(), 'init.sql'), encoding='utf-8') as f:
    schema = f.read()
clean = '\n'.join(line.split('--', 1)[0] for line in schema.splitlines())
for chunk in clean.split(';'):
    if not chunk.strip():
        continue
    try:
        cur.execute(chunk.strip())
    except mysql.connector.Error as exc:
        # Seed bukan first-run (jalankan ulang lokal): baris INSERT tanpa
        # IGNORE di init.sql boleh duplikat — abaikan hanya kode duplicate.
        if exc.errno != 1062:
            raise
    if cur.with_rows:
        cur.fetchall()

# Akun uji. PIN plaintext sengaja dipakai: backend verify_pin() melakukan
# lazy-upgrade ke hash saat login pertama.
cur.executemany(
    """INSERT INTO users (username, full_name, role, pin, branch_code)
       VALUES (%s, %s, %s, '123456', 'SBY')
       ON DUPLICATE KEY UPDATE pin=VALUES(pin), is_active=1, branch_code='SBY'""",
    [
        ('driversby_guruh', 'Driver E2E Surabaya', 'driver'),
        ('ga_sby', 'GA E2E Surabaya', 'ga'),
        ('finance_sby', 'Finance E2E Surabaya', 'finance'),
    ],
)
cur.execute(
    """INSERT INTO drivers (name, nopol, vehicle_type, bbm_type, is_active)
       VALUES ('DRIVERSBY_GURUH', 'B 1126 DFC', 'AVANZA', 'PERTALITE', 1)
       ON DUPLICATE KEY UPDATE nopol=VALUES(nopol), vehicle_type=VALUES(vehicle_type),
                               bbm_type=VALUES(bbm_type), is_active=1"""
)
cur.execute(
    """INSERT IGNORE INTO vehicles (vehicle_type, nopol, bbm_default, initial_odo_km)
       VALUES ('AVANZA', 'B 1126 DFC', 'PERTALITE', 78000)"""
)
cur.execute(
    """INSERT IGNORE INTO bbm_types (name, price_per_liter) VALUES ('PERTALITE', 10000)"""
)

# Reset semua laporan service dari run sebelumnya. Tanpa ini skenario 1 bisa
# lolos memakai kartu riwayat basi yang teksnya identik dengan kiriman baru.
cur.execute("DELETE FROM driver_service_reports")

# Laporan service SUBMITTED untuk skenario GA (reset bila dijalankan ulang).
cur.execute(
    """INSERT INTO driver_service_reports
       (display_id, driver_name, driver_display_name, nopol, vehicle_type,
        km_kendaraan, keluhan, status, ga_note, created_at)
       VALUES ('SRV-E2E-SEED-0001', 'DRIVERSBY_GURUH', 'Driver E2E',
               'B 1126 DFC', 'AVANZA', 78000,
               '1. Rem depan berbunyi keras\n2. AC kurang dingin',
               'SUBMITTED', '', NOW())
       ON DUPLICATE KEY UPDATE status='SUBMITTED', ga_note='', reviewed_by='',
                               reviewed_at=NULL, keluhan=VALUES(keluhan)"""
)

# Klaim BBM menunggu ACC-2 untuk skenario Finance (tanpa approval_requests
# pending — gate then allows GA approve). display_id tidak UNIQUE: hapus dulu.
SEED_CLAIM = 'BBM-E2E-SEED-0001'
try:
    cur.execute(
        "DELETE FROM approval_requests WHERE doc_type='bbm' AND display_id=%s",
        (SEED_CLAIM,),
    )
except mysql.connector.Error:
    pass  # tabel approval dibuat saat startup aplikasi
cur.execute("DELETE FROM transactions WHERE display_id=%s", (SEED_CLAIM,))
cur.execute(
    """INSERT INTO transactions
       (display_id, driver_name, nopol, vehicle_type, bbm_type, nominal,
        liter, price_per_liter, odo_km, spbu_type, status, transaction_type,
        ml_anomaly_flag, is_dummy, created_at)
       VALUES (%s, 'DRIVERSBY_GURUH', 'B 1126 DFC', 'AVANZA', 'PERTALITE',
               100000, 10, 10000, 78000, 'non_rekanan', 'pending', 'CLAIM', 0, 0, NOW())""",
    (SEED_CLAIM,),
)
# Data uji rekrutmen (Rilis C) — NIK khusus, tidak dipakai produksi.
for i, nik in enumerate(('3573019900000001', '3573019900000002',
                         '3573019900000003', '3573019900000004'), start=1):
    case_id = f'RC-E2E-{i:04d}'
    cur.execute(
        """INSERT INTO recruitment_cases
           (case_id, nik, nama, first_seen_at, first_branch)
           VALUES (%s,%s,%s,NOW(),'SBY')
           ON DUPLICATE KEY UPDATE nama=VALUES(nama)""",
        (case_id, nik, f'Peserta Uji {i}'))
    cur.execute(
        """INSERT INTO recruitment_steps
           (case_id, step_type, status, branch_code, evidence_type,
            evidence_id, completed_at)
           VALUES (%s,'CV','SELESAI','SBY','cv_online_submission',%s,NOW())
           ON DUPLICATE KEY UPDATE status='SELESAI'""",
        (case_id, f'CV-E2E-{i}'))
    cur.execute(
        """INSERT INTO cv_online_submissions
           (registration_no, source, submitted_at, nama, nik, nik_raw,
            branch_code, consent_at)
           VALUES (%s,'e2e',NOW(),%s,%s,%s,'SBY',NOW())""",
        (f'CV-E2E-{i}', f'Peserta Uji {i}', nik, nik))

cur.execute(
    """INSERT INTO applicants
       (display_id, nama_lengkap, no_hp, interview_at, status)
       VALUES ('PLM-E2E-0001','Pelamar Lama Uji','081299990001',NOW(),'interview')
       ON DUPLICATE KEY UPDATE nama_lengkap=VALUES(nama_lengkap)""")

cur.close()
conn.close()
print('[e2e] Seed selesai.')
PY

# --- 2. Build SPA yang disajikan Flask di /app/* ------------------------
echo "[e2e] Build SPA ..."
(cd "$ROOT/frontend" && npm run build)
bash "$ROOT/scripts/build-spa.sh" --skip-npm >/dev/null

# --- 3. Start Flask lokal + tunggu health --------------------------------
# -t memakai TMPDIR sistem (ubuntu-latest tidak punya /tmp/opencode).
LOG=$(mktemp -t bpf-e2e-server.XXXXXX.log)
echo "[e2e] Start Flask (log: $LOG) ..."
"$PYTHON" "$ROOT/app.py" >"$LOG" 2>&1 &
SERVER_PID=$!
cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

ready=0
for _ in $(seq 1 60); do
  if curl -fsS "$E2E_BASE_URL/api/health" >/dev/null 2>&1; then ready=1; break; fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then break; fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  echo "[e2e] Flask gagal start / health tidak siap. Log server:" >&2
  tail -80 "$LOG" >&2
  exit 1
fi
echo "[e2e] /api/health 200 — jalankan Playwright."

# --- 4. Jalankan E2E (argumen diteruskan, mis. --grep) --------------------
(cd "$ROOT/frontend" && npm run e2e -- "$@")

# --- 5. Bersihkan data uji rekrutmen -------------------------------------
"$PYTHON" - "$ROOT" <<'PY'
import sys
import mysql.connector
root = sys.argv[1]
sys.path.insert(0, root)
from modules import config
conn = mysql.connector.connect(**config.DB_CONFIG)
cur = conn.cursor()
for nik in ('3573019900000001', '3573019900000002',
            '3573019900000003', '3573019900000004'):
    for table in ('recruitment_events', 'training_attendance',
                  'first_work_submissions', 'cv_online_submissions',
                  'recruitment_steps', 'recruitment_cases'):
        cur.execute(f'DELETE FROM {table} WHERE nik=%s', (nik,))
cur.execute("DELETE FROM applicants WHERE display_id='PLM-E2E-0001'")
conn.commit()
cur.close()
conn.close()
print('[e2e] Data uji rekrutmen dibersihkan.')
PY
