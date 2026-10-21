# 🔄 Receptionist — Data Lama (2 Google Sheet) → Event Ledger

**Status:** 📝 **USULAN — belum ada kode yang ditulis** (kecuali pembersihan 6 baris yatim, lihat §3)
**Tanggal bahasan:** 2026-10-16
**Sumber pertanyaan:** user `receptionist_sby` (Rafa Rahti, role `receptionist`, cabang SBY)
**Prasyarat baca:** `CHANGELOG.md` (v2.42.0 receptionist), `guides/USER_GUIDE.md` §Receptionist

---

## 1. Objek bahasan

Dua **sumber data lama berbasis Google Sheet** di modul Receptionist:

| # | Sumber | Config key (`system_config`) | Sheet ID | Tabel tujuan |
|---|---|---|---|---|
| 1 | Sheet **Pelamar** (Google Form lama, tab `H2` file POPH1) | `receptionist_applicants_sheet_url` | `1VIavwXGX1e9R6dbfkmLltEUo0QgpgDEalUPxD2SF8a0` | `applicants` |
| 2 | Sheet **In-Out Karyawan** (tab `In Out Karyawan BPF SBY`) | `receptionist_inout_sheet_url` | `1oBmm62eY06QDzErmt1jWw0VX4usScd0hOKqX0I0o2gM` | `employee_inout` |

Konfigurasi dibaca dari **DB master `bpf_asset_system`** (bukan DB cabang) lewat `_get_sheet_url()`
(`modules/routes_receptionist.py:465`) → `_fetch_sheet_rows()` (`modules/routes_overtime.py:355`).
Nilai di DB masih sama dengan default di kode — belum pernah diganti Apps Script.

Keduanya **masih produksi** per 2026-10-16: HTTP 200, auto-sync 30 menit
(`start_receptionist_auto_sync`, `:838`), sync terakhir `2026-10-16 08:24` (mode `hybrid`),
plus push realtime `onEdit` → `POST /api/receptionist/webhook` (`scripts/gas_bridge_receptionist_v2.gs`, rev 6).

---

## 2. Temuan data (hasil pemeriksaan 2026-10-16)

### 2.1 Sheet Pelamar
- **616 baris valid**, rentang `2026-05-01 … 2026-10-12`; semua header dikenali; 0 baris dilewati.
- 1 nama duplikat (`MARIA`, tanggal berbeda = wajar).
- **Anomali:** baris 279 sel `Jam` berisi `12/30/1899` (artefak format Excel) → tersimpan `00:00:00`. Total 3 baris `applicants` berjam `00:00:00`.
- **Tidak sinkron dengan DB: 6 baris yatim** (`source_uid` 622 di DB vs 616 di sheet). Akar masalah: `source_uid = md5(nama|tanggal|jam)` dan sync hanya INSERT/UPDATE — **tidak pernah DELETE**.

### 2.2 Sheet In-Out
- **1.819 baris mentah → hanya 1.293 valid** (526 baris kosong di ekor sheet).
- Rentang `2026-05-01 … 2026-10-15`.
- **901 dari 1.293 baris `pergi=1 & datang=0`** (1.292 pergi vs 391 datang) → sheet ini praktis **log keberangkatan**, bukan pasangan keluar-masuk. Statistik "masih di luar" di halaman In-Out jadi tidak realistis.
- 1 baris ber-flag `TRUE` tanpa waktu.
- **Tidak ada yatim** di sini karena sync-nya full-replace (`DELETE ... WHERE source='sheet'` + `INSERT`).
- Semua 1.293 baris ber-`source='sheet'` — **belum ada satu pun catatan dari aplikasi** (mode `hybrid` aktif tapi belum dipakai).
- Sheet masih **aktif ditulis**: 1.293 → **1.306 baris** dalam ~1 jam pengamatan. Sumber lama ini masih hidup, bukan arsip mati.

---

## 3. Aksi yang SUDAH dijalankan (2026-10-16)

Pilihan user: **"Bersihkan 6 baris yatim di applicants, cukup laporan ini saja"**.

- Backup: `bpf-workhub/backups/applicants_orphan_cleanup_20261016.json` (4,2 KB; folder `backups/` gitignored).
- Dihapus 6 baris (semua `status='interview'`, tidak dipakai `applicant_attendance` maupun `employee_inout`):

| id | display_id | nama | catatan |
|---|---|---|---|
| 2141 | PLM-SBY-20260916-0278 | AZIZ NOVANDI | Jam sheet `12/30/1899` → UID berubah |
| 2200 | PLM-SBY-20260916-0337 | WIDYA PUSPITASARI | Jam 00:00 → 09:13:11 |
| 2399 | PLM-SBY-20260922-0013 | ARYA NURISKI | sudah hilang dari sheet |
| 2401 | PLM-SBY-20260922-0015 | ANGGUN NURI LESTARI | Jam 00:00 → 09:12:29 |
| 2427 | PLM-SBY-20261006-0006 | LANA UTERA PRADANA | di sheet dikoreksi → LANA **PUTRA** PRADANA |
| 2429 | PLM-SBY-20261006-0008 | FARIANSYAH YULINDARO SIREGAR | di sheet dikoreksi → **FAH**RIANSYAH |

Verifikasi pasca-aksi:
- `applicants` total **1536 → 1530**; baris ber-`source_uid` **622 → 616** = jumlah UID sheet.
- Distribusi per bulan identik dengan sheet (Mei 126, Jun 158, Jul 122, Agu 96, Sep 85, Okt 29).
- Re-check yatim: **orphan = 0**.
- Sync dijalankan ulang lewat `_do_sync_applicants()`: *"0 baru, 616 diperbarui, 0 dilewati"* — yatim tidak kembali.
- `/api/health` = 200.

**Belum ditangani (sengaja, di luar lingkup pilihan user):** kode sync belum punya prune otomatis → yatim akan menumpuk lagi setiap baris sheet yang nama/jam-nya diedit; sel `12/30/1899` di sheet masih ada; 526 baris kosong & 1 baris `TRUE` tanpa waktu di sheet In-Out tidak disentuh.

---

## 4. Akar masalah kenapa data lama belum bisa "dioperasikan"

| # | Akar masalah | Bukti di kode |
|---|---|---|
| 1 | Sheet menyimpan **citra baris**, bukan **kejadian** | `source_uid = md5(nama\|tanggal\|jam)` (`:503`); sync hanya INSERT/UPDATE, tanpa prune → 6 yatim |
| 2 | In-Out = **satu baris dua flag** (`pergi`,`datang`) | `normalize_inout_row` (`:415`); full-replace `DELETE ... WHERE source='sheet'` (`:588`) → riwayat ditimpa, bukan ditambah |
| 3 | Identitas = **nama teks bebas** | `EMPLOYEE_ROSTER_SQL` (`:79`) `GROUP BY TRIM(nama)`; pencarian `nama LIKE` — "FARIANSYAH" vs "FAHRIANSYAH", "LANA UTERA" vs "LANA PUTRA" jadi dua orang; dua "MARIA" jadi satu |
| 4 | Tidak ada **waktu kejadian otoritatif** | waktu dari sel sheet (`_parse_time_with_sec`, `:339`); di app pun `applicant_attendance` di-upsert `ON DUPLICATE KEY UPDATE attended_at=...` (`modules/routes_applicants.py:567`) → klik ulang menimpa jam asli, riwayat hilang |

Kesimpulan: perbaikannya bukan "mengencangkan sync", tapi **mengganti apa yang disimpan: dari status → kejadian**.

---

## 5. Usulan: 3 lapis (people → events → proyeksi)

```
LAPIS 1  people / person_aliases      → SIAPA (identitas stabil, employee_code)
LAPIS 2  employee_events              → APA & KAPAN (append-only, jam server)
LAPIS 3  employee_inout, applicant_*  → proyeksi/UI (turunan dari lapis 2)
```

Sheet lama turun pangkat dari "database" menjadi **adapter impor** (`source='sheet_import'`).
Aplikasi jadi sumber kebenaran; sheet jadi cermin ekspor (fase akhir).

### 5.1 Lapis 1 — identitas (prasyarat)

```sql
people(id, employee_code, nama_lengkap, nama_norm, jabatan, branch_code,
       status, applicant_id, joined_at, resigned_at)
-- status: pelamar | karyawan | keluar ; employee_code: KRY-SBY-0001 / PLM-SBY-YYYYMMDD-NNNN

person_aliases(person_id, alias_norm, source, verified_by)  -- UNIQUE(alias_norm)
-- source: sheet_pelamar | sheet_inout | manual
```

Urutan pencocokan: `nama_norm` persis → `person_aliases` → fuzzy (Jaro-Winkler ≥ 0,92) →
**antrean tinjau manual** ("Perlu ditautkan"). Nama kembar diputus oleh jabatan + branch;
kalau tetap ambigu → manual, jangan menebak.

### 5.2 Lapis 2 — ledger kejadian (inti "ketika diklik, tahu kapan")

```sql
employee_events(
  id, person_id,
  event_type,           -- interview|training_h1..training_h4|lulus|rejected|resign|
                        -- register_karyawan|keluar|kembali|izin|dinas_luar
  occurred_at DATETIME, -- KAPAN kejadian (jam server, TZ Asia/Jakarta)
  recorded_at TIMESTAMP DEFAULT NOW(),  -- kapan sistem tahu
  late_sync TINYINT,    -- recorded_at - occurred_at > 10 menit (diisi belakangan)
  source,               -- app | sheet_import | api
  source_ref,           -- kunci idempotensi (lihat §6)
  actor_username, actor_name, actor_role,
  device_at, payload_json,
  UNIQUE KEY uq_ev_ref (source, source_ref)
)
```

Aturan emas: **tidak ada UPDATE, tidak ada DELETE — koreksi = kejadian baru.**
`occurred_at` = jawaban "kapan klik itu"; `recorded_at` = jawaban "kapan dicatat";
selisih keduanya = alarm audit (sekarang tidak ada sama sekali).

### 5.3 Lapis 3 — proyeksi

- `employee_inout` tetap ada untuk kompatibilitas UI/PDF, tapi **diturunkan**: `keluar` membuka baris,
  `kembali` menutupnya — bukan lagi full-replace (`:588`) yang menghapus ID & riwayat tiap 30 menit.
- Kehadiran (`applicant_attendance`, stage `interview`/`training_1..4`) tidak lagi menimpa jam pertama;
  jam pertama = kejadian pertama, klik berikutnya = baris baru di timeline.
- `ON DELETE`/koreksi manual tetap lewat step-up PIN (`modules/stepup.py`) seperti sekarang.

---

## 6. Cara kerja klik (kontrak endpoint)

`POST /api/events` — body `{person_id | nama, event_type, note, client_token, occurred_at?, reason?}`

1. Frontend: tombol ditekan → buat `client_token` (UUID), tombol di-disable, kirim request.
2. Server: cek role → resolve `person_id` → **validasi urutan** (mesin status) → tulis dengan
   `occurred_at = NOW()` (jam server) → jalankan proyeksi → `emit_event` (Socket.IO yang sudah dipakai)
   → kembalikan baris kejadian.
3. Frontend menampilkan `occurred_at` **dari respons server** — jadi yang tampil = yang tersimpan.
   Jam HP hanya dikirim sebagai `device_at` untuk deteksi jam melenceng, tidak pernah jadi waktu resmi.
4. **Anti-dobel:** `UNIQUE(source, source_ref)` dengan `source_ref = md5(person_type|client_token)`.
   Klik ganda / retry jaringan = satu kejadian. (   Menggantikan `POST /api/receptionist/inout`
   (`:1444`) yang saat ini bisa mencetak dua baris.)
5. **Urutan (mesin status):** `training_h3` ditolak bila `h2` belum ada; `kembali` ditolak bila tidak ada
   `keluar` terbuka → `409` dengan pesan jelas; admin boleh paksa (`override`) dan itu tercatat.
6. **Offline / isi belakangan:** antrean IndexedDB, kirim ulang dengan `client_token` yang sama;
   bila `occurred_at` dari klien dipakai, server menandai `late_sync=1` sehingga "kapan sebenarnya"
   tetap bisa dibedakan dari "kapan diinput".

---

## 7. Impor data lama (sekali, idempoten)

Kunci impor = **identitas baris sheet**, bukan isi baris:
`source_ref = md5(spreadsheet_id | tab | nomor_baris)` → `UNIQUE`.

- Edit sel di sheet = **revisi baris yang sama** → kejadian diperbarui hanya bila belum ada kejadian
  `app` yang bergantung padanya; kalau sudah ada, revisi sheet **diabaikan + dicatat di `sheet_conflicts`**.
  Kelas "6 baris yatim" tidak bisa lahir lagi dari desain ini.
- Sheet In-Out: `pergi=1` → kejadian `keluar`; `datang=1` → `kembali`; dipasangkan per `person_id`
  **+ tanggal kerja**. 901 baris tanpa pasangan otomatis muncul sebagai daftar kerja
  "keluar tanpa catatan kembali (dari sheet)".
- 526 baris kosong di ekor: diabaikan validator + dicatat di `sheet_import_log` (jejak, bukan diam-diam).
- Nama tak dikenal → antrean "Perlu ditautkan", **bukan** baris hantu.
- Backfill awal: 1.530 `applicants` + ~1.306 `employee_inout` → ledger dengan `occurred_at` dari sheet,
  `recorded_at` = waktu impor, `source='sheet_import'`. Tabel lama dibiarkan hidup sampai Fase 3.

**Transisi:** impor masuk (sheet→ledger) dan cermin keluar (app→sheet) tetap jalan supaya manajer yang
bekerja di sheet tidak kehilangan apa pun. Cermin keluar **wajib bertanda** `origin='app-mirror'` agar
webhook `onEdit` tidak mengimpor balik tulisan kita sendiri (loop). Dua arah penuh **tidak** diusulkan.

---

## 8. Rollout bertahap

| Fase | Isi | Verifikasi |
|---|---|---|
| 0 | Ledger + importer jalan **shadow**: menulis kejadian, UI masih baca tabel lama | Hitung matched/unmatched; bandingkan in-out turunan ledger vs `employee_inout` selama 1 minggu. Nol perubahan yang dilihat user |
| 1 | Halaman identitas/alias + tautkan manual; input pelamar dialihkan ke form aplikasi (`POST /api/applicants/manual` sudah ada) | Orphan = 0, unmatched = 0 |
| 2 | UI baca ledger; mode in-out SBY `hybrid` → `app` (tombol sheet dimatikan) | Laporan harian PDF dari ledger = laporan lama (`GET /api/receptionist/inout/report`) |
| 3 | Sheet jadi cermin ekspor read-only; baris lama di-*tombstone* otomatis | Batas "yatim menumpuk lagi tiap baris sheet diedit" hilang permanen |

---

## 9. Referensi kode (titik sentuh bila diimplementasikan)

| Berkas | Baris | Isi |
|---|---|---|
| `modules/routes_receptionist.py` | 98 | `ensure_receptionist_schema()` — DDL `employee_inout`, `employee_inout_stage`, `employee_inout_events`, kolom sync `applicants` |
| | 286 | `_inout_mode()` — mode `sheet` / `hybrid` (`receptionist_inout_mode`) |
| | 319 | `_log_inout_event()` — audit trail yang sudah ada (cikal bakal pola ledger) |
| | 481 | `_do_sync_applicants()` — upsert `source_uid = md5(nama\|tanggal\|jam)` |
| | 544 | `_do_sync_inout()` — full-replace baris `source='sheet'` |
| | 690 | `_upsert_webhook_rows()` — upsert push Apps Script `onEdit` |
| | 1444 | `POST /api/receptionist/inout` — klik keluar / masuk dari aplikasi (INSERT `:1470`, UPDATE `:1507`) |
| `modules/routes_applicants.py` | 531 | `POST /api/applicants/<id>/attendance` — klik I/H1–H4 (upsert, menimpa jam) |
| `modules/routes_applicants.py` | 121 | `register_applicant_routes()` — list + verifikasi + status |
| `init.sql` | 440 / 465 | `applicants` / `applicant_attendance` |
| `frontend/src/views/dashboard/ReceptionistView.vue` | 25 | `STAGE_SHORT` = `interview:'I', training_1..4:'H1..H4'` |
| `scripts/gas_bridge_receptionist_v2.gs` | — | Bridge Apps Script (push `onEdit` + pull `/exec`) |
| `scripts/migrate_applicants_sheet.py` | — | Preseden migrasi massal dari sheet (mengosongkan tabel lalu isi ulang) |

---

## 10. Keputusan yang masih terbuka

1. **Sumber kebenaran:** aplikasi (diusulkan) vs sheet tetap master (murah, tapi kebutuhan
   "kapan kejadian klik itu" tidak akan pernah bisa dipenuhi).
2. **Cutover in-out:** kapan mode `hybrid` → `app` untuk SBY, dan apakah sheet masih perlu ditulis (cermin).
3. **Nama kembar / ambigu:** siapa yang berwenang menautkan di antrean "Perlu ditautkan"
   (receptionist, GA HR, atau admin pusat).
4. **`occurred_at` dari klien saat offline:** toleransi selisih jam device vs server (usulan: 5 menit,
   di luar itu ditandai `perlu_verifikasi`).
5. **Nasib sheet lama:** dibekukan (read-only) atau tetap boleh diedit selama Fase 0–1.
