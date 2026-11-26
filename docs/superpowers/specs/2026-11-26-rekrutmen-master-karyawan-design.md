# Design — Integrasi Rekrutmen & Master Karyawan (26 November 2026)

Status: menunggu persetujuan
Rilis: C (rekrutmen) lalu D (master karyawan)

## Intent

Rekrutmen WorkHub sekarang punya empat pintu yang datanya belum benar-benar
mengalir: portal publik meminta NIK + tanggal lahir, CV Online menyimpan data
standar, FirstWork meminta ulang hampir semua isian, dan dashboard Pelamar milik
resepsionis tidak punya NIK sehingga tidak bisa disatukan dengan kasus portal.
Di sisi lain, In-Out Karyawan hanya berisi 1.657 baris sheet dengan 76 nama
panggilan dan tidak dipakai lagi; belum ada master karyawan yang bisa dicari
resepsionis dan dilihat lengkap oleh GA HR.

Tujuan desain ini: **satu orang, satu NIK, satu riwayat**—dari dicatat
resepsionis, mengisi CV, training, TKD, FirstWork, sampai menjadi karyawan.
Portal publik tetap ada, tetapi menjadi pintu yang tenang dan fleksibel:
cek NIK sekali, lihat langkah berikutnya, dan boleh mengerjakan tahap mana pun
yang sudah terbuka—termasuk langsung FirstWork setelah CV, sementara tahap lain
menyusul.

## Goals

- NIK wajib saat resepsionis mencatat pelamar baru; satu kasus per NIK di
  master, lintas cabang.
- Portal publik: cek NIK **sekali**, tanpa tanggal lahir; tampilan elegan;
  tahap boleh dilewati/dikerjakan belakangan setelah CV selesai.
- FirstWork cukup unggah KTP; data lain diambil dari CV + OCR KTP; kartu nama
  digital resmi berjabatan **Business Consultant** bisa diunduh/dicetak.
- Menu rekrutmen menjadi **3 tab**: Data Rekrutment, Soal TKD, Tautan Portal.
- Tab Data Rekrutment menampilkan satu baris per orang dan linimasa lengkap:
  verifikasi, interview, H1–H4, pulang (mengundurkan diri), lulus, CV, training
  H1/H2, TKD, FirstWork—masing-masing dengan waktu, aktor, cabang, dan alasan.
- Master karyawan lengkap: semua peserta FirstWork lama dianggap aktif; GA HR
  menonaktifkan yang sudah keluar. Resepsionis mencari nama/NIK lalu mencatat
  keluar/masuk dengan satu klik; GA HR melihat data lengkap.
- Data awal diisi dari FirstWork lama, unitedw, dan 76 nama In-Out lama;
  idempoten, dapat diulang, dan tidak mengubah data sumber.

## Non-goals

- Payroll, gaji, rekening bank, BPJS, kontrak kerja, dan dokumen kepegawaian
  lain.
- Mengubah mesin TKD, bank soal, atau penilaian yang sudah ada.
- Memigrasikan baris In-Out lama sebagai absensi baru; baris lama hanya arsip.
- Aplikasi mobile native; tetap web responsif.
- Menghubungkan setiap karyawan ke akun `users` aplikasi (bisa menyusul).
- Notifikasi WhatsApp/email, pengingat rotasi PIN, atau integrasi eksternal.
- Menjadikan OCR KTP sebagai verifikasi hukum; OCR hanya bantuan isi.

## Anti-goals

- Dua orang/kasus untuk NIK yang sama.
- Data resepsionis dan data portal tetap di dunia terpisah.
- Memaksa urutan tahap selain gerbang CV dan kunci Training Hari 2.
- Endpoint publik yang bisa dipakai memetakan cabang/tahap lewat tebakan NIK.
- Master karyawan yang mengklaim semua orang aktif tanpa kendali GA HR.
- NIK lengkap di URL, log, PDF, atau respons publik.

## Fakta & batasan yang sudah diperiksa

- `applicants` berada di **DB cabang**; `recruitment_cases`,
  `recruitment_steps`, `case_branch_history`, `training_attendance`,
  `cv_online_submissions`, dan `first_work_submissions` berada di **DB master**.
- `applicants` **belum punya kolom NIK**. Status yang ada: `interview`,
  `training_1`–`training_4`, `lulus`, `resigned`, `rejected`.
- "Pulang" yang dimaksud pengguna = **mengundurkan diri** (`resigned`) dengan
  alasan wajib; bukan status baru.
- Sheet FirstWork lama: 1.845 baris, 1.737 NIK valid unik, 104 NIK tidak valid,
  4 NIK ganda. Sudah terwakili di `first_work_submissions` (1.738 baris lama)
  dan sudah di-backfill sebagai kasus pada Rilis B.
- Unitedw: 226 pengajuan 13–24 Nov sudah diimpor; **44 pengajuan baru 25 Nov
  2026** dengan 24 kolom lengkap belum masuk.
- In-Out lama: 1.657 baris, **76 nama unik**, format nama panggilan, dan **0
  irisan nama** dengan FirstWork. Ini populasi staf kantor, bukan Business
  Consultant.
- `users` aktif: 61; bukan master karyawan dan tidak dipakai sebagai sumber
  utama.
- Peran yang ada: `receptionist`, `traineer`, `finance`, `ga_hr`, `admin`.
- Kredensial unitedw hanya dipakai untuk riset; tidak disimpan di repo, log,
  atau dokumen.

## Pendekatan yang dipertimbangkan

1. **Satu tulang punggung NIK + linimasa kejadian** *(dipilih)*.
   NIK menjadi kunci kasus di master; setiap perubahan dicatat sebagai event
   bertanggal. Data asli tetap di tabel modulnya; event adalah proyeksi untuk
   membaca riwayat. Master karyawan dibangun dari kasus yang lulus.
2. **Tempel kolom di tabel yang ada**. Tambah `nik` dan `status_changed_at/by`
   di `applicants`, join saat menampilkan. Lebih cepat, tetapi riwayat hanya
   status terakhir, lintas cabang rapuh, dan tidak memenuhi syarat "tahu kapan
   status berubah".
3. **Employee-first**. Sejak intake orang langsung masuk tabel karyawan.
   Paling sederhana untuk out/in, tetapi pelamar yang tidak lolos ikut menjadi
   "karyawan", migrasi berat, dan makna pelamar/karyawan bercampur.

**Dipilih: 1**, karena memenuhi kebutuhan riwayat, lintas cabang, dan pemisahan
makna pelamar vs karyawan tanpa menggandakan data sumber.

## Keputusan yang sudah disetujui pengguna

- NIK wajib untuk pencatatan pelamar baru oleh resepsionis.
- "Pulang" = mengundurkan diri dengan alasan wajib.
- Semua peserta FirstWork lama dianggap karyawan aktif; GA HR menonaktifkan
  yang sudah keluar.
- Portal publik tetap ada, tampilannya lebih elegan, dan tahap boleh
  dilewati/dikerjakan belakangan; contoh: CV → FirstWork → training/TKD.
- Menu rekrutmen cukup 3 tab.
- Data awal diambil dari unitedw + sheet lama; pengguna akan memberikan akses.
- Dua rilis berurutan: C (rekrutmen) lalu D (master karyawan).

## Design

### A. Identitas, intake, dan kasus

**Kolom baru di `applicants` (DB cabang, idempoten):**

| kolom | tipe | catatan |
|---|---|---|
| `nik` | CHAR(16) NULL | 16 digit; wajib untuk input manual baru |
| `nik_source` | VARCHAR(20) DEFAULT '' | `manual`, `sheet`, `cv_link`, `import` |
| `linked_at` | DATETIME NULL | kapan NIK berhasil ditautkan |
| `link_status` | ENUM('linked','unlinked','ambiguous') DEFAULT 'unlinked' | untuk baris lama/sheet |

- Tambah `UNIQUE KEY uq_applicants_nik (nik)` per DB cabang. MySQL mengizinkan
  banyak NULL, jadi baris lama tanpa NIK tetap aman.
- Satu NIK boleh punya **satu baris `applicants` per cabang**. Perpindahan
  cabang tidak memblokir: cabang baru membuat baris sendiri yang menempel ke
  kasus yang sama. Baris cabang adalah **sumber aksi** (verifikasi, interview,
  H1–H4, pulang, lulus); status, tahap, dan kehadiran yang ditampilkan adalah
  **agregat tingkat kasus** dari event master, sehingga dua cabang tidak bisa
  menampilkan status berbeda untuk orang yang sama.
- Input manual baru: NIK wajib 16 digit, divalidasi dengan `normalize_nik`.
  NIK ganda di cabang yang sama ditolak 409 dengan menunjuk `display_id` yang
  ada.
- Baris hasil sync sheet/legacy boleh tanpa NIK; UI menandainya
  **"Belum tertaut"** dan menyediakan aksi **Tautkan NIK** (resepsionis/GA HR).
- Verifikasi manual tidak lagi otomatis saat input. Resepsionis menekan
  **Verifikasi** setelah memeriksa data; waktunya masuk linimasa. Baris hasil
  sync yang sudah membawa `verified_by/verified_at` tetap dianggap terverifikasi.

**Kasus master (`recruitment_cases`) tetap menjadi identitas global.**

- Helper baru `ensure_case(nik, nama, branch_code, source)` di
  `modules/recruitment_service.py`:
  - bila NIK sudah ada, pakai kasus itu; isi nama hanya bila nama kasus kosong;
  - bila belum ada, buat kasus dengan `case_id` opak (pola Rilis A);
  - catat `case_branch_history` (first/last seen) tanpa memblokir perpindahan.
- Alur input manual:
  1. Validasi NIK.
  2. Cek duplikat NIK di DB cabang.
  3. `ensure_case` di master.
  4. Insert baris `applicants` (dengan NIK) di DB cabang.
  5. Catat event `RECEPTIONIST_CREATED` (dan `VERIFIED` bila petugas langsung
     memverifikasi).
- Bila penulisan master gagal, input manual gagal dengan pesan jelas; tidak ada
  baris cabang tanpa kasus. Bila insert cabang gagal setelah kasus dibuat,
  kasus tanpa pelamar dibiarkan (tidak berbahaya) dan dapat dipakai ulang.
- Sync sheet: bila sheet punya NIK, pakai NIK; bila tidak, cocokkan nama + HP;
  bila tetap tidak ketemu, simpan `nik=NULL` + `link_status='unlinked'`.
  Sync tidak boleh menimpa NIK yang sudah diisi manual.
- Backfill penautan lama (skrip sekali jalan):
  - Untuk setiap pelamar tanpa NIK, cari CV terbaru dengan nama + HP sama
    (pola `_resolve_applicant` di `training_service`, dibalik).
  - Bila hasil tunggal, isi NIK + `link_status='linked'`, `ensure_case`, catat
    event.
  - Bila ambigu, tandai `ambiguous` dan laporkan; jangan menebak.

### B. Linimasa kejadian (`recruitment_events`, DB master)

| kolom | tipe | catatan |
|---|---|---|
| `id` | BIGINT PK | |
| `case_id` | VARCHAR(40) | |
| `nik` | CHAR(16) | |
| `event_type` | VARCHAR(40) | daftar di bawah |
| `event_at` | DATETIME | waktu bisnis |
| `branch_code` | VARCHAR(10) | cabang saat kejadian |
| `actor_role` | VARCHAR(50) | |
| `actor_name` | VARCHAR(150) | |
| `source_module` | VARCHAR(30) | `applicants`, `cv`, `training`, `tkd`, `firstwork`, `employees`, `manual` |
| `source_id` | VARCHAR(64) | id baris sumber |
| `note` | VARCHAR(500) | alasan/catatan |
| `metadata_json` | TEXT | skor, hari, nomor kartu, dll. |
| `created_at` | TIMESTAMP | waktu ingestion |

- `UNIQUE KEY uq_re_event (source_module, branch_code, source_id, event_type)`
  membuat penulisan idempoten. `source_id` memakai id yang unik global
  (`display_id` untuk pelamar, id master untuk tabel master), bukan id
  branch-local, agar event dari cabang berbeda tidak saling menimpa.
- Index: `(case_id, event_at)`, `(nik, event_at)`, `(branch_code, event_at)`.
- Jenis event minimal:
  `RECEPTIONIST_CREATED`, `VERIFIED`, `INTERVIEW`, `TRAINING_H1`–`TRAINING_H4`,
  `RESIGNED`, `PASSED`, `REJECTED`, `CV_SUBMITTED`, `TRAINING_PORTAL_D1`,
  `TRAINING_PORTAL_D2`, `TKD_STARTED`, `TKD_SUBMITTED`, `TKD_SCORED`,
  `FIRSTWORK_SUBMITTED`, `CARD_ISSUED`, `EMPLOYEE_CREATED`,
  `EMPLOYEE_DEACTIVATED`, `EMPLOYEE_REACTIVATED`, `NIK_LINKED`.
- **Sumber kebenaran tetap tabel modul.** Event ditulis setelah transaksi sumber
  commit, dengan pola *best effort*: bila master gagal, aksi pengguna tetap
  berhasil, kegagalan dicatat, dan skrip
  `scripts/rebuild_recruitment_events.py` dapat membangun ulang event dari
  tabel sumber (idempoten). Tidak ada transaksi terdistribusi.
- Endpoint riwayat:
  `GET /api/recruitment/cases/<case_id>/timeline` (staff) mengembalikan event
  terurut, NIK termasker sesuai peran.
- Event ditulis dari:
  - input/verifikasi/kehadiran/status pelamar (DB cabang → master),
  - submit CV, training portal, TKD, FirstWork (master),
  - promosi/nonaktif karyawan (master).

### C. Portal publik: cek sekali, tahap fleksibel

**Lookup**

- `GET /api/recruitment/lookup?nik=...` — **tanpa DOB**.
- Respons minimal: `{status, known, can_continue, session_token}`.
  `session_token` hanya diterbitkan bila NIK valid (16 digit), ditandatangani,
  berumur 30 menit, dan mengandung `{nik, branch, purpose}`. NIK tidak pernah
  masuk URL.
- Rate limit per IP dipertahankan (mis. 10 percobaan / 10 menit), `no-store`.
- NIK tidak valid → `known=false`, tanpa token.

**Ringkasan**

- `GET /api/recruitment/portal/summary?token=...` mengembalikan:
  - `nama_masked` (nama depan + inisial),
  - `branch_code`, `branch_name`,
  - `stages`: CV/TRAINING/TKD/FIRSTWORK dengan status, waktu selesai, dan
    `can_start`,
  - `next_action`,
  - `card_token` bila FirstWork sudah ada.
- Tidak ada alamat, tanggal lahir, atau NIK lengkap di respons.
- `Cache-Control: no-store`; rate limit; NIK di log termasker.

**Aturan tahap**

- **CV adalah gerbang tingkat kasus.** CV `SELESAI` di cabang mana pun membuka
  tahap lain; step tetap dicatat di cabang tempat aksi dilakukan.
- Setelah CV selesai, **semua tahap terbuka** dan boleh dikerjakan dalam urutan
  apa pun. Contoh: CV → FirstWork → Training → TKD.
- **Training Hari 2 tetap terkunci sampai Hari 1 tercatat** (aturan server yang
  sudah ada, dipertahankan).
- NIK yang dikenal tetapi CV belum selesai hanya menampilkan CTA CV.
- NIK baru/unknown: CTA "Mulai dari CV Online"; token onboarding membawa NIK
  agar form CV tidak menanyakan ulang.
- **Identitas satu sesi untuk semua tahap.** Training dan TKD memakai
  `session_token` yang sama; tidak ada form publik yang meminta tanggal lahir.
  `training_service` dan `tkd_service` memverifikasi token (NIK + cabang +
  purpose), bukan DOB. DOB turunan NIK hanya menjadi data, bukan bukti
  identitas. Tautan langsung tanpa token meminta NIK sekali, lalu menerbitkan
  token; bukan DOB.
- **Cabang token = cabang tautan portal.** Token selalu membawa cabang dari
  tautan (`?token=<token cabang>`); NIK tak dikenal di-onboard ke cabang itu.
  Kasus yang berpindah cabang tetap memakai cabang tautan untuk aksi baru,
  sementara linimasa menampilkan semua cabang.

**UI portal**

- Satu kolom NIK + tombol **Cek**.
- Setelah cocok: kartu sapaan ringkas (nama termasker, cabang), stepper 4 tahap
  yang tenang (Selesai/Berikutnya/Belum), dan kartu aksi.
- Kartu yang selesai tetap bisa dibuka untuk melihat/ mengunduh kartu, tetapi
  tampil redup—bukan papan pengumuman.
- Bahasa: "Langkah berikutnya", bukan "Tahap selesai" yang mencolok.
- Form menerima `?token=<token cabang>&s=<session_token>`; NIK terkunci dan
  tidak perlu diketik ulang. Bila `s` tidak ada (tautan langsung), form boleh
  meminta NIK sekali sebagai fallback.

**Trade-off keamanan yang disadari**

NIK-only + ringkasan stage menambah permukaan enumerasi dibanding lookup
boolean Rilis A. Mitigasi: rate limit, token bertanda tangan dan berumur
pendek, nama termasker, tanpa data sensitif lain, `no-store`, dan audit. Ini
konsekuensi yang diterima demi "cek sekali" dan portal yang menunjukkan langkah
berikutnya.

### D. FirstWork: cukup KTP, lalu kartu

**Form**

- Identitas dari `session_token`: nama, NIK (ditampilkan termasker), cabang.
  Tidak ada isian ulang nama/NIK/pendidikan/HP/referensi.
- Unggah KTP wajib (JPG/PNG/PDF, maks 5 MB) → normalisasi + OCR yang sudah ada.
- Setelah unggah, tampil ringkasan **"Data terbaca dari KTP"** (collapsible):
  nama, NIK, alamat, RT/RW, kel/desa, kecamatan, agama, status kawin,
  kewarganegaraan, berlaku hingga, golongan darah. Pengguna boleh memperbaiki;
  tidak wajib membuka.
- Data CV menang untuk field standar (nama, tempat/tanggal lahir, jenis
  kelamin, alamat, HP, pendidikan). OCR hanya mengisi field yang belum ada.
- Consent tetap wajib.
- Tanpa `session_token`: minta NIK saja; bila CV belum selesai, arahkan ke CV.

**Submit**

- Pastikan kasus ada dan langkah CV `SELESAI`; jika belum, 409 dengan pesan.
- Simpan `first_work_submissions` (pola yang ada), KTP, scan, SHA-256, dan
  field demografi.
- Set langkah `FIRSTWORK` menjadi `SELESAI`, catat event
  `FIRSTWORK_SUBMITTED` + `CARD_ISSUED`.
- Terbitkan `card_token` (bertanda tangan, 7 hari) untuk unduhan publik.
- Kartu tersedia segera setelah submit; dapat diunduh ulang dari portal
  (ringkasan menerbitkan token baru) atau oleh staff.

**Kartu**

- Kelas baru `BusinessConsultantCardPDF` di `modules/pdf_generator.py`.
- Format **A6 landscape (148 × 105 mm)**, satu kartu per halaman, siap cetak;
  kop/logo resmi, nama, **Business Consultant**, cabang, nomor registrasi,
  NIK 4 digit terakhir, QR `BPF-FW:<registration_no>` (payload dipertahankan
  agar pemindai lama tetap bekerja).
- Tidak ada NIK lengkap di teks maupun metadata PDF.
- Endpoint publik: `GET /api/first-work/card/<id>.pdf?t=<card_token>`;
  endpoint staff tetap ada untuk cetak ulang.
- Builder boleh menyesuaikan ukuran setelah uji cetak, tetapi tetap satu kartu
  per halaman dan bukan sertifikat A4.

### E. Menu rekrutmen: 3 tab

`RecruitmentHubView.vue` menjadi:

1. **Data Rekrutment** (`?tab=pelamar`) — komponen baru
   `RecruitmentPeopleView.vue`.
2. **Soal TKD** (`?tab=tkd`) — `TkdView` yang ada, sub-tab Bank Soal/Hasil/
   Pengaturan tetap.
3. **Tautan Portal** (`?tab=tautan`) — `RecruitmentLinksView` yang ada.

- Tab lama `kasus`, `cv`, `firstwork` diarahkan ke `pelamar` (URL lama aman).
- Sidebar tetap satu menu **Rekrutmen**; badge antrean mengikuti tab.
- CV Online dan FirstWork bukan tab lagi; pengelolaannya ada di detail orang.
- `finance` mendapat **Data Rekrutment read-only** (tanpa aksi tulis), melihat
  ringkasan FirstWork dan ekspor CSV; NIK termasker.
- Form publik lama `/apply` **dipensiunkan**: rute diarahkan ke portal; tanpa
  tautan cabang, tampil halaman yang meminta tautan portal ke cabang. Tidak ada
  lagi intake publik tanpa NIK. Sync sheet resepsionis tetap ada untuk data
  lama, dan baris tanpa NIK ditandai **Belum tertaut**.
- Aksi lama layar Pelamar yang tetap hidup di Data Rekrutment: Sync Sheet
  (resepsionis), kelola user-options/upline (admin), hapus baris (GA HR/admin),
  serta laporan/ekspor tahap. Semuanya menjadi tombol toolbar atau aksi detail,
  bukan tab.

**Daftar Data Rekrutment**

- Satu baris per orang/kasus, kolom: nama, NIK termasker, cabang, tahap
  sekarang, status, kejadian terakhir, aksi cepat.
- Filter: cari nama/NIK (NIK penuh dicari di server), cabang, tahap, status,
  "belum tertaut", "perlu tindakan".
- Baris `applicants` tanpa NIK tetap muncul dengan penanda **Belum tertaut**;
  setelah ditautkan, baris bergabung ke kasus.
- Endpoint baru `GET /api/recruitment/people` (staff) menggabungkan kasus
  master + pelamar cabang + event terakhir. NIK lengkap hanya untuk `ga_hr` dan
  `admin`; peran lain menerima NIK termasker, sementara pencarian exact NIK
  penuh tetap diproses di server.
- Detail `GET /api/recruitment/people/<case_id>` mengembalikan kasus, langkah,
  riwayat cabang, event, ringkasan CV, training, TKD, FirstWork, dan tautan
  kartu, dengan aturan masking yang sama.

**Detail orang (drawer/modal)**

- Linimasa vertikal: waktu, aktor, cabang, alasan/catatan.
- Bagian data: identitas, CV, training H1/H2, TKD, FirstWork/kartu.
- Aksi sesuai peran:
  - resepsionis: verifikasi, catat interview/H1–H4, pulang (alasan wajib),
    lulus/jadikan karyawan, tautkan NIK;
  - traineer/GA HR: review CV, evidence Training/TKD, exception, cetak kartu,
    ekspor;
  - GA HR/admin: semua + koreksi.
- Ekspor CV/FirstWork massal tetap tersedia sebagai tombol di tab ini.

### F. Master karyawan

**Tabel `employees` (DB master, NIK global):**

| kelompok | kolom |
|---|---|
| identitas | `id`, `employee_no`, `nik` (unik, NULL untuk legacy), `nama`, `nama_norm`, `tempat_lahir`, `tanggal_lahir`, `jenis_kelamin`, `agama`, `status_perkawinan`, `kewarganegaraan`, `golongan_darah` |
| kontak | `alamat`, `rt_rw`, `kel_desa`, `kecamatan`, `domisili`, `no_hp`, `no_hp_norm`, `email`, `kontak_darurat` |
| pekerjaan | `jabatan` (default **Business Consultant**), `branch_code`, `tanggal_masuk`, `status_kepegawaian`, `atasan`, `referensi` |
| pendidikan | `pendidikan_terakhir`, `sekolah_menengah`, `perguruan_tinggi` |
| asal-usul | `source` (`firstwork`, `unitedw`, `recruitment`, `inout_legacy`, `manual`), `source_uid`, `case_id`, `needs_nik` |
| status | `is_active`, `deactivated_at`, `deactivated_by`, `deactivation_reason` |
| audit | `created_at`, `updated_at` |

- `UNIQUE KEY uq_emp_nik (nik)`; `UNIQUE KEY uq_emp_source (source, source_uid)`;
  index `nama_norm`, `branch_code`, `is_active`.
- `employee_no` memakai counter per cabang, format `KRY-<CABANG>-<5 digit>`
  (pola `first_work_branch_counters`). Bila builder menilai counter berlebih,
  boleh memakai `id` global asalkan tetap unik dan mudah dibaca; keputusan
  builder.
- Baris tanpa NIK sah selama `needs_nik=1`; GA HR melengkapi. NIK NULL tidak
  melanggar unique.

**Tabel `employee_attendance_events`:**

| kolom | tipe |
|---|---|
| `id` | BIGINT PK |
| `employee_id` | BIGINT |
| `nik` | CHAR(16) NULL |
| `branch_code` | VARCHAR(10) |
| `direction` | ENUM('OUT','IN') |
| `event_at` | DATETIME |
| `actor_username` | VARCHAR(100) |
| `actor_name` | VARCHAR(150) |
| `note` | VARCHAR(255) |
| `voided_at` | DATETIME NULL |
| `voided_by` | VARCHAR(100) NULL |
| `void_reason` | VARCHAR(255) NULL |
| `source` | VARCHAR(20) DEFAULT 'app' |
| `created_at` | TIMESTAMP |

- Status "Di Kantor / Di Luar" = arah event terakhir yang tidak di-void.
- Satu klik = satu event; bisa berkali-kali sehari.
- Koreksi oleh GA HR/admin memakai void + event baru, bukan menghapus riwayat.
- Index `(employee_id, event_at)`, `(branch_code, event_at)`.

**Promosi pelamar → karyawan**

- Aksi **Lulus / Jadikan Karyawan** memanggil layanan baru
  `promote_to_employee(case_id, jabatan, branch_code)`:
  - NIK wajib; bila kosong, aksi ditolak dan UI meminta lengkapi NIK.
  - Ambil data dari kasus + CV terbaru + FirstWork terbaru; isi yang kosong.
  - `jabatan` default **Business Consultant**, `tanggal_masuk` hari ini,
    `source='recruitment'`, `case_id` terisi.
  - Bila karyawan dengan NIK sama sudah ada, perbarui field kosong dan
    aktifkan kembali; jangan membuat duplikat.
  - Catat event `EMPLOYEE_CREATED`/`EMPLOYEE_REACTIVATED` + audit.
- Alur lama `register-employee` yang menulis `employee_inout` tidak dipakai lagi
  oleh UI baru. Endpoint lama boleh dipertahankan sebagai alias/deprecated
  sampai Rilis D stabil, tetapi tidak menulis In-Out baru.

**Halaman karyawan (satu rute, dua peran)**

- Rute `/employees`, menu **Karyawan** di grup SDM & Armada, peran
  `receptionist`, `ga_hr`, `admin`.
- Daftar:
  - cari nama/NIK (NIK penuh di server; nama fuzzy),
  - filter cabang, status aktif, `needs_nik`,
  - kolom: nama, NIK (termasker untuk resepsionis), jabatan, cabang, status,
    lokasi sekarang (Di Kantor/Di Luar), kejadian terakhir,
  - tombol toggle **Keluar** / **Kembali** untuk resepsionis.
- Toggle:
  - `POST /api/employees/<id>/attendance` body `{direction, note}`;
  - server menolak arah yang sama dua kali (409);
  - cabang karyawan harus sama dengan cabang sesi (kecuali HO admin);
  - waktu dari server, aktor dari sesi; audit.
- Detail:
  - resepsionis: profil ringkas (NIK termasker), status, riwayat keluar/masuk;
  - GA HR/admin: profil lengkap, edit field HR, nonaktifkan/aktifkan (alasan
    wajib), ekspor, riwayat rekrutmen read-only.
- Arsip In-Out lama:
  - menu In-Out dihapus; `/inout` dialihkan ke `/employees` dengan banner
    "Arsip In-Out lama";
  - data lama tetap bisa dibaca admin/GA HR sebagai arsip, tidak menulis baru.

**Pengisian awal (seed)**

Skrip `scripts/seed_employees.py` (dry-run default, `--commit` untuk menulis):

- Sumber:
  1. `first_work_submissions` (1.738 lama + 226 unitedw yang sudah masuk) —
     sumber utama karena sudah ada di DB dan sudah di-backfill sebagai kasus;
  2. CSV unitedw baru (44 baris 25 Nov 2026) — diimpor lebih dulu dengan
     importer Rilis B, lalu ikut terambil;
  3. sheet FirstWork lama — dipakai untuk rekonsiliasi field yang kosong;
  4. nama unik dari `employee_inout` per DB cabang (76 di SBY) — kerangka staf
     kantor.
- Aturan:
  - Saat **insert pertama**, semua peserta FirstWork/unitedw valid →
    `is_active=1`, `jabatan='Business Consultant'`, `tanggal_masuk` = waktu
    FirstWork pertama, `source='firstwork'`/`'unitedw'`.
  - Seed **tidak pernah mengaktifkan ulang** karyawan yang sudah dinonaktifkan
    GA HR dan tidak menimpa field yang sudah diedit. Untuk identitas yang sudah
    ada, seed hanya mengisi field kosong; `is_active`, `deactivated_*`, dan
    field HR tidak disentuh.
  - NIK tidak valid/kosong (104 baris) → tetap diimpor dengan `nik=NULL`,
    `needs_nik=1`, `source_uid` dari ID FP/hash baris; GA HR melengkapi.
  - NIK ganda → satu baris karyawan; field digabung (yang terbaru menang untuk
    field kosong); `source_uid` alternatif dicatat di `metadata`/catatan.
  - Nama In-Out lama → `source='inout_legacy'`, `jabatan='Staf'`,
    `is_active=1`, `needs_nik=1`; tidak digabung paksa dengan FirstWork karena
    0 irisan nama.
  - Semua aktif sesuai keputusan pengguna; GA HR yang menonaktifkan.
- Idempoten: upsert berdasarkan NIK (bila ada) atau `(source, source_uid)`;
  putaran kedua harus 0 insert.
- Laporan: jumlah inserted/updated/skipped/invalid per sumber, NIK termasker;
  tidak mencetak NIK lengkap.
- File CSV mentah tidak disalin ke repo; setelah impor dihapus dari host/NAS.

### G. Peran & izin

| Peran | Data Rekrutment | Karyawan | Catatan |
|---|---|---|---|
| `receptionist` | cabang sendiri; verifikasi, absensi, pulang, lulus, tautkan NIK | cari + toggle keluar/masuk cabang sendiri; NIK termasker | kasus yang pindah keluar hilang dari daftar cabang asal; riwayat tetap di GA HR/traineer |
| `traineer` | cabang sendiri; review CV, training/TKD, evidence | tidak | |
| `ga_hr` | semua cabang; semua aksi rekrutmen | penuh: edit, nonaktifkan, ekspor, koreksi absensi | NIK lengkap |
| `finance` | Data Rekrutment read-only: ringkasan FirstWork + ekspor | tidak | NIK termasker |
| `admin` | semua + HO agregat | semua | |

- Non-HO selalu terkurung cabang sesi; HO admin melihat semua.
- Pencarian NIK penuh dilakukan di server dengan exact match; tampilan tetap
  termasker untuk peran yang tidak berhak.
- Semua aksi tercatat di audit log dan event.

### H. Migrasi, rilis, dan rollback

**Rilis C — v2.136.0 (rekrutmen)**

1. Skema: `applicants.nik` + index/unique (12 DB cabang),
   `recruitment_events` (master), DDL di runtime helper + `init.sql`.
2. `ensure_case`, penulisan event idempoten, rebuild script.
3. Intake NIK wajib + tautkan NIK + verifikasi eksplisit; `/apply` dialihkan ke
   portal.
4. Portal: lookup NIK-only + token + summary; hapus DOB dari lookup/form
   terkait; stepper dan kartu aksi baru.
5. FirstWork: token, KTP-only, OCR opsional, kartu Business Consultant + token
   unduhan.
6. Menu 3 tab + `RecruitmentPeopleView` + detail linimasa; redirect tab lama.
7. Backfill event dari data yang ada; tautkan pelamar lama (nama+HP) secara
   best-effort; laporkan yang ambigu.
8. Impor 44 pengajuan unitedw baru (dry-run → commit, idempoten).
9. Deploy, stamp v2.136.0, smoke test, dokumentasi.

**Rilis D — v2.137.0 (master karyawan)**

1. Skema `employees`, `employee_attendance_events`, counter nomor karyawan
   (bila dipakai), DDL + `init.sql`.
2. Layanan promosi, API karyawan, toggle absensi, void/koreksi.
3. Halaman `/employees` (resepsionis + GA HR), menu, arsip In-Out.
4. Seed karyawan dari FirstWork/unitedw/In-Out (dry-run → commit), rekonsiliasi
   jumlah.
5. Deploy, stamp v2.137.0, smoke test, dokumentasi.

**Urutan data:** C dulu (NIK + kasus + event), lalu D (karyawan). Impor 44
unitedw sebelum seed karyawan. Semua impor idempoten dan dapat diulang.

**Rollback:** semua perubahan skema aditif (kolom/tabel/index baru); tidak ada
penghapusan kolom. Rute lama dipertahankan sebagai redirect. Impor dapat
dibatalkan berdasarkan penanda `source`/`source_uid`. Perilaku
`register-employee` lama dipertahankan sampai Rilis D terbukti stabil.

### I. Verifikasi & kriteria penerimaan

**Backend**

- Intake: NIK wajib, 16 digit, duplikat ditolak, kasus dibuat/dipakai ulang,
  event tercatat; sync sheet tanpa NIK tidak menimpa NIK manual; NIK yang sama
  di cabang berbeda memakai kasus yang sama dan tidak saling menimpa status.
- Token: lookup tanpa DOB, token bertanda tangan, kedaluwarsa, purpose-bound;
  summary menolak token invalid; rate limit; `no-store`; training dan TKD
  menerima token yang sama dan tidak meminta DOB.
- Tahap: CV gate tingkat kasus (CV selesai di cabang mana pun membuka tahap
  lain); semua tahap terbuka setelah CV; Training Hari 2 tetap terkunci;
  FirstWork setelah CV.
- FirstWork: hanya KTP + consent; OCR mengisi field kosong; data CV tidak
  tertimpa; submit idempoten; card token; PDF tanpa NIK lengkap.
- Event: idempoten, rebuild menghasilkan set yang sama; kegagalan master tidak
  menggagalkan aksi sumber; event cabang berbeda tidak saling menimpa.
- Karyawan: seed idempoten dan tidak mengaktifkan ulang karyawan yang sudah
  dinonaktifkan; NIK NULL + `needs_nik`; duplikat digabung; promosi tidak
  menduplikasi; toggle OUT/IN menolak arah sama; void/koreksi; scope cabang.
- Peran: resepsionis tidak melihat NIK lengkap; GA HR melihat; finance tidak
  mengedit.

**Frontend**

- Portal: satu kolom NIK, ringkasan setelah cek, stepper tenang, tahap bisa
  dibuka dalam urutan apa pun setelah CV, Training Hari 2 disabled.
- Data Rekrutment: daftar gabungan, filter, penanda "belum tertaut", detail
  linimasa, aksi sesuai peran.
- Karyawan: cari, toggle keluar/masuk, status berubah, detail GA HR, nonaktif
  dengan alasan.
- Menu hanya 3 tab rekrutmen.

**E2E (Playwright)**

- Resepsionis input NIK → verifikasi → interview → H1.
- Portal cek NIK → CV → FirstWork (KTP) → unduh kartu → Training → TKD.
- Lulus → karyawan otomatis → resepsionis keluar → kembali → GA HR melihat
  riwayat dan menonaktifkan.
- Pelamar tanpa NIK lama: tautkan NIK → muncul di kasus yang sama.

**Data**

- 1.737 NIK valid FirstWork + 44 unitedw baru + 76 nama In-Out terbaca;
  104 NIK invalid ditandai `needs_nik`.
- Tidak ada NIK ganda pada `employees` (NIK non-NULL).
- Putaran kedua seed/impor: 0 insert.

**Rilis**

- pytest produksi hijau, frontend test + build hijau, stamp 7 titik + DB
  master/12 cabang konsisten, container healthy, smoke test lulus.
- `docs/internal/PROGRESS.md` dan `CHANGELOG.md` diperbarui per rilis.

## Yang diserahkan ke builder

- Ukuran akhir kartu (A6 landscape disarankan) setelah uji cetak.
- Format `employee_no` bila counter per cabang dianggap berlebih.
- Daftar event final (boleh menambah bila sumber data menuntut).
- Batas pagination dan bentuk respons API yang paling praktis.
- Strategi rekonsiliasi nama In-Out yang berupa panggilan.
- Apakah OCR confidence disimpan; disarankan ya, di `metadata_json`.
- Detail visual stepper/kartu, selama tetap tenang dan tidak memamerkan tahap
  selesai.
