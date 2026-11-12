# Rancangan: Menyatukan Laporan & Analisis ke Meja Kerja BBM, Kasbon & SPBU

**Tanggal:** 12 November 2026 · **Versi kode acuan:** v2.99.0
**Sifat:** rancangan (belum ada perubahan kode/data)
**Pertanyaan yang dijawab:** bagaimana tiga halaman laporan Finance — *Rekap Klaim BBM*,
*Realisasi Pengeluaran*, *Analisis BBM & Armada* — dilebur ke modul operasional
*BBM, Kasbon & SPBU* tanpa membuat angka saling bertentangan.

---

## 1. Kondisi hari ini

| Halaman | Rute | Sumber data | Aturan hitung | Filter |
|---|---|---|---|---|
| BBM, Kasbon & SPBU | `/cash` | `transactions`, `fuel_cash_requests`, `subsidy_transactions` | status per tab (masuk/siap cair/riwayat) | **tidak ada periode** |
| Rekap Klaim BBM | `/rekap` | `transactions` | **hanya `archived`**, basis `created_at` | rentang tanggal, driver, nopol, jenis |
| Realisasi Pengeluaran | `/expenses` | `transactions`, `fuel_cash_requests`, `purchase_orders` | LPJ = `CASH_LPJ` **non-rejected**; kasbon = **COMPLETED** | tahun + bulan, cabang |
| Analisis BBM & Armada | `/analytics` | `transactions`, `drivers`, `vehicle_assignments`, `fuel_cash_requests` | klaim `archived`; kasbon `COMPLETED` | rentang tanggal |

Empat halaman, empat definisi. Akibatnya untuk **satu pertanyaan yang sama**
(“berapa biaya BBM bulan ini?”) muncul tiga angka berbeda:

1. **Rekap** menghitung klaim `archived` saja → klaim yang sudah dibayar tapi belum
   diarsipkan tidak terlihat.
2. **Realisasi** menghitung LPJ yang masih `pending` (belum diverifikasi GA) sebagai
   “realisasi”, sehingga angkanya bisa lebih besar dari yang benar-benar sah.
3. **Analisis** memakai klaim `archived` + kasbon `COMPLETED` — dua basis waktu
   berbeda (`created_at` vs `handover_at`) dalam satu layar.

Dua celah logika yang ikut ditemukan saat penelusuran:

- **Kasbon yang masih di driver hilang dari laporan.** `fuel_cash_requests` dihitung
  hanya bila `status='COMPLETED'`. Kasbon berstatus `FUNDS_WITH_DRIVER` atau
  `LPJ_SUBMITTED` — justru dana yang perlu ditagih — tidak muncul di “Sisa Kasbon”.
- **LPJ tidak pernah menjadi `archived`.** `approve-lpj` hanya mengubah transaksi LPJ
  ke `verified_ga`. Karena Rekap hanya membaca `archived`, LPJ yang sudah sah tidak
  pernah masuk Rekap, sementara Realisasi sudah menghitungnya sejak `pending`.

## 2. Prinsip rancangan

1. **Satu konteks, satu angka.** Periode + cabang + jenis disimpan sekali (URL +
   store), dipakai semua tab. Tidak ada halaman yang punya filter sendiri-sendiri.
2. **Satu definisi status.** Satu peta status → label → ember (`antre`, `terverifikasi`,
   `dibayar`, `final`, `ditolak`) dipakai backend dan frontend.
3. **Setiap angka bisa diklik.** KPI dan baris rekap membuka daftar transaksi sumber
   dengan filter yang sama — bukan sekadar angka.
4. **Pekerjaan dulu, laporan kemudian.** Yang tampil paling atas adalah yang perlu
   ditindak (antrean + anomali), bukan grafik.
5. **Tidak ada migrasi data di fase awal.** Semua perubahan memakai kolom yang sudah ada.

## 3. Alur input → output (yang harus dipegang semua halaman)

### 3.1 Klaim BBM (driver beli langsung)

```
Driver isi klaim + foto (ODO, nota, struk)      → transactions.transaction_type='CLAIM', status='pending'
GA verifikasi bukti                             → status='verified_ga'
Finance cairkan (step-up PIN)                   → status='os_finance'
Arsip / serah terima dokumen                    → status='archived'   ← FINAL
Ditolak kapan saja                              → status='rejected'
Pencocokan SPBU (advisory, tidak mengubah uang) → subsidy_match / subsidy_tx_id
```

### 3.2 Kasbon → LPJ (uang muka)

```
Driver ajukan kasbon (kode unik harian)   → fuel_cash_requests DRAFT (total = base + kode)
ACC atasan → GA                           → GA_APPROVED
Finance setujui pencairan (step-up)       → FINANCE_APPROVED
GA serahkan dana ke driver                → FUNDS_WITH_DRIVER  (handover_at terisi) ← UANG KELUAR
Driver isi LPJ + foto                     → LPJ_SUBMITTED, transaksi CASH_LPJ 'pending'
GA verifikasi LPJ                         → cash COMPLETED, transaksi 'verified_ga'  ← FINAL (tanpa payout)
GA tolak LPJ                              → kembali FUNDS_WITH_DRIVER, transaksi 'rejected'
```

**Konsekuensi definisi:** karena dana kasbon sudah keluar di `handover_at`, status final
LPJ adalah `verified_ga` — bukan `archived`. Maka “LPJ sah” = `CASH_LPJ` berstatus
`verified_ga`/`archived`, dan `archived` bukan syarat.

### 3.3 Data SPBU (SubsidiTepat)

```
Agen tarik data Pertamina → /api/subsidy/import → subsidy_transactions (master)
Auto-match per klaim      → subsidy_match = match | close | mismatch | no_record
Finance jodohkan manual   → subsidy_tx_id + jejak siapa/kapan
```

Pencocokan **tidak boleh mengubah nominal atau status bayar** — hanya bukti pendukung.

## 4. Definisi resmi metrik (satu sumber kebenaran)

| Metrik | Tabel | Syarat | Basis tanggal |
|---|---|---|---|
| Klaim masuk | transactions | `CLAIM`, status `pending`/`modified` | `created_at` |
| Klaim siap cair | transactions | `CLAIM`, `verified_ga` | `created_at` |
| Klaim dibayar | transactions | `CLAIM`, `os_finance`/`archived` | `created_at` |
| LPJ diajukan | transactions | `CASH_LPJ`, `pending` | `created_at` |
| **LPJ sah (realisasi)** | transactions | `CASH_LPJ`, `verified_ga`/`archived` | `created_at` |
| Kasbon diajukan | fuel_cash_requests | semua kecuali `REJECTED` | `created_at` |
| **Kasbon cair** | fuel_cash_requests | `handover_at IS NOT NULL` | `handover_at` |
| **Dana di driver (outstanding)** | fuel_cash_requests | `handover_at IS NOT NULL` **dan** status `FUNDS_WITH_DRIVER`/`LPJ_SUBMITTED` | `handover_at` |
| Sisa per kasbon | kasbon − LPJ terkait | `total_amount − COALESCE(lpj.nominal,0)` | — |
| Pembelian diterima | purchase_orders + po_receipts | `qty_terima × harga` | `order_date` |
| Selisih SPBU | transactions ↔ subsidy_transactions | `match`/`close`/`mismatch`/`no_record` | `transaction_date` |

Semua halaman memakai tabel ini. “Total realisasi” = **Klaim dibayar + LPJ sah +
Pembelian diterima**; kasbon cair ditampilkan sebagai jembatan, bukan biaya.

## 5. Bentuk baru: satu meja kerja, lima tab

```
/cash?tab=ringkasan|bbm|kasbon|subsidi|laporan
      &view=rekap|realisasi|analisis        (khusus tab laporan)
      &from=2026-11-01&to=2026-11-30&branch=SBY
      &status=verified_ga&driver=&nopol=&q=
```

```
┌──────────────────────────────────────────────────────────────────────┐
│ ⛽ BBM, Kasbon & SPBU            [SBY ▾]  [1–30 Nov 2026 ▾]  [⟳]    │
├──────────────────────────────────────────────────────────────────────┤
│ Ringkasan │ BBM │ Kasbon & LPJ │ SPBU │ Laporan                      │
├──────────────────────────────────────────────────────────────────────┤
│ PERLU TINDAKAN (7)                                                   │
│  ⏳ 3 klaim menunggu GA > 2 hari        Rp 1,2 jt   [Buka]          │
│  🚗 2 kasbon di driver > 14 hari        Rp 2,5 jt   [Tagih]         │
│  🔴 4 klaim mismatch SPBU               Rp 1,8 jt   [Periksa]       │
│  ⚠️ 1 LPJ melebihi kasbon               Rp 150 rb   [Lihat]         │
├──────────────────────────────────────────────────────────────────────┤
│ KPI: Klaim dibayar · LPJ sah · Kasbon cair · Dana di driver          │
├──────────────────────────────────────────────────────────────────────┤
│ (isi tab)                                                            │
└──────────────────────────────────────────────────────────────────────┘
```

Tab **Laporan** memuat tiga sub-tab yang sekarang berdiri sendiri:

- *Rekap Klaim* — tabel klaim dengan kolom status & tautan SPBU.
- *Realisasi* — kartu kasbon cair / LPJ sah / dana di driver / pembelian,
  tabel bulanan, drill-down per baris.
- *Analisis* — tren, frekuensi, efisiensi, fleet health.

Rute lama (`/rekap`, `/expenses`, `/analytics`) tetap hidup sebagai **redirect** yang
membawa query lama (`?start_date=&end_date=` → `from/to`), sehingga tautan/bookmark
tidak putus.

### 5.1 Konteks bersama

- `WorkspaceContextBar` (sticky): cabang (sesuai role), periode (preset 7/30/bulan
  ini/YTD/kustom), jenis (Semua / Klaim BBM / LPJ Kasbon), kotak cari.
- Store Pinia `useBbmWorkspace` menyinkronkan state ↔ query URL (mengganti `window.location`).
- Badge tab memakai `/api/nav/badges` yang sudah ada; badge **dihitung dalam periode**
  agar konsisten dengan isi tab.

### 5.1a Isolasi cabang (aturan keras)

Setiap Finance **milik satu cabang**. Yang boleh melihat lebih dari satu cabang
hanya Admin Pusat dan Finance HO (`finance_hu`, dapat ditambah via env
`FINANCE_HO_USERNAMES`). Aturan ini berlaku di semua tab dan endpoint:

| Sesi | Cakupan | `?branch=ALL` | Cabang lain | Tanpa parameter |
|---|---|---|---|---|
| Finance cabang | cabangnya | 403 | 403 | cabang sendiri (bukan SBY) |
| Finance HO | semua | boleh | boleh | ALL |
| Admin Pusat | semua | boleh | boleh | ALL |
| Admin cabang | suffix + `managed_branches` | 403 | 403 | cabang sesi |
| Sesi tanpa cabang | — | 403 | 403 | 403 (fail-closed) |

Bukan hanya angkanya yang dibatasi: daftar cabang yang dikirim ke pemilih juga
dipersempit, sehingga UI tidak menawarkan cabang yang tidak boleh dibuka.
Logika dipusatkan di `modules/branch_scope.py` dan dipakai endpoint laporan
apa pun yang membaca lebih dari satu DB cabang. Endpoint yang memakai
`get_db_connection()` sudah ter-scope otomatis oleh DB sesi.

### 5.2 Angka → baris → aksi

Setiap KPI/baris rekap adalah tautan ke tabel operasional:

| Klik | Membuka |
|---|---|
| Klaim dibayar Rp … | tab BBM, filter `status=os_finance,archived` |
| LPJ sah Rp … | tab BBM, `type=CASH_LPJ&status=verified_ga` |
| Dana di driver Rp … | tab Kasbon, `status=FUNDS_WITH_DRIVER,LPJ_SUBMITTED` |
| mismatch SPBU | tab SPBU, `match=mismatch` |
| satu kasbon | detail kasbon + LPJ terkait + tombol aksi yang sah untuk role |

Tombol aksi (cairkan, approve LPJ, jodohkan SPBU) tetap memakai endpoint dan
step-up yang sudah ada — tidak ada jalur uang baru.

## 6. Perubahan backend

1. **`modules/bbm_scope.py`** (baru): satu pembangun klausa `WHERE` + basis tanggal
   untuk seluruh metrik §4, dipakai `/api/transactions/archive`, `/api/expenses/*`,
   `/api/analytics/data`, `/api/vehicle-health`, dan endpoint baru.
2. **`GET /api/bbm/workspace/summary`** (baru): mengembalikan KPI, seri harian/bulanan,
   antrean, ember rekonsiliasi, dan `meta` (periode, cabang, basis, `generated_at`,
   `basis_version`). Semua angka di UI berasal dari sini atau dari daftar yang
   memakai scope yang sama.
3. **Perbaikan definisi** (wajib, kecil, tanpa migrasi):
   - kasbon cair: `handover_at IS NOT NULL` (bukan hanya `COMPLETED`);
   - LPJ sah: `verified_ga`/`archived` (bukan `<> 'rejected'`);
   - tambah metrik `outstanding` per kasbon.
4. **Ekspor** CSV/PDF memakai `meta` yang sama sehingga kop laporan menyebut
   periode, cabang, basis, dan waktu dibuat.
5. **Tes kontrak** (`tests/test_bbm_scope_contract.py`): untuk rentang & cabang yang
   sama, total Rekap = total LPJ sah + klaim dibayar; total Realisasi = metrik yang
   sama; `outstanding` + LPJ sah = kasbon cair. Tes ini yang mencegah angka kembali
   menyimpang di kemudian hari.

## 7. Urutan pengerjaan

| Fase | Isi | Dampak data | Perkiraan |
|---|---|---|---|
| 0 | Dokumen ini + kesepakatan definisi §4 | — | sekarang |
| 1 | Shell workspace + 3 laporan jadi sub-tab + redirect rute lama — **selesai v2.100.0**; context bar bersama menyusul di Fase 2 | tidak ada | 1–2 hari |
| 2 | `bbm_scope.py` + `/api/bbm/workspace/summary` + perbaikan definisi + tes kontrak — **selesai v2.100.1/v2.101.0** (Rekap, Realisasi, Analisis, dan PDF satu definisi); context bar periode bersama selesai v2.102.0 | tidak ada | 2–3 hari |
| 3 | Antrean “Perlu Tindakan” + kartu Dana di Driver → tab Kasbon — **selesai v2.103.0**; KPI lain dan aksi langsung dari baris menyusul | tidak ada | 2–3 hari |
| 4 | Pensiunkan endpoint/duplikasi lama, rapikan PDF & CSV | tidak ada | 1 hari |

Fase 1 bisa dirilis sendiri: pengguna langsung mendapat satu tempat kerja, meski
angka masih memakai definisi lama. Fase 2 yang menyamakan angkanya.

## 8. Keputusan yang perlu diambil pemilik proses

1. **Basis tanggal LPJ:** sudah diputuskan — `created_at` + status sah
   (`verified_ga`/`archived`), agar periode mengikuti kejadian, bukan waktu
   verifikasi (v2.100.1).
2. **Kasbon cair vs kasbon selesai:** sudah diputuskan — ditampilkan terpisah,
   plus kartu “Dana di Driver” (v2.100.1), karena uang yang masih di driver
   adalah risiko yang harus terlihat.
3. **Ambang “perlu tindakan”:** klaim > 2 hari, kasbon di driver > 14 hari,
   LPJ > 7 hari — apakah angka ini sesuai SOP?
4. **Cabang untuk laporan lintas cabang:** sudah diputuskan — hanya Admin
   Pusat dan Finance HO (`finance_hu`) yang boleh memilih `ALL`/cabang lain;
   Finance cabang terkunci ke cabangnya (v2.99.1). Bila nanti ada role
   `finance_hu` resmi, cukup daftarkan username-nya.

## 9. Risiko

- **Beban query.** Summary lintas kategori menambah query; dibatasi periode default
  30 hari dan index `(status, created_at)` sudah ada.
- **Perubahan angka yang terlihat.** Setelah definisi disamakan, “Sisa Kasbon”
  akan naik (kasbon di driver kini terhitung). Ini benar, tetapi perlu penjelasan
  satu kali di UI (“sejak v…, dana di driver ikut dihitung”).
- **Kebiasaan pengguna.** Redirect + label yang sama dengan halaman lama menjaga
  orientasi; jangan mengganti nama menu “Laporan & Analisis” sekaligus.
