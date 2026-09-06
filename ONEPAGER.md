<p align="center">
  <img src="presentasi/bpf-badge.png" width="96" alt="BPF" />
</p>

# BPF WorkHub — Ringkasan Satu Halaman

**PT Bestprofit Futures · Kantor Pusat Jakarta**  
Equity Tower, SCBD Lot 9, Jl. Jend. Sudirman Kav. 52-53, Jakarta Selatan 12190 · Telp: 031-5349888

Sistem digital untuk pengelolaan BBM armada, kasbon driver, pembelian air minum, dan jadwal kunjungan tim — satu aplikasi, semua pihak terhubung.

---

## 🎯 Mengapa Sistem Ini Ada?

Sebelumnya, pencatatan BBM, kasbon, dan pembelian air minum dilakukan manual — rawan tercecer, sulit ditelusuri, dan lama diverifikasi. Sistem ini menggantikan catatan manual dengan alur digital yang jelas, terekam, dan bisa diverifikasi siapa pun kapan pun.

---

## 👥 Siapa Memakai dan Untuk Apa?

| Peran | Aktivitas Utama |
|-------|-----------------|
| **Driver** | Isi klaim BBM dari HP (foto struk wajib), lihat jadwal kunjungan, terima notifikasi |
| **Chief Driver** | Atur penugasan kunjungan ke driver, pantau status |
| **GA** | Verifikasi klaim BBM & kasbon driver, kelola data pengguna |
| **Finance** | Verifikasi & cairkan klaim, verifikasi pembelian air minum, rekap per OB |
| **OB** | Ajukan pembelian air minum (galon/botol/gelas) lengkap dengan foto sebelum & sesudah |
| **Marketing** | Catat jadwal kunjungan nasabah, pantau realisasi tim |
| **Receptionist** | Verifikasi & kelola data pelamar kerja: kehadiran interview + 4 hari training |
| **GA — Aset** | Pemeliharaan 15 unit AC kantor (health score) + 8 kendaraan + 12 komponen |
| **Traineer / Upline** | Pantau kehadiran orang yang direkrutnya |
| **Admin** | Kelola akun & nama penanda tangan, lihat analytics |
| **IT Surabaya** | Scrape artikel, upload ke WordPress dengan SEO & backlinks otomatis |

**Setiap peran hanya melihat halaman sesuai wewenangnya** (prinsip *least privilege*).

---

## ✨ Fitur Utama

- **Klaim BBM dari HP** — isi nominal, liter, odometer, foto struk; GA & Finance verifikasi di layar.
- **Kasbon driver** — pengajuan → persetujuan GA → pencairan Finance, semua tercatat.
- **Pembelian air minum** — OB mengisi tanggal, jumlah, foto before/after; Finance verifikasi → dokumen PDF.
- **Jadwal kunjungan marketing** — input jadwal + jam kunjungan, penugasan ke driver, hasil kunjungan terekam.
- **Rute otomatis hemat BBM** — Chief Driver sekali klik membagi kunjungan per area & urut jam (rute searah).
- **Sistem pelamar kerja** — form publik, jam interview otomatis; Receptionist mencatat kehadiran; laporan PDF resmi.
- **Notifikasi realtime** — driver langsung tahu klaimnya sudah diverifikasi atau ada jadwal baru.
- **Bisa dipakai offline** — koneksi tersambung kembali, data otomatis tersinkron.
- **Laporan PDF & Excel** — logsheet, rekap, dan dokumen tanda terima siap diunduh — **keasliannya bisa dibuktikan** (hash SHA-256 per dokumen).
- **News Scraper & SEO** — scrape artikel, upload ke WordPress, financial authority backlinks otomatis, duplicate checker.

---

## 🔒 Keamanan & Kualitas

- Login dengan PIN 6 digit per pengguna · sesi aman · proteksi laju permintaan (rate limit) · **PIN ulang untuk aksi uang** (step-up auth).
- Semua aksi tercatat (siapa, kapan, apa) — tidak bisa "hilang".
- Pemeriksaan otomatis keanehan pengisian (anomali) membantu mencegah salah input.
- **Program 6 tahap ISO/IEC 27001:2022 selesai** — secrets terkelola, step-up auth, access review triwulanan, audit kerentanan otomatis (CI + Dependabot + Trivy), retensi & arsip dokumen, serta verifikasi keaslian dokumen.
- 104 tes antarmuka (vitest) + 443 tes backend (pytest) — setiap perubahan diuji otomatis di CI.

---

## 📋 Apa yang Bisa Dilihat Langsung di Demo

1. **Driver** mengajukan klaim BBM dari HP → **GA** menyetujui → **Finance** memverifikasi.
2. **OB** mengajukan pembelian air minum dengan foto → **Finance** verifikasi → PDF tanda terima.
3. **Marketing** membuat jadwal kunjungan → **Chief Driver** menugaskan → hasil kunjungan tercatat.
4. **Pelamar** mengisi form → **Receptionist** memverifikasi & mencatat kehadiran → **Traineer** melihat rekrutannya.
5. Dashboard **Admin**: analytics, pengguna, dan pantauan realtime.

---

## 📄 Dokumen Pendukung

- Materi lengkap: `PRESENTASI.md`
- Slide presentasi: `presentasi/index.html` / `presentasi/BPF_Fleet_BBM_System_Presentasi.pdf`
- Lembar latihan: `PELATIHAN.md`
- Video walkthrough: `presentasi/videos/`
- Panduan pengguna: `USER_GUIDE.md`

---

*BPF WorkHub v2.35.1 · Ringkasan Satu Halaman*
