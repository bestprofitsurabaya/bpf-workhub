# 🛢️ Agen Subsidi Tepat (bagian bpf-workhub — v2.68.0)

Agen akun perseroan **Subsidi Tepat / MyPertamina** yang menarik **riwayat
transaksi BBM SPBU** dan mengimpornya ke tabel master `subsidy_transactions`
bpf-workhub — bahan verifikasi klaim BBM di Finance.

> 2026-10-23: repo mandiri `subsiditepat` (bestprofitsurabaya) **disatukan**
> ke sini sesuai arahan user. File `pull/push` + `docs/recon.md` identik;
> lokasi baru ini yang dipakai cron — repo lama hanya arsip/wawancara.

## Alur

```
login.mjs (headful, Xvfb) → OTP email sekali → verify.mjs → token.json (~7 hari)
pull.mjs [hari] → data/bbm_*.json
push.mjs → POST /api/subsidy/import   (X-SUBSIDY-TOKEN)
        → POST /api/subsidy/auto-match (tandai match/close/no_record — advisory)
```

## Jadwal

Cron harian (user `it-ef`): `15 6 * * *` → `agent/subsiditepat/scripts/daily_sync.sh`.

## Rahasia (tidak pernah ke-commit — lihat .gitignore)

`/.env`, `/token.json`, `/profile/`, `/data/`, `/artifacts/`.

## Ganti token (habis ~7 hari)

```bash
cd /home/it-ef/bpf-workhub/agent/subsiditepat
python3 -c 'import subprocess,os' 2>/dev/null   # Xvfb :99 harus hidup
node login.mjs     # tunggu OTP email
node verify.mjs <kode_otp>
```

Xvfb: `Xvfb :99 -screen 0 1200x900x24 &` bila belum jalan.
