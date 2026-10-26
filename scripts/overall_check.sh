#!/bin/bash
# ============================================================
# overall_check.sh — cek sehat menyeluruh BPF WorkHub dalam satu perintah
#
# Jalankan di HOST NAS (user it-ef):
#   cd ~/bpf-workhub && bash scripts/overall_check.sh
# Durasi ±6 menit (pytest penuh ±4,5 mnt + vitest ±1 mnt + smoke ±0,5 mnt).
#
# Memeriksa:
#   1. Container web running & healthy
#   2. /api/health merespons 200
#   3. Stamp 7 titik + DB (check_version_stamps.py --with-db)
#   4. pytest PENUH di container
#   5. vitest PENUH di frontend/
#   6. Smoke E2E Pengadaan (24 uji) + Rekap Pengeluaran (13 uji)
# Keluaran: daftar status per langkah + verdict satu baris.
# Exit code 0 = semua sehat; ≠0 = ada langkah gagal (rujukan: log per langkah).
# ============================================================
set -u
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
WEB=bpf-workhub-web
declare -a NAMES RESULT

step() {
  local name="$1"; shift
  local out log rc
  log=$(mktemp /tmp/overall_step.XXXXXX)
  if bash -o pipefail -c "$*" >"$log" 2>&1; then
    NAMES+=("$name"); RESULT+=("OK")
    echo "[OK   ] $name"
  else
    NAMES+=("$name"); RESULT+=("GAGAL")
    echo "[GAGAL] $name  (log: $log)"
    echo "--------- output terakhir ---------"
    tail -12 "$log"
    echo "-----------------------------------"
  fi
  LASTLOG="$log"
  return 0
}

# 1. Container
step "Container $WEB up & healthy" \
  "docker ps --filter name=$WEB --format '{{.Status}}' | grep -q 'healthy'"

# 2. /api/health
step "/api/health merespons 200" \
  "docker exec $WEB python3 -c \"import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/api/health',timeout=8).status==200 else 1)\""

# 3. Stamp versi 7 titik + DB
step "Stamp versi 7 titik + DB konsisten" \
  "docker exec -w /app $WEB python3 scripts/check_version_stamps.py --with-db | grep -q '✅ Semua titik stamp konsisten'"

# 4. pytest penuh
step "Pytest penuh (guaranteed no-fail summary)" \
  "docker exec -w /app $WEB sh -c 'python3 -m pytest tests/ -q' | tail -1"

# 5. vitest penuh
step "Vitest penuh (frontend/)" \
  "cd $ROOT/frontend && npx vitest run 2>&1 | tail -3"

# 6. Smoke E2E — salin skrip terbaru dari repo ke container dulu
cp_smokes="docker cp $ROOT/scripts/smoke_procurement.py $WEB:/tmp/ && docker cp $ROOT/scripts/smoke_expenses.py $WEB:/tmp/"
step "Siapkan skrip smoke di container" "$cp_smokes"

step "Smoke Pengadaan (24 uji)" \
  "docker exec -w /app $WEB python3 /tmp/smoke_procurement.py"

step "Smoke Rekap Pengeluaran (13 uji)" \
  "docker exec -w /app $WEB python3 /tmp/smoke_expenses.py"

# ---- verdict ----
echo ""
echo "================ VERDICT ================"
for i in "${!NAMES[@]}"; do
  printf '%-42s %s\n' "${NAMES[$i]}" "${RESULT[$i]}"
done
if printf '%s\n' "${RESULT[@]}" | grep -q GAGAL; then
  echo "➡ SEHAT: TIDAK — periksa langkah GAGAL di atas (log disimpan di /tmp/overall_step.*)"
  exit 1
fi
echo "➡ SEHAT: ✅ Semua langkah lulus — sistem dalam kondisi prima."
exit 0
