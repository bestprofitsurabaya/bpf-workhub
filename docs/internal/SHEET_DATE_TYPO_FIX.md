# 📝 Paket Koreksi Google Sheet — Typo Tanggal Overtime (18 sel)

Konteks: DB sudah dikoreksi (17 via repair script + 1 estimasi sel rusak,
semua ber-jejak audit `overtime_update`). Tanpa koreksi di SHEET, full sync
(🔄 Refresh) akan menimpa DB dengan nilai salah lagi. Tab yang diedit =
**tab PERTAMA** tiap spreadsheet (bridge membaca getSheets()[0]).

## Spreadsheet 1 — Driver
ID: `1L-7ZT0p48gVZEbDJS-azMqpGobmvmqCDB9J6sAB3DGM`
https://docs.google.com/spreadsheets/d/1L-7ZT0p48gVZEbDJS-azMqpGobmvmqCDB9J6sAB3DGM/edit

| Baris sheet | Nama | NO FORM | Timestamp submit | Nilai sekarang | Ubah menjadi |
|---:|---|---|---|---|---|
| 2783 | Rizky pratama adi nugraha | 2784 | 2023-06-20 23:00 | 2923-06-15 | **2023-06-15** |
| 2786 | Rizky pratama adi nugraha | 2787 | 2023-06-20 23:07 | 2923-06-16 | **2023-06-16** |
| 3567 | Fajar rahmat gemilang | 3568 | 2023-12-15 18:53 | 2033-11-23 | **2023-11-23** |
| 3570 | Fajar rahmat gemilang | 3571 | 2023-12-15 18:57 | 2033-11-24 | **2023-11-24** |
| 3573 | Fajar rahmat gemilang | 3574 | 2023-12-15 19:03 | 2033-11-27 | **2023-11-27** |
| 3579 | Fajar rahmat gemilang | 3580 | 2023-12-15 19:14 | 2033-11-30 | **2023-11-30** |
| 3583 | Faat rahmat gemilang | 3584 | 2023-12-15 19:22 | 2033-12-04 | **2023-12-04** |
| 3589 | Fajar rahmat gemilang | 3590 | 2023-12-15 20:05 | 2033-12-08 | **2023-12-08** |
| 3626 | fajar rahmat gemilang | 3627 | 2024-01-18 15:56 | 2033-11-15 | **2023-11-15** ⚠️
| 3646 | fajar rahmat gemilang | 3647 | 2024-01-18 16:33 | 2033-12-26 | **2023-12-26** ⚠️
| 4635 | Rizky abiem s | 4636 | 2024-07-18 08:00 | 2004-07-15 | **2024-07-15** |
| 8348 | Ahmat Mauliddin Haryadi | 8349 | 2026-07-04 10:04 | 2029-06-29 | **2026-06-29** |
| 8709 | Ahmat Mauliddin Haryadi | 8710 | 2026-08-29 21:17 | 2096-08-27 | **2026-08-27** |

> Catatan baris 1921 (sel rusak `00:25:08`): sel itu berformat JAM, bukan tanggal.
> Set format sel ke tanggal dulu (Format → Number → Date), lalu isi nilainya.
> Nilai di tabel adalah ESTIMASI (MM-DD dari census 11 Sep + tahun submit).
> Baris bertanda ⚠️: pengajuan Jan-2024 utk OT Nov/Des — tahun mundur ke 2023
> (OT tidak mungkin setelah submit); sama dgn nilai koreksi DB ber-jejak audit.

## Spreadsheet 2 — OB/Security
ID: `1AsBq-rHssGmv5vHAzorrphZeNxchodkJQXz1wdBPoms`
https://docs.google.com/spreadsheets/d/1AsBq-rHssGmv5vHAzorrphZeNxchodkJQXz1wdBPoms/edit

| Baris sheet | Nama | Timestamp submit | Nilai sekarang | Ubah menjadi |
|---:|---|---|---|---|
| 55 | Edwin P | 2026-01-14 06:52 | 1926-01-08 | **2026-01-08** |
| 56 | Edwin P | 2026-01-14 06:53 | 1926-01-09 | **2026-01-09** |
| 60 | Edwin P | 2026-01-14 07:00 | 1926-01-13 | **2026-01-13** |
| 75 | Edwin P | 2026-01-15 21:34 | 1926-01-14 | **2026-01-14** |

## Setelah semua sel dikoreksi
1. 🔄 Refresh Data Overtime (full sync) di aplikasi — nilai baru menimpa DB.
2. Verifikasi sisa anomali = 0 (saya bisa jalankan census ulang kapan pun).
3. KHUSUS OB/Security: 4 baris lama (OTL-SH-3567…, OTL-SH-468f…, OTL-SH-e457…,
   OTL-SH-1a34…) akan JADI yatim karena kunci sinkronnya memuat tanggal —
   setelah sync ulang saya yang menghapusnya dari DB (ber-jejak audit).
4. KHUSUS Driver: aman otomatis — kunci sinkron (nama|timestamp) tidak berubah.

---

## 📨 Template pesan permintaan akses edit sheet Driver

Salin-teks pesan di bawah ini untuk dikirim ke pemilik spreadsheet
(email/WA). Isi tabel sudah final — cukup ganti [NAMA] sebelum kirim.

---

**Subjek: Permohonan akses edit — Sheet Overtime Driver (14 tanggal perlu dikoreksi)**

Selamat pagi/siang Pak/Bu,

Saya [NAMA] dari tim IT — PT Bestprofit Futures. Menghubungi terkait
spreadsheet **Overtime Driver** yang dikelola Bapak/Ibu:

https://docs.google.com/spreadsheets/d/1L-7ZT0p48gVZEbDJS-azMqpGobmvmqCDB9J6sAB3DGM/edit

Dari audit data overtime (14 September), ditemukan **14 baris dengan salah
ketik tahun** pada kolom "Tanggal Overtime" (contoh: 2923-06-15, 2033-11-23,
1926-01-08). Kemungkinan besar salah ketik saat input, dan nilai ini ikut
tersalin ke aplikasi BPF WorkHub setiap kali data disinkronkan.

Mohon kesediaan Bapak/Ibu untuk **memberi akses edit** (Share → role *Editor*
ke alamat tim IT) **atau langsung mengoreksi 14 sel berikut** di **tab paling
kiri/k pertama** spreadsheet:

| Baris | Nama | Tanggal sekarang | Ubah menjadi |
|---:|---|---|---|
| 1921 | Rizky Pratama | *sel rusak berformat jam (00:25:08)** | **2021-09-22** |
| 2783 | Rizky pratama adi nugraha | 2923-06-15 | **2023-06-15** |
| 2786 | Rizky pratama adi nugraha | 2923-06-16 | **2023-06-16** |
| 3567 | Fajar rahmat gemilang | 2033-11-23 | **2023-11-23** |
| 3570 | Fajar rahmat gemilang | 2033-11-24 | **2023-11-24** |
| 3573 | Fajar rahmat gemilang | 2033-11-27 | **2023-11-27** |
| 3579 | Fajar rahmat gemilang | 2033-11-30 | **2023-11-30** |
| 3583 | Fajar rahmat gemilang | 2033-12-04 | **2023-12-04** |
| 3589 | Fajar rahmat gemilang | 2033-12-08 | **2023-12-08** |
| 3626 | Fajar rahmat gemilang | 2033-11-15 | **2023-11-15** |
| 3646 | Fajar rahmat gemilang | 2033-12-26 | **2023-12-26** |
| 4635 | Rizky abiem s | 2004-07-15 | **2024-07-15** |
| 8348 | Ahmat Mauliddin Haryadi | 2029-06-29 | **2026-06-29** |
| 8709 | Ahmat Mauliddin Haryadi | 2096-08-27 | **2026-08-27** |

\* Khusus baris 1921: sel tanggalnya tersimpan berformat **jam**, bukan
tanggal. Ubah dulu format selnya ke tanggal (Format → Number → Date), baru
isi nilainya.

Catatan: baris 3626 & 3646 diisi Januari 2024 untuk overtime November/Desember
2023 — karena tanggal overtime tidak mungkin setelah tanggal pengajuan, tahun
dikoreksi mundur ke 2023.

Setelah dikoreksi, tim IT akan menjalankan sinkronisasi ulang dan memastikan
tidak ada lagi anomali tanggal di aplikasi. Data di sisi aplikasi saat ini
sudah sementara diperbaiki dan tercatat di audit log, namun dapat tertimpa
kembali bila sheet sumber belum dikoreksi.

Terima kasih banyak atas bantuan Bapak/Ibu.

Hormat kami,
[NAMA] — Tim IT
PT Bestprofit Futures
