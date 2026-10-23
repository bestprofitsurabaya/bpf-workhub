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

- Cron harian (user `it-ef`): `15 6 * * *` → `scripts/daily_sync.sh`.
- Cron `@reboot` → `scripts/otp_supervisor.mjs` (supervisor OTP, tick 4 dtk;
  start manual: `setsid nohup node scripts/otp_supervisor.mjs >> artifacts/otp_supervisor.log 2>&1 &`).

## Rahasia (tidak pernah ke-commit — lihat .gitignore)

`/.env`, `/token.json`, `/profile/`, `/data/`, `/artifacts/`.

## Ganti token (habis ~7 hari) — TIDAK PERLU LAGI CLI

**Cara utama (v2.69.0, dari dashboard):** Finance buka menu 💰 Finance →
kartu ⛽ *Data SPBU — Subsidi Tepat* → panel **🔑 Login ulang agen**:
1. Klik *✉ Minta OTP Email* — supervisor host menjalankan `login.mjs`
   (Chrome headful di Xvfb `:98` khusus agen) → OTP dikirim MyPertamina
   ke email akun.
2. Baca 6 digit dari email, ketik di kolom OTP → *✔ Kirim OTP* —
   `verify.mjs` menaut token baru, lalu otomatis pull → import → auto-match.

**Cara manual (cadangan):** jalankan `node login.mjs` (Xvfb `:98` harus
hidup: supervisor mengelolanya otomatis) lalu `node verify.mjs <kode>`.

⚠️ Jangan pakai Xvfb `:99` bawaan `xvfb-run` — display itu ber-Xauthority
klien tanpa XAUTHORITY ditolak ("Missing X server"). Supervisor sengaja
memakai display `:98` sendiri tanpa -auth.
