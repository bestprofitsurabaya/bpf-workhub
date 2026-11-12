# 🔍 Audit Meja Kerja BBM, Kasbon & SPBU (v2.99.1 → v2.104.0)

**Tanggal:** 12 November 2026 · **Auditor:** sesi pemeliharaan BPF WorkHub
**Ruang lingkup:** seluruh perubahan yang belum ter-commit pada repo NAS
(`~/bpf-workhub`, HEAD `acb9136` → working tree v2.104.0) — workspace BBM,
isolasi cabang, definisi metrik tunggal, antrean "Perlu Tindakan", KPI yang
bisa diklik, ekspor PDF/CSV.

**Metode:** (1) baca kode + diff penuh; (2) probe HTTP langsung ke sistem
live (`https://127.0.0.1:5000`) memakai sesi GA & Finance nyata; (3) query
DB produksi read-only; (4) uji kontrak baru (pytest) + suite penuh; (5) audit
endpoint mati (`scripts/audit_endpoints.py`).

**Hasil singkat:** 10 temuan — **8 diperbaiki di v2.104.0**, 2 diterima
dengan alasan eksplisit (A-07, A-08). Tidak ada temuan yang membuka data
antar cabang atau membuka jalur uang baru. Gerbang rilis
`scripts/overall_check.sh` kembali hijau (9/9 langkah).

---

## 1. Ringkasan temuan

| # | Temuan | Severity | Status di v2.104.0 |
|---|---|---|---|
| A-01 | GA melihat tab BBM **kosong tanpa penjelasan** (403 → daftar kosong) | Sedang (UX/data) | ✅ Diperbaiki |
| A-02 | Default cakupan HO ≠ desain (`ALL` jadi cabang sesi) | Sedang (kontrak) | ✅ Diperbaiki + dites |
| A-03 | Definisi "LPJ sah" ditulis ulang di drill-down | Rendah (duplikasi) | ✅ Diperbaiki |
| A-04 | `data-testid` antrean bentrok antar jenis baris | Rendah (uji) | ✅ Diperbaiki |
| A-05 | GA bisa diarahkan ke tab SubsidiTepat yang tidak ada | Rendah (UX) | ✅ Diperbaiki |
| A-06 | Suite penuh merah: `SettingsView` menyangkar 8 seksi, ada 9 | Rendah (kualitas) | ✅ Diperbaiki |
| A-07 | Antrean SPBU mismatch belum punya data produksi | Info | ⚠️ Diterima (diberi tahu) |
| A-08 | Antrean "dana di driver" tidak punya aksi langsung | Info | ⚠️ Diterima (memang begitu) |
| A-09 | Gerbang rilis `overall_check.sh` **merah** — smoke basi | Sedang (proses rilis) | ✅ Diperbaiki |
| A-10 | Stamp versi di DB tertinggal di v2.97.0 (UI menampilkan versi lama) | Rendah (konsistensi) | ✅ Diperbaiki |

---

## 2. Temuan detail

### A-01 — GA melihat tab BBM kosong tanpa penjelasan (403 diam-diam)

**Bukti (live, sebelum perbaikan):**
```
$ curl -b ga.jar "https://127.0.0.1:5000/api/finance/bbm?tab=incoming"
{"msg":"Role tidak diizinkan untuk aksi ini.","status":"error"}   HTTP:403
```
Panel `BbmKasbonPanel` memanggil endpoint itu untuk 3 dari 4 sub-tab
(Masuk / Siap dicairkan / Sudah diproses). Panel ini dirender di `/cash`
untuk **semua** peran termasuk GA — dan tab BBM adalah tab default. Akibatnya
akibatnya GA melihat "Masuk **0**, Siap dicairkan **0**, Sudah diproses **0**"
padahal antrean GA berisi klaim nyata.

**Analisis:** ini **bukan** kebocoran data — GA sudah boleh melihat data yang
sama lewat `/api/queue` (tab `ga`/`finance`/`driver_confirm`) dan
`/api/cash/history` (terverifikasi live: keduanya 200). Yang rusak adalah
pengalaman: daftar kosong tanpa penjelasan, padahal datanya ada.

**Perbaikan:** `modules/routes_api_transactions.py` — `@role_required(['ga',
'finance', 'admin'])` + regresi `tests/test_finance_bbm_workspace.py::test_ga_bisa_membaca_daftar_bbm_panel_workspace`
(m-role driver tetap 403).

---

### A-02 — Default cakupan HO tidak sesuai desain

**Bukti (kode + kontrak):** `modules/branch_scope.py::resolve_report_scope`
memeriksa cabang sesi **lebih dulu**, sehingga `all_branches` (HO) baru
dipakai bila cabang sesi tidak ada di daftar yang diizinkan. Akibatnya
Admin Pusat / Finance HO **tanpa `?branch=`** mendapat `selected = 'SBY'`
(cabang sesinya), bukan `'ALL'`.

Desain yang berlaku (`docs/internal/DESIGN_BBM_WORKSPACE_20261112.md` §5.1a)
menyatakan:

| Sesi | Tanpa parameter |
|---|---|
| Admin Pusat | `ALL` |
| Finance HO | `ALL` |

**Analisis:** arahnya fail-safe (lebih sempit, bukan lebih longgar), jadi
tidak kebocoran. Tapi ini **kontrak yang menyimpang** dan confusing: API
yang dipanggil tanpa parameter memberi angka berbeda dari yang diberikan
`?branch=ALL`, tanpa penjelasan.

**Perbaikan:** `resolve_report_scope` kini memakai seluruh cakupan yang
diizinkan untuk HO lebih dulu. Ditutup tes baru
`tests/test_branch_scope.py` (11 tes) — modul ini **sebelumnya tidak punya
tes sama sekali**, padahal ia penjaga satu-satunya di jalur laporan
lintas-cabang.

**Catatan:** aplikasi (SPA) selalu mengirim `?branch=` eksplisit, jadi
perilaku di UI tidak berubah; yang berubah adalah kontrak API untuk pemanggil
lain (skrip, mobile, agent).

---

### A-03 — Definisi "LPJ sah" ditulis ulang di drill-down

**Bukti:** `modules/routes_expense.py::_detail_rows` menulis
`AND status IN ('verified_ga', 'archived')` langsung, sementara
`modules/bbm_scope.py::LPJ_VALID_STATUSES` adalah sumber kebenaran yang
dipakai kartu, PDF, dan ringkasan.

**Risiko:** kalau definisi diubah, drill-down Realisasi diam-diam jadi
berbeda dari kartu — persis kelas bug yang v2.100.1–v2.101.0 sengaja
dibereskan.

**Perbaikan:** helper baru `bbm_scope.statuses_in()`; drill-down memakai
`bbm_scope.LPJ_VALID_STATUSES`. Tidak ada lagi penulisan ulang status
di luar `bbm_scope.py` (dicek dengan grep seluruh `modules/`).

---

### A-04 — `data-testid` antrean bentrok antar jenis baris

**Bukti:** baris antrean memakai `action-row-{id}`, sementara `id` berasal dari
dua tabel berbeda (`transactions.id` dan `fuel_cash_requests.id`) — keduanya
dimulai dari 1. Dua baris berbeda bisa memakai testid yang sama.

**Perbaikan:** testid kini memakai kunci antrean: `action-row-{key}-{id}` dan
`action-do-{key}-{kind}-{id}`.

---

### A-05 — GA bisa diarahkan ke tab yang tidak ada

**Bukti:** item antrean SPBU mismatch menunjuk `target: 'subsidy'`. Tab
SubsidiTepat hanya dirender untuk Finance/Admin (`v-if="isFinance"`), tetapi
`openQueue()` tetap menetapkan `activeSection = 'subsidy'` → GA mendarat di
panel yang tombolnya tidak terlihat.

**Perbaikan:** `openQueue()` mengarahkan `subsidy` → `bbm` bila peran bukan
Finance/Admin.

---

### A-06 — Suite penuh merah karena assertion basi

**Bukti:** `frontend/src/views/SettingsView.test.js` menyangkar
`8` tombol navigasi, sementara `SECTIONS` di `SettingsView.vue` berisi **9**
(seksi *Deploy* masuk sejak v2.98.1, commit `29a1f92`, tanpa test pendamping).
Akibatnya `npx vitest run` (seluruh 43 file) **merah** — bukan karena
perubahan v2.104.0, tapi karena tidak pernah diperbarui sejak v2.98.1.

**Perbaikan:** assertion diselaraskan ke 9 + komentar menyebut asal
perubahannya. Tidak ada assertion yang dilonggarkan.

---

### A-09 — Gerbang rilis `overall_check.sh` merah karena smoke basi

**Bukti:** `bash scripts/overall_check.sh` → "Smoke Rekap Pengeluaran" GAGAL,
"Smoke Generator PDF BBM" GAGAL (6 dari 19 gagal). Ini **bukan** caused oleh
v2.104.0 — dibuktikan dengan menjalankan modul `branch_scope.py` versi
sebelum-sesi (rekonstruksi dari blok yang berubah) pada kasus yang sama:

```
kasus                                            | SEBELUM v2.104.0 | v2.104.0
smoke: finance tanpa branch + ?branch=SBY        | 403 forbidden    | 403 forbidden
smoke: admin tanpa branch + ?branch=ALL          | 200 ALL          | 200 ALL
sesi bercabang: finance SBY + ?branch=SBY        | 200 SBY          | 200 SBY
HO finance_hu tanpa branch (tanpa ?branch=)      | 200 SBY          | 200 ALL   ← satu-satunya beda
```

Satu-satunya perbedaan adalah **perbaikan A-02** yang memang dimaksudkan.
Sisanya identik → smoke sudah merah **sebelum** sesi ini.

**Akar masalah (4, semuanya basi):**
1. `login()` di kedua smoke **`s.pop('branch_code', None)`** — menghapus
   cabang sesi. Sejak isolasi cabang (v2.99.1) sesi tanpa cabang rightly
   ditolak 403 → seluruh pemeriksaan gagal. (Smoke ini bertanggal v2.71.)
2. `smoke_expenses` masih memakai definisi lama `status='COMPLETED'` untuk
   kasbon, dan assertion `grand_total = totals` menjumlahkan kasbon —
   padahal definisi tunggal (v2.100.1) memakai `handover_at` dan total
   realisasi = PO + LPJ. Ketiganya **tertutup** oleh 403 di atas.
3. `smoke_pdf_bbm` mengasumsikan periode "bulan berjalan" punya klaim final.
   Data saat ini: klaim final terakhir 22 Okt → November kosong → PDF 404.
   Periode sekarang **diambil dari data**, bukan dari asumsi kalender.
4. `smoke_pdf_bbm` masih mengharapkan **302** untuk rekap kosong, padahal
   aplikasi sejak lama menjawab **404 + pesan jelas** (keputusan sadar:
   "redirect diam-diam membuat pengguna mengira PDF kosong/rusak").

**Perbaikan:** kedua smoke diperbarui (login mengeset branch; definisi kasbon
mengikuti `handover_at`; assertion total diperbaiki + ditambah invariant
"sisa kasbon = kasbon cair − LPJ sah"; periode rekap dari data; ekspektasi
404 + pesan; perbandingan SQL memakai `bbm_scope.REKAP_SCOPE_SQL` supaya
tidak bisa menyimpang lagi).

**Hasil:** Smoke Rekap Pengeluaran **14/14**, Smoke Generator PDF BBM
**19/19**. Gerbang `overall_check.sh` hijau kembali.

---

### A-10 — Stamp versi di DB tertinggal di v2.97.0

**Bukti:** `scripts/check_version_stamps.py --with-db` → "DB master
(system_config) = v2.97.0" dan "DB branches.system_version = v2.97.0",
padahal kodenya v2.104.0.

**Analisis:** dua titik DB ini **tidak** ikut ter-update saat versi kode
dinaikkan. `write_branch_identity()` hanya menulis `system_config` di DB
*cabang*; `branches.system_version` (master) hanya berubah kalau Admin
mengedit cabang lewat UI, dan `system_config` master hanya berubah kalau
Admin menyimpan form Identitas. Akibatnya UI Pengaturan → Identitas/Cabang
menampilkan versi lama (v2.97.0) sementara sistem berjalan v2.104.0.

Tidak ada yang membaca nilai ini untuk keputusan bisnis (deploy guard
membandingkan CHANGELOG, PDF memakai konstanta kode), jadi ini soal
**kebenaran tampilan**, bukan security.

**Perbaikan:** `scripts/sync_version_stamp.py` (baru, idempoten) —
menyinkronkan kedua titik dari `IDENTITY_DEFAULTS` (sumber kebenaran di kode,
bukan versi yang diketik manual) sehingga otomatis ikut setiap bump versi.
Nilai identitas lain (nama perusahaan, alamat, telepon) tidak disentuh:
`save_company_identity` hanya menulis key yang ada di `values`.

Setelah sinkron: **9/9 titik stamp (7 file + 2 DB) = v2.104.0.**

---

### A-07 — Antrean SPBU mismatch belum punya data produksi (DITERIMA)

Aturan mismatch **tidak dikarang**: `modules/routes_subsidy.py::_judge` sudah
menghitung verdict (`match` / `close` / `mismatch`) dari selisih volume &
nominal terhadap kandidat SPBU, dan mesin auto-match sudah menulisnya ke
`transactions.subsidy_match`. Antrean v2.104.0 **hanya membaca** nilai itu.

Masalahnya: data produksi saat ini belum punya baris `subsidy_match='mismatch'`
— kolomnya masih berisi `linked`/kosong pada klaim yang sudah diverifikasi
manual. Verifikasi live:

```
$ docker exec bpf-workhub-db mysql ... -e "SELECT subsidy_match, COUNT(*) FROM transactions GROUP BY subsidy_match"
linked | N     (sisanya kosong)
```

**Konsekuensi:** antrean keempat **benar-benar kosong** di produksi sampai
`POST /api/subsidy/auto-match` dijalankan. Ini ditampilkan apa adanya
("Tidak ada antrean menua") — bukan dipalsukan dengan angka.

**Tindak lanjut (disarankan):** jalankan auto-match sekali, lalu periksa
apakah ada verdict `mismatch` yang masuk — itulah bukti hidup untuk aturan
ini. **Jangan** menulis aturan mismatch baru sebelum ada data.

---

### A-08 — Antrean "dana di driver" tidak punya aksi langsung (DITERIMA)

Antrean `driver_due_lpj` (kasbon `FUNDS_WITH_DRIVER` > 14 hari) sengaja
**tidak** punya tombol aksi. Uang di sana belum "berhak" cair — LPJ-nya
belum ada, dan LPJ hanya boleh dibuat driver. Menekan tombol dari panel
Finance/GA untuk "membuat LPJ" berarti memalsukan pertanggungjawaban.

Yang bisa (dan belum) ditambahkan: pengingat/tagihan ke driver, atau
*broadcast* WhatsApp. Itu fitur baru — bukan bagian dari ajax ini.

---

## 3. Yang sudah diverifikasi (bukan temuan)

| Pemeriksaan | Metode | Hasil |
|---|---|---|
| Isolasi cabang: Finance cabang tak bisa baca cabang lain | `tests/test_branch_scope.py` + `tests/test_expenses.py` (route-level) | ✅ 403 |
| Isolasi cabang: `?branch=ALL` ditolak untuk Finance/admin cabang | idem | ✅ 403 |
| Sesi tanpa cabang / peran asing → fail-closed | `test_branch_scope.py` | ✅ 403, daftar kosong |
| Kode cabang tak dikenal → `unknown` (400), bukan 403 | idem | ✅ |
| Definisi metrik tunggal dipakai kartu, PDF, CSV, drill-down | `tests/test_bbm_scope.py` | ✅ |
| Aksi uang dari antrean tetap butuh step-up PIN | kode + endpoint | ✅ `@stepup_required` |
| Peran menentukan tombol antrean (GA vs Finance) | `CashView.test.js` | ✅ |
| Akses GA ke `/api/finance/bbm` | probe live + tes | ✅ 403 → 200 setelah fix |
| Parameter `type` pada `/api/finance/bbm` | validasi whitelist | ✅ 400 untuk nilai asing |
| Satu jenis antrean gagal ≠ panel mati | `test_bbm_action_queue.py` | ✅ |
| Isolasi DB per cabang pada endpoint sesi | `resolve_db_name()` + `get_db_connection()` | ✅ otomatis |
| 7 titik stamp versi konsisten | `scripts/check_version_stamps.py` | ✅ v2.104.0 |

---

## 4. Sisa pekerjaan yang Known (bukan temuan)

1. **Antrean mismatch butuh data nyata** — jalankan auto-match (A-07).
2. **Kartu "Pembelian Barang" belum punya daftar tujuan** — tidak ada tab/list
   PO di meja kerja; tidak dibuatkan tombol mati.
3. **Phase 4 belum tuntas:** `scripts/audit_endpoints.py` → 53 path tanpa
   referensi frontend. Mayoritas adalah **route SPA** (`/admin/*`, `/login`,
   `/m/*`), endpoint agen/agent, dan dipakai `window.open`/mobile — **belum**
   diverifikasi satu per satu. Tidak ada endpoint yang dihapus di v2.104.0
   karena berisiko besar tanpa verifikasi ini.
4. **KPI = cabang sesi, Realisasi = bisa lintas cabang.** Angka KPI diberi
   label cabang ("Cabang: SBY") agar tidak pernah tertukar dengan laporan
   konsolidasi. Menyatukan scope-nya (KPI mengikuti pemilih Realisasi)
   adalah pekerjaan tersendiri.

---

## 5. Jejak audit & bukti

- **Commit:** `feat(bbm): meja kerja BBM v2.99.1→v2.104.0 — definisi tunggal, isolasi cabang, antrean perlu tindakan, KPI → baris → aksi`
- **Tes baru:** `tests/test_branch_scope.py` (11), `tests/test_bbm_action_queue.py` (12),
  `tests/test_finance_bbm_workspace.py` (+1), `frontend/src/components/BbmWorkspaceKpi.test.js` (4),
  `frontend/src/views/CashView.test.js` (+5), `frontend/src/views/ExpensesView.test.js` (+1).
- **Suite penuh:** 1244 pytest (6 skip) + 307 vitest hijau.
- **Deploy:** image dibangun ulang dari working tree, container `bpf-workhub-web`
  recreate, `/api/health` → `state=ok`, `repo_version=running_version=v2.104.0`.

---

*Dokumen ini ditulis untuk manusia, bukan untuk robot. Kalau ada angka di sini
yang tidak cocok dengan apa yang kamu lihat di layar, jangan percaya dokumen
ini — believe the data.*
