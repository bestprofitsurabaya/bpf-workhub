# Absensi Training di Portal Rekrutmen (2 Hari) — Design

Tanggal: 2026-11-25
Status: menunggu persetujuan

## Intent

Peserta rekrutmen dapat mencatat kehadiran training **Hari 1 dan Hari 2**
langsung dari portal satu tautan (`/app/recruitment-portal?token=...`), tanpa
PIN tambahan. Absensi harus aman (identitas + cabang terverifikasi), valid
(satu orang satu catatan per hari), dan tetap mengisi kolom **H1/H2** pada
dashboard Pelamar milik receptionist.

PIN `474747` adalah pintu masuk form UnitedW dan **tidak** dipakai di WorkHub.

## Goals

- Kartu "Training Absensi" di portal aktif (bukan "Segera tersedia").
- Form publik: NIK + tanggal lahir + konfirmasi hadir. Tanpa unggah berkas.
- Hari 2 terkunci sampai Hari 1 tercatat (ditegakkan di server, bukan hanya UI).
- Absensi tercatat di hub Rekrutmen (`recruitment_steps.TRAINING`) dan, bila
  pelamar berhasil dicocokkan, mengisi `applicant_attendance` `training_1` /
  `training_2` sehingga kolom H1/H2 menyala.
- Cabang selalu berasal dari token portal (tidak bisa dipilih pengguna).

## Non-goals

- OCR KTP, foto selfie, tanda tangan digital, cetak kartu.
- PIN gate seperti UnitedW.
- Membuat baris Pelamar baru secara otomatis.
- Mengubah alur manual receptionist (tetap bisa menandai H1–H4 sendiri).
- Mengubah skema tabel `applicants`.

## Pendekatan yang dipilih

**Form publik per hari + tabel absensi baru, dengan pencocokan identitas ketat.**

Alternatif yang ditolak:

1. *Tulis langsung ke `applicant_attendance` tanpa tabel bukti* — tidak ada
   jejak submit portal, dan absensi orang yang belum ada di daftar Pelamar
   akan hilang tanpa catatan.
2. *Satu form berisi dua tanggal sekaligus* — peserta bisa mengisi Hari 2
   sebelum Hari 1 dan bukti per hari menjadi kabur.

## Model data

Tabel baru `training_attendance` (DB master, dibuat idempoten):

| kolom | tipe | catatan |
|---|---|---|
| id | BIGINT PK | |
| case_id | VARCHAR(40) | `recruitment_cases.case_id` |
| nik | CHAR(16) | |
| branch_code | VARCHAR(10) | dari token |
| day | TINYINT | 1 atau 2 |
| nama | VARCHAR(150) | snapshot nama kasus |
| attended_at | DATETIME | waktu server |
| applicant_id | INT NULL | terisi bila berhasil dicocokkan |
| link_status | ENUM('linked','unlinked','ambiguous') | hasil pencocokan |
| ip | VARCHAR(45) | audit |
| user_agent | VARCHAR(255) | audit |
| created_at | TIMESTAMP | |

- `UNIQUE KEY (case_id, branch_code, day)` — satu absensi per hari per cabang.
- `KEY (nik)`, `KEY (applicant_id)`, `KEY (branch_code, attended_at)`.

## Alur

### Portal

1. Pelamar membuka portal dengan token cabang, isi NIK + tanggal lahir, klik
   **Cek** (perilaku sekarang).
2. Kartu "Training Absensi" menjadi aktif dan mengarah ke
   `/app/training-form?token=...`.
3. Di form: NIK + tanggal lahir + pilihan **Hari 1 / Hari 2** + centang
   pernyataan, lalu **Simpan Absensi**.
4. Hari 2 nonaktif (disabled) sampai Hari 1 tercatat; server menolak dengan 409
   bila dipaksa.
5. Setelah simpan: tampil konfirmasi "Absensi Hari N tercatat" + status kedua
   hari + tombol kembali ke portal.

### Verifikasi identitas & cabang

- Token divalidasi ke `cv_online_branch_forms` (`active=1`); cabang tulisan
  diambil dari baris token, bukan dari input.
- NIK + tanggal lahir dicocokkan ke `recruitment_cases` (NIK unik). Bila kasus
  belum ada atau tanggal lahir beda → 404 generik (tidak membocorkan data).
- Rate limit per IP untuk endpoint status dan submit (Redis + fallback memori,
  pola yang sudah dipakai lookup).

### Pencocokan ke Pelamar (kolom H1/H2)

Dilakukan saat submit, tanpa mengubah skema `applicants`:

1. Ambil identitas dari `cv_online_submissions` terbaru dengan NIK tersebut
   (nama, `no_hp_norm`).
2. Cari `applicants` dengan nama ternormalisasi sama **dan** nomor HP
   ternormalisasi sama, status bukan terminal.
3. Tepat satu kandidat → `link_status='linked'`, isi `applicant_id`, lalu
   `INSERT ... ON DUPLICATE KEY UPDATE` ke `applicant_attendance`
   (`training_1`/`training_2`, `marked_by='Portal Training'`, catatan hari).
   Status pelamar naik mengikuti aturan tahap yang sudah ada (tidak pernah
   menurunkan status).
4. Nol kandidat → `link_status='unlinked'`; lebih dari satu → `'ambiguous'`.
   Absensi tetap tersimpan dan tampil di hub, dengan penanda bahwa data Pelamar
   belum terhubung. Receptionist dapat menandai H1/H2 manual seperti biasa.

Pencocokan sengaja menuntut **nama dan HP sama persis** dan hasil tunggal.
Tidak ada pencocokan "mirip" dan tidak ada pembuatan pelamar otomatis.

### Hub Rekrutmen

- `recruitment_steps` tipe `TRAINING` untuk kasus+cabang:
  Hari 1 → `PENDING`, Hari 2 → `SELESAI` (dengan `evidence_type='training_attendance'`,
  `evidence_id` = id absensi terakhir, `completed_at` = waktu Hari 2).
- Detail kasus menampilkan baris "Training Hari 1/2" beserta waktu dan status
  tautan Pelamar.
- Absensi manual receptionist tetap berjalan dan tidak ditimpa oleh proses ini
  kecuali pada stage yang sama (upsert by applicant+stage).

## Keamanan

- Tidak ada kunci/jawaban atau data pribadi yang dikirim ke browser selain
  status hari milik NIK yang bersangkutan setelah NIK+tanggal lahir benar.
- Token cabang tidak pernah ditulis ke log aktivitas.
- Semua submit dicatat `log_activity_async` (`training_attendance_portal`)
  tanpa NIK penuh (mask 4 digit terakhir).
- CSRF tidak relevan (tanpa sesi); perlindungan = token cabang + verifikasi
  identitas + rate limit.

## Dampak & rilis

- Skema baru otomatis saat startup (pola `ensure_*_schema`), aman diulang.
- Endpoint baru: `GET /api/recruitment/training/status`,
  `POST /api/recruitment/training/attendance`.
- Halaman baru: `/app/training-form` (publik, token).
- Perubahan UI: kartu portal, form training, detail kasus di hub.
- Versi rilis mengikuti kebiasaan repo (minor bump) dan dicatat di CHANGELOG.

## Pengujian

- Backend: token salah/nonaktif, NIK tidak dikenal, tanggal lahir salah,
  Hari 2 sebelum Hari 1 (409), submit ganda (idempoten), linked/unlinked/
  ambiguous, status pelamar tidak menurun, isolasi cabang.
- Frontend: kartu training aktif setelah lookup, form menolak Hari 2 saat
  belum ada Hari 1, pesan sukses, mode seluler 390 px.
- Regresi: suite frontend & backend yang ada tetap lulus.

## Yang diserahkan ke builder

- Nama kolom akhir dan tipe ENUM bila builder menemukan konvensi repo berbeda.
- Penempatan komponen form (view baru vs komponen di `RecruitmentPortalView`).
- Detail copy bahasa Indonesia dan tata letak kartu status.
