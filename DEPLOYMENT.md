Berikut hasil penulisan ulang file markdown secara keseluruhan. Saya pertahankan semua informasi teknis penting (perintah, tabel, konfigurasi), namun saya balut dengan bahasa yang lebih ramah, penjelasan sederhana untuk istilah teknis, serta struktur visual yang konsisten. Anda bisa langsung menyalin blok di bawah ini sebagai file `.md` baru:

````markdown
# 📘 Panduan Lengkap BPF WorkHub
### Versi 2.28.2 · PT. Bestprofit Futures — Surabaya

> Dokumen ini adalah panduan untuk memasang, mengatur, dan merawat aplikasi **BPF WorkHub**.
> Ditulis dengan bahasa sederhana agar bisa dipahami siapa saja — bukan hanya teknisi.
>
> 💡 **BPF WorkHub dalam satu kalimat:** aplikasi internal untuk mengelola penugasan kendaraan,
> pengajuan kasbon BBM driver, foto lembur, hingga notifikasi langsung (*real-time*) ke ponsel driver.

---

## 🧭 Daftar Isi

1. [Istilah Penting — Baca Ini Dulu](#1-istilah-penting--baca-ini-dulu)
2. [Cara Kerja Sistem (Arsitektur & Port)](#2-cara-kerja-sistem-arsitektur--port)
3. [Yang Harus Disiapkan Sebelum Instalasi](#3-yang-harus-disiapkan-sebelum-instalasi)
4. [Pemasangan Pertama Kali](#4-pemasangan-pertama-kali)
5. [Pengaturan Aplikasi (Variabel Lingkungan)](#5-pengaturan-aplikasi-variabel-lingkungan)
6. [Memperbarui ke Versi Terbaru](#6-memperbarui-ke-versi-terbaru)
7. [Cadangkan & Pulihkan Data (Backup & Restore)](#7-cadangkan--pulihkan-data-backup--restore)
8. [Mengawasi Kondisi Aplikasi (Monitoring & Log)](#8-mengawasi-kondisi-aplikasi-monitoring--log)
9. [Akses Lewat Internet dengan Keamanan (HTTPS)](#9-akses-lewat-internet-dengan-keamanan-https)
10. [Kalau Ada Masalah? (Troubleshooting)](#10-kalau-ada-masalah-troubleshooting)
11. [Daftar Alamat Halaman & Layanan (Endpoint)](#11-daftar-alamat-halaman--layanan-endpoint)
12. [Akses Alternatif via Cloudflare Tunnel](#12-akses-alternatif-via-cloudflare-tunnel)
13. [Antarmuka Admin Vue 3 — Build & Deploy](#13-antarmuka-admin-vue-3--build--deploy)
14. [Checklist Akhir Sebelum Go-Live](#14-checklist-akhir-sebelum-go-live)

---

## 1. Istilah Penting — Baca Ini Dulu

Sebelum masuk ke panduan teknis, mari samakan pemahaman dulu. Beberapa istilah di dokumen ini mungkin asing bagi Anda:

| Istilah | Artinya dalam Bahasa Sederhana |
|----------------------------------------|
| **Docker** | "Kotak ajaib" yang mengemas aplikasi beserta segala kebutuhannya, supaya bisa berjalan sama persis di komputer mana pun. |
| **Container** | Satu kotak Docker yang berisi satu bagian aplikasi (misalnya: aplikasi web, database). |
| **Database** | Tempat penyimpanan data terstruktur — seperti lemari arsip digital yang rapi. |
| **Volume** | "Laci penyimpanan permanen." Meski aplikasi dimatikan atau di-update, isi laci ini tetap aman. |
| **Port** | Nomor "pintu" tempat sebuah program mendengarkan permintaan. Contoh: port 5000. |
| **Reverse Proxy** | "Resepsionis gedung" — penerima tamu di depan yang meneruskan permintaan ke ruangan yang tepat, sekaligus menjaga keamanan. |
| **HTTPS** | Versi aman dari HTTP. Data yang lewat dienkripsi (disandikan) sehingga tidak bisa dibaca pihak lain. |
| **Endpoint** | Alamat spesifik tempat aplikasi menerima permintaan. Contoh: `/login`, `/api/stats`. |
| **Backup** | Salinan data cadangan, disimpan agar bisa dikembalikan jika terjadi masalah. |
| **Log** | Catatan aktivitas harian aplikasi — sangat berguna saat mencari penyebab masalah. |

---

## 2. Cara Kerja Sistem (Arsitektur & Port)

Bayangkan BPF WorkHub sebagai sebuah kantor kecil dengan beberapa ruangan:

```
        Internet / VPN (dunia luar)
                 │
                 ▼
   ┌─────────────────────────────────┐
   │   REVERSE PROXY (nginx :5000)   │  ← Resepsionis / pintu utama (HTTPS)
   └─────────────────────────────────┘
                 │
      ┌──────────┴──────────┐
      ▼                     ▼
┌──────────────┐      ┌──────────────────┐
│   bbm_web    │◄────►│   bbm_mariadb    │
│  Aplikasi    │ data │    Database      │
│  port 5000   │      │    MariaDB       │
└──────────────┘      └──────────────────┘
      │
      ├── 🗄️  bbm_db_data  → laci data (tetap ada walau aplikasi restart)
      └── 📷  uploads/     → laci foto & bukti (juga permanen)
```

### 👥 Siapa Saja "Penghuninya"?

| Komponen | Nama Kotak | Port di Server | Tugasnya |
|----------|------------|----------------|----------|
| 🌐 Aplikasi Web | `bbm_web` | `5000` (produksi) · `5001` (untuk uji coba/dev) | Otak aplikasi. Sekalian menjadwalkan pembersihan foto lembur tiap 30 menit. |
| 🗄️ Database | `bbm_mariadb` | `3307` (di luar) · `3306` (di dalam) | Menyimpan semua data: user, transaksi, riwayat, dsb. |
| ⚡ Cache | `bbm_redis` | Hanya internal | "Catatan tempel cepat" — memb