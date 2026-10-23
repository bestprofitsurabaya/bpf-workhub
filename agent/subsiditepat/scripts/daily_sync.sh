// Sinkronisasi harian Subsidi Tepat → bpf-workhub (v2.68.0 "satukan" agen)
//   pull data riwayat SPBU (portal resmi, token __mpv-token) →
//   POST bpf-workhub /api/subsidy/import (X-SUBSIDY-TOKEN) →
//   POST bpf-workhub /api/subsidy/auto-match (tandai match/close/no_record).
// Cron terpasang (root user it-ef):
//   15 6 * * *  <DIR>/scripts/daily_sync.sh >> artifacts/sync_cron.log 2>&1
# shellcheck disable=SC2164
set -u
BASE="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$BASE"
mkdir -p artifacts data

echo "=== $(date '+%F %T') mulai sinkron ==="

# 1) tarik data 40 hari terakhir (overlap antar-run, idempoten via uq_txid)
if ! node pull.mjs 40 > artifacts/.last_pull.log 2>&1; then
  echo "❌ pull.mjs GAGAL — kemungkinan token.json expired (~7 hari)."
  echo "   Perlu login ulang: node login.mjs (Xvfb) + OTP email + node verify.mjs <kode>."
  echo "=== berhenti ==="
  exit 1
fi

# 2) kirim ke workhub
if ! node push.mjs > artifacts/.last_push.log 2>&1; then
  echo "❌ push.mjs GAGAL (workhub / token import?)."
  cat artifacts/.last_push.log
  exit 1
fi
cat artifacts/.last_push.log

# 3) tandai kandidat kecocokan klaim BBM (advisory — putusan tetap Finance)
TOKEN="$(grep -m1 '^SUBSIDY_IMPORT_TOKEN=' .env | cut -d= -f2-)"
if [ -n "$TOKEN" ]; then
  curl -s --max-time 120 -X POST -H "Content-Type: application/json" \
    -H "X-SUBSIDY-TOKEN: $TOKEN" \
    "${WORKHUB_API:-http://127.0.0.1:5001}/api/subsidy/auto-match" \
    >> artifacts/.last_automatch.log 2>&1 \
    && echo "auto-match OK" || echo "auto-match gagal (lihat artifacts/.last_automatch.log)"
else
  echo "⚠ SUBSIDY_IMPORT_TOKEN tidak ada di .env — auto-match dilewati"
fi

echo "=== $(date '+%F %T') sinkron selesai OK ==="
