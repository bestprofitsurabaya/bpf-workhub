# 🧭 DEVELOPER — BPF WorkHub

Dokumen untuk yang memelihara dan mengembangkan sistem ini. Semua angka, nama, dan alur di sini **dikroscek langsung ke kode dan server yang berjalan** (container `bpf-workhub-*`, MariaDB di `bpf-workhub-db`, dan crontab host) — bukan salinan dari dokumen lama.

Tanggal disusun ulang: 3 November 2026 (era v2.77.0).

---

## 1. Gambaran arsitektur

Satu aplikasi, empat container, satu host NAS (Debian 13, RAM 3,8 GB dibagi bersama Nextcloud dan proyek lain).

```txt
  https://nasbpfsby.duckdns.org:5000
        │  (TLS di nextcloud_nginx — listen 5000 ssl)
        ▼
 nextcloud_nginx ── static assets (hash): cache 30 hari; route lain: no-cache ──┐
        │  proxy_pass $upstream_bbm = http://bpf-workhub-web:5000              │ (jaringan bersama nextcloud_net)
        ▼                                                                      │
┌──────────────────────────── Docker Compose (project: bpf-workhub) ───────────┤
│  web    Python 3.11-slim · Flask 3 · SocketIO (async gevent) · gunicorn       │
│         --worker-class gevent -w 1 --timeout 300 → 127.0.0.1:5001 di host     │
│         SPA /app/ dari stage build Node · PWA /m/ dari bind mount ./mobile    │
│         cron in-container: cleanup foto OT (*/30) & auto-scrape (6/10/14/18)  │
│  db     MariaDB 10.11 · max_connections 500 · 127.0.0.1:3307 di host          │
│  redis  Redis 7-alpine · maxmemory 64 MB · allkeys-lru                        │
│  backup MariaDB image + scheduler loop · dump 03:00 · drill restore Minggu    │
└───────────────────────────────────────────────────────────────────────────────┘
  ▲
  │  crontab host (user it-ef):
  │    15 6 * * *  agent/subsiditepat/scripts/daily_sync.sh    (06:15 WIB)
  │    @reboot     agent/subsiditepat/scripts/otp_supervisor.mjs  (jaga gate OTP)
```

### Kunci desain yang sering ditanya

| Pertanyaan | Jawaban (dan di mana buktinya) |
|---|---|
| Kenapa gunicorn hanya 1 worker? | Room Socket.IO in-memory, per-proses. Konkurensi ditangani gevent via greenlet. Menaikkan jumlah worker = notifikasi nyasar antar proses. Lihat catatan di `app.py` dan CMD `Dockerfile`. |
| Kenapa tidak pakai ORM? | `mysql-connector-python` + connection pool manual di `modules/config.py` — ringan, tanpa lapisan tambahan. |
| Kenapa SPA di-build ke dalam image? | Catatan di `docker-compose.yml`: dulu bind `./static` menimpa hasil build di image → SPA fresh deploy rusak. Kini SPA milik image; yang di-bind hanya `mobile/`. |
| Kenapa DB per cabang? | Isolasi data antar cabang (audit & retensi). Konvensinya dijaga guard CI: `scripts/check_branch_db_map.py` + `modules/branch_db_map.py`. |

---

## 2. Peta database (bagian yang paling sering salah di dokumen lama)

Sumber kebenaran = tabel `branches` di DB master + guard CI. **Jangan menebak.**

```bash
PW="$(grep MYSQL_ROOT_PASSWORD .env | cut -d= -f2)"
docker exec bpf-workhub-db mariadb -uroot -p"$PW" -N -e \
  'SELECT code, db_name, is_active FROM bpf_asset_system.branches ORDER BY code;'
```

Hasil kroscek 3 Nov 2026 — **12 cabang aktif**:

| Cabang | Database |
|---|---|
| **SBY** (Surabaya; cabang default) | **`bpf_asset_system`** — sengaja berbagi DB master |
| BDG, BJM, JKT, JKT2, JMB, LPG, MDN, MLG, PKU, PTK, SMG | `bpf_branch_<nama_full>` — contoh: MLG → `bpf_branch_malang` (nama lengkap, bukan singkatan kode 3 huruf) |

Pemetaan penuh: BDG→`bpf_branch_bdg`, BJM→`bpf_branch_bjm`, JKT→`bpf_branch_jkt`, JKT2→`bpf_branch_jkt2`, JMB→`bpf_branch_jmb`, LPG→`bpf_branch_lpg`, MDN→`bpf_branch_mdn`, MLG→`bpf_branch_malang`, PKU→`bpf_branch_pku`, PTK→`bpf_branch_ptk`, SMG→`bpf_branch_smg`.

Catatan penting:

- **SBY = cabang default** → datanya hidup di DB master, bukan di `bpf_branch_sby` (DB itu tidak ada). Dokumen lama pernah menulis daftar 9 cabang yang sebagian sudah tidak ada (`mlb`, `pnk`, `stt`, `tgl`, `vbi`) — jangan dipakai lagi. Penegasan konvensi: docstring `modules/branch_db_map.py` (latar 14 Sep 2026).
- Master + 11 DB cabang masing-masing berisi **54 tabel** yang setara (ensure-schema menjaga paritas saat startup).
- **Tabel FirstWork hidup di DB master** (fitur terpusat, dibaca lintas cabang oleh admin): `first_work_submissions` (1 baris = 1 pendaftar; kolom `fingerprint_no` & `bpf_no` unik), `first_work_events` (audit, termasuk event `consent` UU PDP & `ktp_purge` retensi), `first_work_referrers` (master pengundang), `first_work_sheet_stage` (staging migrasi sheet), `first_work_branch_forms` (token form publik per cabang), `first_work_id_counters` (counter seri B/C untuk ID Fingerprint & ID BPF). Modul: `modules/routes_first_work.py` + `modules/first_work_schema.py`; form publik `/app/first-work-form?cabang=<KODE>&t=<token>` (wajib token semua cabang sejak v2.84.0, wajib consent sejak v2.85.0); QR statis dibuat lokal di browser `FirstWorkView.vue`; cron retensi foto KTP `scripts/first_work_ktp_retention.py` (90 hari pasca-keputusan, config `first_work_ktp_retention_days`); rate limit publik via `helpers.redis_rate_hit` (Redis INCR+EXPIRE, fallback memori). Endpoint `GET /api/first-work/branch-forms` dapat diakses **admin & traineer** (scope cabang sendiri) sejak v2.86.1 — trainer dapat tautan ber-token cabangnya.
- Cabang **PLM dihapus 23 Okt 2026**: row `branches` + DB `bpf_branch_plm` didrop; dump terakhirnya disimpan `/srv/bpf-workhub/backups_migrasi/branch_plm_last_backup_20261023_030001.sql.gz`; kode dokumen pelamar `PLM-` tetap berlaku (kode dokumen, bukan cabang).
- Transaksi (BBM, SubsidiTepat, air minum) hidup **di DB cabang**; identitas user, cabang, log audit pusat, registry dokumen, `system_config` — di master (termasuk milik SBY).

Akses cepat tiap DB:

```bash
docker exec bpf-workhub-db mariadb -uroot -p"$PW" bpf_asset_system -e "SELECT COUNT(*) FROM users;"
docker exec bpf-workhub-db mariadb -uroot -p"$PW" bpf_branch_mlg -e "SHOW TABLES;"
```

### Pool koneksi

| Pool | Ukuran | Catatan |
|---|---|---|
| Master | 25 | DB master (SBY + shared) |
| Cabang | 5 × 11 | Lazy init — hanya dibuka bila dipakai; aktif tampil di `/api/health` |
| Retry | 3× | Fallback saat pool penuh, tanpa membuka koneksi non-pool |
| `max_connections` | 500 | `--max-connections` di compose; dulu 152 (exhausted) → naikkan di 2026 |

---

## 3. Struktur folder

| Path | Isi |
|---|---|
| `app.py` | Entry Flask: wiring semua rujukan modul, middleware keamanan, lifecycle startup |
| `modules/` | `config.py` (pool), `security.py` (PIN/hash/audit), `stepup.py` + `pin_security.py` (konfirmasi PIN ulang untuk aksi uang), `routes_*.py` per modul, generator (`pdf_generator`, `water_report`, `excel_generator`), integrasi (`news_scraper`, `transcoder`, `pdfkit`, `subsidy_attest`), schema enforcer (`*_schema.py`) |
| `frontend/` | Vue 3 + Vite: `views/`, `components/`, `stores/` (Pinia: auth, identity), `router/index.js` dengan guard per role. Uji: vitest |
| `mobile/` | PWA shell statik driver/OB/security (service worker + manifest) — bind mount, tanpa rebuild |
| `agent/subsiditepat/` | Playwright/Chrome di host: `login.mjs`, `pull.mjs`, `push.mjs`, `verify.mjs`, `scripts/otp_supervisor.mjs`, `artifacts/` (screenshot & log) |
| `scripts/` | CLI ops & migrasi: `backup-db.sh`, `restore-test.sh`, `run-tests.sh`, `release.sh`, `check_version_stamps.py`, `check_branch_db_map.py`, `auto_scrape.py`, `gas_bridge_*.gs` (Apps Script untuk overtime & receptionist) |
| `init.sql` | Seed lengkap: schema, branch 12, akun demo, config awal |
| `tests/` | 75 file pytest (1022 test), termasuk hasil audit: `test_pentest_hardening_v274.py`, `test_finance_ui_audit_v275.py` |
| Data hidup | Volume `bpf-workhub_db_data` / `_redis_data` / `_backups` + bind `/srv/bpf-workhub/{uploads,data/transcoder,data/subsidy_attest}` |

---

## 4. Lifecycle startup — apa yang `app.py` lakukan

Alasan restart sederhana sering "menyembuhkan" gangguan: banyak pengaman tabel bisa jalan sendiri saat boot.

1. **SocketIO init** — async mode mengikuti worker gunicorn (dideteksi dari `sys.argv`). Patch gevent tidak dilakukan di dalam modul (bisa merusak importlib lock saat pytest mengimport).
2. **Ensure-schema idempoten** (urutan nyata di `app.py`): notifikasi → branch manager (tabel `branches`, kolom user) → seed cabang utama → `doc_sequences` (nomor dokumen, disinkronkan ke semua DB aktif) → registry dokumen (hash) → tabel ACC berjenjang + kolom `manager_username` → riwayat tukar driver → tabel retensi → appointment, overtime, receptionist, subsidy.
3. **Background thread** — hapus foto overtime lama (> 180 hari) tiap 30 menit.
4. **Middleware** — CSRF (HMAC konstan-waktu; PWA driver membawa `X-CSRF-Token`), headers no-cache & security (CSP, HSTS via `X-Forwarded-Proto`), access log JSON per request, session binding IP+UA (log-warning, tidak blok — driver di-skip karena HP sering pindah jaringan), teardown yang melepas koneksi pool bila route lupa.

Prinsipnya: kebutuhan tabel baru umumnya cukup ditulis sebagai fungsi `ensure_*()` yang dipanggil di startup — tanpa file migrasi terpisah. Contoh pola: `modules/overtime_schema.py`.

---

## 5. Alur SubsidiTepat & gate OTP

Tiga aktor: **agen di host** (punya Chrome + Xvfb), **container web** (tanpa browser), **dashboard Finance**.

1. Cron host `daily_sync.sh` 06:15 WIB → `pull.mjs` tarik riwayat transaksi SPBU → POST `/api/subsidy/import` dengan token `SUBSIDY_IMPORT_TOKEN` → auto-match klaim ↔ transaksi (toleransi liter/nominal di `modules/routes_subsidy.py`).
2. Token/portal kadaluarsa? Finance menekan **Minta OTP Email** di dashboard → backend menulis `otp_request.json` ke `agent/subsiditepat/gate/` (bind mount ke container sebagai `/app/subsidy_gate`).
3. `otp_supervisor.mjs` (host, dijalankan `@reboot`) menjalankan `login.mjs` di Chrome headful → portal MyPertamina mengirim OTP ke `bbm.sby@bestprofit-futures.co.id` → Finance mengetik 6 digit di dashboard → `otp_submit.json` → `verify.mjs` → token baru → pull & match otomatis.
4. Status agen satu arah: `idle → starting → waiting_otp → verifying → syncing → done | error`. Anti request ganda: backend menolak minta OTP lagi saat `starting/waiting_otp`, dan menghormati cooldown `timeToResend` (180 detik) dari portal. OTP sendiri tidak pernah melalui server BPF WorkHub — ia tinggal di email + laptop user.

---

## 6. Stamp versi — 7 titik yang wajib

Setiap rilis mengganti versi di 7 titik ini (di-cek CI dan manual):

1. `modules/company_identity.py` → `'system_version': 'vX.Y.Z'`
2. `modules/pdf_generator.py` → `SYSTEM_VERSION = 'BPF WorkHub vX.Y.Z'`
3. `frontend/src/stores/identity.js` → `system_version`
4. `frontend/public/sw.js` → `const CACHE = 'bpf-spa-YYYYMMDD-vX.Y.Z'`
5. `CHANGELOG.md` → entri teratas
6. `docs/internal/USER_LIST.md`
7. `guides/USER_GUIDE.md`

Verifikasi:

```bash
docker exec bpf-workhub-web python3 /app/scripts/check_version_stamps.py   # harapannya lulus
```

Stamp di DB (`system_config` master + `branches.system_version`) disinkron otomatis saat boot oleh `modules/company_identity.py`; bila boot gagal pakai `scripts/sync_branch_stamp.py`.

> Container membaca file dari **image**, bukan bind mount — edit CHANGELOG **sebelum** `docker compose build web`, bukan sesudah.

---

## 7. Deploy (urutan di server)

```bash
cd /home/it-ef/bpf-workhub
git pull origin main
# rilis baru: bump 7 stamp → commit → build
docker compose build web          # SPA ikut ter-build di image (stage frontend-build)
docker compose up -d web          # hanya web restart; db/redis/backup dibiarkan
sleep 15
curl -s http://127.0.0.1:5001/api/health | python3 -m json.tool
docker exec bpf-workhub-web python3 /app/scripts/check_version_stamps.py
```

Health yang sehat: `checks.database = ok`, `checks.redis = ok`, dan semua pool cabang `ready`.

### Mulai cepat per masalah

| Gejala | Cek pertama |
|---|---|
| Login loop setelah HTTPS | `SESSION_COOKIE_SECURE=true` (cookie Secure wajib via proxy HTTPS; `false` hanya untuk dev http LAN) |
| "Pool exhausted" di log | Cek `Max_used_connections` dan konfigurasi pool (kini `max_connections=500`) |
| Scraper gagal DNS | Compose punya fallback `dns`: DNS internal `172.60.199.1` + 1.1.1.1 + 8.8.8.8 |
| Notifikasi nyasar antar user | Jangan menaikkan jumlah worker gunicorn — room Socket.IO in-memory, `-w 1` wajib |
| SPA masih versi lama | Bump `CACHE` di `sw.js` + reload keras di browser |
| OTP tidak sampai | Cek status supervisor (log `otp_supervisor.mjs`), cooldown 180 dtk, lalu email `bbm.sby@…` |

---

## 8. Backup & restore (kondisi nyata, 3 Nov 2026)

| Isu | Nyata |
|---|---|
| Dump harian | 03:00 WIB — 12 DB (master + 11 cabang) → volume `bpf-workhub_backups`, gzip |
| Retensi | 30 hari |
| Freshness check | Backup terumur > `BACKUP_MAX_AGE_HOURS` (30 jam) → alert Uptime Kuma (`BACKUP_KUMA_ALERT_URL`) |
| Heartbeat | `BACKUP_KUMA_HEARTBEAT` di-curl tiap backup sukses |
| Drill restore | Minggu 04:00 (`RESTORE_TEST_CRON`) — restore ke DB sementara lalu di-drop; log terakhir: `OK — users=53 transactions=63` |

Restore manual:

```bash
PW="$(grep MYSQL_ROOT_PASSWORD .env | cut -d= -f2)"
docker exec -i bpf-workhub-db mariadb -uroot -p"$PW" < dump.sql                  # semua DB
docker exec -i bpf-workhub-db mariadb -uroot -p"$PW" bpf_branch_mlg < dump.sql   # restore satu DB
```

Log: `docker exec bpf-workhub-backup tail -20 /var/log/backup.log`.

---

## 9. Uji & CI

| Jalur | Cara |
|---|---|
| Backend (75 file, 1022 test) | `./scripts/run-tests.sh` — skip 2 file butuh DB (default aman); `--db` untuk lengkap |
| Di dalam container | `docker exec bpf-workhub-web python3 -m pytest /app/tests -q` |
| SPA | `cd frontend && npx vitest run` (+ `npm run build`) |
| CI (`.github/workflows/ci.yml`) | 3 job: (1) build SPA + vitest + `npm audit`, (2) pytest + `pip-audit` + cek stamp versi + cek peta cabang→DB, (3) **Trivy** image scan — HIGH/CRITICAL gagal build |

---

## 10. Konvensi repo

- `main` di GitHub `bestprofitsurabaya/bpf-workhub`.
- Kredensial, `.env`, `uploads/`, `data/`, artifacts agen — **tidak pernah** masuk git (guard `.gitignore`).
- Nilai sensitif yang muncul di log otomatis dimask: `*** sensitive parameters replaced ***`.
- Dokumen lainnya dikelola lewat [INDEX.md](INDEX.md); dokumen ini disusun ulang dengan kroscek server — pertahankan kebiasaan itu tiap perubahan arsitektur besar.

---

*Terakhir diverifikasi 3 Nov 2026 melawan server live · era v2.77.0.*
