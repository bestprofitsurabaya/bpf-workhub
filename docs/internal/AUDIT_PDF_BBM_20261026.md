# Audit PDF Generator — Sisi Transaksi BBM
Tanggal: 2026-10-26 · Basis: v2.71.0 (commit `be34337`, branch `main`)
Target: `modules/pdf_generator.py`, `modules/routes_reports.py`, `modules/engine.py`

## 1. Siapa yang menyentuh transaksi BBM (VERIFIED)

| Kelas / Fungsi | Penggunaan | Menyentuh BBM? |
|---|---|---|
| `PDFReportCompact.generate_compact_report` (pdf_generator.py:393) | `routes_reports.py` → `GET /admin/report/<tx_id>` | **Ya — per-transaksi** |
| `BBMReportPDF.generate_table` (pdf_generator.py:949) | `routes_reports.py` → `GET /admin/rekap/pdf` | **Ya — rekap bulk** |
| `WaterReceiptPDF`, `BranchSummaryPDF`, `ApplicantReportPDF`, `InOutReportPDF`, `AssetReportPDF`, `ConsolidatedReportPDF`, `OvertimeReportPDF`, `OvertimeDetailReportPDF` | route lain | Tidak (scope lain) |

Jadi jawaban pertanyaan user: **ya, ada dua PDF yang menyentuh transaksi BBM** — laporan per-transaksi dan rekap dana BBM.

## 2. Hal yang sudah BENAR (dibaca + diuji)

1. **Urutan aman `is_reported`** (`routes_reports.py:26-33`): PDF dirender dulu → baru
   `UPDATE transactions SET is_reported=TRUE`. Bila render gagal → HTTP 500 → tidak menandai. ✅
2. **Isi laporan per-transaksi lengkap**: info grid (nopol, driver, BBM, SPBU, nominal, liter,
   harga/L, ODO, KM/L, appointment, GPS), narasi kronologis, approval bar
   (GA/Finance/TTD/Archive), grid foto bukti, dan footer stamp identitas
   (`system_name` + `system_version` dari `system_config` → v2.71.0). ✅
3. **Rekap BBM** (`BBMReportPDF`, landscape): kolom NO/TANGGAL/NOPOL/DRIVER/AMOUNT/LITER/
   KM-ODO/KM-L/TIPE/HEALTH; filter driver & nopol (`LIKE` %..%) dan periode di `get_rekap_data`. ✅
4. **Rekonsiliasi Subsidi Tepat** dibaca live dari DB master saat PDF dibuat - hasil
   dokumen Finance selalu data MyPertamina terkini; fallback aman bila master offline. ✅
5. **Test PDF**: `tests/test_pdf_compact.py` + `tests/test_pdf_header_layout.py` →
   **4 passed** (dijalankan lokal dengan font direstore dari git index). ✅

## 3. Temuan (bug / anomali)

### A. Emoji 💰 ikut lenyap di rekap — kolom TIPE hambar  *(kosmetik, terkonfirmasi)*
`BBMReportPDF.generate_table` menulis `'💰 Kasbon'` untuk `CASH_LPJ`, tapi
`_table_row → clean_text` membuang SEMUA karakter non-ASCII
(`re.sub(r'[^\x20-\x7E\n\r\t]', '', ...)`). Hasil uji nyata:
`clean_text('💰 Kasbon') == 'Kasbon'` — emoji tidak pernah muncul, sedangkan baris klaim
malah menampilkan `-`. Kolom TIPE jadi ambigu.
**Saran**: ganti teks polos → `'KASBON'` vs `'KLAIM'` (aman semua font + hasil copy-paste PDF jelas).

### B. Rantai filter `type` mati (dead parameter)  *(minor bug)*
- `rekap_pdf` membaca `filters['type']`… tapi `filters` tidak pernah punya key `type` (baris 53-58) — `filters.get('type')` selalu `None`.
- `get_rekap_data(..., tx_type=...)` **menerima `tx_type` tapi tidak pernah menerapkannya di query** (engine.py:91-113).
- SPA `RekapView` pun hanya kirim `start_date` & `end_date`; `nopol`/`driver`/`type` tidak dipanggil dari UI.
Efek: `GET /admin/rekap/pdf?type=CASH_LPJ` diam-diam diabaikan. Tidak merusak data, tapi
klaim fitur filter di komentar/kontrak route tidak akurat.

### C. "Budget Bulanan" di cross-check salah hitung  *(akurasi data — patut dibetulkan)*
`_draw_cross_check` (pdf_generator.py:484):
```sql
... WHERE driver_name=%s AND MONTH(created_at)=MONTH(CURDATE())
```
Tanpa pembanding `YEAR` → transaksi bulan yang sama **tahun-tahun sebelumnya ikut
dijumlahkan** ke "Budget Bulanan" — angka bisa membengkak. Tanpa filter status juga
(rejected/pending ikut terhitung).
**Saran**: tambahkan `AND YEAR(created_at)=YEAR(CURDATE())` + batasi status terukur.

### D. Rekap PDF memasukkan transaksi `rejected`  *(review bisnis)*
`get_rekap_data` mengambil `status IN ('verified','archived','os_finance','verified_ga','rejected')`.
Klaim yang DITOLAK ikut tampil di "REKAP DANA BBM" tanpa penanda di kolom TIPE — pembaca
bisa mengira dana terpakai. Bandingkan Wave-20 (`/app/expenses`) yang sengaja hanya hitung
yang terukur. **Saran**: tampilkan status di tabel, atau keluarkan rejected dengan filter eksplisit.

### E. Hasil deteksi multifill tidak dipakai PDF rekap  *(fitur tidur)*
`get_rekap_data` menghitung `km_awal/km_akhir/total_km/rata_rata/is_multifill` (dengan
threshold `multifill_km_threshold` dari `system_config`) — tapi `BBMReportPDF` render
`km_per_liter` mentah per baris untuk kolom KM-L & HEALTH. Rumitnya: kolom komputasi
multifill hanya dimanfaatkan oleh tayangan HTML klasik yang sudah dipensiunkan (v2.5).
**Saran (opsional)**: tambah kolom `KM/AKHIR` atau tanda `*` multifill di PDF, atau hapus
komputasinya bila mau hemat kinerja.

### F. Kerentanan deployment: tanpa `fonts/` PDF per-tx langsung 500  *(hardening)*
`BPFBasePDF` fallback ke `helvetica` bila `fonts/DejaVuSans*.ttf` tidak ada; teks `⚠`/`✓`
yang dikirim mentah (tanpa `clean_text`) kemudian melempar `FPDFUnicodeEncodingException`.
Terbukti lokal: sebelum font direstore, 2 test gagal persis begitu. Di produksi
Dockerfile sudah `COPY fonts/` jadi aman **saat ini**, tapi tidak ada guard eksplisit.
**Saran**: log warning / fail-fast saat start bila font tidak ditemukan.

## 4. Yang masih tertunda (penyebab infrastruktur)
- **Smoke live** `GET /admin/report/<tx yang is_reported=TRUE>` + rekap PDF di container NAS —
  belum bisa: sshd NAS (`192.168.2.31:22`) saat ini *connection refused* (ping OK, host hidup).
  Fallback DuckDNS:2211 juga timeout — patut dicek manajer/host.
- Deploian fix ke NAS & push GitHub menyusul setelah SSH pulih.
- Catatan: salinan lokal `/tmp/opencode/bpf-workhub` sempat sebagian kosong; dipulihkan dari
  git index (`git checkout-index`) → md5 kini identik dengan repo v2.71.0.

## 5. Rekomendasi langkah berikut
1. Fix A + B + C (fokus nilai nyata: kebenaran "Budget Bulanan") → bump v2.71.1 → stamp.
2. Putuskan status `rejected` di rekap (D) bersama user.
3. Smoke live + pytest penuh di container setelah NAS kembali hidup; push GitHub.

## 6. Penanganan (v2.72.0 — keputusan user: restore fitur, reject tetap sah, budget tidak dipakai)

User menindaklanjuti temuan: **fitur multifill pernah dibungkam**
perombakan template; **reject adalah fitur sah Finance** (temuan D = bukan data sampah);
**Budget Bulanan tidak dipakai lagi**.

| Temuan | Tindakan v2.72.0 |
|---|---|
| E — fitur tenggelam | ✅ `BBMReportPDF.generate_table` direstrukturisasi: kolom **KM ISI / KM AKHIR / JARAK KM / KM/L** dari hasil engine (km_awal, km_akhir, total_km, rata_rata); kolom **M-FILL = YA** (amber) untuk pengisian beruntun + keterangan kaki tabel |
| D — rejected tanpa tanda | ✅ kolom **STATUS** ditambahkan; mapping pending/verified/verified_ga/os_finance/arsip/rejected; **DITOLAK merah** (keterangan di kaki tabel: dana tidak cair) |
| A — emoji hambar | ✅ TIPE teks polos **KASBON / KLAIM** |
| B — filter type mati | ✅ route membaca `?type=` dan `get_rekap_data` menerapkan `AND t.transaction_type = %s` (semantik `CLAIM` vs `CASH_LPJ`, sama dengan `/api/transactions/archive`) |
| C — budget salah hitung | ✅ blok **dihapus** (tidak dipakai lagi); slot kolom kanan diisi Catatan GA |
| F — guard font | (belum dikerjakan — catat ke backlog hardening) |

Test: **`tests/test_pdf_rekap_bbm.py`** 13 kasus baru (header/kolom, hasil engine,
marker M-FILL + warna, KM/L dicoret ke '-', mapping status 7 kasus, TIPE polos
anti-emoji pada byte stream, fallback non-engine, filter type via inspect sumber,
penghapusan budget via render + Inspect) — lulus bersama test PDF lama.
Stamp: `SYSTEM_VERSION = 'BPF WorkHub v2.72.0'` + `company_identity` + entri CHANGELOG.

**Menyusul setelah SSH NAS hidup**: simpan laporan ini di `docs/internal/`,
smoke live (tx `is_reported=TRUE` + rekap PDF + `?type=`), pytest penuh di
container, stamp PROGRESS/USER_GUIDE/USER_LIST, commit + push GitHub.
