# 🔎 Audit Keselarasan & Fungsi UI Role Finance — 28 Oktober 2026 (v2.75.0)

> Pertanyaan audit: *"pastikan backend dan frontend finance berfungsi
> optimal"*. Metodologi: (1) inventaris semua halaman SPA yang terbuka
> untuk role `finance` + item sidebar; (2) cross-check statis panggilan
> `api()` tiap view ↔ rute backend ↔ `@role_required`; (3) verifikasi
> fungsi **live ke DB real cabang** via smoke `scripts/smoke_finance_ui.py`
> (37 uji, tanpa mutasi data uang nyata).

## 1. Permukaan UI finance (inventory)

Router `frontend/src/router/index.js` — halaman dengan `finance` di
`meta.roles`, plus item sidebar `AppLayout.vue`:

| Halaman | View | Item sidebar | Endpoint FE → BE |
|---|---|---|---|
| `/dashboard` | AdminDashboard | **Antrean Verifikasi** (badge `bbm_verify_pending`) | stats, nav/badges, queue, subsidy match/link/unlink/attest, transactions/detail, cross-check, finance-review, finance-remark, transaction-flags, queue reject/modify/payout/archive, branches/stats |
| `/finance` | FinanceDashboard | **Dashboard Finance** (badge `finance_pending`) | queue, subsidy status/otp status/otp request/otp submit/auto-match/link/unlink/attest, water/recap, payout/archive |
| `/trips` | TripsView | Log Perjalanan | trips, trip-detail/:id |
| `/rekap` | RekapView | Rekap | transactions/archive |
| `/cash` | CashView | Kasbon / BBM (badge) | cash history, daily-code GET+POST, pending-lpj, detail/:id |
| `/analytics` | AnalyticsView | Analytics | vehicle-health, analytics/data |
| `/approvals` | ApprovalsView | — (disengaja, wave-18A) | approvals |
| `/water` | WaterView | Air Minum (badge) | water brands GET/POST/DELETE, edit-enabled, purchases GET/PUT/DELETE |
| `/procurement` | ProcurementView | Pengadaan | procurement orders GET/POST, suppliers GET/POST/PUT/DELETE |
| `/expenses` | ExpensesView | Rekap Pengeluaran | expenses/recap |
| `/home` | HomeView | (beranda semua role) | — |

## 2. Hasil cross-check statis FE↔BE

Semua endpoint yang dipanggil halaman finance **ditemukan** di backend
(modul yang menyimpannya: routes_spa, routes_subsidy, routes_cash,
routes_water, routes_procurement, routes_expense, routes_api_transactions,
routes_api_master, routes_nav). Dua "kandidat putus" dari scan otomatis
ternyata **false positive**:

1. `POST /api/subsidy/otp/request` & `auto-match` initial terdeteksi
   "tanpa guard" — keduanya guard manual di dalam body (finance/admin
   via sesi ATAU agen dengan header `X-SUBSIDY-TOKEN`), sesuai desain
   cron/agen. ✔
2. `GET /api/water/edit-enabled` terdeteksi admin-only — salah jendela
   regex (PUT admin-only di baris yang sama). GET memakai
   `WATER_ROLES = ['ob','finance','admin']`. ✔

Keselarasan **write-guard** (finance):

| Aksi (FE) | Endpoint | BE guard | Step-up | Konsisten? |
|---|---|---|---|---|
 Cairkan klaim | `POST /api/queue/payout/:id` | finance,admin | ✅ `stepup_required` | ✔ (FE `stepup.require` di kedua dashboard) |
 Arsipkan klaim | `POST /api/queue/archive/:id` | finance,admin | — (risiko rendah, sudah dibayar) | ✔ |
 ACC finance kasbon | `POST /api/cash/approve-finance/:id` | finance,admin | ✅ | ✔ |
 Verifikasi air minum | `POST /api/water/purchases/:id/verify` | WATER_FINANCE_ROLES | ✅ | ✔ |
 Edit/hapus air minum | `PUT/DELETE /api/water/purchases/:id` | WATER_FINANCE_ROLES | ✅ | ✔ |
 Kelola merk & supplier | water/brands, procurement/suppliers POST/PUT/DELETE | finance,admin | — | ✔ |
 Kode harian | `POST /api/cash/daily-code` | finance,admin (guard manual) | — | ✔ |
 Subsidi Tepat link/unlink/attest/otp | POST routes_subsidy | finance,admin | — | ✔ |
 Setujui/Edit/Tolak klaim (GA) | queue approve-ga/reject/modify/unverify | ga,admin | (varies) | ✔ — FE `canApprove = ['ga','admin']` menyembunyikan tombolnya dari finance; BE menolak 403 (dua lapis; diverifikasi smoke) |

## 3. Temuan & tindakan

| # | Severity | Temuan | Tindakan |
|---|---|---|---|
| 1 | LOW | **`GET /api/cash/daily-code` tanpa sesi** — bisa dipanggil anonim; baca mode manual (`cash_code_manual`) + tulis DB `get_or_create` kode harian | ✅ FIXED v2.75.0 — wajib sesi (driver maupun back-office); POST sudah lama finance/admin saja. Test: `tests/test_finance_ui_audit_v275.py` (3 kasus) |
| 2 | Catatan | **ACC Atasan disembunyikan dari sidebar finance** (wave-18A) padahal router & `/api/approvals*` mengizinkan finance | Syarat desain dipertahankan (tata-tampil, bukan keamanan); finance membuka URL langsung tetap dibaca modul. Tidak diubah |
| 3 | Catatan | **`/api/branches/stats` admin-only** tapi dipanggil AdminDashboard yang juga finance buka | FE sudah menangkap dengan `.catch` → kolom cabang kosong, tanpa error yang terlihat. Diterima sebagai desain (data cabang digunakan admin; finance dibiarkan). Tidak diubah |

## 4. Verifikasi fungsi live (smoke 37/37 lulus)

`scripts/smoke_finance_ui.py` di container (session finance, DB real SBY):

- **Read-walk 25 endpoint** — semua 200 (`stats`, `nav/badges`, `queue`,
  `subsidy/*`, `transactions/archive`, `trips`, `cash/history`,
  `cash/daily-code`, `water/*`, `procurement/*`, `vehicle-health`,
  `analytics/data`, `approvals`, `expenses/recap`) + 3 GET dengan id uji
  (200/404 sah).
- **Write-guard negatif** (tanpa mutasi):
  - `queue/payout`, `cash/approve-finance`, `water verify` → **428**
    `STEPUP_REQUIRED` (guard bekerja sebelum body);
  - `queue/reject` & `queue/modify` oleh finance → **403** (memang GA);
  - `water brands delete` & `payout` oleh OB → **403**;
  - `queue/archive` id uji → 409 tanpa efek.
- **Siklus tulis bersih**: merk air minum `UJIFIN-<run>` dibuat finance →
  dinonaktifkan kembali (list bersih, tidak ada UJIFIN- tersisa) —
  membuktikan alur tulis finance betul-betul hidup end-to-end.

## 5. Kesimpulan

Backend & frontend finance **berfungsi optimal & selaras**. Satu celah
kecil ditemukan & ditutup (daily-code tanpa sesi), sisanya catatan desain.
Smoke baru masuk ke perpustakaan smoke (dipanggil manual seperti
smoke_procurement; overall_check tidak diubah untuk menjaga durasinya).
