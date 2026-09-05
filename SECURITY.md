# 🔐 Keamanan & Kepatuhan Standar — BPF WorkHub v1.0

> **Dokumen ini menjelaskan bagaimana BPF WorkHub menjaga keamanan data dan mutu layanan**, serta bagaimana penerapannya mengacu pada standar internasional yang diakui dunia.
>
> Ditulis dengan bahasa sederhana agar dapat dipahami oleh siapa saja — bukan hanya tim teknis.

**PT. Bestprofit Futures — Kantor Pusat Jakarta**
Equity Tower, SCBD Lot 9, Jl. Jend. Sudirman Kav. 52-53, Jakarta Selatan 12190
📞 Telp: 031-5349888

---

## 📋 Daftar Isi

1. [🛡️ ISO/IEC 27001:2022 — Standar Keamanan Informasi](#1--isoiec-270012022--standar-keamanan-informasi)
2. [🎯 ISO 9241-11 — Standar Kemudahan Penggunaan](#2--iso-9241-11--standar-kemudahan-penggunaan)
3. [✅ ISO 9001 — Standar Manajemen Mutu](#3--iso-9001--standar-manajemen-mutu)
4. [🔒 Ringkasan Fitur Keamanan](#4--ringkasan-fitur-keamanan)
5. [📞 Kontak Tim IT](#5--kontak-tim-it)

---

## 1️⃣ 🛡️ ISO/IEC 27001:2022 — Standar Keamanan Informasi

**Apa itu?**
Ini adalah standar internasional tentang cara sebuah organisasi **melindungi informasinya** — memastikan data hanya bisa diakses orang yang berhak, dan setiap aktivitas penting tercatat dengan jelas.

**Bagaimana BPF WorkHub menerapkannya?**

Sistem menggunakan dua prinsip utama:

- 👤 **Hak akses sesuai peran** — Setiap pengguna (admin, GA, finance, marketing, chief driver, dll.) hanya dapat membuka menu dan halaman yang memang menjadi tanggung jawabnya. Menu lain tidak tampil sama sekali di layar mereka.
- 🔑 **Akses seminimal mungkin** (*least privilege*) — Seseorang hanya diberi kewenangan sebatas yang ia butuhkan untuk bekerja, tidak lebih. Ini mencegah salah satu orang memiliki "kunci semua pintu".
- ✂️ **Pemisahan tugas** (*segregation of duties*) — Tugas-tugas sensitif dibagi ke beberapa peran, sehingga tidak ada satu pun orang yang bisa melakukan segalanya sendirian.

### 🗺️ Pemetaan Kontrol Keamanan

| Aspek Keamanan | Bagaimana BPF WorkHub Melakukannya |
|---|---|
| **Siapa boleh masuk ke mana** | Setiap orang masuk dengan *username* + PIN 6 digit. Menu yang tidak jadi wewenangnya disembunyikan dari tampilan — dan jika dipaksa lewat alamat URL langsung, sistem menolak dengan pesan **403 (Akses Ditolak)**. |
| **Hak khusus admin** | Halaman-halaman paling sensitif — Manajemen User, Pengaturan, dan Audit Log — **hanya bisa dibuka oleh Admin**. Pembatasan ini diberlakukan di dua lapis: di server dan di tampilan aplikasi. |
| **Cara masuk yang aman** | PIN tersimpan aman di database. Akun yang sudah dinonaktifkan tidak bisa login. Sesi login memiliki masa kedaluwarsa otomatis, dan sistem menolak upaya manipulasi alamat tujuan setelah login. |
| **Verifikasi ulang aksi berisiko** | Aksi yang menggerakkan uang (approve kasbon, serah terima dana, payout klaim BBM, verifikasi air minum) wajib dikonfirmasi dengan **PIN ulang user yang sedang login** sebelum dijalankan (step-up auth, ISO/IEC 27001 A.8.5). Grant verifikasi hanya berlaku sementara (10 menit) dan hilang saat logout. |
| **Catatan aktivitas** | **Setiap perubahan data tercatat**: siapa yang melakukannya, apa yang diubah, kapan, dan dari perangkat/IP mana. Semua ini bisa dilihat Admin di halaman Audit Log. |
| **Pemantauan berkala** | Ada indikator status koneksi secara *real-time* (⚡ terhubung / 🔴 terputus) di bilah atas aplikasi. Log teknis juga dapat dipantau oleh tim IT. |
| **Perlindungan dari celah umum** | Data yang dikirim selalu divalidasi; permintaan yang mengubah data wajib menyertakan token keamanan (proteksi *CSRF*); halaman dilindungi dari penyimpanan cache yang tidak diinginkan; dan kode ditulis dengan teknik yang tahan terhadap serangan umum seperti *SQL injection*. |
| **Konfigurasi & rilis terkendali** | Kredensial penting (kunci rahasia, akses database) tidak dituliskan di kode, melainkan diatur lewat konfigurasi terpisah. Sebelum setiap versi dirilis, wajib lolos **391 pengujian otomatis** (pytest) + **98 uji antarmuka** (vitest) terlebih dahulu. |

---

### 👥 Matriks Hak Akses per Peran

Tabel berikut menunjukkan **siapa dapat mengakses apa**:

| Fitur / Halaman | 👑 Admin | 🚚 GA | 💰 Finance | 📣 Marketing | 🧭 Chief Driver |
|---|:---:|:---:|:---:|:---:|:---:|
| Dashboard & statistik | ✅ | ✅ | ✅ | – | – |
| Log Perjalanan (*trips*) | ✅ | ✅ | ✅ | – | – |
| Penugasan kendaraan | ✅ | ✅ | – | – | – |
| Rekap & Analitik | ✅ | ✅ | ✅ | – | – |
| Marketing Hub | – | – | – | ✅ | – |
| Papan Chief Driver | ✅ | ✅ | – | – | ✅ |
| Manajemen User | ✅ | – | – | – | – |
| Pengaturan | ✅ | – | – | – | – |
| Audit Log | ✅ | – | – | – | – |

> 🛡️ **Pengamanan berlapis tiga:**
> 1. **Di server** — setiap halaman dan API memeriksa hak akses pemohon.
> 2. **Di aplikasi** — navigasi antarhalaman ikut memvalidasi peran pengguna.
> 3. **Di tampilan** — menu yang bukan wewenang sengaja tidak ditampilkan.
>
> Hasilnya: meskipun seseorang mencoba membuka URL halaman terlarang secara langsung, sistem akan **menolak dengan kode 403**.

---

## 2️⃣ 🎯 ISO 9241-11 — Standar Kemudahan Penggunaan

**Apa itu?**
Standar internasional yang mengukur apakah sebuah aplikasi **mudah, nyaman, dan efektif digunakan** manusia.

| Prinsip | Artinya | Wujudnya di BPF WorkHub |
|---|---|---|
| **🎯 Efektivitas** | Pengguna bisa mencapai tujuannya tanpa hambatan. | Dashboard tiap peran hanya menampilkan informasi yang relevan bagi mereka; ada tombol aksi cepat satu klik; status pekerjaan selalu terlihat jelas. |
| **⚡ Efisiensi** | Tugas selesai dengan langkah sesedikit mungkin. | Antarhalaman berpindah tanpa memuat ulang (teknologi *SPA*); menu sudah difilter sesuai peran sehingga tidak perlu mencari-cari; ada filter instan dan pintasan. |
| **😊 Kepuasan** | Pengguna merasa nyaman memakainya. | Tampilan responsif (nyaman dibuka dari HP maupun komputer), tersedia *dark mode*, notifikasi visual yang ramah, dan seluruh antarmuka berbahasa Indonesia. |

---

## 3️⃣ ✅ ISO 9001 — Standar Manajemen Mutu

**Apa itu?**
Standar internasional tentang cara sebuah organisasi **memastikan produk dan layanannya bermutu konsisten** — mulai dari dokumentasi yang rapi hingga proses rilis yang terkendali.

| Klausul Standar | Artinya | Penerapan di BPF WorkHub |
|---|---|---|
| **Klausul 4–5** — Konteks & Kepemimpinan | Ruang lingkup dan pembagian peran tertulis dengan jelas. | Panduan lengkap tersedia dalam dokumen README, USER_GUIDE, dan DEPLOYMENT. |
| **Klausul 7.5** — Informasi Terdokumentasi | Semua hal penting didokumentasikan, tidak bergantung pada ingatan orang. | Dokumentasi lengkap: CHANGELOG (catatan perubahan), DEPLOYMENT.md (panduan rilis), USER_GUIDE.md (panduan pengguna), SECURITY.md (dokumen ini). |
| **Klausul 8.1** — Perencanaan Operasional | Proses kerja dirancang dan diikuti secara konsisten. | Alur rilis baku: catat perubahan di CHANGELOG → beri nomor versi → publikasikan sebagai *GitHub Release* (diotomatisasi lewat `scripts/release.sh`). |
| **Klausul 8.6** — Rilis Produk | Tidak ada produk keluar tanpa pemeriksaan. | Sebelum setiap rilis wajib lolos: **323 pengujian otomatis** (`pytest`) + **83 uji frontend** (`vitest`), proses build aplikasi, serta uji coba langsung fitur HTTP & WebSocket (diverifikasi otomatis di GitHub Actions tiap push). |
| **Klausul 10** — Peningkatan Berkelanjutan | Selalu ada ruang untuk menjadi lebih baik. | Masukan pengguna dan jejak audit menjadi dasar perbaikan di setiap versi — lihat CHANGELOG untuk riwayatnya. |

---

## 4️⃣ 🔒 Ringkasan Fitur Keamanan

Berikut ringkasan seluruh lapisan perlindungan yang dimiliki BPF WorkHub:

| Fitur | Fungsi Singkatnya |
|---|---|
| 🔑 **Login PIN** | Setiap orang masuk dengan *username* + PIN pribadi 6 digit. |
| ⏳ **Sesi Otomatis** | Sesi login tersimpan aman di *cookie* terenkripsi, dan akan berakhir secara otomatis. |
| 🎫 **Proteksi CSRF** | Semua perubahan data (tambah/ubah/hapus) wajib menyertakan token keamanan — mencegah "permintaan palsu" yang dikirim tanpa sepengetahuan pengguna. |
| 👥 **Hak Akses Berjenjang** | 11 jenis peran berbeda, masing-masing hanya mendapat kewenangan seperlunya, dijaga berlapis. |
| 📜 **Jejak Audit** | 30+ jenis aktivitas tercatat lengkap: siapa, kapan, dan apa yang dilakukan. |
| 🚧 **Anti Tebak Paksa** | Percobaan login berulang kali yang mencurigakan akan dibatasi otomatis (melalui *rate limiting*). |
| 🧬 **Verifikasi PIN Ulang (Step-up)** | Aksi approve/pay berisiko wajib konfirmasi PIN ulang user yang sedang login — modal PIN muncul otomatis, grant sementara 10 menit, hilang saat logout. |
| 📍 **Watermark Foto** | Foto bukti lapangan dilengkapi stempel lokasi GPS dan waktu — sulit dipalsukan. |
| 🏰 **Pengaturan Keamanan Browser** | Standar pelindung aktif: CSP, X-Frame-Options, Referrer-Policy, dan Permissions-Policy (mencegah halaman disalahgunakan oleh situs lain). |
| 💾 **Cadangan Data Harian** | Database dicadangkan otomatis setiap hari pukul **03.00 WIB**, dan disimpan selama **30 hari**. |

---

## 5️⃣ 📞 Kontak Tim IT

Untuk pertanyaan, laporan kendala, atau saran perbaikan terkait keamanan BPF WorkHub:

**PT. Bestprofit Futures — Kantor Pusat Jakarta**
Equity Tower, SCBD Lot 9, Jl. Jend. Sudirman Kav. 52-53, Jakarta Selatan 12190
📞 Telp: **031-5349888**

---

*BPF WorkHub v2.29.6 · Dokumen Keamanan & Kepatuhan · Diperbarui 4 September 2026*

---

## 📝 Catatan Perubahan dari Versi Asli

Beberapa hal yang saya sesuaikan agar lebih mudah dipahami:

1. **Menambahkan penjelasan "Apa itu?"** di awal tiap standar ISO — pembaca awam kini tahu kont