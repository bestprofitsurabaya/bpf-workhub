# 📖 Panduan Pengguna BPF WorkHub v2.29.0

> **Siapa pun kamu — sopir, OB, admin, atau pimpinan — panduan ini ditulis untuk kamu.**
> Tidak perlu paham teknis. Cukup ikuti langkah-langkah sesuai bagianmu.
>
> **PT. Bestprofit Futures — Surabaya**

---

## Daftar Isi

1. [Selamat Datang](#1-selamat-datang)
2. [Cara Masuk (Login)](#2-cara-masuk-login)
3. [Untuk OB — Pembelian Air Minum 💧](#3-untuk-ob--pembelian-air-minum)
4. [Untuk Driver — BBM & Perjalanan 🚗](#4-untuk-driver--bbm--perjalanan)
5. [Untuk GA — Verifikasi & Pengawasan 🧾](#5-untuk-ga--verifikasi--pengawasan)
6. [Untuk Finance — Pembayaran & Rekap 💰](#6-untuk-finance--pembayaran--rekap)
7. [Untuk Marketing — Jadwal Appointment 📣](#7-untuk-marketing--jadwal-appointment)
8. [Untuk Chief Driver — Pembagian Tugas 🚛](#8-untuk-chief-driver--pembagian-tugas)
9. [Untuk Receptionist — Pelamar Kerja 🪪](#9-untuk-receptionist--pelamar-kerja)
10. [Untuk Traineer / Upline — Pantau Rekrutan 🎯](#10-untuk-traineer--upline--pantau-rekrutan)
11. [Untuk GA — Aset & Pemeliharaan 🔧](#11-untuk-ga--aset--pemeliharaan)
    - [11.5 Untuk GA HR — Data Overtime ⏰](#115-untuk-ga-hr--data-overtime-)
    - [11.6 Migrasi Data dari Google Sheet 📥](#116-untuk-ga-hr--migrasi-data-driver-dari-google-sheet-)
12. [Untuk Admin — Pengaturan Sistem ⚙️](#12-untuk-admin--pengaturan-sistem)
13. [Kasbon: Alur Lengkap dari A sampai Z](#13-kasbon-alur-lengkap-dari-a-sampai-z)
14. [Untuk IT — News Scraper & Content Management 📰](#14-untuk-it-sebagai-cabang--news-scraper--content-management-)
15. [Mengatasi Masalah (Troubleshooting)](#15-mengatasi-masalah-troubleshooting)
16. [Istilah-istilah Penting](#16-istilah-istilah-penting)

---

## 1. Selamat Datang

Aplikasi ini adalah **satu tempat untuk semua urusan armada dan kantor**:

- **Driver** mencatat pembelian BBM, mengajukan kasbon (uang muka), dan melaporkan perjalanan.
- **OB** mengajukan pembelian air minum galon/botol/gelas.
- **GA, Finance, Marketing, Chief Driver, dan Admin** memverifikasi, menyetujui, dan mengelola semuanya dari dashboard masing-masing.

Setiap orang **hanya melihat menu sesuai tugasnya**. Tidak ada yang tercampur — tiap bagian punya halaman sendiri (prinsip *least privilege*: akses seminimal mungkin).

> 💡 Aplikasi bisa dibuka dari **komputer, laptop, atau HP** — cukup pakai browser.

---

## 2. Cara Masuk (Login)

### 2.1 Halaman Login

1. Buka alamat aplikasi (tanyakan ke Admin jika belum tahu).
2. Halaman **Login** akan muncul.
3. Isi **Username** dan **PIN 6 digit** milikmu.
4. Klik **🔐 Masuk**.

Setelah masuk, kamu otomatis diarahkan ke halaman utama sesuai peranmu:

| Peran | Contoh Username | Langsung dibawa ke |
|-------|----------------|--------------------|
| Admin | `admin` | Dashboard Admin |
| GA | `ga_sby`, `ga_hu`, ... | Dashboard GA |
| Finance | `finance_sby`, `finance_hu`, ... | Dashboard Finance |
| GA HR | `gahr_sby`, `gahr_hu`, ... | Data Overtime |
| Marketing | `marketing_sby`, `marketing_hu`, ... | Marketing Hub |
| Chief Driver | `chief_driver` | Dashboard Chief Driver |
| Driver | `driver_1`, `driver_2`, ... | Aplikasi Driver |
| OB | `ob` | Halaman Air Minum |
| IT | `it_sby`, `it_hu`, ... | News Scraper |

### 2.2 Keluar dari Aplikasi

Klik tombol **🚪 Keluar** di pojok kanan atas. Selalu keluar jika memakai komputer bersama agar data tetap aman.

### 2.3 Kalau Lupa PIN?

Mintalah **Admin** untuk mereset PIN-mu (dari halaman Manajemen User). Jangan berbagi PIN dengan siapa pun — PIN adalah tanda tangan digitalmu.

> 🔑 **Saran:** segera ganti PIN setelah pertama kali masuk. PIN awal semua akun biasanya `123456`.

### 2.4 Memasang di Layar Utama HP (Opsional)

1. Buka aplikasi di browser HP (Chrome).
2. Ketuk ikon **⋮** (titik tiga) di pojok kanan atas.
3. Pilih **"Tambahkan ke Layar Utama"** (Add to Home Screen).
4. Aplikasi tampil seperti aplikasi biasa di HP-mu — bisa dibuka sekali sentuh. 📱

---

## 3. Untuk OB — Pembelian Air Minum 💧

> **Kamu adalah OB (Office Boy).** Tugasmu: mencatat pembelian air minum dan mengunggah bukti fotonya. Bagian yang lain (jenis, merek, verifikasi) sudah diurus Finance & GA — kamu tinggal mengisi form.

### 3.1 Yang Kamu Lihat

Setelah login, kamu langsung berada di **Halaman Air Minum**. Di sana ada form pengajuan dan daftar pengajuanmu.

### 3.2 Mengajukan Pembelian Air Minum (Langkah demi Langkah)

1. Isi **Tanggal** pembelian.
2. Isi **Jumlah yang dibeli** (berapa galon/botol/gelas).
3. Pilih **Jenis air minum** — pilihannya: **Gelas, Botol, atau Galon** (disediakan Finance).
4. Pilih **Merk** dari daftar (misalnya AQUA Galon, Le Minerale, dll).
5. **Unggah foto bukti** — dua foto wajib:
   - 📸 **Foto sebelum diisi** (kondisi galon kosong / sebelum isi ulang)
   - 📸 **Foto sesudah diisi** (galon sudah terpasang/penuh)
6. Klik **Kirim**.

Pengajuanmu akan muncul di daftar dengan status **"Menunggu Verifikasi"**.

> ⚠️ **Foto wajib.** Pengajuan tanpa foto bukti tidak bisa diproses. Foto juga harus jelas menunjukkan waktu (time stamp) — inilah bukti bahwa air benar-benar dibeli.

### 3.3 Setelah Kamu Mengirim

- **Finance** akan memeriksa dan memverifikasi pengajuanmu (bisa menambah catatan).
- Jika disetujui, akan terbit **PDF tanda terima** yang ditandatangani Finance (penyerah) dan GA (penerima).
- Jika ditolak, lihat alasan penolakan dan perbaiki pengajuannya.

### 3.4 Status yang Mungkin Kamu Lihat

| Status | Artinya |
|--------|---------|
| Menunggu Verifikasi | Sudah dikirim, sedang diperiksa Finance |
| Terverifikasi | Disetujui — nanti terbit tanda terima PDF |
| Ditolak | Ada yang kurang — perbaiki sesuai alasan |

> 💡 Semua pengajuanmu **hanya terlihat olehmu, Finance, dan Admin**. OB lain tidak bisa melihat pengajuanmu.

---

## 4. Untuk Driver — BBM & Perjalanan 🚗

> **Kamu adalah Driver.** Tiga hal utama: (1) melaporkan pembelian BBM, (2) mengajukan kasbon, (3) mencatat log perjalanan. Semuanya dari satu aplikasi yang ramah HP.

### 4.1 Halaman Driver

Buka halaman Driver (bisa dipasang di HP). **Login dengan Username & PIN** yang diberikan Admin. Ada 4 tab: **⛽ BBM**, **💰 Kasbon**, **🗺️ Trip**, **📊 Rapor**.

### 4.2 Melaporkan Pembelian BBM (Bayar Dulu, Klaim Belakangan)

1. Buka tab **⛽ BBM**.
2. **GPS otomatis aktif** — lokasi + alamat detail terdeteksi.
3. Isi data pembelian: **jenis BBM**, **liter**, **harga per liter**, **nominal**, **SPBU**.
4. **Ambil foto** — pilih **📷 Kamera** (ambil langsung) atau **🖼️ Galeri** (dari album foto).
5. Foto otomatis diberi **watermark** (nama perusahaan + tanggal + lokasi GPS + koordinat).
6. Klik **Kirim**.

Klaimmu masuk antrean **GA** untuk disetujui, lalu **Finance** untuk dibayar. Statusnya bisa kamu pantau di daftar riwayat.

### 4.3 Mengajukan Kasbon (Uang Muka Sebelum Berangkat)

1. Buka tab **💰 Kasbon**.
2. Isi **nominal dasar** yang kamu butuhkan. Sistem otomatis menambahkan **kode unik** (angka receh, misal Rp 100.000 + kode) supaya pembayaranmu bisa dicocokkan.
3. Klik **💰 Ajukan Kasbon**.

Alur lengkapnya ada di [Bagian 10](#10-kasbon-alur-lengkap-dari-a-sampai-z).

### 4.4 Mencatat Log Perjalanan (Trip)

1. Buka tab **🗺️ Trip**.
2. Isi **tujuan perjalanan, lokasi berangkat, lokasi tujuan, dan KM awal**.
3. Saat sampai, catat **KM akhir** dan klik selesai.

> 💡 **Auto-Save**: setiap perubahan di tab Trip tersimpan otomatis ke HP (IndexedDB). Jika app tertutup atau HP mati, data akan pulih saat dibuka lagi. Draft otomatis terhapus setelah submit berhasil.

> 📍 **Detail GPS**: lokasi otomatis terdeteksi dengan detail lengkap — jalan, kelurahan, kecamatan, kota, provinsi, kode pos, dan SPBU terdekat.

Laporan ini dipakai GA untuk meninjau dan menghitung efisiensi kendaraan.

### 4.5 Cek Performa Kendaraan (Rapor)

Di tab **📊 Rapor**, masukkan **nomor polisi** kendaraanmu untuk melihat performa bahan bakar (rata-rata km/liter). Statusnya: **HEMAT**, **CUKUP**, atau **BOROS**.

### 4.6 Mode Offline 📡

Pernah di jalan tanpa sinyal? Tenang:

- Data yang kamu isi **tersimpan otomatis di HP**.
- Saat sinyal kembali, aplikasi **mengirim sendiri datanya** ke server.
- Tanda **🟡 Offline** di atas layar berarti datamu belum terkirim. Tekan **🔄 Sinkron** untuk mengirim manual.

### 4.7 Jadwal Appointment Saya

Jika Marketing menjadwalkan kunjungan untukmu, jadwalnya muncul di aplikasi Driver. Setelah kunjungan selesai, isi **hasil kunjungan** — data ini menjadi bahan laporan Marketing.

---

## 5. Untuk GA — Verifikasi & Pengawasan 🧾

> **Kamu adalah GA (General Affairs).** Dashboard-mu adalah pusat kendali: menyetujui klaim BBM, memverifikasi anomali, menyetujui kasbon, dan mengawasi laporan perjalanan.

### 5.1 Dashboard GA

Setelah login, kamu langsung masuk **Dashboard GA** (`/app/ga`). Di sana ada:

- **🕐 Antrean Klaim BBM** — klaim driver yang menunggu persetujuanmu.
- **🛡 Verifikasi Anomali** — klaim ber-tanda ⚠️ yang perlu diperiksa lebih teliti.
- **💵 Kasbon menunggu approve** — jumlah & nominal.
- **🗺️ Laporan perjalanan pending** — laporan yang belum ditinjau.

> ⚡ **Anti-ngoding:** kalau ada klaim baru masuk saat kamu sedang membuka dashboard, antreannya **langsung ter-refresh sendiri**. Tidak perlu muat ulang halaman.

### 5.2 Menyetujui Klaim BBM

1. Di antrean klaim, periksa data klaim & foto bukti.
2. Klik **✅ Approve** jika benar.
3. Klaim berpindah ke antrean Finance untuk pembayaran.

### 5.3 Menolak Klaim

1. Klik **✕ Tolak**.
2. **Alasan penolakan wajib diisi** — ini penting untuk jejak audit.
3. Driver akan melihat alasan tersebut di aplikasinya.

### 5.4 Memverifikasi Klaim Ber-Tanda ⚠️

Klaim dengan tanda ⚠️ (anomali) punya tombol **🛡 Verifikasi** tersendiri. Saat diverifikasi, pastikan bukti (foto, nominal, waktu) benar-benar cocok. Kamu akan diminta konfirmasi sebelum menyetujui.

### 5.5 Menyetujui & Menyerahkan Kasbon

Lihat [Bagian 10](#10-kasbon-alur-lengkap-dari-a-sampai-z) — peranmu ada di langkah **GA: menyetujui & menyerahkan dana**.

### 5.6 Menu Lain yang Bisa Kamu Akses

- **Log Perjalanan** — meninjau laporan trip driver.
- **Assignments** — menugaskan/menukar kendaraan antar driver.
- **Kasbon / BBM** — melihat semua pengajuan.
- **Analytics** — memantau performa armada.

---

## 6. Untuk Finance — Pembayaran & Rekap 💰

> **Kamu adalah Finance.** Tugasmu: membayar klaim, mengatur kode unik kasbon, memverifikasi pembelian air minum, dan menyediakan data (jenis & merk air) untuk OB.

### 6.1 Dashboard Finance

Setelah login, kamu langsung masuk **Dashboard Finance** (`/app/finance`). Di sana ada:

- **💧 Rekap Air Minum** — ringkasan pembelian (total, menunggu verifikasi, terverifikasi, ditolak), **per OB**, **per jenis** (gelas/botol/galon), dan **per merk**.
- **🕐 Antrean Verifikasi** — pengajuan air minum yang menunggu keputusanmu.
- **💵 Kasbon menunggu Finance** — kasbon yang sudah disetujui GA & siap kamu cairkan, plus LPJ yang menunggu.

### 6.2 Memverifikasi Pembelian Air Minum

1. Buka **Antrean Verifikasi** (di dashboard atau halaman Air Minum).
2. Periksa pengajuan OB: tanggal, jumlah, jenis, merk, dan **dua foto bukti** (sebelum & sesudah).
3. Setuju? Isi **remark** (mis. "sesuai struk") dan klik verifikasi.
4. Perlu catatan tambahan? Tulis di kolom **note** — catatanmu ikut tersimpan sebagai jejak audit.
5. Setelah terverifikasi, **PDF tanda terima** otomatis bisa dicetak — ditandatangani **Finance** (yang menyerahkan) dan **GA** (yang menerima).

### 6.3 Menyediakan Jenis & Merk Air Minum

OB memilih jenis & merk dari daftar yang **kamu** kelola:

- Jenis: **Gelas, Botol, Galon**.
- Merk: daftar brand (mis. AQUA Galon, Le Minerale, dll) — bisa ditambah/diubah dari menu yang tersedia.

### 6.4 Rekap & Export

- Filter rekap berdasarkan **tanggal** (secara otomatis menampilkan 90 hari terakhir).
- Klik **⬇️ Export CSV** untuk mengunduh data ke Excel.

### 6.5 Menyetujui Pencairan Kasbon

Lihat [Bagian 10](#10-kasbon-alur-lengkap-dari-a-sampai-z) — peranmu ada di langkah **Finance: menyetujui pencairan**.

### 6.6 Menu Lain

- **Rekap** — mencetak rekap & laporan (PDF).
- **Kasbon / BBM**, **Analytics**, **Log Perjalanan**.

---

## 7. Untuk Marketing — Jadwal Appointment 📣

> **Kamu adalah Marketing.** Tugasmu: menjadwalkan kunjungan (appointment) untuk para driver.

### 7.1 Membuat Appointment Baru

1. Buka **Marketing Hub**.
2. Pilih **tanggal** kunjungan dan **sesi** (Sesi 1 pagi / Sesi 2 sore).
3. Isi **Jam Kunjungan** (opsional) — jam spesifik di dalam rentang sesi (mis. 09:15). Kosongkan untuk memakai jam awal sesi otomatis.
4. Isi **nama calon nasabah, nama marketing, dan alamat lengkap**.
5. Simpan. Driver akan menerima jadwalnya di aplikasi.

> 💡 **Jam kunjungan penting!** Chief Driver memakai jam ini untuk menyusun **rute otomatis** — appointment diurutkan sesuai jam dan dibagi per area, sehingga driver tidak bolak-balik.

### 7.2 Memantau & Mengedit

- Semua jadwal tampil di papan **realtime** — perubahan langsung terlihat semua orang yang berhak.
- Bisa **mengedit** (termasuk jam kunjungan) atau **membatalkan** jadwal; statusnya langsung diperbarui (mis. "Selesai dikunjungi").

### 7.3 Hasil Kunjungan = Data Konversimu

Setelah driver mengunjungi lokasi, driver mengisi **hasil kunjungan**. Data ini menjadi laporan konversi untukmu. Notifikasi 🔔 memberi tahu saat status berubah.

---

## 8. Untuk Chief Driver — Pembagian Tugas 🚛

> **Kamu adalah Chief Driver.** Tugasmu: memastikan setiap driver punya tugas, dan setiap tugas ada drivernya.

### 8.1 Dashboard Chief Driver

- **Ringkasan harian** — gambaran tugas hari ini.
- **Board "Belum Ditugaskan"** — kunjungan yang belum ada drivernya.
- **Panel "Tugas Per Driver"** — melihat beban tiap driver sekaligus.

### 8.2 Atur Rute Otomatis ⚡ (Hemat BBM)

Ini fitur andalan untuk membagi kunjungan:

1. Pastikan marketing sudah mengisi **jam kunjungan** tiap appointment.
2. Klik tombol **⚡ Atur Rute Otomatis** di board.
3. Sistem menampilkan **saran rute per driver**: urutan kunjungan sesuai jam, dikelompokkan per area (searah), plus estimasi **jarak, liter, dan biaya BBM**.
4. Ada angka **hemat berapa persen** dibanding penugasan biasa — bukti efisiensi untuk manajemen.
5. Klik **✅ Terapkan Rute** — tiap driver otomatis mendapat jadwal + urutan kunjungan + notifikasi 🗺️.

Penugasan manual yang sudah dibuat tetap dihormati — rute otomatis hanya melengkapi yang belum ditugaskan.

### 8.3 Menugaskan Driver (Manual)

Dari board "Belum Ditugaskan", pilih driver untuk tiap kunjungan lalu klik **Tugaskan**. Tugas langsung muncul di aplikasi driver yang bersangkutan. Bisa juga **🔄 ganti** driver, **↩️ batalkan tugas**, atau **🌍 ubah area** kunjungan.

### 8.4 Unduh Rekap Harian

Ada tombol **📥 unduh rekap** untuk laporan harian (Excel).

### 8.5 Real-Time ⚡

Semua perubahan papan berjalan realtime — saat driver menyelesaikan tugas, statusnya langsung berubah tanpa muat ulang.

---

## 9. Untuk Receptionist — Pelamar Kerja 🪪

> **Kamu adalah Receptionist.** Pelamar kerja mengisi form sendiri lewat halaman publik (tanpa login). Tugasmu: memverifikasi, memperbaiki data yang salah, mencatat kehadiran interview & training, dan membuat laporan PDF resmi.

### 9.1 Pelamar Mengisi Form (Halaman Publik `/app/apply`)

- Pelamar membuka **Formulir Pendaftaran Kerja** (link dari resepsionis): Nama Lengkap, Pendidikan, No. HP, UPLINE, User (dropdown), Posisi.
- **Tanggal & jam interview diambil otomatis** dari waktu pengiriman form — pelamar langsung mendapat No. Registrasi (mis. `PLM-20260813-…`).
- **Kolom User berupa dropdown** — pilihannya dikelola Receptionist (lihat §9.4). Nilai awal diambil dari daftar User pada Google Sheet lama (TEAM YUSIE 3, TEAM EDI 2, dst.).

### 9.4 Kelola Pilihan User (Dropdown) ⚙️

- Klik tombol **⚙️ Kelola User** di dashboard Receptionist untuk membuka modal daftar opsi.
- **＋ Tambah** opsi baru (cth: `TEAM BARU 6`), **🚫 Nonaktifkan / ✅ Aktifkan** (opsi nonaktif tidak muncul di form pelamar), atau **🗑 Hapus**.
- Perubahan langsung berlaku di form publik & dropdown edit — semua tercatat di Audit Log (`user_option_*`).

### 9.2 Dashboard Receptionist `/app/receptionist`

- **Mencari & memfilter**: kolom tanggal (dari/sampai), UPLINE, User, Status, dan kotak pencarian (nama/HP/posisi).
- **✅ Verifikasi** — pastikan data pelamar benar, lalu klik tombol centang.
- **✏️ Edit** — perbaiki kesalahan input pelamar (nama, HP, upline, dll).
- **🎯 Catat Kehadiran** — buka modal kehadiran, lalu tandai **Interview** dan/atau **Training Hari 1–4** sesuai tahap yang dihadiri. Status pelamar otomatis mengikuti tahap terjauh.
- **🚪 Mengundurkan Diri** — jika pelamar berhenti (mis. setelah training hari 1), pilih *Mengundurkan Diri* dan **tuliskan alasannya (WAJIB karena pelamar sudah pernah hadir)**.
- **🏁 Lulus / ✕ Tolak** — setelah 4 hari training tuntas, tandai **Lulus**; atau **Tolak** dengan alasan (opsional).
- **🗑 Hapus** — hapus data pelamar beserta riwayat kehadirannya.
- **⚙️ Kelola User** — atur pilihan dropdown User untuk form pelamar (lihat §9.4).

### 9.3 Laporan PDF Resmi 📄

- Pilih **tahap laporan** (Interview / Training H1–H4), atur rentang tanggal + filter UPLINE/User sesuai kombinasi yang biasa kamu pakai, lalu klik **📄 Laporan PDF**.
- Hasilnya dokumen resmi **berkop & berlogo BPF**, berisi tabel kehadiran, ringkasan total, dan blok tanda tangan Receptionist — siap cetak/arsip.

---

## 10. Untuk Traineer / Upline — Pantau Rekrutan 🎯

> **Kamu adalah Traineer / Upline.** Halaman ini menampilkan **hanya orang yang kamu rekrut** (UPLINE = kamu) — otomatis, tanpa perlu filter manual.

### 10.1 Dashboard Traineer `/app/traineer`

- **Lihat rekrutanmu**: nama, posisi, user, jadwal interview, dan **chip kehadiran** (I · H1 · H2 · H3 · H4) — chip menyala hijau sesuai tahap yang sudah dihadiri.
- **Filter & cari**: rentang tanggal, UPLINE/User/Status, dan kotak pencarian.
- **Kartu statistik**: total rekrutan, yang sudah interview, dalam training, lulus, mundur.

> ℹ️ Traineer hanya **melihat** (read-only) — edit, kehadiran, dan PDF dikelola Receptionist.

---

## 11. Untuk GA — Aset & Pemeliharaan 🔧

> **Kamu adalah GA.** Halaman **🔧 Aset & Pemeliharaan** (`/app/assets`) menggantikan aplikasi aset lama (Streamlit) — semua dikelola di WorkHub.

### 11.1 Unit AC Kantor ❄️

- **15 unit AC** tampil (ID, merk, tipe, kapasitas, lokasi per ruangan, status).
- Klik **🛠️** untuk mencatat **log servis**: tanggal, teknisi, parameter teknikal (ampere kompresor, tekanan rendah/tinggi, delta T, dst.), biaya sparepart, catatan — **health score 0–100 dihitung otomatis** dari parameter.
- **＋ Tambah AC** untuk unit baru; **✏️ edit** & **🗑 hapus** untuk kelola master.

### 11.2 Kendaraan 🚗

- **8 kendaraan asli kantor** (Innova + 7 Avanza) — data diambil dari tabel kendaraan BBM, jadi satu sumber data.
- Klik **🛠️** untuk mencatat **log servis per komponen**: odometer, jenis servis, komponen (dropdown dari master), biaya, montir, no. invoice.

### 11.3 Rekomendasi Otomatis 📋

- **🔄 Perbarui Rekomendasi** → sistem menyarankan: AC yang sudah > 90 hari tanpa servis atau health rendah, dan komponen kendaraan yang melewati umur pakai (km/bulan vs standar).
- Tandai **✅ Selesai** setelah dikerjakan, atau **✕** untuk membatalkan.

### 11.4 Komponen & Laporan 🧩

- **Tab Komponen**: master komponen + umur standar + estimasi biaya (dasar rekomendasi).
- **📄 Laporan PDF AC / Kendaraan**: dokumen resmi berlogo BPF + TTD General Affairs.

---

## 11.5 Untuk GA HR — Data Overtime ⏰

> **Kamu adalah GA HR.** Halaman **⏰ Overtime** (`/app/ga-hr`) menampilkan dua data overtime: **Driver** (dari Google Sheet) dan **OB/Security** (form publik).

### Tab 🚗 Driver

- Data ditarik dari Google Sheet lama (diisi Google Form) — **8.665 baris (2020–2026) sudah dimigrasikan** ke tabel `overtime_driver`.
- Klik **🔄 Refresh dari Google Sheet** untuk menyinkronkan — baris baru ditambahkan, baris lama diperbarui.
- **Otomatis**: setiap kali user GA HR atau Admin **login atau logout**, data Driver langsung disinkronkan ulang di background — tanpa perlu menekan tombol apa pun. (Refresh dibatasi maksimal 1× per 30 detik agar tidak membebani Google.)
- **🔔 Notifikasi**: saat sinkronisasi menemukan **data Driver baru** atau ada **form publik OB/Security** yang diisi, lonceng 🔔 di pojok kanan atas langsung berbunyi (realtime).
- **✏️ Edit & 🗑️ Hapus**: tiap baris punya tombol aksi — koreksi typo (nama, kendaraan, tanggal, jam, keterangan, broker/manager) lewat modal edit, atau hapus baris yang keliru. Semua aksi tercatat di Audit Log.
- Filter **tanggal** & **pencarian** nama/kendaraan/broker/manager/keterangan.
- Tombol **⚙️ Sumber Data**: URL yang dibaca server. Bila sheet **private**, ganti dengan URL Google Apps Script Web App (template: `scripts/apps_script_overtime_driver.gs`) supaya refresh tetap berjalan tanpa membuka akses sheet. **Tidak perlu akses ke akun pemilik** — cukup akun Google mana pun yang sudah punya akses (termasuk view/read-only) membuat script standalone di `script.google.com` lalu deploy sebagai Web App (*Execute as: Me*, *Who has access: Anyone*).
- Tanggal & jam dari Apps Script (format ISO UTC) otomatis dikonversi ke **zona WIB** saat disimpan.

### Tab 🧑‍🔧 OB & Security

- Data lama (546 baris) sudah dimigrasikan penuh; baris baru masuk lewat **form publik** atau **sinkronisasi Google Sheet**.
- Filter posisi (OB/Security), tanggal, sumber, dan pencarian.
- **🔄 Refresh** — tarik data terbaru dari Google Sheet OB/Security (sama seperti tab Driver).
- **📋 Detail/Excel** — generate report detail per nama OB/Security (PDF atau Excel). Kolom Biaya kosong untuk diisi GA HR.
- **⚙️ Sumber Data** — atur URL Google Sheet OB/Security di modal config (terpisah dari Driver).

### Form Publik (tanpa login)

- Bagikan tautan **`/app/overtime-form`** ke karyawan OB/Security — mereka mengisi sendiri: dropdown **Posisi** (OB/Security) & **Nama** (sesuai data yang ada), tanggal, jam mulai/selesai, keterangan.
- Setiap pengiriman mendapat nomor bukti `OTL-*` dan langsung tampil di dashboard GA HR.

### Akun GA HR

- Akun demo tersedia: **username `ga_hr_officer`, PIN `123456`** (role GA HR) — atau buat sendiri di Manajemen User (`/app/users`) oleh Admin.

### 🗑️ Foto OT Auto-Cleanup (v2.28.2)

Foto overtime yang diunggah ke server secara otomatis **dibatasi penyimpanannya maksimal 6 bulan**. Setelah 6 bulan, foto akan dihapus otomatis untuk menghemat storage server.

- **Otomatis**: cron di container membersihkan foto tiap 30 menit
- **Manual**: Admin bisa trigger cleanup dari API (`POST /api/overtime/cleanup-photos`)
- Data overtime lainnya (nama, tanggal, jam, keterangan) **tetap tersimpan** di database — hanya foto yang dihapus

### Kolom di Tab Driver

- **Tanggal · Nama · No. Kendaraan · Waktu · Keterangan · Broker/Manager** — No. Kendaraan, broker (Nama Broker/Marketing), dan manager (Nama Manager/Team leader) ikut tampil di tabel, laporan PDF, dan pencarian.

### 📄 Cetak Laporan & Form (v2.27.0+)

Tiga format PDF tersedia (didukung untuk Driver DAN OB/Security):

1. **📄 PDF (Laporan Ringkas)** — tabel ringkas semua data, ditandatangani GA HR. Klik tombol **📄 PDF** di toolbar. Untuk OB/Security, kolom PLAT diganti POSISI.
2. **📋 Detail/Excel (Report Per Nama)** — pilih nama + periode, lalu pilih **📄 PDF** atau **📊 Excel**. Kolom Biaya di Excel kosong untuk diisi manual oleh GA HR. Untuk OB/Security, kolom PLAT diganti POSISI.
3. **📄 Cetak Form (Formulir Permohonan)** — klik tombol **📄** pada baris data overtime. PDF berisi: ID form, detail OT, blok TTD (Manager/Finance/GA HR/Chief Driver/Kepala Cabang), dan link foto. Untuk OB/Security, judul form menampilkan POSISI (bukan No. Kendaraan).

---

## 11.6 Untuk GA HR — Migrasi Data Driver dari Google Sheet 📥

> Kamu hanya punya akses **view (read-only)** ke sheet overtime Driver dan tidak punya akses ke akun pemilik. Tenang — tetap bisa sinkron.

1. Buka **https://script.google.com** → **New project** (proyek *standalone*, jangan lewat menu sheet — itu butuh akses edit).
2. Hapus isi `Code.gs`, tempel semua kode dari **`scripts/apps_script_overtime_driver.gs`**, lalu simpan.
3. **Deploy** → **New deployment** → type **Web app**:
   - *Execute as:* **Me** (akun Anda yang punya akses ke sheet)
   - *Who has access:* **Anyone**
4. Saat diminta izin: pilih akun yang sama → **Advanced** → *Go to … (unsafe)* → **Allow** (script hanya membaca).
5. Salin URL `https://script.google.com/macros/s/…/exec`, tempel di dashboard GA HR → **⚙️ Sumber Data** → **Simpan**.
6. Tekan **🔄 Refresh** — data terbaru (termasuk yang baru diisi di Google Form) langsung masuk ke WorkHub.

**Kenapa bisa?** Script dieksekusi *atas nama akun Anda* (yang sudah diberi akses baca oleh pemilik), jadi bisa membaca sheet private. Hasilnya jadi JSON publik yang dibaca server WorkHub — sheet tidak pernah dibuka aksesnya.

---

## 12. Untuk Admin — Pengaturan Sistem ⚙️

> **Kamu adalah Admin.** Kamu memegang kunci utama: membuat akun, mengatur nama untuk tanda terima, dan memantau jejak audit.

### 12.1 Manajemen User (Halaman Users)

- **Membuat akun baru** — pilih peran (Admin, GA, Finance, Marketing, Chief Driver, Driver, OB, **Receptionist**, **Traineer**, **GA HR**, **IT Surabaya**), isi nama & PIN.
- **Mengganti nama** — misalnya mengganti nama placeholder OB dengan nama asli. Nama ini yang tampil di dokumen (mis. PDF tanda terima air minum).
- **Reset PIN** — kalau user lupa PIN.
- **Nonaktifkan/Aktifkan** — akun yang dinonaktifkan **tidak bisa login** (tanpa harus dihapus, supaya jejak datanya tetap aman).
- **Hapus** — hapus akun (jika memang tidak dipakai).

### 12.2 Pengaturan (Settings)

- **Manajemen Driver** — tambah/hapus data driver.
- **Manajemen Armada** — tambah kendaraan (nopol, jenis, dll).
- **Nama untuk Tanda Terima Air Minum** — set **nama Finance** (yang menyerahkan) & **nama GA** (yang menerima). Nama ini otomatis tercetak di PDF tanda terima air minum.
- Pengaturan lain sesuai kebutuhan kantor.

### 12.3 Audit Log (Jejak Digital)

Semua aksi penting tercatat di **Audit Log**: siapa, melakukan apa, kapan. Berguna saat ada selisih atau pertanyaan. Bisa difilter berdasarkan aksi & peran.

### 12.4 Dark Mode 🌙

Suka tampilan gelap? Klik tombol **🌙/☀️** di pojok kanan atas. Pilihanmu tersimpan otomatis.

---

## 13. Kasbon: Alur Lengkap dari A sampai Z

Kasbon = uang muka yang diberikan ke driver sebelum berangkat. Alurnya seperti relay — tiap bagian menyentuh sekali:

### Langkah 1 — Driver mengajukan 💰
Driver isi nominal + kode unik otomatis. Status: **Draft**.

### Langkah 2 — GA menyetujui ✅
GA menyetujui pengajuan & **menyerahkan dana** ke driver (bisa juga dibatalkan jika batal berangkat). Status: **Disetujui GA**.

### Langkah 3 — Finance mencairkan 💵
Finance melihat antrean kasbon di Dashboard Finance dan menyetujui pencairan. Status: **Menunggu Serah / Diserahkan**.

### Langkah 4 — Driver mengisi LPJ 📋
Setelah dana diterima, driver mengisi **LPJ (Laporan Pertanggungjawaban)** — berapa yang benar-benar dipakai, lengkap dengan bukti. Status: **LPJ Diajukan**.

### Langkah 5 — GA memverifikasi LPJ 🧾
GA memeriksa LPJ. Jika sesuai, status menjadi **Selesai** 🎉. Jika tidak, dikembalikan ke driver untuk diperbaiki.

### Apa itu Kode Unik? 🤔
Angka "receh" yang ditambahkan ke nominal kasbon (mis. Rp 100.023, bukan Rp 100.000). Tujuannya: saat Finance membayar, **nominal persis ini** memastikan uang itu memang untuk kasbon tersebut — mencegah kesalahan pembayaran. Kode unik harian diatur oleh **Finance**.

### Bisa dibatalkan? 
- **Draft** → driver bisa menghapus sendiri.
- **Sudah diproses** → batal hanya lewat Admin/GA dengan alasan yang tercatat.

---

## 14. Untuk IT (Semua Cabang) — News Scraper & Content Management 📰

> **Kamu adalah IT Cabang.** Halaman **📰 News Scraper** (`/app/it`) memungkinkanmu scrape artikel dari newsmaker.id DAN Detik Finance, upload ke WordPress dengan SEO optimization, dan mengelola financial authority backlinks. Setiap cabang hanya melihat site WordPress milik cabang sendiri.

### 14.1 Mengelola WordPress Sites

1. Klik **➕ Add Site** untuk menambah WordPress site baru.
2. Isi: **Site Name**, **API URL** (endpoint posts WP), **Username**, **App Password**, **Branch Code** (SBY, JKT, BDG, dst).
3. Klik **🔌 Test** untuk memverifikasi koneksi.
4. Password ditampilkan dengan tombol **👁/🙈** untuk show/hide.
5. Branch Code menentukan situs mana yang terlihat oleh user IT cabang.
6. Bisa menambah **multiple sites** dengan credentials berbeda.

### 14.2 Scrape Artikel

1. Pilih **Sumber Berita**: Semua Sumber / Newsmaker.id / Detik Finance.
2. Atur **jumlah halaman** (1-20).
3. Klik **🔍 Check Articles** — artikel dari sumber terpilih akan di-scrape.
4. Newsmaker.id: ~16 artikel komoditas per halaman dari `newsmaker.id/id/news/commodity`.
5. Detik Finance: ~48 artikel dari homepage + tag pages.
6. Artikel muncul sebagai kartu dengan **badge sumber** (cyan=Newsmaker, orange=Detik).
7. Gunakan **tombol filter** di atas daftar untuk membedakan artikel per sumber.

### 14.3 Upload ke WordPress

1. Pilih artikel yang mau diupload (checkbox per artikel).
2. Pilih **target site** dari dropdown.
3. Klik **📤 Upload to WordPress**.
4. **Progress bar** bergerak sesuai tahapan: login → filter → upload → selesai.
5. **Pre-filter otomatis** — artikel yang sudah ada di WordPress otomatis di-skip (hanya artikel BARU yang diproses).
6. **SEO Optimization** otomatis: schema markup, meta description, word count.
7. **Financial Authority Backlinks** otomatis berdasarkan keyword.
8. **Source backlink** otomatis ke sumber asli (Newsmaker/Detik).
9. **Tag otomatis** dibuat berdasarkan judul artikel.
10. Hasil upload: jumlah baru, update, error, dan berapa yang di-skip (sudah ada di WP).

> 💡 **Tips:** Jika upload terasa lambat, kemungkinan banyak artikel sudah ada di WP. Pre-filter otomatis menanganinya — kamu tidak perlu khawatir upload duplikat.

### 14.4 Tab Report 📋

1. Klik tab **📋 Report** untuk melihat detail per-artikel.
2. Filter: tanggal, site, status, source, search judul.
3. Summary: total, new, updated, error, avg SEO score.
4. Klik **📥 Export CSV** untuk download laporan lengkap.

### 14.5 Financial Authority Backlinks

Klik **🔗 Backlinks** untuk melihat/mengelola:
- **24+ authority sites**: OJK, BI, BEI, IMF, Bloomberg, Reuters, dll.
- **Keyword mapping**: keyword dalam artikel otomatis di-link ke situs otoritas.
- **Tambah keyword mapping** baru: pilih keyword + target authority site.

### 14.6 Duplicate Checker

1. Pilih site → klik **🔍 Check Duplicates**.
2. Artikel duplikat terdeteksi: judul, jumlah duplikat, post IDs.
3. Klik **🗑 Delete Duplicates** untuk menghapus (keep latest only).

### 14.7 Auto-Scrape (Otomatis)

Sistem memiliki **cron otomatis** yang berjalan 4× sehari:

| Jam (WIB) | Keterangan |
|-----------|------------|
| 06:00 | Pagi — artikel semalam |
| 10:00 | Siang — artikel pagi |
| 14:00 | Sore — artikel siang |
| 18:00 | Sore — artikel menjelang malam |

**Alur otomatis:**
1. Scrape newsmaker.id (gold, oil, silver).
2. Fetch konten setiap artikel (dengan retry jika gagal).
3. Login ke semua WordPress site aktif.
4. Fetch semua post yang sudah ada di WP.
5. **Pre-filter** — skip artikel yang sudah ada.
6. Upload hanya artikel BARU ke WP.
7. Log: `/app/data/news_scraper/auto_scrape.log`

> 💡 Kamu tetap bisa upload manual kapan saja — auto-scrape hanya membantu agar artikel baru tidak terlewat.

### 14.8 Settings SEO

- **🔍 Auto-SEO**: aktifkan untuk optimasi otomatis.
- **🔗 Authority Backlinks**: aktifkan untuk backlink otomatis.
- **Max backlinks**: jumlah maksimal backlinks per artikel.
- **Static Tags**: tag yang selalu ditambahkan (comma separated).
- **⚙️ Daily Limit**: atur jumlah maksimal publish per hari (1-100).
  - Default: 10/hari
  - Bisa diubah dari Tab Dashboard → ⚙️ Pengaturan

### 14.9 Retry & Error Handling

Jika situs berita rate-limit (HTTP 429) atau error server (5xx), sistem otomatis **retry 3× dengan exponential backoff** (tunggu 2 detik → 4 detik → 8 detik). Ini memastikan artikel tetap bisa di-scrape meskipun situs sedang sibuk.

Jika upload ke WordPress gagal, pesan error sekarang menampilkan **response body** dari WordPress (bukan cuma "HTTP 400") — memudahkan debugging.

---

## 15. Mengatasi Masalah (Troubleshooting)

| Masalah | Solusi |
|---------|--------|
| **Tidak bisa login ("Username atau PIN salah")** | Periksa huruf besar/kecil & angka PIN. Jika tetap gagal, minta Admin reset PIN. |
| **Login terlalu sering gagal** | Sistem sengaja mengunci sementara (anti peretasan). Tunggu beberapa menit lalu coba lagi. |
| **Halaman tidak muncul / blank** | Muat ulang (F5). Coba browser lain atau mode penyamaran. |
| **Foto bukti tidak bisa diunggah** | Pastikan foto berukuran wajar (di bawah 16 MB) dan format JPG/PNG. |
| **Pengajuan air minum ditolak** | Baca alasan penolakan di daftar pengajuannya, perbaiki, ajukan ulang. |
| **Data offline belum terkirim** | Pastikan HP terhubung internet, lalu tekan **🔄 Sinkron** di aplikasi Driver. |
| **Lupa PIN / akun terkunci** | Hubungi Admin — hanya Admin yang bisa mereset PIN. |
| **Aplikasi terasa lambat** | Periksa koneksi internet. Data akan tetap tersimpan di HP (offline). |
| **Muncul pesan "CSRF token tidak valid"** | Muat ulang halaman dan coba lagi (sesi browser sedang kedaluwarsa). |

> Kalau masalah tetap berlanjut, hubungi Admin / tim IT dengan menyebutkan: **siapa kamu, kapan kejadiannya, dan pesan error yang muncul.**

---

## 16. Istilah-istilah Penting

| Istilah | Artinya (bahasa sehari-hari) |
|---------|------------------------------|
| **PIN** | Kata sandi 6 digit milikmu. |
| **Role / Peran** | Jabatanmu di sistem (Admin, GA, Finance, dll) — menentukan menu yang kamu lihat. |
| **Klaim BBM** | Laporan driver soal pembelian BBM, lengkap dengan bukti, untuk diganti uangnya. |
| **Kasbon** | Uang muka yang diterima driver sebelum berangkat. |
| **LPJ** | Laporan Pertanggungjawaban — bukti pemakaian kasbon setelah dana diterima. |
| **Kode Unik** | Angka receh tambahan pada nominal kasbon supaya pembayaran mudah dicocokkan. |
| **Anomali** | Kejanggalan pada klaim (tanda ⚠️) — perlu pemeriksaan ekstra oleh GA. |
| **Appointment** | Jadwal kunjungan yang dibuat Marketing untuk driver. |
| **Jam Kunjungan** | Jam spesifik kunjungan dalam sesi (mis. 09:15) — dipakai untuk menyusun urutan rute. |
| **Rute Otomatis** | Fitur Chief Driver membagi kunjungan per area & urut jam → driver searah, hemat BBM. |
| **Trip / Log Perjalanan** | Catatan perjalanan driver (dari mana, ke mana, KM berapa). |
| **Tanda Terima (PDF)** | Dokumen resmi — misalnya bukti pembelian air minum, ditandatangani Finance & GA. |
| **Audit Log** | Buku catatan digital semua aksi penting di sistem. |
| **SPBU Rekanan** | SPBU langganan kantor tempat driver mengisi BBM. |
| **Offline Mode** | Kondisi tanpa internet — data tetap tersimpan di HP dan terkirim otomatis saat online. |
| **Pelamar Kerja** | Orang yang mendaftar kerja via form publik — datanya dikelola Receptionist. |
| **UPLINE / Traineer** | Orang yang merekrut pelamar — bisa memantau kehadiran rekrutannya. |
| **Kehadiran (I · H1–H4)** | Tanda hadir pelamar: Interview, lalu Training Hari 1 sampai 4. |

---

## 📞 Kontak & Dukungan

Ada pertanyaan atau kendala? Hubungi **Admin** atau **tim IT** — mereka bisa melihat riwayat sistem (Audit Log) untuk membantu menyelesaikan masalahmu dengan cepat.

*BPF WorkHub v2.28.2 · Panduan Pengguna*
