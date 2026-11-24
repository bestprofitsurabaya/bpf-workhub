# Design — Hub Rekrutmen & Ujian TKD online (24 November 2026)

Status: **draft, menunggu persetujuan**. Belum ada kode produksi yang diubah.
Revisi 24 Nov: temuan builder-check (skor resmi di kasus, finalisasi lazy,
kuota HITUNG per tier, impor insert-only, peran pengaturan) sudah dimasukkan.

## Intent

Rekrutmen saat ini tersebar di tiga menu (Rekrutmen, Absensi FirstWork,
Registrasi CV Online) dan dua tautan publik yang harus disalin terpisah
(CV Online dan FirstWork). Pelamar juga belum bisa mengerjakan TKD sendiri;
nilai TKD hanya dicatat manual sebagai bukti di dashboard kasus, sehingga
pelamar tidak pernah melihat skornya lagi.

Perubahan ini menyatukan alur itu:

1. **Satu menu Rekrutmen** berisi tab Pelamar, Kasus, CV Online, FirstWork,
   TKD, dan Tautan.
2. **Satu tautan publik per cabang** — portal rekrutmen — yang menjadi pintu
   masuk CV, FirstWork, dan TKD. Tautan CV/FirstWork tidak lagi dibagikan.
3. **TKD online di HP pelamar** dengan bank soal, penilaian otomatis di server,
   maksimal 2 percobaan, dan skor yang bisa dilihat lagi dengan NIK + tanggal
   lahir.

Tujuan akhirnya bukan sekadar memindahkan Google Form. Isi dan “rasa” tes
asli dipertahankan: pengetahuan perusahaan/industri berjangka, skenario
hitungan ala “Pak Budi/Ibu Dian”, pilihan modal, dan pertanyaan motivasi.
Yang berubah hanya formatnya — dari uraian menjadi pilihan ganda, isian
angka, dan isian singkat — supaya bisa dinilai otomatis.

## Keputusan yang sudah diambil

- **Auto-grade penuh.** Tidak ada esai yang dinilai manual. Soal uraian
  diubah menjadi pilihan ganda/isian yang menguji pengetahuan yang sama.
- **Maksimal 2 percobaan.** Skor resmi otomatis = **nilai tertinggi** dari
  percobaan yang ada. Koreksi manual staff menang atas skor otomatis.
  Tidak ada percobaan ke-3 lewat portal.
- **Traineer hanya boleh mengedit skor TKD** pada data kandidat (belum field
  rekrutmen lain).
- **Esensi tes dipertahankan**, termasuk skenario hitungan dan cabang modal.

## Goals

- Satu menu dan satu tautan portal per cabang; tautan lama tetap hidup.
- Pelamar bisa melihat status, mengerjakan TKD, dan melihat skor lagi
  kapan saja dari HP.
- Skor dihitung server-side; kunci jawaban tidak pernah dikirim ke browser.
- Perubahan bank soal tidak mengubah skor percobaan lama.
- Traineer/GA-HR/Admin bisa mengelola bank soal, melihat hasil, dan
  mengoreksi skor dengan jejak audit.
- Tidak menambah dependency baru (CSV memakai `csv` Python, QR memakai
  `qrcode` yang sudah ada).

## Non-goals

- Tidak menilai esai secara otomatis atau manual di dalam WorkHub.
- Tidak ada proctoring (kamera, kunci browser, deteksi pindah tab).
- Tidak ada bank soal per cabang; bank soal global.
- Tidak mengubah data pelamar selain skor TKD.
- Tidak menambah percobaan ke-3, reset percobaan, atau banding otomatis.
- Tidak mengubah form CV Online/FirstWork selain cara tautannya dibagikan.
- Tidak menghapus data TKD manual yang sudah ada.

## Anti-goals

- Kunci jawaban, poin, atau pembahasan bocor ke response publik.
- Pelamar otomatis ditolak sistem setelah 2x gagal; keputusan tetap di staff.
- Tautan lama yang sudah tersebar (`/first-work`, `/cv-online`,
  `/recruitment-cases`) mati atau memaksa login.
- Mengedit soal membuat skor historis berubah.
- NIK lengkap masuk ke tabel baru, log, audit, atau URL.

## Constraints

- Repo `bpf-workhub` di NAS; rilis lewat `docker compose build web`, bukan
  bind-mount.
- Skema idempoten dijalankan saat startup (`ensure_*_schema`), dan `init.sql`
  harus mencerminkan DDL untuk pemeriksaan schema drift.
- Pola token cabang sudah ada di `cv_online_branch_forms`; jangan membuat
  token baru.
- Pola role staff rekrutmen: `traineer`, `ga_hr`, `admin`; `finance` hanya
  membaca FirstWork.
- NIK selalu dimasker di UI/log; `case_id` opaque.
- UI berbahasa Indonesia, mobile-first untuk halaman publik.
- Versi rilis mengikuti kebiasaan repo: bump 7 titik + DB, CHANGELOG,
  PROGRESS, commit tunggal per versi.

## Riset sumber aturan transaksi

Aturan yang dipakai untuk kunci jawaban diambil dari situs resmi:

- Formula & biaya:
  `https://www.bestprofit-futures.co.id/prosedur/ilustrasi-transaksi`
  - `[ (Selling Price − Buying Price) × Contract Size × n Lot ] −
    [ (Facility Fee + VAT) × n Lot ]`
  - Emas Loco London: contract size **100 troy ounce**.
  - Facility fee: **US$15/lot/sisi**; total **US$30/lot** settle.
  - VAT 11%: **US$1,65/lot/sisi**; total **US$3,3/lot** settle.
  - Rollover emas: **US$5/lot/malam/sisi** + VAT 11%.
- Produk & mekanisme: `https://www.bestprofit-futures.co.id/edukasi/loco-london-gold`,
  `https://www.bestprofit-futures.co.id/edukasi/mekanisme-perdagangan`.
- Lembaga & regulasi: `https://www.bestprofit-futures.co.id/profil/badan-regulasi`
  (Bappebti, OJK, BI, BBJ/JFX, KBI, SITNA).
- Legalitas: `https://www.bestprofit-futures.co.id/profil/legalitas-bisnis`
  dan `https://bappebti.go.id/pialang_berjangka/detail/499`
  - Izin Usaha Pialang Berjangka: **499/BAPPEBTI/SI/X/2004**
  - Izin SPA: **1157/BAPPEBTI/SP/3/2007**
  - Keanggotaan KBI: **48/AK-KBI/I/2007**
  - Anggota Bursa: **SPAB-071/BBJ/05/04**

Contoh hitung yang dipakai ulang (sesuai formula resmi):

| Skenario | Hitung kotor | Biaya (30 + 3,3)/lot | Bersih |
|---|---|---|---|
| Pak Budi: 2.334 → 2.339, 4 lot | 5 × 100 × 4 = 2.000 | 33,3 × 4 = 133,2 | **1.866,8** |
| Ibu Dian $30k: 2.340 → 2.403, 9 lot | 63 × 100 × 9 = 56.700 | 33,3 × 9 = 299,7 | **56.400,3** |
| Ibu Dian $50k: 2.339 → 2.404, 15 lot | 65 × 100 × 15 = 97.500 | 33,3 × 15 = 499,5 | **97.000,5** |
| Ibu Dian $100k: 2.352 → 2.405,5, 30 lot | 53,5 × 100 × 30 = 160.500 | 33,3 × 30 = 999 | **159.501** |

Catatan: soal $100k asli menulis “30% lot” dan harga “$24055”. Agar bisa
dinilai otomatis, soal baru menyebut eksplisit: modal $100.000, margin
$1.000/lot, 30% modal dipakai sebagai margin = 30 lot, harga jual $2.405,5.
Asumsi ini ditulis di dalam soal, bukan di kunci tersembunyi.

## Approaches yang dipertimbangkan

### A. Bentuk menu

1. **Tetap tiga menu** — paling murah, tetapi tujuan “clean” tidak tercapai.
2. **Submenu Rekrutmen** — masih terlihat sebagai beberapa item.
3. **Satu menu + tab** (dipilih) — satu pintu, tab sesuai peran, URL tab
   bisa di-bookmark.

### B. Penilaian TKD

1. **Hybrid** (PG/angka otomatis, esai manual) — menunggu koreksi staff,
   skor tidak langsung muncul, beban staff tinggi.
2. **Tanpa bank soal** (input skor manual) — tidak ada ujian online.
3. **Auto-grade penuh** (dipilih) — skor langsung, 2 percobaan berjalan,
   cocok untuk HP. Konsekuensinya soal uraian harus diubah format.

### C. Sumber soal

1. **Pakai Google Form apa adanya** — tidak ada kunci, tidak bisa auto-grade,
   tidak terikat identitas kasus.
2. **Bangun mini-LMS** — esai, anti-cheat, pembahasan; berlebihan.
3. **Bank soal WorkHub hasil konversi** (dipilih) — kontrol penuh, snapshot
   per percobaan, kunci di server.

### D. Penyimpanan percobaan

1. **Rujuk soal hidup** — edit soal mengubah skor lama. Ditolak.
2. **Snapshot per percobaan** (dipilih) — teks, opsi, kunci, dan poin
   dibekukan saat percobaan dibuat.

### E. Otoritas skor

1. **Hanya dari attempt** — koreksi staff harus mengubah attempt.
2. **Skor resmi di kasus (`recruitment_cases`) + attempt sebagai riwayat**
   (dipilih) — satu angka per orang meski ada beberapa baris langkah karena
   pindah cabang; koreksi staff sederhana, teraudit, dan tes manual tanpa
   attempt tetap bisa dicatat.

## Design

### 1. Information architecture

Satu route staff:

```
/recruitment?tab=pelamar|kasus|cv|firstwork|tkd|tautan
```

Tab dan peran:

| Tab | Isi | Peran |
|---|---|---|
| Pelamar | `ReceptionistView` (alur pelamar lama) | receptionist, traineer, admin |
| Kasus | `RecruitmentCasesView` | traineer, ga_hr, admin |
| CV Online | `CvOnlineView` | traineer, ga_hr, admin |
| FirstWork | `FirstWorkView` | traineer, finance, ga_hr, admin |
| TKD | sub-tab Bank Soal / Hasil / Pengaturan (ubah Pengaturan: **admin** saja) | traineer, ga_hr, admin |
| Tautan | satu link portal + QR per cabang | receptionist, traineer, ga_hr, admin |

Catatan peran: `traineer` dan `ga_hr` dapat mengelola bank soal, melihat
hasil, dan mengoreksi skor TKD, tetapi **tidak** dapat mengubah pengaturan
global (jumlah soal, durasi, ambang lulus, kuota, aktif/nonaktif) — itu
hanya `admin`. `receptionist` hanya melihat tab Tautan (dan Pelamar).
“Traineer hanya boleh mengedit skor TKD” berarti pada **data kandidat**:
Traineer tidak mengubah identitas, langkah, atau field rekrutmen lain;
bank soal adalah konten global, bukan data kandidat.

- Route `/recruitment` memakai gabungan peran di atas. Tab yang tidak
  diizinkan tidak dirender; akses langsung ke `?tab=` yang terlarang
  diarahkan ke tab pertama yang diizinkan.
- Menu sidebar “Rekrutmen & Trainee” diganti **satu item** “Rekrutmen”
  (`/recruitment`, ikon 🪪). Badge lama tetap ada di tab, bukan di menu.
- Rute lama tetap hidup:
  - `/receptionist` → `/recruitment?tab=pelamar`
  - `/recruitment-cases` → `/recruitment?tab=kasus`
  - `/cv-online` → `/recruitment?tab=cv`
  - `/traineer` → `/recruitment?tab=pelamar`
  - `/first-work` **tidak dijadikan redirect murni**. Route ini tetap
    terdaftar, lalu guard global memutuskan:
    - belum login → `/first-work-form` (perilaku lama, tautan lama tetap
      membuka form publik);
    - sudah login → `/recruitment?tab=firstwork`.
    Redirect murni akan dijalankan sebelum guard, sehingga tautan lama
    yang belum login akan mendarat di halaman login.
- View lama diberi prop opsional `embedded` untuk menyembunyikan
  `PageHeader`/padding luar saat dirender di dalam hub. Default tetap
  seperti sekarang, sehingga route lama tidak berubah.

Sketsa:

```
┌────────────────────────────────────────────────────────────┐
│ 🪪 Rekrutmen                                                │
│ [Pelamar] [Kasus] [CV Online] [FirstWork] [TKD] [Tautan]    │
├────────────────────────────────────────────────────────────┤
│  (isi tab)                                                  │
└────────────────────────────────────────────────────────────┘
```

### 2. Portal publik & alur pelamar

Portal tetap di `/app/recruitment-portal?token=<token cabang>`. Empat kartu
tetap ada, tetapi TKD menjadi kartu aktif setelah identitas diverifikasi.

Alur:

1. Pelamar membuka tautan portal cabang.
2. Masukkan NIK 16 digit + tanggal lahir → `lookup` (boolean, seperti
   sekarang) untuk membuka kartu.
3. Saat membuka kartu TKD, portal memanggil `POST /api/recruitment/tkd/status`
   dengan NIK + tanggal lahir + token. Server mencocokkan NIK **dan**
   tanggal lahir ke `recruitment_cases` (bukan hanya format tanggal).
4. Kartu menampilkan salah satu status:
   - **Belum pernah tes** — “20 soal, 25 menit, 2 kesempatan, lulus 70.”
   - **Sedang berlangsung** — sisa waktu + tombol “Lanjutkan”.
   - **Sudah tes, masih bisa mencoba** — skor resmi + “Coba lagi
     (kesempatan 2 dari 2)”.
   - **Lulus** — skor resmi + “Lulus”.
   - **Kesempatan habis** — skor resmi + “Hubungi Traineer cabang.”
   - **Dikecualikan** — “Dikecualikan staff; hubungi Traineer.”

   Angka yang ditampilkan selalu **skor resmi** (`recruitment_cases.
   tkd_score`), bukan sekadar attempt terbaik. Bila Traineer mengoreksi
   skor, pelamar melihat skor koreksi meski lebih rendah dari attempt
   terbaik. Bila kasus lama punya baris TKD `SELESAI` tetapi skor NULL,
   kartu menampilkan “Skor belum tercatat — hubungi Traineer”, bukan 0.
   Bila ada baris TKD `DIKECUALIKAN`, status itu yang ditampilkan
   (beserta skor resmi bila ada) dan portal tidak menawarkan tes.
5. Sebelum mulai, pelamar memilih **rencana modal** ($30.000 / $50.000 /
   $100.000), meniru cabang modal di form asli. Pilihan ini tidak dinilai,
   disimpan di percobaan, dan menentukan varian soal hitung “Ibu Dian”.
   TKD tidak menunggu langkah Training (modul itu belum ada); kartu terbuka
   setelah identitas dikenal dan bank soal siap.
6. Ujian satu soal per layar, timer di atas, jawaban tersimpan otomatis.
   20 soal dinilai, lalu **1 pertanyaan motivasi** (tidak dinilai, boleh
   dilewati) sebagai soal terakhir — mempertahankan pertanyaan “target di
   BPF” dari form asli.
7. Selesai → skor langsung tampil. Pelamar bisa menutup browser dan
   membuka lagi nanti dengan NIK + tanggal lahir yang sama.

**Identitas kasus lama.** Di produksi, 1.750 dari 1.957 kasus punya
`tanggal_lahir` NULL (hasil backfill FirstWork lama). Supaya mereka tetap
bisa memakai TKD, verifikasi memakai aturan berurutan:

1. Bila `recruitment_cases.tanggal_lahir` terisi → harus sama persis.
2. Bila NULL → tanggal lahir diturunkan dari NIK: digit 7–12 adalah
   `DDMMYY` (perempuan `DD+40`), dengan pivot abad (YY > tahun berjalan →
   1900+YY, selain itu 2000+YY). Tanggal yang dimasukkan harus sama dengan
   hasil turunan ini.
3. Bila NIK tidak menghasilkan tanggal valid → pesan generik “Data belum
   lengkap, hubungi Traineer”; staff mencatat skor manual.

Catatan keamanan: NIK memang memuat tanggal lahir, jadi pemeriksaan ini
mencegah salah ketik/akses tidak sengaja, bukan autentikasi kuat. Untuk
nilai tinggi, Traineer tetap memverifikasi identitas di cabang. OTP/scan KTP
di luar cakupan rilis ini.

Sketsa kartu:

```
┌──────────────────────────────────────┐
│ 3  Test Kemampuan Dasar              │
│    Fit and Proper Test               │
│    Skor terbaik: 86,67 · Lulus       │
│    [Lihat hasil]                     │
└──────────────────────────────────────┘
```

Sketsa ujian:

```
┌──────────────────────────────────────┐
│ Soal 7 dari 20          ⏱ 18:42      │
│ ███████░░░░░░░░░░░░░                 │
│                                      │
│ Ibu Dian membeli emas ...            │
│                                      │
│ ( ) A. US$56.400,30                  │
│ (•) B. US$56.400,3                   │
│ ( ) C. US$56.700,00                  │
│ ( ) D. US$56.999,70                  │
│                                      │
│ [← Sebelumnya]        [Berikutnya →] │
└──────────────────────────────────────┘
```

Aturan yang ditampilkan sebelum mulai: jumlah soal, durasi, ambang lulus,
jumlah kesempatan, dan “tidak ada kunci/pembahasan yang ditampilkan”.

### 3. Model data

Semua tabel baru di DB master, mengikuti pola `recruitment_*` (tanpa FK,
`case_id` string, NIK tidak diduplikasi).

#### 3.1 `tkd_questions`

```sql
CREATE TABLE IF NOT EXISTS tkd_questions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(40) NOT NULL,
  category ENUM('REGULASI','PERUSAHAAN','PRODUK','HITUNG','PROFIL') NOT NULL,
  type ENUM('MCQ','NUMERIC','SHORT_TEXT','PROFILE_TEXT') NOT NULL,
  prompt TEXT NOT NULL,
  options JSON NULL,
  answer JSON NULL,
  points DECIMAL(5,2) NOT NULL DEFAULT 1,
  modal_tier VARCHAR(10) NULL,
  active TINYINT NOT NULL DEFAULT 0,
  sort_order INT NOT NULL DEFAULT 0,
  created_by VARCHAR(100) NOT NULL DEFAULT '',
  updated_by VARCHAR(100) NOT NULL DEFAULT '',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_tkd_q_code (code),
  KEY idx_tkd_q_cat (category, active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Bentuk `options`/`answer`:

```json
// MCQ
options: [{"id":"a","text":"..."},{"id":"b","text":"..."}]
answer:  {"option":"b"}

// NUMERIC
answer:  {"value":1866.8,"tolerance":0.5}

// SHORT_TEXT
answer:  {"aliases":["499/BAPPEBTI/SI/X/2004"]}

// PROFILE_TEXT
answer:  null
```

Aturan validasi: MCQ minimal 2 opsi dan tepat satu kunci; NUMERIC wajib
punya nilai; SHORT_TEXT minimal satu alias; PROFILE tidak berpoin dan
tidak masuk undian soal bernilai.

#### 3.2 `tkd_settings` (satu baris)

```sql
CREATE TABLE IF NOT EXISTS tkd_settings (
  id TINYINT PRIMARY KEY DEFAULT 1,
  question_count INT NOT NULL DEFAULT 20,
  duration_minutes INT NOT NULL DEFAULT 25,
  pass_score DECIMAL(5,2) NOT NULL DEFAULT 70,
  max_attempts INT NOT NULL DEFAULT 2,
  quota JSON NULL,
  shuffle_options TINYINT NOT NULL DEFAULT 1,
  active TINYINT NOT NULL DEFAULT 0,
  updated_by VARCHAR(100) NOT NULL DEFAULT '',
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Default kuota: `{"REGULASI":7,"PERUSAHAAN":4,"PRODUK":6,"HITUNG":3}`.
Jumlah kuota harus sama dengan `question_count`. Kuota HITUNG sengaja 3
agar setiap tier modal (yang punya 2 soal inti + soal umum) selalu cukup;
lihat §4.2. `active=0` berarti TKD belum dibuka untuk pelamar (bank belum
siap atau sedang ditinjau).

`ensure_tkd_schema()` menyisipkan baris `id=1` dengan default di atas bila
belum ada. Server menolak simpan pengaturan bila jumlah kuota ≠
`question_count`, bila `max_attempts` ≠ 2, atau bila `active=1` sementara
bank belum memenuhi syarat kesiapan §4.3.

#### 3.3 `tkd_attempts`

```sql
CREATE TABLE IF NOT EXISTS tkd_attempts (
  id VARCHAR(40) NOT NULL,
  case_id VARCHAR(40) NOT NULL,
  attempt_no INT NOT NULL,
  branch_code VARCHAR(10) NOT NULL DEFAULT '',
  modal_tier VARCHAR(10) NOT NULL DEFAULT '',
  status ENUM('BERLANGSUNG','SELESAI','KEDALUWARSA') NOT NULL,
  settings_snapshot JSON NOT NULL,
  pass_score_snapshot DECIMAL(5,2) NOT NULL,
  started_at DATETIME NOT NULL,
  expires_at DATETIME NOT NULL,
  submitted_at DATETIME NULL,
  score DECIMAL(5,2) NULL,
  total_points DECIMAL(6,2) NOT NULL DEFAULT 0,
  correct_count INT NOT NULL DEFAULT 0,
  passed TINYINT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_tkd_a_case_no (case_id, attempt_no),
  KEY idx_tkd_a_case (case_id, status),
  KEY idx_tkd_a_branch (branch_code, submitted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

`id` = `TKD-` + 16 hex. `attempt_no` 1..`max_attempts`. `settings_snapshot`
menyimpan jumlah soal, durasi, kuota, dan `max_attempts` saat mulai.

#### 3.4 `tkd_attempt_items`

```sql
CREATE TABLE IF NOT EXISTS tkd_attempt_items (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  attempt_id VARCHAR(40) NOT NULL,
  question_id BIGINT NOT NULL,
  position INT NOT NULL,
  snapshot JSON NOT NULL,
  answer JSON NULL,
  answered_at DATETIME NULL,
  is_correct TINYINT NULL,
  points_awarded DECIMAL(5,2) NULL,
  UNIQUE KEY uq_tkd_i_attempt_pos (attempt_id, position),
  KEY idx_tkd_i_attempt (attempt_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

`snapshot` membekukan `prompt`, `type`, `category`, `options` (urutan yang
disajikan), `answer` (kunci), `points`, dan `tolerance`. Kunci hanya ada
di server; response publik tidak pernah menyertakan field ini.

#### 3.5 Skor resmi di `recruitment_cases`

TKD adalah milik **orang**, bukan cabang. Karena `recruitment_steps` unik
per `(case_id, step_type, branch_code)`, satu kasus bisa punya beberapa baris
TKD bila pindah cabang. Supaya tidak ada dua skor resmi, skor disimpan di
kasus; baris langkah hanya mencerminkan status/evidence.

```sql
ALTER TABLE recruitment_cases
  ADD COLUMN tkd_score DECIMAL(5,2) NULL,
  ADD COLUMN tkd_score_source ENUM('AUTO','MANUAL') NULL,
  ADD COLUMN tkd_score_note VARCHAR(500) NULL,
  ADD COLUMN tkd_score_updated_by VARCHAR(100) NULL,
  ADD COLUMN tkd_score_updated_at DATETIME NULL,
  ADD COLUMN tkd_best_attempt_id VARCHAR(40) NULL,
  ADD COLUMN tkd_passed TINYINT NULL;
```

Migrasi idempoten: cek `information_schema.COLUMNS` sebelum `ALTER`, seperti
pola `ensure_cv_online_nik_columns()`. `init.sql` ikut diperbarui.

Definisi:

- `tkd_score` = skor resmi TKD (0–100), satu angka per orang.
- `tkd_score_source='AUTO'` = dihitung dari attempt terbaik.
- `tkd_score_source='MANUAL'` = dikoreksi staff; auto berikutnya tidak
  menimpa sampai staff mengedit lagi.
- `tkd_score_note` = alasan koreksi (wajib saat manual).
- `tkd_best_attempt_id` = attempt yang menghasilkan skor auto terbaik.
- `tkd_passed` = keputusan lulus saat skor terakhir dihitung; disimpan agar
  perubahan ambang tidak membalik status historis.
- Status baris TKD di `recruitment_steps` disinkronkan: `SELESAI` bila
  `tkd_passed=1`, `PENDING` bila sudah ada percobaan/skor tetapi belum
  lulus, `DIKECUALIKAN` hanya lewat aksi staff yang sudah ada.
- Kasus lama yang punya baris TKD `SELESAI` tetapi `tkd_score` NULL
  (saat ini **0 baris**; dicek di produksi) dianggap “sudah menyelesaikan
  TKD, skor belum tercatat”: portal tidak menawarkan tes online, staff
  dapat mengisi skor manual. Tidak ada backfill skor dari audit.

### 4. Bank soal & esensi tes asli

Bank soal global, bukan per cabang. Soal disusun dari form asli
“Fit and Proper Test” dan fakta resmi di atas.

#### 4.1 Pemetaan form asli → soal auto-grade

| Form asli | Esensi yang dipertahankan | Bentuk baru | Kunci/acuan |
|---|---|---|---|
| 1. Apa yang Anda ketahui tentang PT BPF? | Profil perusahaan | MCQ | Pialang berjangka berizin Bappebti, anggota BBJ & KBI |
| 2. Apa itu Kliring Berjangka Indonesia? | Peran KBI | MCQ | Lembaga kliring yang menjamin penyelesaian & mengelola risiko |
| 3. Keuntungan transaksi di BBJ? | Transparansi & hedging | MCQ | Perdagangan teratur/transparan, price discovery, hedging, kliring |
| 4. Produk di BBJ? | Produk | MCQ | GOL, GOL250, OLE (multilateral); XUL/XAG/BCO/HKK/JPK/forex (SPA) |
| 5. Mekanisme perdagangan berjangka? | Mekanika | MCQ | Margin, lot, contract size, dua arah, likuidasi |
| 6. Amankah transaksi di BPF? | Keamanan & legalitas | MCQ | Izin Bappebti, dana nasabah terpisah, anggota KBI |
| 7. Target/tujuan di BPF | Motivasi | PROFILE_TEXT (tidak dinilai) | Disimpan untuk wawancara |
| 8. Acuan hukum legalitas | Regulasi | MCQ | UU 32/1997 jo. UU 10/2011 |
| 9. Perbedaan LPS dan KBI | Peran lembaga | MCQ | LPS menjamin simpanan bank; KBI kliring PBK |
| 10. Apa itu Bappebti? | Regulator | MCQ | Badan pengawas di bawah Kementerian Perdagangan |
| 11. Nomor izin Bappebti BPF | Legalitas | SHORT_TEXT | `499/BAPPEBTI/SI/X/2004`; varian SPA `1157/BAPPEBTI/SP/3/2007` |
| 12. Hitung profit Pak Budi | Skenario hitung | NUMERIC | **1.866,8** |
| 13. Pilih modal | Cabang skenario | Pilihan sebelum tes (tidak dinilai) | $30k / $50k / $100k → varian soal Ibu Dian |
| 14. Ibu Dian modal $30k | Skenario hitung | NUMERIC ×2 | Bersih **56.400,3**; biaya **299,7** |
| 15. Ibu Dian modal $50k | Skenario hitung | NUMERIC ×2 | Bersih **97.000,5**; biaya **499,5** |
| 16. Ibu Dian modal $100k | Skenario hitung | NUMERIC ×2 | Bersih **159.501**; biaya **999** |

Perubahan yang disengaja:

- Pertanyaan “komisi yang diterima konsultan” diubah menjadi “total biaya
  transaksi (facility fee + VAT)” karena situs resmi hanya menetapkan
  facility fee, bukan porsi komisi konsultan. Esensi biaya tetap diuji.
- Harga `$24055` pada soal asli diperbaiki menjadi `$2.405,5` dan asumsi
  lot/margin ditulis eksplisit.
- Salah ketik (“nelakukan”, “Lasannya”) diperbaiki; tidak mengubah maksud.

#### 4.2 Ukuran bank

Target awal: **30 soal bernilai + 1 soal profil** (motivasi; pilihan modal
ada di layar sebelum tes, bukan di bank soal). Komposisi:

| Kategori | Jumlah | Isi |
|---|---|---|
| REGULASI | 8 | UU, Bappebti, OJK/BI, KBI, LPS, SITNA, izin |
| PERUSAHAAN | 5 | Profil BPF, legalitas, anggota bursa/KBI, dana terpisah |
| PRODUK | 7 | Emas/perak/BCO/index/forex, contract size, rollover, SPA vs multilateral |
| HITUNG | 10 | 4 soal umum (2 Pak Budi: profit & biaya; 2 short sell/rollover) + 3 tier × 2 soal Ibu Dian |
| PROFIL | 1 | Motivasi/target karier (teks, tidak dinilai) |

Ujian mengambil kuota `REGULASI 7 · PERUSAHAAN 4 · PRODUK 6 · HITUNG 3`.
Dengan 4 soal umum + 2 soal tier, setiap tier punya pool HITUNG 6 soal
sehingga kuota 3 selalu terpenuhi tanpa memunculkan tier lain. Sisa bank
(1 soal per kategori bernilai) menjadi cadangan rotasi antar-percobaan.

Dengan 30 soal bernilai dan ujian 20 soal bernilai + 1 pertanyaan motivasi,
dua percobaan akan mendapat set yang berbeda (overlap minimal 10 soal).
Kuota stratifikasi menjaga setiap percobaan tetap mencakup regulasi,
perusahaan, produk, dan hitungan.

#### 4.3 Impor & verifikasi

- Impor CSV (UTF-8) dengan kolom:
  `code,category,type,prompt,option_a..option_e,correct,tolerance,points,modal_tier,active`.
- `correct` untuk MCQ = huruf opsi; NUMERIC = angka; SHORT_TEXT = alias
  dipisah `|`.
- Kolom `active` di CSV **diabaikan** (hanya dipakai saat ekspor). Semua
  baris hasil impor masuk sebagai **draft** (`active=0`), lalu staff
  meninjau preview (tampilan pelamar + kunci) dan mengaktifkan.
- Dua mode impor:
  - **Tambah baru** (default): kode yang sudah ada **dilewati** dan
    dilaporkan (`inserted`, `skipped`, `errors`). Soal aktif tidak pernah
    berubah karena impor.
  - **Perbarui draft** (opsional, dipilih eksplisit): hanya memperbarui
    baris dengan `active=0`; soal aktif tetap dilewati. Tidak ada mode yang
    menimpa soal aktif.
- Ekspor CSV untuk review di luar aplikasi.
- Bank dianggap siap bila jumlah soal bernilai aktif ≥ `question_count`,
  setiap kategori memenuhi kuota, dan setiap varian modal
  ($30k/$50k/$100k) punya minimal **3** soal HITUNG aktif (cukup untuk
  kuota HITUNG). Selama belum siap, `tkd_settings.active` tidak boleh
  diaktifkan dan portal menampilkan “TKD segera tersedia”.

Seed awal disimpan sebagai `docs/seed/tkd_bank_v1.csv` dan dimuat lewat
`scripts/seed_tkd_bank.py` dengan aturan **insert-if-absent** berdasarkan
`code`: kode yang sudah ada tidak disentuh, sehingga menjalankan ulang
script tidak mengembalikan editan staff. Semua baris baru masuk draft.
Script **tidak** dijalankan otomatis saat startup.

### 5. Pembuatan & penilaian percobaan

#### 5.1 Mulai

`POST /api/recruitment/tkd/start`:

```json
{ "nik": "16 digit", "dob": "YYYY-MM-DD", "token": "<token cabang>",
  "modal_tier": "30k" }
```

`POST /api/recruitment/tkd/status` memakai payload yang sama tanpa
`modal_tier` dan mengembalikan status, skor resmi, attempt aktif, serta
sisa waktu.

1. Rate limit per IP + per NIK.
2. Validasi token cabang aktif. Cabang token dipakai sebagai
   `attempt.branch_code`; tidak wajib sama dengan cabang terakhir kasus,
   karena pelamar bisa membuka tautan cabang mana pun. Staff melihat hasil
   di cabang tempat tes dikerjakan, dan skor resmi tetap satu di kasus.
3. Cocokkan NIK + tanggal lahir ke `recruitment_cases` memakai aturan
   identitas di §2 (kolom `tanggal_lahir`, atau turunan NIK bila kolom
   NULL). Gagal → pesan generik “Data belum lengkap, hubungi Traineer.”
4. Kunci baris kasus (`SELECT ... FOR UPDATE`) untuk mencegah dua start
   bersamaan.
5. Bila ada attempt `BERLANGSUNG`:
   - belum kedaluwarsa → kembalikan attempt itu (resume), bukan membuat baru;
   - sudah lewat `expires_at` → finalisasi sebagai `KEDALUWARSA` dari
     jawaban tersimpan, lalu lanjut ke langkah berikutnya.
6. Bila langkah TKD kasus berstatus `DIKECUALIKAN` → 409 “Dikecualikan
   staff; hubungi Traineer.” Bila skor resmi sudah ≥ ambang lulus → 409
   “Sudah lulus; tidak perlu tes lagi.” Bila jumlah attempt ≥
   `max_attempts` → 409 “Kesempatan habis.” Jadi percobaan ke-2 hanya
   terbuka bila percobaan pertama < 70.
7. Ambil sampel soal:
   - Kuota per kategori dari `tkd_settings.quota` untuk soal bernilai.
   - Untuk HITUNG, hanya varian `modal_tier` yang dipilih yang masuk pool
     (soal tanpa tier dianggap umum). Varian tier lain tidak pernah muncul.
   - Bila soal HITUNG tier terpilih kurang dari kuota, kekurangan diisi
     dari kategori lain — **bukan** dari tier modal lain — agar soal
     rencana modal yang tidak dipilih tidak muncul.
   - Bila total soal bernilai kurang → 409 “Bank soal belum siap.”
   - Tambahkan satu soal `PROFILE_TEXT` aktif di posisi terakhir (tidak
     dihitung dalam `question_count` dan tidak berpoin); jawabannya
     disimpan di `tkd_attempt_items.answer` sebagai `{"text":"..."}`.
   - Tier dipilih **per percobaan** dan disimpan di attempt; percobaan
     kedua boleh memilih tier berbeda, dengan skor tetap dinormalisasi
     ke 0–100.
8. Buat `tkd_attempts` + `tkd_attempt_items` dengan snapshot. Acak opsi
   MCQ bila `shuffle_options=1`.
9. Kembalikan soal tanpa kunci/poin, `expires_at`, dan `remaining_seconds`.

Aturan percobaan:

- Maksimal **2**, tetap. Kolom `max_attempts` disimpan untuk masa depan,
  tetapi API/UI menolak nilai selain 2 pada rilis ini.
- Percobaan ke-2 hanya terbuka bila percobaan pertama belum lulus (< 70).
- Satu percobaan aktif per kasus.
- Percobaan kedaluwarsa tetap dihitung dan dinilai dari jawaban tersimpan.
- Tidak ada percobaan ke-3 lewat portal.

#### 5.2 Selama ujian

- `PUT /api/recruitment/tkd/attempts/<id>/answers/<position>` menyimpan
  jawaban per soal (debounce di klien). Body: `{"answer": <nilai>}` dengan
  bentuk `{"option":"b"}` untuk MCQ, angka untuk NUMERIC, `{"text":"..."}`
  untuk SHORT_TEXT/PROFILE_TEXT. Server memvalidasi bahwa attempt
  milik sesi, status `BERLANGSUNG`, dan belum lewat `expires_at`.
- Jawaban MCQ divalidasi terhadap opsi di snapshot; teks dipotong sesuai
  batas.
- Angka menerima simbol mata uang, spasi, titik, dan koma. Aturan parse:
  bila koma ada → koma = desimal, titik = pemisah ribuan; bila hanya titik
  → titik = desimal. Contoh: `1.866,8`, `1866.8`, dan `$1866,8` sama-sama
  menjadi `1866.8`.
- Timer dihitung server-side dari `started_at`/`expires_at`. Klien hanya
  menampilkan sisa waktu dari server; tidak ada kepercayaan pada jam klien.
- Reload/HP mati: `GET /api/recruitment/tkd/attempts/<id>` mengembalikan
  soal, jawaban tersimpan, dan sisa waktu. Bila waktu sudah habis, server
  memfinalisasi attempt dan mengembalikan hasil, bukan soal.

#### 5.3 Selesai & penilaian

`POST /api/recruitment/tkd/attempts/<id>/submit`:

1. Kunci baris attempt (`FOR UPDATE`); idempoten — submit ulang mengembalikan
   hasil yang sama.
2. Bila `NOW() > expires_at + 60 detik` → finalisasi jawaban tersimpan
   sebagai `KEDALUWARSA`; selain itu `SELESAI`.
3. Nilai tiap item dari snapshot:
   - MCQ: opsi sama persis.
   - NUMERIC: `abs(jawaban − kunci) <= tolerance` (default 0,5; untuk angka
     besar boleh 1).
   - SHORT_TEXT: normalisasi huruf besar, buang spasi/tanda baca, cocok
     dengan salah satu alias.
   - PROFILE: tidak dinilai.
4. `score = round(points_awarded / total_points × 100, 2)`;
   `passed = score >= pass_score_snapshot`.
5. Simpan `submitted_at`, `score`, `correct_count`, `passed`.
6. Sinkronkan langkah TKD (lihat 5.4).
7. Kembalikan `score` (percobaan ini), `passed`, `official_score`
   (`tkd_score` setelah sinkronisasi), `best_score`, `attempts_used`,
   `max_attempts`, dan pesan. Tidak ada kunci/pembahasan.

Ambang lulus default **70**. Karena 20 soal × 1 poin, 14/20 = 70 tepat.

**Finalisasi percobaan terlantar.** Tidak ada cron/worker baru. Attempt
`BERLANGSUNG` yang sudah lewat `expires_at` difinalisasi **lazy** oleh
pemanggilan server berikutnya yang menyentuh attempt/kasus itu:

- `GET /status` (portal dibuka lagi),
- `POST /start` (pelamar menekan mulai/lanjut),
- `GET /attempts/<id>` (resume),
- `GET /attempts/<id>/result` (hasil),
- `GET /api/recruitment/tkd/attempts` (staff membuka tab Hasil).

Finalisasi memakai jawaban tersimpan, menyetel `status='KEDALUWARSA'`,
menghitung skor, dan menyinkronkan skor kasus. Attempt kedaluwarsa tetap
**menghabiskan satu kesempatan** dan bisa menjadi skor terbaik. Bila kasus
tidak pernah dibuka lagi, baris tetap `BERLANGSUNG` di DB sampai ada akses
berikutnya; ini tidak memblokir staff karena tab Hasil juga memicu
finalisasi.

#### 5.4 Sinkronisasi skor & langkah TKD

- Skor otomatis terbaik = `MAX(score)` dari attempt `SELESAI/KEDALUWARSA`.
- Bila `tkd_score_source` bukan `MANUAL`, tulis `tkd_score`,
  `tkd_best_attempt_id`, `tkd_score_source='AUTO'`, dan `tkd_passed`
  (dihitung dengan `pass_score_snapshot` attempt terbaik).
- Baris `recruitment_steps` TKD untuk kasus disinkronkan:
  - `tkd_passed=1` → `SELESAI`, `completed_at` = waktu submit attempt
    terbaik, `evidence_type='tkd_attempt'`, `evidence_id=<attempt id>`,
    `actor='system:tkd'`.
  - ada attempt/skor tetapi belum lulus → `PENDING`, `completed_at=NULL`.
  - belum ada attempt → baris boleh belum ada (`BELUM`).
  - Baris `DIKECUALIKAN` tidak diubah oleh sinkronisasi otomatis.
- Bila kasus punya beberapa baris TKD (pindah cabang), semua baris
  non-`DIKECUALIKAN` disamakan statusnya; skor tetap satu di kasus.
- Setelah 2x gagal, status tetap `PENDING` dengan skor tertinggi. Sistem
  **tidak** otomatis menolak; staff memutuskan lewat koreksi skor atau
  pengecualian.

#### 5.5 Koreksi skor oleh Traineer

`POST /api/recruitment/tkd/score`:

```json
{ "case_id": "RC-...", "score": 75, "reason": "Salah input / koreksi hasil" }
```

- Peran: `traineer`, `ga_hr`, `admin`.
- Skor 0–100 (2 desimal), alasan wajib (maks. 500 karakter).
- Menulis `tkd_score`, `tkd_score_source='MANUAL'`, `tkd_score_note`,
  `tkd_score_updated_by/at`, dan `tkd_passed` (dihitung dengan ambang saat
  ini). Bila belum ada baris TKD, buat untuk cabang terakhir kasus
  (`_latest_branch_code`); bila ada, sinkronkan semua baris non-
  `DIKECUALIKAN`.
- Langkah berstatus `DIKECUALIKAN` tetap dikecualikan; skor kasus tetap
  diperbarui agar tidak hilang.
- Attempt tidak diubah; riwayat tetap utuh.
- Audit `recruitment_tkd_score_edit` berisi `case_id`, skor lama/baru,
  alasan, aktor. NIK tidak masuk audit.

Koreksi manual menang atas auto: attempt baru setelah koreksi tetap dicatat,
tetapi skor resmi tidak ditimpa sampai staff mengedit lagi.

### 6. UI staff

#### 6.1 Tab TKD → Bank Soal

- Daftar soal: kode, kategori, tipe, cuplikan, status aktif, modal tier.
- Filter kategori/status/cari; tombol “Tambah”, “Edit”, “Aktifkan/Nonaktifkan”,
  “Preview”, “Impor CSV”, “Ekspor CSV”.
- Form soal: kategori, tipe, prompt, opsi A–E, kunci, toleransi, poin,
  modal tier. Validasi di klien dan server.
- Preview menampilkan tampilan pelamar dan kunci (khusus staff).
- Penghapusan = nonaktifkan (soft delete); soal yang pernah dipakai tidak
  dihapus fisik.

#### 6.2 Tab TKD → Hasil

- Tabel: nama, NIK termasker, cabang, attempt ke-, status, skor, lulus,
  mulai/selesai, sumber skor (AUTO/MANUAL).
- Filter: cabang, status, rentang tanggal, cari nama/NIK (NIK penuh hanya
  untuk query, respons tetap termasker).
- Detail attempt: pilihan jawaban per soal, kunci, benar/salah, poin,
  modal tier, dan jawaban pertanyaan motivasi (item `PROFILE_TEXT`
  terakhir). Khusus staff.
- Tombol “Koreksi skor” (modal: skor + alasan) → endpoint 5.5.
- Tombol “Cari kasus / koreksi tanpa attempt” untuk tes manual: cari
  nama/NIK, pilih kasus, isi skor + alasan. Ini jalur untuk kandidat yang
  tidak pernah membuka TKD online.
- Ringkasan: jumlah percobaan, skor terbaik, skor resmi.

#### 6.3 Tab TKD → Pengaturan

- Jumlah soal, durasi, ambang lulus, kuota kategori, acak opsi,
  aktif/nonaktif. **Maksimal percobaan tetap 2** (tidak dapat dinaikkan
  lewat UI; kolom disimpan untuk masa depan). **Ubah pengaturan hanya
  `admin`**; `traineer`/`ga_hr` hanya membaca, agar ambang dan status
  global tidak berubah sepihak.
- Indikator kesiapan: “Soal aktif: 30/20 · REGULASI 8/7 ·
  PERUSAHAAN 5/4 · PRODUK 7/6 · HITUNG 10/3 · tiap tier ≥3”.
- Perubahan dicatat di audit. Mengubah ambang tidak mengubah status historis
  sampai ada submit/koreksi baru.

#### 6.4 Tab Tautan

- Satu kartu per cabang (sesuai scope peran):
  - Nama cabang + kode.
  - URL portal: `/app/recruitment-portal?token=<form_token>`.
  - Tombol “Salin tautan”, “QR”, “Cetak QR”.
- Tidak ada tombol salin tautan CV/FirstWork. Teks penjelas: “Bagikan satu
  tautan ini; pelamar memilih CV, FirstWork, atau TKD dari portal.”
- QR dibuat lokal di browser dengan `qrcode` (sudah ada); URL bertoken tidak
  dikirim ke layanan QR pihak ketiga.
- Endpoint baru `GET /api/recruitment/portal-links` (peran receptionist,
  traineer, ga_hr, admin) memakai token yang sama dari
  `cv_online_branch_forms` dan aturan scope cabang yang sudah ada.

### 7. API surface

Publik (tanpa login, `Cache-Control: no-store`):

| Method | Path | Fungsi |
|---|---|---|
| POST | `/api/recruitment/tkd/status` | Status TKD setelah NIK+DOB+token |
| POST | `/api/recruitment/tkd/start` | Mulai/resume percobaan |
| GET | `/api/recruitment/tkd/attempts/<id>` | Resume soal + jawaban |
| PUT | `/api/recruitment/tkd/attempts/<id>/answers/<pos>` | Simpan jawaban |
| POST | `/api/recruitment/tkd/attempts/<id>/submit` | Selesai + skor |
| GET | `/api/recruitment/tkd/attempts/<id>/result` | Hasil percobaan |

Staff (`traineer`, `ga_hr`, `admin` kecuali disebut lain):

| Method | Path | Fungsi |
|---|---|---|
| GET | `/api/recruitment/tkd/questions` | Daftar soal + kunci |
| POST | `/api/recruitment/tkd/questions` | Tambah soal |
| PUT | `/api/recruitment/tkd/questions/<id>` | Edit soal |
| POST | `/api/recruitment/tkd/questions/<id>/toggle` | Aktif/nonaktif |
| POST | `/api/recruitment/tkd/questions/import` | Impor CSV (draft) |
| GET | `/api/recruitment/tkd/questions/export.csv` | Ekspor CSV |
| GET | `/api/recruitment/tkd/attempts` | Daftar hasil |
| GET | `/api/recruitment/tkd/review/<id>` | Detail hasil + kunci (khusus staff) |
| POST | `/api/recruitment/tkd/score` | Koreksi skor resmi |
| GET/PUT | `/api/recruitment/tkd/settings` | Baca/ubah pengaturan |

Catatan: path publik `GET /api/recruitment/tkd/attempts/<id>` hanya
mengembalikan soal + jawaban tersimpan tanpa kunci dan hanya untuk sesi
pelamar. Detail staff memakai prefix `review/` agar tidak bertabrakan dan
tidak bisa diakses tanpa login.
| GET | `/api/recruitment/portal-links` | Link portal per cabang (termasuk receptionist) |

Perubahan endpoint lama:

- `GET /api/recruitment/cases` menambahkan `tkd_score`, `tkd_score_source`,
  `tkd_score_note`, `tkd_passed` di level kasus (NIK tetap termasker).
  Dashboard Kasus menampilkan skor itu di kolom TKD, bukan per baris cabang.
- `POST /api/recruitment/steps/<id>/evidence` untuk TKD: bila `score`
  diisi, tulis ke skor kasus (`MANUAL`) lewat aturan 5.5 dan hitung status;
  bila kosong, perilaku lama (`SELESAI`) dipertahankan.
- `GET /api/recruitment/tkd/settings`: peran baca `traineer/ga_hr/admin`;
  **ubah hanya `admin`** (lihat 6.3).

### 8. Keamanan & privasi

- **Kunci jawaban hanya di server.** Response publik tidak memuat
  `answer`, `points`, `is_correct`, atau pembahasan.
- **Snapshot** membekukan soal/kunci/opsi/poin per attempt; edit bank tidak
  mengubah skor lama.
- **Identitas**: NIK + tanggal lahir harus cocok dengan `recruitment_cases`;
  token cabang aktif wajib untuk status/start. Pesan gagal dibuat generik.
- **Sesi**: Flask session menyimpan `tkd_case_id`, `tkd_verified_at`,
  `tkd_branch` (tanpa NIK), berlaku 2 jam. Attempt hanya bisa diakses bila
  `attempt.case_id` sama dengan sesi.
- **Rate limit** (Redis, pola `redis_rate_hit`):
  - status/start: 10/menit/IP + 5/menit/NIK (hash);
  - simpan jawaban: 60/menit/attempt;
  - submit: 5/menit/attempt.
- **Audit** tanpa NIK: start, submit, koreksi skor, CRUD bank, perubahan
  pengaturan, impor CSV.
- **Anti-enumerasi**: status TKD hanya menjawab setelah NIK+DOB cocok;
  NIK tidak pernah dikembalikan; daftar staff memakai `nik_masked`.
- **Input**: prompt/opsi teks biasa (Vue escaping), batas panjang prompt
  2.000, opsi maks. 6, CSV maks. 500 baris.
- **SQL** parameterized; nama tabel/kolom tidak dari input pengguna.
- **CSRF**: endpoint publik mengubah state hanya dengan sesi TKD + attempt
  id; start memerlukan token cabang. Cookie `SameSite=Lax`, `HttpOnly`,
  `Secure` di produksi.
- **Tanpa PII di URL**: attempt id opaque, bukan NIK.

### 9. Edge cases

| Kasus | Perilaku |
|---|---|
| Bank belum siap / settings nonaktif | Portal “TKD segera tersedia”; start 409 |
| Dua tab mulai bersamaan | Kunci baris kasus; tab kedua mendapat attempt yang sama |
| Submit ganda | Idempoten; hasil sama |
| HP mati / refresh | Jawaban tersimpan; resume dengan sisa waktu |
| Waktu habis saat submit | Toleransi 60 detik; lewat itu dinilai `KEDALUWARSA` |
| Soal diedit saat attempt berjalan | Snapshot attempt tidak berubah |
| Ambang lulus diubah | Attempt lama menyimpan `pass_score_snapshot`; status lama tidak dihitung ulang |
| Koreksi manual lalu ada attempt baru | Skor resmi tetap `MANUAL` sampai diedit lagi |
| Tanggal lahir kasus kosong | Dipakai tanggal turunan NIK; bila NIK tidak menghasilkan tanggal valid → staff mencatat skor manual |
| Baris TKD lama `SELESAI` tanpa skor | Portal “skor belum tercatat”; staff mengisi skor manual |
| Percobaan ditinggalkan | Difinalisasi lazy saat status/start/resume/hasil diakses; tetap dihitung satu kesempatan |
| Tier modal dipilih, soal tier kurang | Kekurangan diisi dari kategori lain, bukan tier modal lain |
| Token cabang dirotasi | Link lama gagal untuk start; attempt aktif tetap bisa diselesaikan lewat sesi |
| Pelamar ganti NIK di tengah jalan | Sesi terikat kasus lama; NIK baru harus verifikasi ulang |
| Langkah TKD sudah `DIKECUALIKAN` | Koreksi skor boleh, status tetap dikecualikan |

### 10. Migrasi & rilis

1. Tambah `modules/tkd_schema.py` (`ensure_tkd_schema`) dan panggil di
   `app.py` setelah `ensure_recruitment_schema()`. Termasuk ALTER kolom
   skor di `recruitment_cases` yang idempoten.
2. Perbarui `init.sql` dengan DDL baru + kolom skor kasus.
3. Deploy dengan `tkd_settings.active=0` (fitur terlihat staff, belum bisa
   dipakai pelamar).
4. Jalankan `scripts/seed_tkd_bank.py` (draft). Staff meninjau kunci di
   Bank Soal, lalu mengaktifkan soal dan settings.
5. Uji pilot 1 cabang dengan beberapa kandidat; bandingkan skor hitung
   dengan kalkulator manual.
6. Umumkan satu tautan portal lewat tab Tautan; hentikan pembagian tautan
   CV/FirstWork.
7. Catat di `docs/internal/PROGRESS.md` dan CHANGELOG.

Tidak ada dependency baru. `qrcode` dan `csv` sudah tersedia.

### 11. Pengujian

Backend (pytest):

- Penilaian MCQ, numeric (koma/titik/toleransi), short text (alias,
  normalisasi).
- Sampel stratifikasi memenuhi kuota; hanya varian tier terpilih yang
  masuk, tier lain tidak muncul; setiap tier punya cukup soal HITUNG.
- Batas 2 attempt; attempt aktif tidak menduplikasi; expiry difinalisasi
  lazy saat status/start/resume/hasil diakses dan tetap dihitung satu
  kesempatan.
- Skor terbaik = nilai tertinggi; status langkah benar.
- Koreksi manual: simpan, audit, tidak ditimpa auto, status dihitung ulang;
  skor resmi manual yang lebih rendah tetap ditampilkan ke pelamar.
- Kasus lama `SELESAI` tanpa skor ditampilkan sebagai “belum tercatat”.
- Impor CSV melewati kode yang sudah aktif; seed insert-if-absent tidak
  mengubah baris yang ada.
- NIK/DOB salah, token salah, sesi salah → ditolak tanpa kebocoran.
- Response publik tidak memuat kunci/poin (assert key absence).
- Snapshot tidak berubah setelah edit bank.
- Migrasi/ALTER idempoten; seed idempoten.

Frontend (vitest):

- Portal: status kartu, aturan sebelum mulai, pilihan modal, timer,
  autosave, submit, hasil, “coba lagi”, “kesempatan habis”.
- Hub: tab sesuai peran, redirect tab terlarang, rute lama tetap hidup,
  `/first-work` tanpa login tetap ke form publik.
- Bank soal: validasi form, preview, impor/ekspor.
- Hasil: filter, detail, modal koreksi skor.
- Tautan: satu link per cabang, salin, QR.

Manual (viewport 375px):

- Mulai → jawab → kunci layar → buka lagi → lanjut → submit.
- Buka portal lagi dengan NIK+DOB → skor terlihat.
- Dua percobaan → skor resmi = tertinggi (sebelum koreksi manual).
- Koreksi skor oleh Traineer → pelamar melihat skor resmi baru.

### 12. Yang diserahkan ke builder

- Menulis 30 soal seed lengkap (variasi di luar 16 soal inti di tabel 4.1)
  dan memverifikasi kuncinya bersama HR/Traineer.
- Memilih nama akhir endpoint/kolom bila ada konvensi repo yang lebih pas.
- Merapikan gaya UI mengikuti komponen yang sudah ada (`PageHeader`, `Modal`,
  `alert`, `btn`, `card`).
- Menentukan apakah pertanyaan motivasi wajib atau opsional (default:
  opsional, sebagai soal terakhir sebelum submit).
- Menyusun fixture tes dan urutan rilis internal.

## Pertanyaan yang masih terbuka

Tidak ada yang menghalangi implementasi. Dua hal yang perlu dikonfirmasi
saat review desain:

1. **Jumlah soal/durasi**: default 20 soal, 25 menit, lulus 70. Semua bisa
   diubah di Pengaturan tanpa kode. Apakah angka ini disetujui?
2. **Bank soal draft**: seed diimpor sebagai draft dan baru aktif setelah
   HR/Traineer memeriksa kunci. Apakah alur review ini diterima, atau mau
   langsung aktif dengan tanggung jawab verifikasi di tim?
