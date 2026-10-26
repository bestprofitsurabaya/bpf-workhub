# Audit Fitur Terbenam — Backend yang Tidak Dimunculkan / Tidak Terdokumentasi
Tanggal: 2026-10-26 · Basis: v2.72.0 (commit `0dc7097`)

Metode: inventaris 253 route server (`@*.route`) × pemanggil di frontend src/SPA
dist/static, mobile, lalu grep manual per kandidat (dengan alias underscore/hyphen)
+ cekspa dokumentasi `guides/USER_GUIDE.md` (17 entri keyword).

## A. API SERVE tapi tidak pernah dipanggil klien mana pun

| # | Endpoint | Modul | Apa fungsinya | Hukum: useful? | Saran |
|---|---|---|---|---|---|
| 1 | `POST /api/assignments/swap` | routes_api_assignments | **Tukar pengemudi per kendaraan** (tercatat ke tabel `assignment_swaps`: kategori, alasan, nama GA) | ⭐⭐⭐ Berguna — prosedur ganti driver sekarang jalan manual di luar sistem | Hidupkan UI: tombol "Tukar Driver" di AssignmentsView + form kategori/alasan |
| 2 | `GET /api/assignments/swap-history` | routes_api_assignments | Riwayat swap 100 terakhir | ⭐⭐⭐ Pasangan #1 | Tampilkan tab Riwayat di AssignmentsView |
| 3 | `GET /api/assignments/pending` | routes_api_assignments | Assignment yang **belum dikonfirmasi driver** (`confirmed_by_driver=0`) | ⭐⭐⭐ Menutup lingkar: GA tahu siapa yang belum pegang kiriman tugas | Badge di AssignmentsView + tombol mirror |
| 4 | `POST /api/assignments/confirm` | routes_api_assignments | Driver menyetujui assignment — tanpa ini kolom konfirmasi yang di DB tak pernah bisa isi=1 dari UI | ⭐⭐⭐ driver perlu tombol "Konfirmasi Tugas" di DriverView | Sambungkan driver SPA |
| 5 | `POST /api/assignment-remark` | routes_api_assignments | Catatan GA untuk penugasan (driver_notes) — PDF cross-check membacanya! | ⭐⭐ Form kecil di AssignmentsView — terbantu PDF laporan kit |
| 6 | `GET /api/get-performance/<plat>` | routes_api_transactions | Laporan performa per-plate (GA/Finance/Admin) | ⭐ AnalyticsView memakai jalur lain | Simpan sebagai legacy; dokumentasikan sebagai API data bila mau dipakai |
| 7 | `GET /api/receptionist/employees` (v2.42.0) | routes_receptionist | **Roster karyawan** untuk input keluar-masuk | ⭐⭐ EmployeeInOutView perlu daftar karyawan yang benar | Expose dropdown/list di pager InOut |
| 8 | `GET /api/teams`, `POST /api/teams/sync` | routes_appointments | **Tim Marketing** (member dari marketing_members; admin re-sync sheet) | ⭐⭐ Berguna ketika appointment membuat tim marketing formal | Expose filter/label dropdown Marketing + tombol Sync di admin |
| 9 | `GET /api/dummy-data/status` + `POST /api/dummy-data/toggle` | routes_api_master | Mode data dummy (is_dummy) untuk demo — badge v2.56 sengaja exclude dummy | ⭐ Kegunaan ops saja | Dokumentasikan sebagai API ops (tombol UI sengaja tidak pernah ada) |
| 10 | `POST /api/subsidy/import` | routes_subsidy | Upsert riwayat SPBU dari **agen sinkron harian** (dipakai `agent/subsiditepat/daily_sync.sh` + `push.mjs` — jadi BUKAN dead kode) | ⭐ OK — sudah terdokumen di `docs/DEVELOPER.md` | Tambah catatan singkat di USER_GUIDE (opsional) |

⚠️ Catatan penting: `/api/expenses/recap`, `/api/admin/documents`, `/api/system-config/*`,
`/api/assets/report` keliru ter-flag oleh skrip pertama — semuanya riil dipakai
(ExpensesView & Pengaturan). Skrip matcher diperbaiki memakai normalisasi
template-literal & uji grep per kandidat.

## B. Endpoint LEGACY (tertinggi: cleanup ringan di wave nyaring)

| Endpoint | Penggantinya | Aksi |
|---|---|---|
| `POST /api/verify-pin` | `/api/step-up` (v2.47) | Usul hapus (no-caller), atau beri Deprecation header |
| `GET /api/vehicle_bbm/<t>` | `/api/vehicle-allowed-bbm/<t>` (masih dipakai FE) | Usul hapus duplikat |

## C. Dokumentasi PUTRA yang hilang di USER_GUIDE — ✅ DITAMBAHKAN sesi ini

1. **5.7 Pengadaan Belanja (PO)** (v2.70.0) — supplier, PO rinci, penerimaan bertahap open→partial→closed, pembatalan wajib step-up.
2. **6.8 Rekap Pengeluaran** (v2.71.0) — apa yang dihitung (PO diterima + kasbon COMPLETED), apa yang tidak (air minum & overtime — tanpa kolom nominal).
3. **6.9 Subsidi Tepat (MyPertamina)** — agen sinkron harian, login OTP Finance, match klaim↔SPBU, seksi rekonsiliasi di PDF laporan.
4. **14.11 Transcoder Media** (v2.46.0) — yt-dlp + ffmpeg, format 720p/1080p, fase job.

Prioritas berikutnya dari daftar A: **#1–#5 (proyek: fitur Assignment yang selesai
setengah via UI)** — satu wave kecil "Assignment Konfirmasi & Swap" cukup untuk
menghidupkan semua ini, memakai konvensi yang sama (role gate, audit log, smoke).
