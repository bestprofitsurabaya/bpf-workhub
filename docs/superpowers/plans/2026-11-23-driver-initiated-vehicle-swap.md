# Driver Mengajukan Ganti Kendaraan — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Driver dapat mengajukan tukar kendaraan (dua arah) atau pindah ke kendaraan kosong dari panel Profil; GA menyetujui; kedua pihak menyelesaikan serah terima dengan odometer + foto.

**Architecture:** Satu tabel antrean `assignment_swap_requests` + log eksekusi `assignment_swaps` yang diberi `request_id`. Logika keputusan murni (validasi, rencana tukar/pindah, kelengkapan bukti) dipisah ke `modules/assignment_swap_service.py` agar bisa diuji tanpa DB; endpoint di `modules/routes_api_assignments.py` menjadi lapisan tipis HTTP + transaksi. UI: panel `DriverProfileSheet.vue` dari header driver dan tab pengajuan di `AssignmentsView.vue`.

**Tech Stack:** Python 3 / Flask / MariaDB 10.11 / mysql-connector, Vue 3 `<script setup>` / Pinia / Vitest, pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-11-23-driver-initiated-vehicle-swap-design.md`

## Global Constraints

- Versi rilis: `v2.132.0`; satu commit rilis di akhir (konvensi repo: stamp + CHANGELOG + PROGRESS + tes + `scripts/overall_check.sh` sebelum commit/push).
- Tanpa dependency baru. Tanpa perubahan `.env`. Tanpa migrasi data.
- Semua teks UI baru berbahasa Indonesia, mengikuti gaya yang ada.
- Skema harus aditif dan idempoten: `init.sql` + `ensure_assignment_tables()` untuk master dan setiap cabang.
- Identitas driver selalu dari sesi (`resolve_driver_scope('')`); body tidak dipercaya.
- Approve/reject hanya role `ga`/`admin`; finance hanya baca.
- Serah terima wajib `odometer` (0–2.000.000) + foto; tidak ada jalur konfirmasi tanpa bukti untuk assignment hasil pengajuan.
- `check_schema_drift.py` harus hijau untuk master + 11 cabang setelah rilis.

## Review Focus

- Driver tanpa assignment aktif membuka panel profil → empty state yang jelas, bukan error 500 atau daftar kosong tanpa penjelasan.
- Cabang tanpa baris `vehicles` (mis. MALANG saat ini) → daftar kendaraan kosong kosong, tidak error.
- Dua klik Setujui beruntun / dua approver bersamaan → tepat satu pertukaran, tidak ada assignment ganda.
- Unggah bukti tanpa foto, ekstensi berbahaya, atau >16 MB → 400/413 tanpa baris DB setengah jadi.
- Pengajuan `superseded` setelah koreksi GA → driver tetap bisa konfirmasi assignment berikutnya (tidak terkunci).

---

### Task 1: Skema + ensure idempoten

**Files:**
- Modify: `init.sql` (tabel `assignment_swap_requests`, kolom `assignment_swaps.request_id`)
- Modify: `modules/routes_api_assignments.py` (`ensure_assignment_tables`)
- Test: `tests/test_swap_requests_v2132.py`

**Interfaces:**
- Produces: tabel `assignment_swap_requests` dengan kolom sesuai spec §8.1; `assignment_swaps.request_id INT NULL`.
- Produces: `ensure_assignment_tables(conn=None) -> bool` tetap nama & kontraknya (tidak menutup conn milik pemanggil).

- [x] **Step 1: Tulis tes gagal** — `test_ensure_membuat_dua_tabel`, `test_ensure_menambah_request_id_bila_belum_ada`, `test_ensure_tidak_menutup_conn_luar`.
- [x] **Step 2: Jalankan** `python3 -m pytest tests/test_swap_requests_v2132.py -q` → FAIL (tabel/kolom belum ada).
- [x] **Step 3: Implementasi** — tambah DDL ke `init.sql`; di `ensure_assignment_tables` buat `assignment_swap_requests` dan cek `information_schema.COLUMNS` untuk `assignment_swaps.request_id`, `ALTER TABLE ... ADD COLUMN` bila belum ada.
- [x] **Step 4: Jalankan tes** → PASS; jalankan `python3 -m pytest tests/test_assignment_swap_v273.py tests/test_init_sql.py -q` → PASS.

### Task 2: Logika murni (validasi, rencana, bukti)

**Files:**
- Create: `modules/assignment_swap_service.py`
- Test: `tests/test_swap_service_v2132.py`

**Interfaces:**
- `class SwapError(Exception)` dengan `.http_status`, `.code`, `.msg`, `.extra`.
- `clean_reason(value) -> str` (strip; 10–500, selain itu `SwapError(400,'reason')`).
- `validate_category(value) -> str` (`driver_request|vehicle_issue|mutasi|other`).
- `normalize_swap_type(value) -> str` (`exchange|move`).
- `validate_odometer(value) -> int` (0–2.000.000).
- `request_code(request_id: int, day: date|None=None) -> str` → `SWR-YYYYMMDD-0007`.
- `handover_complete(swap_type, requester_at, target_at) -> bool` (`move`: requester saja).
- `handover_side(req, driver_name) -> 'requester'|'target'|None`.
- `received_nopol(req, side) -> str`.
- `build_approve_plan(req, assignments, vehicle=None) -> dict`:
  `{close_ids, new_assignments, driver_updates, swap_logs}`; raises `SwapError(409,'state_changed')` bila assignment tidak cocok.
- `supersede_conflicts(rows, req) -> list[int]` (pengajuan approved lain yang belum lengkap).

- [x] **Step 1: Tulis tes gagal** untuk setiap fungsi; nilai batas: alasan 9/10/500/501, odo -1/0/2.000.000/2.000.001, exchange vs move, `build_approve_plan` exchange (A-X, B-Y) dan move (A-X, Y kosong), mismatch → `SwapError`.
- [x] **Step 2: Jalankan** `python3 -m pytest tests/test_swap_service_v2132.py -q` → FAIL (modul belum ada).
- [x] **Step 3: Implementasi** fungsi murni; tanpa query DB.
- [x] **Step 4: Jalankan** → PASS.

### Task 3: Konteks, buat, daftar, batal

**Files:**
- Modify: `modules/assignment_swap_service.py`
- Modify: `modules/routes_api_assignments.py`
- Test: `tests/test_swap_requests_v2132.py`

**Interfaces:**
- `active_driver_accounts(conn, names, branch_code, master_conn=None) -> set[str]`.
- `fetch_context(conn, driver_name, branch_code, master_conn=None) -> dict` → `{me, free_vehicles, partners, requests}`.
- `create_request(...) -> dict` (row hasil INSERT + `request_code`).
- `list_requests(conn, driver_name=None, status=None) -> list[dict]`.
- `cancel_request(conn, request_id, driver_name) -> dict`.
- Routes: `GET /api/assignments/swap-context`, `POST /api/assignments/swap-requests`, `GET /api/assignments/swap-requests`, `POST /api/assignments/swap-requests/<id>/cancel`.

- [x] **Step 1: Tulis tes gagal** — context driver tanpa assignment (200, `me=None`), move sukses, exchange sukses, move ke nopol terisi → 409, target tanpa akun → 409, alasan pendek → 400, duplikat pending → 409, cancel milik sendiri/pengaju lain.
- [x] **Step 2: Jalankan** → FAIL.
- [x] **Step 3: Implementasi** service + route; identitas dari `resolve_driver_scope`; `branch_code=session.get('branch_code')`; transaksi + commit; `request_code` diisi setelah INSERT.
- [x] **Step 4: Jalankan** → PASS; regresi `tests/test_assignment_swap_v273.py`.

### Task 4: Approve, reject, supersede, invarian, kunci alur lama

**Files:**
- Modify: `modules/assignment_swap_service.py`
- Modify: `modules/routes_api_assignments.py` (`create`, `swap`, `release`, `confirm`)
- Test: `tests/test_swap_requests_v2132.py`

**Interfaces:**
- `approve_request(conn, request_id, ga_name, acknowledge_supersede=False, master_conn=None) -> dict`.
- `reject_request(conn, request_id, ga_name, note) -> dict`.
- `supersede_requests_for(cur, drivers, nopols, note) -> int`.
- `assert_single_active(cur, drivers, nopols) -> None`.
- Routes: `POST .../approve`, `POST .../reject`.
- Existing `create/swap/release` dibungkus transaksi + `FOR UPDATE` + supersede + invariant.

- [x] **Step 1: Tulis tes gagal** — exchange sukses (2 assignment, 2 log, cache 3 kolom), move sukses (1 assignment, X tanpa assignment, 2 log pool), bukan pending → 409, state berubah → 409, finance → 403, konflik tanpa ack → 409 `supersede_required`, dengan ack → lama `superseded`, reject tanpa catatan → 400.
- [x] **Step 2: Jalankan** → FAIL.
- [x] **Step 3: Implementasi** transaksi `start_transaction` → lock → plan → tulis → supersede → invariant → commit/rollback.
- [x] **Step 4: Jalankan** → PASS; regresi seluruh `tests/test_assignment_swap_v273.py`.

### Task 5: Serah terima + guard konfirmasi

**Files:**
- Modify: `modules/assignment_swap_service.py`
- Modify: `modules/routes_api_assignments.py` (`handover`, `pending`, `confirm`)
- Test: `tests/test_swap_requests_v2132.py`

**Interfaces:**
- `submit_handover(conn, request_id, driver_name, odometer, photo) -> dict`.
- Route: `POST /api/assignments/swap-requests/<id>/handover` (multipart, `save_file(...,'SWAP', nopol, UPLOAD_FOLDER)`).
- `pending` menambah `handover_request_id`; `confirm` menolak 409 `handover_required` hanya bila nopol cocok.

- [x] **Step 1: Tulis tes gagal** — exchange A lalu B → `completed`; move satu bukti → `completed`; kirim ganda → 409; driver lain → 403; assignment berubah → 409 + `superseded`; tanpa foto/odo invalid → 400; pending join; confirm guard cocok vs superseded.
- [x] **Step 2: Jalankan** → FAIL.
- [x] **Step 3: Implementasi** upload + service + join guard; hapus file best-effort bila service gagal.
- [x] **Step 4: Jalankan** → PASS.

### Task 6: Panel Profil driver

**Files:**
- Create: `frontend/src/components/DriverProfileSheet.vue`
- Modify: `frontend/src/views/driver/DriverView.vue`
- Test: `frontend/src/components/DriverProfileSheet.test.js`
- Test: `frontend/src/views/driver/DriverView.test.js`

**Interfaces:**
- `DriverProfileSheet` props `modelValue: Boolean`; emits `update:modelValue`, `changed`.
- Memakai `GET /api/assignments/swap-context`, `POST /api/assignments/swap-requests`, `.../cancel`, `.../handover`.
- DriverView: blok identitas header jadi tombol pembuka; banner `handover_request_id` membuka panel.

- [x] **Step 1: Tulis tes gagal** — panel terbuka dari header; daftar kosong vs berisi; tombol Ambil mengirim `move`, Tukar `exchange`; alasan <10 mengunci; FormData handover berisi odometer+photo.
- [x] **Step 2: Jalankan** `cd frontend && npx vitest run src/components/DriverProfileSheet.test.js src/views/driver/DriverView.test.js` → FAIL.
- [x] **Step 3: Implementasi** komponen + integrasi header/banner; jangan menambah item navigasi.
- [x] **Step 4: Jalankan** → PASS; `npx vitest run` penuh.

### Task 7: Tab pengajuan GA

**Files:**
- Modify: `frontend/src/views/AssignmentsView.vue`
- Test: `frontend/src/views/AssignmentsView.test.js`

**Interfaces:**
- Tab `pengajuan`; badge jumlah `pending`; approve dengan `acknowledge_supersede` saat konflik; reject wajib catatan; polling 60 detik berhenti saat unmount.

- [x] **Step 1: Tulis tes gagal** — tab tampil, badge, approve/reject endpoint, checkbox supersede, foto tampil sebagai tautan.
- [x] **Step 2: Jalankan** → FAIL.
- [x] **Step 3: Implementasi** UI + state.
- [x] **Step 4: Jalankan** → PASS.

### Task 8: Rilis v2.132.0

**Files:**
- Modify: `CHANGELOG.md`, `docs/internal/PROGRESS.md`, `docs/internal/USER_LIST.md`, `guides/USER_GUIDE.md`, `frontend/src/content/help.js`, semua file stamp versi.
- Modify: dokumen desain (status → disetujui) dan plan ini (checklist).

- [x] **Step 1: Bump** versi ke `v2.132.0` di semua titik stamp (7 file) + `modules/version.py` bila ada.
- [x] **Step 2: Dokumentasi** — CHANGELOG entri v2.132.0; PROGRESS header; USER_GUIDE bagian "Ganti kendaraan dari profil"; help.js langkah driver.
- [x] **Step 3: Tes** — `python3 -m pytest -q`, `cd frontend && npx vitest run`, lalu `bash scripts/overall_check.sh`.
- [x] **Step 4: Stamp DB** — `docker exec -w /app bpf-workhub-web python3 scripts/sync_version_stamp.py && ... check_version_stamps.py --with-db`; drift check master + cabang.
- [x] **Step 5: Build & smoke** — `docker compose build web && docker compose up -d web`; health `ok`; smoke buat pengajuan move lalu cancel (tanpa approve di produksi).
- [x] **Step 6: Commit & push** satu commit rilis; verifikasi `HEAD == origin/main` dan working tree bersih.

## Self-Review

- Spec coverage: skema (T1), validasi & rencana (T2), create/context/list/cancel (T3), approve/reject/supersede/invarian (T4), bukti & guard (T5), UI driver (T6), UI GA (T7), rilis (T8). Non-goals tidak diimplementasikan.
- Review Focus terpetakan: empty state (T3/T6), cabang tanpa vehicles (T2/T3), double approve (T4), upload invalid (T5), superseded tidak mengunci (T5).
- Nama interface konsisten: `build_approve_plan`, `approve_request`, `submit_handover`, `handover_complete`, `handover_side`, `handover_request_id`.
- Penyimpangan sadar: commit per task diganti satu commit rilis agar stamp/versi konsisten dengan konvensi repo.
