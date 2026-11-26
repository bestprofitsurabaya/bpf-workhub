# Desain: Pemeriksaan Identitas Cukup NIK

**Tanggal:** 26 November 2026
**Status:** Disetujui (lingkup: alur pemeriksaan saja)

## Tujuan

Pelamar cukup memasukkan **NIK 16 digit** untuk memeriksa status rekrutmen,
mencatat absensi training, dan membuka TKD. Tanggal lahir tidak lagi diminta
pada alur pemeriksaan.

## Alasan

- Tanggal lahir sudah terenkode di dalam NIK (digit 7–12, `DDMMYY`, dengan
  `+40` pada tanggal untuk perempuan). Meminta tanggal lahir ulang tidak
  menambah keamanan; hanya menambah friksi dan peluang salah isi.
- Satu-satunya kunci identitas yang benar-benar dipakai sistem adalah NIK
  (`recruitment_cases.nik` unik).
- Tanggal lahir tetap berguna sebagai **data diri**, bukan alat verifikasi,
  sehingga isian di CV Online dan FirstWork tidak dihapus.

## Perubahan

### Backend

| Berkas | Sebelum | Sesudah |
|---|---|---|
| `modules/routes_recruitment.py` | lookup wajib `nik` + `dob` valid | lookup cukup `nik` 16 digit |
| `modules/training_service.py` | `_case_for(cursor, nik, dob)` | `_case_for(cursor, nik)` |
| `modules/training_service.py` | `attendance_status(nik, dob, branch)` | `attendance_status(nik, branch)` |
| `modules/training_service.py` | `record_attendance(nik, dob, branch, day)` | `record_attendance(nik, branch, day)` |
| `modules/routes_training.py` | status/absensi wajib `nik` + `dob` | cukup `nik` |
| `modules/tkd_service.py` | `verify_identity(cursor, nik, dob)` | `verify_identity(cursor, nik)` |
| `modules/routes_tkd.py` | body wajib `nik` + `dob` + `token` | body wajib `nik` + `token` |

### Frontend

| Berkas | Perubahan |
|---|---|
| `RecruitmentPortalView.vue` | hapus state/input tanggal lahir; lookup cukup `nik`; panel TKD tanpa `dob` |
| `TrainingFormView.vue` | hapus state/input tanggal lahir; status & absensi cukup `nik` |
| `RecruitmentTkdPanel.vue` | hapus prop `dob`; identitas `{ nik, token }` |

### Keamanan yang dipertahankan

- Rate limit per IP pada lookup, training, dan TKD tetap aktif.
- NIK penuh tidak pernah dikembalikan ke browser; nama tetap disamarkan.
- Token cabang tetap wajib dan tidak pernah diterima dari input pengguna
  untuk menentukan cabang.
- Kunci jawaban TKD tetap tidak pernah dikirim ke browser.

## Non-tujuan

- Tidak menghapus tanggal lahir dari form CV Online/FirstWork.
- Tidak mengubah skema database.
- Tidak mengganti logo: `bestprofit-futures.co.id/assets/bpf-logo.png`
  identik byte-per-byte dengan `static/bpf-logo.png` (SHA-256 sama).

## Copy yang Dihumaniskan

- Portal: "Masukkan NIK untuk melihat rangkuman dan melanjutkan proses."
- Data tidak ditemukan: "Kami belum menemukan data dengan NIK tersebut.
  Mohon periksa kembali 16 digitnya, lalu coba lagi."
- Training: "Data peserta belum kami temukan. Mohon periksa kembali NIK Anda."
- TKD: "Data belum cocok. Periksa kembali NIK Anda atau hubungi Traineer cabang."
- Hitungan soal TKD: "21 soal (20 dinilai)" agar konsisten dengan
  "Soal 1 dari 21".

## Pengujian

- Unit backend: lookup tanpa `dob`, training service/route tanpa `dob`,
  TKD verify tanpa `dob`.
- Unit frontend: portal & training tidak merender input tanggal lahir;
  panel TKD menerima `{ token, nik }`.
- Regresi: hari 2 tetap terkunci, NIK tidak bocor, token salah tetap ditolak.
