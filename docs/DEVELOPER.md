# 🧭 DEVELOPER.md — Onboarding Programmer BPF WorkHub

> Dokumen ini untuk **developer yang melanjutkan pengembangan** sistem ERP
> BPF WorkHub (klaim BBM antar-cabang + Subsidi Tepat + air minum + karbon dsb).
> Baca dari atas ke bawah sekali, lalu jadikan referensi cepat.

---

## 1. Gambaran sistem

BPF WorkHub = Flask backend (`modules/`) + SPA Vue 3 (`frontend/`) + MySQL per-cabang.
Satu **master DB** (`bpf_asset_system`) dan **9 database cabang** (`bpf_branch_*`),
semuanya berada dalam SATU container MariaDB, diakses aplikasi lewat pool terpisah
(master 25 koneksi, cabang 5 koneksi).

```
Browser / PWA mobile driver
        │  (HTTPS: nextcloud_nginx proxy → jaringan nextcloud_net)
        ▼
┌────────────────────────── Docker Compose: bpf-workhub ──────────────────────────┐
│  bpf-workhub-web    Flask + gunicorn (gevent) + SPA hasil build di image        │
│  bpf-workhub-db     MariaDB 10.11 — master + 9 DB cabang                       │
│  bpf-workhub-redis  cache / rate-limit / rate guard                             │
│  bpf-workhub-backup backup harian 03:00 + drill restore mingguan Minggu 04:00  │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Nama standar (WAJIB dipakai semua tooling baru)

| Resource         | Nama                                                             |
|------------------|------------------------------------------------------------------|
| Compose project  | `bpf-workhub` (baris `name:` di `docker-compose.yml`)             |
| Container web    | `bpf-workhub-web` → **`docker exec bpf-workhub-web …`**           |
| Container DB     | `bpf-workhub-db` → `docker exec bpf-workhub-db mariadb -uroot …`  |
| Container redis  | `bpf-workhub-redis`                                               |
| Container backup | `bpf-workhub-backup`                                              |
| Volume data DB   | `bpf-workhub_db_data` (nama eksplisit, TIDAK ikut prefix project) |
| Volume redis     | `bpf-workhub_redis_data`                                          |
| Volume backup    | `bpf-workhub_backups`                                             |
| Network internal | `bpf-workhub_default` + eksternal `nextcloud_net` (HTTPS proxy)   |
| Port host        | web `127.0.0.1:5001` (LAN proxy / SSH tunnel), DB `127.0.0.1:3307` |

⚠️ Hostname **di dalam** jaringan compose tetap **nama service**: `db`, `web`,
`redis` (lihat `DB_HOST=db`, `REDIS_URL=redis://redis:6379/0` di compose) —
bukan nama container.

---

## 3. Quickstart developer

```bash
# 0) kredensial (tidak pernah masuk git)
cp .env.example .env # lalu isi MYSQL_ROOT_PASSWORD, MYSQL_PASSWORD, SECRET_KEY, dst.

# 1) naikkan seluruh stack (DB fresh akan diinisialisasi oleh init.sql)
docker compose up -d
# app menunggu db healthy (depends_on: condition: service_healthy)

# 2) cek sehat
curl http://127.0.0.1:5001/api/health
docker compose ps

# 3) jalankan test
cd frontend && npx vitest run          # 214 test SPA
docker exec bpf-workhub-web python3 -m pytest /app/tests -q   # backend (di image)

# 4) akun coba (lihat docs/internal/USER_LIST.md)
```

Semua data persisten ada di 3 volume `bpf-workhub_*` + bind mount `/srv/bpf-workhub/`
(uploads, transcoder, arsip Berita Acara) — kosong bila fresh install, itu wajar.

---

## 4. Peta database

| Database           | Isi                                                                 |
|--------------------|----------------------------------------------------------------------|
| `bpf_asset_system` | master: user, `branches`, log aktivitas, registry dokumen, config    |
| `bpf_branch_sby`   | cabang Surabaya (utama; klaim BBM, air minum, karbon, dsb)           |
| `bpf_branch_bdg`, `_bjm`, `_jkt`, `_mlb`, `_pnk`, `_stt`, `_tgl`, `_vbi` | cabang lain |
| PLM sudah DIHAPUS (23 Okt 2026): row `branches` + DB `bpf_branch_plm` | di-drop setelah backup; prefix dokumen pelamar `PLM-` tetap (kode dokumen, bukan cabang) |

Klaim BBM & Subsidi Tepat hidup **per cabang** (tabel `transactions`,
`subsidy_attestations` di DB cabang). Joker antar-DB cukup ingat:
master untuk identitas/cabang, `bpf_branch_*` untuk transaksi.

`.env` berisi `MYSQL_ROOT_PASSWORD`; akses cepat DB:
```bash
PW="$(grep MYSQL_ROOT_PASSWORD .env | cut -d= -f2)"
docker exec bpf-workhub-db mariadb -uroot -p"$PW" bpf_asset_system -e "SELECT VERSION();"
```

---

## 5. Aturan emas bump versi — 7 titik stamp

Setiap release WAJIB mengubah versi di **7 titik**, lalu verifikasi otomatis:

1. `modules/company_identity.py` → `'system_version': 'vX.Y.Z'`
2. `modules/pdf_generator.py` → `SYSTEM_VERSION = 'BPF WorkHub vX.Y.Z'` (kop PDF)
3. `frontend/src/stores/identity.js`
4. `frontend/public/sw.js` (const CACHE)
5. `CHANGELOG.md` → entri teratas
6. `docs/internal/USER_LIST.md`
7. `guides/USER_GUIDE.md`

```bash
docker exec bpf-workhub-web python3 /app/scripts/check_version_stamps.py   # → harus ✅
```

Catatan penting: container membaca file dari **image**, bukan bind-mount —
jadi edit CHANGELOG **harus sebelum** `docker compose build web`, bukan sesudah.
Stamp DB (`system_config` master, `branches.system_version`, 8 config cabang)
disinkron otomatis saat boot; update manual hanya perlu bila boot tidak jalan:
`scripts/sync_branch_stamp.py` + UPDATE `system_config`/`branches`.

---

## 6. Cara deploy ke server (urutan)

```bash
git pull origin main
# (opsional) bump versi: 7 stamp → lalu commit
docker compose build web        # SPA ikut ter-build di image (frontend-build stage)
docker compose up -d web        # web restart; db/redis dibiarkan
sleep 15 && curl http://127.0.0.1:5001/api/health
docker exec bpf-workhub-web python3 /app/scripts/check_version_stamps.py   # ✅
```

Persistensi wajib (bind `/srv/bpf-workhub/`): `uploads/` (foto+file user),
`data/transcoder/` (PDF Kit), `data/subsidy_attest/` (PDF + snapshot BA —
dokumen resmi; **jangan pernah hapus**), `mobile/`, `fonts/`, `data/news_scraper/`.

---

## 7. Subsidi Tepat — alur & verifikasi

- Riwayat BBM MyPertamina di-import agen host ke `/api/subsidy/import`
  (token `SUBSIDY_IMPORT_TOKEN` di `.env`); repo agen: `~/subsiditepat`
  (`sync_full.py`, `daily_sync.sh`, `PROGRESS.md`).
- Klaim → verifikasi GA → payout Finance → validasi riwayat SPBU →
  arsip; setelah ≥2 klaim terverifikasi, Finance bisa menerbitkan
  **Berita Acara Rekonsiliasi** (PDF + snapshot hash; root-hash di
  `subsidy_attestations` = jaring pengaman rebuild — mismatch → HTTP 409).
- Uji manual BA: login finance → `/app/dashboard` → antrean klaim →
  ceklis keputusan → payout → arsip → tombol BA.

---

## 8. Backup & restore

- Backup harian oleh `bpf-workhub-backup` (03:00 WIB) ke volume
  `bpf-workhub_backups`; monitoring heartbeat Uptime Kuma opsional di `.env`.
- Restore manual:
```bash
PW="$(grep MYSQL_ROOT_PASSWORD .env | cut -d= -f2)"
docker exec -i bpf-workhub-db mariadb -uroot -p"$PW" < dump.sql   # satu DB: tambahkan nama DB
```
- Drill restore otomatis Minggu 04:00 (`RESTORE_TEST_CRON`).

---

## 9. Konvensi repo

- `main` = cabang utama (`git push origin main`).
- Kredensial & data pribadi tidak pernah masuk git: `.env`, `token.json`,
  `data/`, `artifacts/`, uploads.
- Perubahan UI/UX besar direncanakan bertahap (lihat `CHANGELOG.md` era
  v2.52–v2.53: fase perombakan 1 akses/navigasi → 2 design system → 3 polish).
- Test wajib hijau sebelum commit: `frontend` vitest + backend pytest + build SPA.

---

*Terakhir di-update: v2.53.1 (22 Okt 2026).*
