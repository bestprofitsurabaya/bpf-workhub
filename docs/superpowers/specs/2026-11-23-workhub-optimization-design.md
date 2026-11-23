# Design — Optimasi WorkHub lanjutan (23 November 2026)

## Intent
Setelah rilis v2.131.2, lanjutkan dua jalur: **P2** (kualitas rekayasa: CI, E2E,
ukuran bundle) dan **P3** (kerapian alur harian GA/Finance/Driver). P1 (ODO &
rekonsiliasi data) sengaja ditunda sampai sistem siap. P0 sudah selesai.

## Goals
- Mendeteksi drift skema cabang lebih awal di CI, sebelum deploy.
- Memiliki pengujian E2E untuk alur kritis yang selama ini hanya diuji manual.
- GA bisa memfilter dan memproses banyak catatan service sekaligus.
- Finance mendapat tahu secara realtime saat klaim siap dibayar.
- Driver bisa melihat riwayat feedback km/L tanpa mengirim laporan baru.
- Dokumen resmi service bisa diverifikasi dengan QR; bundle Analytics tidak
  memberati halaman driver.

## Non-goals
- Tidak mengerjakan backfill ODO / rekonsiliasi Subsidi Tepat (P1).
- Tidak mengubah skema `transactions` secara normalisasi besar-besaran.
- Tidak mengganti arsitektur multi-DB cabang.
- Tidak menambah fitur finansial baru di luar notifikasi.

## Constraints
- CI existing: `npm audit`, `pip-audit`, `check_version_stamps.py`,
  `check_branch_db_map.py`, pytest, Trivy. Jangan duplikasi.
- Setiap rilis kode wajib: bump 7 titik stamp + DB, CHANGELOG, PROGRESS,
  commit+push, deploy, uji.
- Perubahan UI harus tetap konsisten dengan pola BBM/Trip/OT (pelajaran dari
  audit tab Service).
- Sesi WhatsApp & ADB sudah ditutup; jangan buka lagi kecuali diminta.

## Approaches yang dipertimbangkan
1. **Stabil dulu** — schema CI + E2E + filter GA + notifikasi Finance saja.
2. **Bertahap lengkap** (dipilih) — Rilis A berisi semua poin di atas kecuali
   QR & bundle splitting; Rilis B menyusul setelah ada pengukuran.
3. **Minimal** — hanya filter GA + notifikasi Finance.

Pilihan: **Opsi 2**. Alasan: P3 dikerjakan hati-hati tanpa menahan P2; QR dan
bundle splitting butuh data pemakaian supaya tidak jadi kerjaan kosmetik.

## Design — Rilis A

### A1. Schema drift check (`scripts/check_schema_drift.py`)
- Parse `CREATE TABLE ... (...)` dari `init.sql`.
- Untuk setiap tabel, ambil daftar kolom dan tipe dasar.
- Hubungkan ke DB master dari env CI (`DB_HOST`, `DB_USER`, `DB_PASSWORD`,
  `DB_NAME=bpf_asset_system`), bandingkan dengan `information_schema.COLUMNS`.
  DB cabang tidak ikut dicek di CI karena tidak tersedia sebagai service.
- Gagal bila ada tabel/kolom yang hilang atau bertipe berbeda.
- Tambah step CI setelah `Run tests` bernama `Check schema drift`.
- Tabel runtime yang dibuat di `appointments_schema.py` tidak ikut dicek bila
  belum ada di `init.sql` (manifest tetap satu sumber).

### A2. E2E Playwright alur kritis
- File `frontend/e2e/critical.spec.ts` dengan tiga skenario:
  1. Driver isi KM manual + 2 keluhan bernomor → kirim → riwayat tampil.
  2. GA buka laporan service → detail → tandai selesai → PDF terunduh.
  3. Finance melihat klaim siap bayar setelah GA approve.
- Script `scripts/ci_e2e.sh`: start Flask dengan env CI, tunggu `/api/health`,
  jalankan `npx playwright test`, matikan server.
- Job CI `e2e` terpisah; seed minimal lewat endpoint/DB uji.
- Tidak menjalankan E2E terhadap produksi.

### A3. Filter & bulk action GA Service
- Backend: `/api/ga/service-reports` menerima `status`, `from`, `to`, `q`.
- Endpoint baru `POST /api/ga/service-reports/bulk-review` dengan
  `{ids:[...], status, ga_note}`; hanya `SUBMITTED` yang boleh diubah.
- Frontend: baris filter atas panel (status, tanggal, cari), checkbox per
  baris, tombol "Tandai selesai (n)" dan "Tolak (n)".
- Tetap satu aksi per baris lewat modal detail. `Tandai selesai` mengubah
  `driver_service_reports.status` menjadi `REVIEWED`; bukan approve klaim.
  Approve klaim tetap lewat `/api/queue/approve-ga/<id>` di Dashboard GA.
- Setiap bulk action dicatat lewat `log_activity_async` ke tabel `activity_logs`
  yang sudah ada (tidak menambah skema).

### A4. Notifikasi Finance realtime
- `modules/realtime.py`: tambah room `finance_board` untuk role
  `finance`/`admin`.
- Saat GA approve klaim (`status -> verified_ga`), emit `new_finance_task`
  ke room tersebut.
- `FinanceDashboard.vue` mengamati event dan memuat ulang kartu antrean.
- Tidak menambah tabel notifikasi baru; cukup event realtime.

### A5. Riwayat feedback driver
- Endpoint `GET /api/driver/feedback-history?nopol=` mengembalikan ringkasan
  per hari dari transaksi sah (5 entri terakhir).
- `BBMTab.vue`: kartu ringkas "Riwayat feedback" di bawah kartu after-submit,
  bisa dibuka/tutup, tidak mengganggu form.

## Design — Rilis B

### B1. QR verifikasi dokumen service
- Tambah dependensi Python `qrcode[pil]` bila belum ada.
- `DriverServicePDF` menyisipkan QR berisi
  `BPF-SERVICE:<display_id>:<sha256(nomor+ Tanggal)>` di halaman pertama.
- Tidak membuat halaman verifikasi publik; QR dipakai GA/Finance untuk
  mencocokkan nomor dokumen secara manual.

### B2. Code-splitting Analytics
- `--vue 5.1.1` dikunci; Analitik memuat library chart secara statis.
- Ubah `AnalyticsView.vue` agar library chart di-`import()` saat `onMounted`.
- Target: chunk `AnalyticsView` turun dari ~216 kB; halaman driver tidak ikut
  memuatnya.

## Risk & mitigasi
- Schema check bisa false-positive karena runtime schema产生 dari
  `appointments_schema.py`. Mitigasi: batasi ke tabel yang memang di-`init.sql`.
- E2E bisa flaky karena GPS/web push. Mitigasi: gunakan data uji & stub,
  jangan bergantung lokasi nyata.
- Bulk action bisa salah klik. Mitigasi: konfirmasi + audit log per aksi.
- Notifikasi Finance bisa dobel. Mitigasi: event hanya dikirim saat transisi
  status, bukan setiap kali halaman dibuka.

## Keputusan builder-check
- Audit log memakai `activity_logs` + `log_activity_async` yang sudah ada.
- Aksi `Tandai selesai` pada laporan service = `status REVIEWED`, terpisah dari
  approve klaim (`verified_ga`) yang tetap lewat antrean GA.
- Schema drift check hanya terhadap DB master di CI (`bpf_asset_system`).
- Format QR: `BPF-SERVICE:<display_id>:<sha256(display_id+tanggal)>`; hash
  memakai tanggal ISO `YYYY-MM-DD`.
- Bulk action dibatasi maksimal 50 ID per permintaan; `ga_note` wajib hanya
  untuk status `REJECTED`.
- Riwayat feedback: 5 entri terakhir dari transaksi `verified_ga`/`archived`
  untuk nopol driver yang bersangkutan.
- Library chart yang dipilih untuk code-splitting: yang sudah dipakai
  `AnalyticsView.vue` (tidak menambah dependency baru).

## Builder check
Desain sudah ditinjau builder. Tidak ada pertanyaan yang harus dikembalikan ke
user; keputusan minor di atas saya tetapkan sebagai call implementasi.
