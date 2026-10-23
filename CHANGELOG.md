# 📋 Changelog — BPF WorkHub

Riwayat perubahan BPF WorkHub. Ditulis untuk manusia, bukan untuk robot.

> Dokumen ini direkonstruksi (12 Okt 2026) setelah isi historisnya hilang
> saat pengeditan massal — ringkasan di bawah disarikan dari commit log
> `git log` yang tetap utuh. Lihat `git log --oneline` untuk rincian
---

## v2.60.0 — 23 Oktober 2026 (fase-3 gelombang 7: header bespoke → standar)

- 🎬 TranscoderView & 📄 PdfKitView: header kustom kini memakai PageHeader
  (meta pil & tombol share ke slot) — SATU-satunya page SPA tersisa dengan
  header bespoke adalah /it (konsol scraper, desain sendiri by design).
- ✔️ 217 vitest hijau.

## v2.59.0 — 23 Oktober 2026 (fase-3 gelombang 6: perapihan visual global)

- 🎨 `main.css` menerima pola primitif: baris tabel melembut (hover sedar
  light/dark), semua tombol & input bertransisi halus dengan ring fokus
  halo primary (:focus-visible, aksesibilitas), tombol sekunder punya hover,
  scrollbar bersih, ikon stat-card dirapikan — efeknya menyapu semua
  halaman tanpa mengubah struktur view mana pun.
- ✔️ 217 vitest hijau.

## v2.58.0 — 23 Oktober 2026 (fase-2 gelombang 5: sisa view SPA — rollout selesai)

- 12 view terakhir masuk standar: Trips, Assignments, Cash, Settings,
  AccessReview, Assets, ChiefDriver, Marketing, Receptionist, EmployeeInOut,
  Overtime (GA HR), Traineer — **seluruh halaman utama SPA kini memakai
  PageHeader yang sama**.
- Publik & PWA mobile (Login/Apply/Form OT/driver/*) sengaja tidak — punya
  layout sendiri; TranscoderView & PdfKitView bertahan desain bespoke-nya.
- ✔️ 217 vitest hijau. Fase-2 design system: SELESAI; lanjut fase-3 polish.

## v2.57.0 — 23 Oktober 2026 (fase-2 gelombang 4: view operasional)

- 🚰 WaterView · 👥 UsersView · 📝 LogsView · ✅ ApprovalsView ·
  ⏰ OvertimeMeView — semuanya kini memakai PageHeader standar
  (tombol aksi di slot header, teks dipertahankan persis).
- Skipped yang aman: Trips/Cash/Assignments/AccessReview (tanpa header
  klasik — akan menyusul pattemplannya di gelombang lanjut).
- ✔️ 217 vitest hijau.

## v2.56.0 — 23 Oktober 2026 (fase-2 gelombang 3: Admin + kebersihan hitungan badge)

- 🧭 **AdminDashboard** memakai PageHeader (binding dinamis per role,
  role-chip di slot aksi) — seluruh halaman Ringkasan kini satu standar.
- 🧮 **Badge/hitungan anti-corup**: `/api/stats` (8 COUNT kategori klaim) dan
  3 badge nav (`ga_pending`, `finance_pending`, `bbm_verify_pending`) kini
  mengecualikan baris `is_dummy=1` — sebelumnya baris demo ter-count padahal
  tak tampil di antrean (badge "2", antrean kosong).
- ✅ test `test_nav_badges` diperbarui (4 lulus) + vitest 217 hijau.

## v2.55.0 — 23 Oktober 2026 (fase-2 gelombang 2: GA · Rekap · Analytics)

- 🧾 **Dashboard GA** — header diberi PageHeader standar
- 📄 **Rekap** + 📈 **Analytics** — kini punya identitas halaman (PageHeader
  dengan subtitle), filter card tetap sebagai aksi periode
- ✔️ 217 vitest hijau

## v2.54.0 — 23 Oktober 2026 (fase-2 perombakan UI/UX: design system global — gelombang 1 Finance)

- 🧱 **Komponen `PageHeader.vue`** — header halaman standar (ikon + judul +
  subtitle + slot aksi) dengan utilitas CSS token di `styles/main.css`
  (`.page-header/.ph-*`), light & dark mode otomatis ikut token.
- 🎨 **Kelas bersama baru**: `.attention-card` (kartu perhatian ala pintasan
  klaim BBM, warna dari `--warning`), sekaligus aturan `.card-pad h3` agar
  judul kartu tidak perlu inline style; kelas lama tetap bekerja (additive).
- 💰 **Dashboard Finance** jadi view pertama yang memakai standard: header →
  `PageHeader`, kartu pintasan Klaim BBM → `.attention-card`.
- ➕ 3 test `PageHeader` — total **217 vitest** hijau.

Versi lanjut: gelombang 2 (GA/Rekap/Analytics), 3 (Admin), 4 (polish wizard
onboarding & PWA).

## v2.53.1 — 22 Oktober 2026 (standardisasi infrastruktur: semua container & volume memakai pola `bpf-workhub`)

Permintaan ops: saat melakukan recreate, *semua* resource Docker memakai nama
`sistem` yang satu dan mudah dilanjutkan programmer baru sebelumnya masih
mencampur prefix lama (`bpf-bbm-system` project, `bbm_web/bbm_mariadb/
bbm_redis/bbm_backup`, volume `bbm_db_data` dst).

- 🐳 **Docker Compose**: `name: bpf-workhub`; container `bpf-workhub-web`,
  `bpf-workhub-db`, `bpf-workhub-redis`, `bpf-workhub-backup`; volume dengan
  **nama eksplisit** `bpf-workhub_db_data`, `bpf-workhub_redis_data`,
  `bpf-workhub_backups` (tidak ikut double-prefix nama project).
- 🥇 **Migrasi data tanpa dump**: stack lama dihentikan (`docker compose down`),
  isi volume dicopy 1:1 via container alpine (`cp -a`), ukuran verifikasi byte
  MATCH (315.559.671 B), lalu stack baru start — DB cabang & arsip utuh.
- 🔧 Skrip & doc operasional ikut direname (`scripts/*`, `docs/public/
  PELATIHAN.md`, `nginx_bbm_system.conf`); dokumen historis PROGRESS tidak
  disinggung (jejak audit tetap asli).
- 📖 **`docs/DEVELOPER.md` baru** — onboarding programmer lanjutan (quickstart,
  peta DB 10 database, 7 titik stamp, cara deploy, uji Berita Acara, agen
  subsiditepat).

## v2.53.0 — 22 Oktober 2026 (fase-1 perombakan UI/UX: akses & navigasi Finance)

**Temuan audit visual** (screenshot dashboard Finance): halaman utama Finance
sama sekali tidak memuat alur klaim BBM, sementara seluruh alur payout,
Subsidi Tepat, dan Berita Acara hidup di `/app/dashboard` yang kunci routenya
`roles: ['admin']` — finance tidak pernah bisa membukanya. Inilah akar protes
"UI finance sangat buruk": bukan kosmetik, tapi akses & klasifikasi navigasi.

- 🔓 `/app/dashboard` dibuka untuk role **finance** (antrean klaim BBM:
  payout, konfirmasi driver, panel Subsidi Tepat, Berita Acara).
- 🧭 Menu sidebar baru **"🕐 Antrean Verifikasi"** (finance) + badge
  `bbm_verify_pending` = jumlah klaim `verified_ga` siap pencairan
  (`routes_nav.py`).
- ⛽ Dashboard Finance: kartu pintasan **"Klaim BBM menunggu keputusan
  Anda"** — hitungan klaim siap cair & menunggu arsip + tombol langsung
  buka antrean (tidak lagi mencari-cari halaman).

Fase berikutnya roadmap perombakan total UI/UX: fase-2 design system global
(token warna/typografi/komponen dasar), fase-3 polish onboarding & PWA.

## v2.52.0 — 22 Oktober 2026 (perombakan modal verifikasi Finance — checklist, tab klasifikasi, zoom bukti)

Audit masukan Finance: modal detail berupa tumpukan linier (badge → data → foto →
form → 3 panel analisis → tombol campur semua role) tanpa urutan kerja —
pemegang keputusan harus bergulir panjang dan menggabungkan info sendiri.

- ✅ **Ringkasan Verifikasi (checklist) di atas modal**: 4 chip status —
  Verifikasi GA (nama+waktu), Anomali ML (diperiksa GA atau tidak ber-flag),
  Subsidi Tepat (tertaut / verdict), Health Score & Budget. Keputusan payout
  cukup melihat satu panel.
- 🗂 **Tab klasifikasi konten**: `📋 Bukti & Data` (data klaim, foto, form
  verifikasi anomali & edit), `⛽ Subsidi Tepat` (kandidat SPBU + taut,
  finance/admin), `💰 Analisis Keuangan` (cross-check + finance review +
  catatan). Bar aksi keputusan selalu tampak di bawah.
- 📷 **Zoom foto bukti**: thumbnail 120px + overlay perbesar full-screen
  (Finance memeriksa nota tanpa membuka tab baru).
- Semua 16 test AdminDashboard tetap lolos (tombol & alur tidak berubah).

## v2.51.0 — 22 Oktober 2026 (Berita Acara Rekonsiliasi Subsidi Tepat — dokumen resmi kantor pusat)

Finance kini dapat menerbitkan **Berita Acara Rekonsiliasi** (PDF landscape, berkop) untuk
satu periode: semua klaim yang **ditaut Finance** di periode itu disandingkan dengan data
sistem Pertamina — dibuat sulit dibantah:

- 🧾 **Bukti pihak ketiga per baris**: `transactionId` SPBU, timestamp server SPBU,
  verifikasi QR, SPBU/witel, volume & nominal menurut sistem Pertamina + selisih vs klaim.
  Kantor pusat bisa mencerminkan setiap nomor langsung di portal
  subsiditepat.mypertamina.id → Riwayat.
- 🔐 **Rantai hash SHA-256**: `hash_n = SHA-256(hash_n-1 + record_n)` (JSON kanonik),
  ROOT = SHA-256(hash terakhir + 'records=N') — ditulis di PDF; mengubah satu angka di
  DB mana pun membuat ROOT tidak cocok dengan cetakan yang sudah diteken.
- 📦 **Snapshot arsip JSON read-only** (`data/subsidy_attest/`) + hash file tercantum
  di dokumen — salinan mentah tarikan portal yang tak dapat diubah dari aplikasi.
- ✍️ **TTD bertingkat** diambil dari data: nama GA (verifikasi masuk) + Finance
  (verifikator final) sebagaimana tercatat di audit trail.
- Modul baru `modules/subsidy_attest.py` (registry `subsidy_attestations` di master,
  builder rantai hash, snapshot, persist), endpoint `POST/GET /api/subsidy/attest` +
  `GET /api/subsidy/attest/<id>/pdf` (unduh dari arsip; bila file arsip hilang,
  PDF dibangun ulang hanya bila ROOT masih cocok — BA lama tak bisa dipalsukan).
- UI: tombol **🖨 Berita Acara SPBU** di header Antrean Kerja (finance/admin) + modal
  periode bulanan, daftar BA tersimpan, unduh PDF.

## v2.50.1 — 22 Oktober 2026 (hotfix: driver gagal submit klaim — 500 & antrean offline)

Ditemukan saat uji klaim nyata driver "ahmad" (user laporan `NotFoundError`
IndexedDB + `POST /driver` 500):

- 🐞 **`POST /driver` 500 — tabel `vehicle_fuel_prices` tak pernah dibuat.**
  Refactor 25 Agu (commit `584ba88`, security review) memindahkan harga ke
  lookup server-side tabel `vehicle_fuel_prices`, tapi migration tabelnya
  tertinggal di SEMUA DB (master + cabang) → `ProgrammingError 1146` setiap
  driver submit klaim.
  - `ensure_fuel_prices_schema()` idempoten (master + tiap cabang saat startup):
    buat tabel + seed harga default per kombinasi kendaraan×BBM dari
    `bbm_types.price_per_liter` (dapat ditimpa Admin per kendaraan nanti).
  - Guard di `driver_form`: bila tabel/lookup gagal → fallback harga 10.000
    (tak 500 lagi).
- 🐞 **IndexedDB store "not found" berulang (antrean offline driver)** — DB di
  browser dibuat bundel lama; bundel baru menagih store yang tak ada, upgrade
  tak jalan karena versi sama → `NotFoundError` tiap sync.
  - `frontend/src/utils/idb.js` v5 + self-heal: deteksi store yang hilang,
    buka ulang dengan versi lebih tinggi dan buat semua store otomatis;
    tangani `VersionError` (DB browser versi lebih tinggi dari kode).

## v2.50.0 — 22 Oktober 2026 (integrasi Subsidi Tepat MyPertamina: verifikasi klaim ↔ riwayat SPBU resmi)

Integrasi dengan akun **Subsidi Tepat (MyPertamina)** milik perseroan: riwayat
transaksi BBM resmi dari SPBU (hasil agen `subsiditepat` di host) kini bisa
dipakai **Finance** saat verifikasi klaim untuk memastikan kecocokan data:

- 🗄️ **Tabel `subsidy_transactions` (master DB)** — arsip otoritatif riwayat
  SPBU lintas cabang: transactionId, tanggal SPBU, nopol, produk, volume,
  nominal, SPBU, kota, tipe verifikasi (QR), + raw payload lengkap.
  Kolom tautan baru `transactions.subsidy_tx_id/match/linked_by/at` (master +
  semua cabang, dibuat idempoten saat startup).
- ⬆️ **`POST /api/subsidy/import`** — upsert data oleh agen (header
  `X-SUBSIDY-TOKEN` == env `SUBSIDY_IMPORT_TOKEN`) atau admin (sesi); idempoten,
  anti-duplikat (`ON DUPLICATE KEY`), jelaskan audit trail `subsidy_import`.
- 🤖 **`GET /api/subsidy/match/<tx>`** — kandidat kecocokan otomatis:
  nopol dinormalisasi ('B 2731 SRQ'='B2731SRQ'), jendela tanggal ±1 hari,
  verdict **MATCH** (selisih ≤0.05 L & ≤Rp 2.000) / **CLOSE** (≤2 L) /
  **NO_MATCH**/**NO_RECORD**. Bersifat ADVISORY — membantu Finance, tidak memblok payout.
- 🔗 **`POST /api/subsidy/link|unlink/<tx>`** — Finance menautkan klaim ke
  transaksi SPBU saat verifikasi (audit trail); UI panel **"⛽ Verifikasi
  Subsidi Tepat"** di modal detail antrean (Finance/admin) di AdminDashboard.
- 📊 **`GET /api/subsidy/status`** — kesiapan data (jumlah row, tarikan terakhir).

## v2.49.3 — 22 Oktober 2026 (audit anti-kecurangan klaim BBM: bukti foto, ODO, kapasitas, cap, joint sign-off)

Tindak lanjut diskusi rute BBM (Finance/GA/Driver/Chief Driver) — menutup celah
dari pembedahan kode 22 Okt 2026:

- 🖼️ **Bukti foto punya sidik jari** — hash SHA-256 konten tiap foto klaim
  dicatat ke `proof_registry` (master DB, lintas cabang). Foto struk/ODO yang
  **sama dipakai ulang klaim mana pun ≤30 hari → DITOLAK** (400) saat submit.
- 📷 **PWA live camera + watermark** — antrean foto di `/m/` kini membuka kamera
  belakang langsung (getUserMedia) dengan cap **tanggal-jam-GPS-nopol yang
  di-burn ke pixel** (atas+bawah, anti-crop). Bila kamera gagal, fallback picker
  galeri — tapi GA menerima sinyal `tanpa EXIF`.
- 🏗️ **EXIF digali & di-flag** — waktu/GPS kamera sediakan dalam `proof_meta`;
  `/api/cross-check` kini menampilkan `proof_signals`: waktu kamera beda jam dari
  klaim, kamera >5 km dari GPS klaim, tanpa EXIF.
- 🏗️ **ODO mundur DITOLAK** dan **baseline ODO hanya dari status tervalidasi**
  (`verified_ga/os_finance/archived`) — klaim rejected/pending tidak lagi
  menjadi pembanding (bug nyata di `routes_driver.py`).
- 🏗️ **Batas fisik** — liter klaim > 100% `fuel_capacity` ditolak; > 90% dan
  ODO tak berubah + cap nominal klaim `bbm_daily_cap_driver` /
  `bbm_weekly_cap_driver` memakai flag anomali (soft cap; default off, diatur
  Admin per cabang via system_config).
- 🚦 **Joint sign-off anomali** — payout (Finance) kini minta klaim ber-flag
  anomali **sudah di-clear GA** (`/api/queue/anomaly-clear`, step-up PIN).
  Unverify kembali mereset clear — payout otomatis tertahan lagi.
- 🚧 **Self-approval level orang** — jurnal ACC kini juga memblok keputusan bila
  full_name akun aktor == nama pengaju (jebol via 2 akun ditutup).
- Kolom baru `transactions.proof_meta/anomaly_cleared_by/at` dibuat idempoten
  (master + semua DB cabang) di startup; registrasi hash best-effort.

## v2.49.2 — 22 Oktober 2026 (temuan audit sysadmin: backup drill, werzeug guard, dokumentasi env, kebersihan repo)

Tindak lanjut audit sistem (security + ops) 22 Oktober 2026:

- 🧹 **Kebersihan repo**: hapus 2 file sisa backup `modules/*.bak-*`
  (`routes_applicants.py.bak-stepup`, `routes_spa.py.bak-last-login`);
  pindahkan snapshot data runtime 7 MB
  (`backup_overtime_driver_sheet_20260906.json`) keluar repo →
  `/srv/bpf-workhub/backups-repo-root/` (disk besar 1.7 TB).
- 🔐 ** Werkzeug dev-runner guard (app.py)**: blok `python app.py` kini
  refuser di produksi (`SystemExit` + instruksi gunicorn) — menghapus
  risiko menambah server dev tanpa proxy di jalur produksi.
  Produksi tetap selalu via gunicorn (`CMD` Dockerfile).
- 🗄️ **Backup lebih diuji, bukan diandalkan**:
  - *backup-freshness-check.sh* — uji gzip -t semua dump hari ini +
    umur file terbaru ≤ `BACKUP_MAX_AGE_HOURS` (default 30 jam), dipanggil
    otomatis di akhir `backup-db.sh`, bertindak lintas (bila check gagal,
    backup exit 1).
  - *restore-test.sh* — drill restore mingguan (Minggu 04:00 WIB,
    `RESTORE_TEST_CRON`) ke DB sementara `restore_dr_tmp` yang di-drop sehabis
    verifikasi row; drill pertama sukses (users=53, transactions=135).
  - Integrasi **Uptime Kuma** opsional: `BACKUP_KUMA_HEARTBEAT` (push tiap
    backup OK) & `BACKUP_KUMA_ALERT_URL` (push saat gagal) di `.env`.
- 📄 **README**: bagian baru *"Variabel Environment"* (termasuk `MIKROTIK_*`
  — kredensial di `.env`, tidak hardcode, saat ini belum dipakai kode) +
  bagian *"Menjalankan Test di Host"* via `scripts/run-tests.sh`.
- 🧪 **run-tests.sh**: default aman (skipp 2 file test butuh DB yang di CI
  sukses dan di host perlu env) dan mode `--db` dengan kredensial `.env`.
  Membenahkan 11 error lama saat pytest di host (root cause: test tanpa
  `DB_PASSWORD`; **CI-parity** kini tersedia lokal).

## v2.49.1 — 22 Oktober 2026 (patch keamanan dependensi: Pillow 13.0.0 + vite/vitest 5.0.3 untuk CI hijau)

Tindak lanjut CI merah (npm audit + pip-audit, Tahap 4/6 ISO 27001):

- `requirements.txt`: **Pillow 12.3.0 → 13.0.0** — menutup **24 CVE** yang
  dilaporkan `pip-audit` (semua fix `13.0.0`). Uji lokal: 161 pytest pada modul
  yang memakai PIL (overtime, PDF Kit, duplikasi foto, scraper layanan, water)
  → lulus.
- `frontend`: **vite 8.2.2 → 8.2.4+**, **vitest 5.0.0 → 5.0.3** — mematikan
  1 vuln high (launch-editor) + 2 moderate (`@vitest/mocker`); `npm audit
  --audit-level=high` → **0 vulnerabilities**, vitest **214 passed**, build SPA
  hijau.
- Stamp versi ikut di-bump **v2.49.1** (7 titik + stamp DB disinkron saat
  redeploy).

## v2.49.0 — 22 Oktober 2026 (UI/UX Admin Cabang P0–P5: dashboard tindakan, modal konfirmasi, onboarding & panduan in-app)

Batch usability UI/UX untuk admin cabang (`admin_<kode>`, P0–P5) + instrumentasi
uji kegunaan. Protokol uji: `docs/internal/USABILITY_TEST_P5.md`.

- **P0 — scoping data & aksi cabang**: admin cabang kini benar-benar terkunci di
  cabangnya — `/api/branches`, `/stats`, `/report-pdf` difilter `admin_branches()`,
  8 aksi lintas cabang (save/seed-demo/activate/deactivate/ensure-db/consolidated*)
  dilindungi `@ho_only` (403), `branch_stats()` dibatasi DB cabangnya, Settings
  read-only untuk admin cabang.
- **P1 — information architecture**: 25 menu datar → **6 grup** per role;
  **badge angka antrean** di sidebar + hasil pencarian; **pencarian menu**
  `Ctrl/Cmd+K`; **breadcrumb**; `GET /api/nav/badges` (ringan, per role, refresh
  realtime + 60 dtk). Tests: `tests/test_nav_badges.py` + AppLayout.test.js.
- **P2 — dashboard berbasis tindakan**: blok **⚡ Perlu Tindakan Hari Ini**
  3–5 kartu klikabel dari utilisation stats — kartu 0 disembunyikan, semua bersih
  → banner sukses. KPI 6 → 3, **Aksi Cepat** dihapus (duplikat sidebar), tabel
  antrean **10 → 6 kolom** (ODO/liter/BBM/foto pindah ke modal Detail).
- **P3 — bahasa manusiawi & modal konfirmasi**: komponen **ConfirmDialog**
  (termasuk mode input wajib) menggantikan **semua** `confirm()`/`prompt()` native
  di 14 view; tombol antrean berteks (Setujui/Tolak/Cairkan/Arsipkan); format
  Rupiah/tanggal/status memakai `utils/format.js` di 5 view; alasan tolak wajib
  dengan validasi inline; label role & status lebih manusiawi.
- **P4 — onboarding & bantuan in-app**: **Help Center** (`❓` / tombol `?`) —
  panduan per halaman (19 halaman) + **glosarium 20 istilah** + pencarian; tur
  onboarding 4 langkah role-aware otomatis sekali per akun/perangkat; aplikasi
  Driver juga dapat bantuan + tur sendiri. Tests: HelpCenter, OnboardingTour.
- **P5 — perangkat uji kegunaan**: protokol 5 tugas + target
  **time-to-first-action < 30 dtk**; instrumentasi `utils/usability.js` hanya
  aktif dengan `?p5=1` (`sessionStorage`, tidak dikirim ke server) dan panel
  diagnostik di Help Center. Sesi 5 partisipan menyusul dengan pengguna nyata.
- **Uji**: `npx vitest run` → **214 passed** (termasuk test Transcoder yang
  flaky-fake-timer diperbaiki); `npm run build` hijau; `pytest tests/test_branches.py
  tests/test_admin_scope.py tests/test_nav_badges.py` → 38 passed. Tanpa perubahan
  dependensi.

## v2.48.0 — 21 Oktober 2026 (PWA Mobile: Driver, OB & Security)

**Fitur baru** — aplikasi **PWA mobile** di `/m/` (satu shell, otomatis deteksi role
driver / ob / security setelah login PIN). Sumber: `mobile/` (bind-mount
`./mobile:/app/mobile:ro` — edit statik tanpa rebuild image; route Python
`/m/` di `modules/routes_spa.py`).

- **Driver** (5 tab): BBM (foto ODO/struk, harga dari server, GPS + reverse
  geocode Nominatim), Trip (multi-rute + muat appointment hari ini), Overtime
  Driver (foto mulai/selesai base64 + GPS), Kasbon (pengajuan & daftar LPJ →
  isi LPJ lewat tab BBM), Rapor (feedback).
- **OB & Security**: submit overtime (nama & posisi diambil dari sesi server,
  foto mulai wajib, GPS) + riwayat sendiri (`/api/overtime/mine`).
- **Offline queue** di localStorage: BBM/TRIP/OVERTIME antre saat offline dan
  dikirim ulang otomatis saat kembali online (mirip perilaku SPA).
- **Service worker** (`/m/sw.js`): app shell cache-first, `/api/` & Nominatim
  selalu network; manifest standalone + ikon maskable 192/512.
- Keamanan tetap di server: sesi + `X-CSRF-Token`, validasi & harga BBM dari
  `vehicle_fuel_prices`, identitas driver dari sesi (bukan body).
- Diverifikasi E2E dari NAS (21 Okt): login driver `wicak` & OB `ob_febri_sby`
  sukses, endpoint yang dipakai app semua 200, portal `/app/` tidak ada regresi,
  `pytest tests/test_driver_session.py tests/test_driver_context.py` 12 passed.

## v2.47.0 — 16 Oktober 2026 (PDF Kit: kompres PDF untuk IT + daftar lindungi otomatis)

**Fitur baru** — halaman **📄 PDF Kit** (`/app/pdfkit`, menu sidebar IT) untuk role IT
cabang (`it_sby` … `it_lpg`) + admin.

- **Enam mode kompresi**: `lossless` (qpdf — struktur & stream dirapikan; teks, tautan,
  dan gambar asli tidak disentuh), `ringan` 150 dpi, `sedang` 120 dpi, `kuat` 100 dpi,
  `maksimal` 72 dpi + JPEG (Ghostscript `pdfwrite`), dan `target` (rantai otomatis
  lossless → ringan → kuat → maksimal yang **berhenti begitu target ukuran tercapai**).
  Pada semua mode Ghostscript teks & vektor tetap teks sehingga masih bisa dicari.
- **Daftar lindungi otomatis** — berkas yang sha256-nya terdaftar di
  `document_registry` (dokumen terbitan aplikasi: kuitansi air minum, laporan overtime,
  laporan in-out) **dilewati** karena mengompresnya mematahkan verifikasi keaslian
  `POST /api/documents/verify`. PDF **bertanda tangan digital** (`pdfsig`) dan
  **terenkripsi** (`pdfinfo`) juga tidak diproses. Statusnya tampil sebagai
  🛡️ *Dilindungi* / ➖ *Dilewati* beserta alasannya — jadi dokumen yang tidak boleh
  dikompres ditolak sistem, bukan bergantung kedisiplinan operator.
- **Berkas asli tidak pernah ditimpa**: hasil selalu berkas baru `*_kompres.pdf`.
  Hasil yang tidak menyusut ≥2% dibuang dan ditandai "sudah optimal" supaya IT tidak
  mengunduh berkas sia-sia. Tiap berkas dilaporkan: jumlah halaman, ukuran sebelum →
  sesudah, persen hemat, mode yang dipakai, dan apakah teks masih bisa diekstrak.
- **REST**: `GET /api/pdfkit/modes`, `POST /api/pdfkit/jobs` (multipart 1–10 berkas,
  maks 100 MB/berkas & 250 MB sekali submit), `GET /api/pdfkit/jobs`,
  `GET/DELETE /api/pdfkit/jobs/<id>`, `POST /api/pdfkit/jobs/<id>/cancel`,
  `GET /api/pdfkit/download/<job_id>/<file>` (path-guard + hanya milik job). Job
  memakai registry in-memory pola Transcoder, antrean `MAX_CONCURRENT=1` (Ghostscript
  haus RAM), hasil di `data/transcoder/pdfkit/` (volume persisten, retensi 48 jam).
- **Laporan pemakaian** — panel **📄 Pemakaian PDF Kit** di halaman **Audit Log**: per user
  menampilkan jumlah job, berkas, byte sebelum → sesudah, byte & persen yang dihemat,
  lengkap dengan filter tanggal & cabang. Sumbernya `activity_logs` (`pdfkit_submit` dari
  route + `pdfkit_done` yang ditulis worker saat job selesai), jadi angkanya tetap ada
  walau berkas hasil sudah kedaluwarsa (retensi 48 jam). Endpoint: `GET /api/pdfkit/report`.
  Submit & selesai memakai **identitas yang sama** (nama lengkap user, cadangan username)
  supaya satu orang tidak terpecah jadi dua baris di laporan.
- **Dependensi image**: `ghostscript` + `qpdf` ditambahkan di Dockerfile; `poppler-utils`
  yang sudah terpasang dipakai untuk `pdfinfo`/`pdfsig`/`pdftotext` (deteksi sifat PDF).
- `modules/doc_integrity.py`: fungsi baru **`lookup_sha256()`** (cari registri dari hash
  tanpa memuat isi PDF) — dipakai PDF Kit, dan `lookup_pdf()` kini memakainya juga.
- **Uji**: 36 pytest (`tests/test_pdfkit.py` — helper, guard, API, logika rantai target,
  agregasi laporan, kompresi nyata gs/qpdf) + vitest (`PdfKitView.test.js`, `LogsView.test.js`)
  lulus; uji nyata: PDF scan 240 dpi 1,7 MB → 121 KB (maksimal), teks tetap terekstrak.
  Fixture autouse menambal `log_activity_async` sehingga menjalankan suite **tidak** menulis
  jejak uji ke `activity_logs` produksi.

---

## v2.46.5 — 30 September 2026 (Scraper: template meta description & SEO title + skrip WP-CLI konversi artikel lama)

- **Template meta Rank Math** — dua field baru di panel upload: template
  *meta description* (`rank_math_description`, dipotong 160 karakter) dan
  *SEO title* (`rank_math_title`, dipotong 60 karakter). Placeholder:
  `{judul}`, `{kategori}`, `{sumber}`, `{tanggal}`. Kosong = Rank Math
  memakai default (judul post / excerpt).
- Meta description & title juga ikut terkirim saat **update** artikel
  duplikat (dulu hanya focus keyword yang diteruskan).
- **Skrip WP-CLI** `tools/wp-cli/convert-classic-to-blocks.php` — konversi
  massal artikel lama classic → blok (mekanisme identik tombol "Convert
  to blocks", via filter `rest_pre_insert_post` → `do_blocks()`), dengan
  dry-run default, gerbang verifikasi konten (HTML asli harus utuh),
  opsi `--post_type/--limit/--offset/--search/--ids/--force`. Scraper
  sejak v2.46.4 memancarkan blok langsung — skrip ini hanya untuk stok
  artikel lama.
- Test: +1 pytest (template meta) → 70 lulus; 12 vitest lulus.

---

## v2.46.4 — 30 September 2026 (Scraper: artikel Gutenberg-ready + fokus keyword Rank Math)

**Masalah:** artikel hasil scraper terbit sebagai HTML polos tanpa komentar
blok `<!-- wp:... -->` → WordPress menganggap seluruh artikel SATU blok
Classic → tata letak terlihat rusak di editor, dan normal kembali hanya
setelah redaksi menekan "Convert to blocks" manual satu per satu.

- **`wp_block()`** — helper baru di `seo_optimizer` yang membungkus segmen
  HTML dalam komentar blok inti yang sesuai: `<p>` → `wp:paragraph`,
  `<h1>`–`<h6>` → `wp:heading` (+ atribut level), `<figure>` ber-`<img>` →
  `wp:image`, `ul/ol` → `wp:list`, `blockquote` → `wp:quote`, sisanya
  (div styling, `<script>` progress bar, CTA) → `wp:html`.
- **`build_article_html()`** kini memancarkan rangkaian blok per segmen:
  header meta, daftar isi, tiap paragraf/H2, disclaimer, dan blok script
  — semua blok valid dan berpasangan, tidak perlu "Convert to blocks"
  lagi. Efek samping: `<script>` tak lagi mengotori meta description
  Rank Math di editor (hanya di blok Custom HTML).
- **Featured image, tautan sumber, dan CTA** di `routes.py` ikut dibungkus
  blok — penyisipan sumber tak lagi memenggal blok lewat penggantian
  marker di tengah blok lain.
- **Truncation konten >120 KB** kini memotong pada batas blok (baris
  kosong) — dulu bisa meninggalkan blok tanpa penutup (error validasi).
- **Rank Math SEO** — post kini mengirim `meta.rank_math_focus_keyword`
  (diturunkan otomatis dari judul, maks 4 kata bermakna) via REST API
  yang sama. Toggle "🎯 Keyword Rank Math" di panel upload (default ON,
  tersimpan di settings). Bila plugin tidak aktif (WP membalas
  `rest_invalid_param`) upload otomatis diulang tanpa meta — artikel
  tetap terbit.
- Test: +23 pytest (blok Gutenberg, pasangan komentar, derivasi keyword,
  meta & fallback e2e) → 69 pytest scraper lulus; 12 vitest ItEfView lulus.

---

## v2.46.3 — 30 September 2026 (Transcoder: auto-delete salinan share publik — retensi cermin)

- Hasil job yang di-*cleanup* (usia >48 jam, atau job dihapus kapan pun)
  ikut menghapus foldernya di share publik Nextcloud — tautan unduh
  publik mati bersamaan dengan hasil lokal, tidak ada berkas yatim.
- `ncshare.delete_folder(job_id)` (best-effort): gagal jaringan/izin tidak
  menggagalkan pembersihan lokal; status `purged`/`purge_detail`
  tercatat di detail job untuk inspeksi.
- Test: +2 pytest (purge sukses & purge gagal tidak menggagalkan hapus job).

---

## v2.46.2 — 30 September 2026 (Transcoder: tautan unduh publik via share Nextcloud)

**Masalah:** tautan unduhan hasil transcode terikat login WorkHub — tidak
bisa dibagikan ke pihak luar (mis. vendor, tim konten) tanpa memberi
akun.

- Panel **share publik** di UI Transcoder (khusus admin): tempel URL
  Nextcloud share `https://…/index.php/s/<token>` + password →
  `POST /api/transcoder/ncshare`; tersimpan di
  `data/transcoder/nc_share.json` (volume persisten). Password tidak
  dikirim balik ke browser (hanya flag `password_set`).
- **Unggah otomatis** — saat job selesai, setiap hasil langsung diunggah
  ke folder share Nextcloud (best-effort: gagal jaringan tidak
  menggagalkan job). URL publik tersedia via tombol "Tautan publik"
  (`GET /api/transcoder/jobs/<id>/public-links`).
- Test: +8 pytest (config share, unggah, public-links, unconfigured).

---

## v2.46.1 — Desember 2026 (Transcoder: polling adaptif tab hidden + AbortController)

- Polling progres job berhenti saat tab dokumen *hidden*
  (`document.visibilitychange`) — hemat request di latar belakang.
- `AbortController` membatalkan fetch in-flight saat komponen unmount
  (hilang warning setState-unmounted).
- Test: 12 vitest TranscoderView lulus.

---

## v2.46.0 — 26 September 2026 (Transcoder: konversi link YouTube multi-format untuk role IT)

Fitur baru untuk role IT cabang (`it_sby` … `it_lpg`) + admin: konversi link
YouTube ke berbagai format audio/video.

- **Engine** `modules/transcoder/` — job manager in-memory thread-safe
  (pola news_scraper): tiap job = worker daemon (unduh yt-dlp → transcode
  ffmpeg), antrean `MAX_CONCURRENT=1` (server 3.8GB). Progres streaming
  via `-progress pipe:1` + `--newline`.
- **Format output**: mp3 (192k), m4a (128k), wav, mp4 720p, mp4 1080p,
  webm (VP9 + Opus, cpu-used 8 utk CPU lemah), mkv (stream copy).
- **REST API** (ber-session + CSRF): submit 1–10 link sekali submit
  (multi-link, strip duplikat, validasi URL YouTube), daftar job (milik
  user; admin semua), polling detail, cancel, delete (hapus hasil),
  unduh hasil (auth + path-guard + batas ekstensi).
- **Hasil disimpan** di `data/transcoder/` (volume `./data`),
  retensi 48 jam lalu auto-cleanup; nama file di-sanitize (anti
  traversal).
- **Docker**: ffmpeg & ffprobe via apt di Dockerfile; RAM limit web
  dinaikkan 1g → 1536m; volume `./data/transcoder`.
- **UI** `TranscoderView.vue`: form submit multi-link + pilih format,
  daftar job + progres per item realtime (polling 2s), cancel/delete,
  unduh hasil. Menu sidebar 🎬 di `AppLayout`, route `/transcoder`
  role IT + admin only.
- Test: 36 pytest transcoder lulus (lifecycle, antrean, cancel, unduh,
  path-traversal, ncshare); 12 vitest TranscoderView lulus.

---

## v2.45.3 — detail lengkap lihat `git show <commit>` (Scraper: cron auto-scrape aktif ulang dgn filter usia)

- Cron auto-scrape (jam 6,10,14,18 WIB) kini hanya meng-upload artikel
  maksimal `AUTO_SCRAPE_MAX_AGE_DAYS` hari (default 1) sehingga backlog
  lama tidak pernah diterjunkan ke site — pelajaran dari rollback batch
  278 artikel backdate di v2.45.2.
- Mode uji: `--dry-run` di `scripts/auto_scrape.py`.

---

## v2.45.2 (Scraper: cron auto-scrape dimatikan sementara)

- Batch catch-up 278 artikel backdate ter-rollback; cron dinonaktifkan
  sampai filter usia siap (aktif kembali di v2.45.3).

---

## v2.45.1 (Docker: cron auto-scrape — wrapper ekspor PATH)

- `python3: not found` di log cron: PATH default cron tanpa
  `/usr/local/bin` → wrapper `auto_scrape.sh` kini mengekspor PATH.

---

## v2.45.0 (Scraper: auto-scrape cron 6,10,14,18 WIB)

- Cron di image: `scripts/auto_scrape.sh` → scrape + upload terjadwal ke
  site cabang; log `data/news_scraper/auto_scrape.log`.

---

## v2.44.0 — Frontend polish & pembersihan

- Telemeetri in-out (v2.41–v2.44): mode **hybrid** (catat manual + impor
  sheet) vs **sheet** (read-only) via `system_config.inout_mode` — UI
  menyesuaikan tombol sort & input; sinkronisasi manual dari sheet
  dipicu tombol "Sinkron" (refresh roster + last_sync).
- Regresi v2.46.6 (12 Okt 2026): mode dibaca SETELAH `conn.close()`
  sehingga nilai selalu fallback 'hybrid' — fix baca selagi koneksi
  hidup + 3 pytest regresi tersendiri (`test_receptionist_inout.py`).

---

> Catatan rekonstruksi: entri v2.46.5 turun (historis) disarikan dari
> commit log `git log --grep 'v2.4'` — rincian penuh tiap versi lihat
> `git show <hash>`.

---

## v2.41.0 — In-Out Karyawan (receptionist)

Fitur pencatatan kehadiran in-out karyawan di meja resepsionis:

- Roster karyawan aktif dengan status datang/pergi hari ini,
  pencatatan keluar/masuk sekali klik, rekap harian.
- Sinkronisasi dari data sheet (impor massal) + pencatatan manual
  (hybrid) — mode dibaca dari `system_config`.
- Route: `/inout` (role receptionist/admin) di dashboard resepsionis.
- Test: pytest `test_receptionist_inout.py` (schema, mode, roster,
  stats); vitest `EmployeeInOutView`.
