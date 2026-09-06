# 🎤 Materi Presentasi — BPF WorkHub v2.35.1

Panduan demo lengkap untuk presentasi di depan audiens. Urutan disusun dari yang paling berkesan ke yang paling teknis. Tiap bagian berisi tujuan, apa yang ditampilkan di layar, poin yang dibicarakan, dan satu kalimat kunci.

**PT. Bestprofit Futures — Kantor Pusat Jakarta**  
Equity Tower, SCBD Lot 9, Jl. Jend. Sudirman Kav. 52-53, Jakarta Selatan 12190  
Telp: 031-5349888

---

## 📋 Daftar Isi

1. [Peta Presentasi](#1-peta-presentasi)
2. [Pembuka — Cerita dari Lapangan](#2-pembuka--cerita-dari-lapangan)
3. [Satu Aplikasi, Semua Peran](#3-satu-aplikasi-semua-peran)
4. [Demo Utama 1 — Air Minum](#4-demo-utama-1--air-minum)
5. [Demo Utama 2 — Dashboard per Peran](#5-demo-utama-2--dashboard-per-peran)
6. [Demo Utama 3 — Klaim BBM & Kasbon](#6-demo-utama-3--klaim-bbm--kasbon)
7. [Demo Utama 4 — Realtime & Notifikasi](#7-demo-utama-4--realtime--notifikasi)
8. [Demo Utama 5 — Driver PWA Offline](#8-demo-utama-5--driver-pwa-offline)
9. [Demo Pendukung — Marketing & Chief Driver](#9-demo-pendukung--marketing--chief-driver)
10. [Demo Pendukung — IT Surabaya & News Scraper](#10-demo-pendukung--it-surabaya--news-scraper-2-menit-)
11. [Demo Pendukung — Pelamar Kerja](#11-demo-pendukung--pelamar-kerja)
12. [Keamanan & Tata Kelola](#12-keamanan--tata-kelola)
13. [Kualitas & Kepatuhan](#13-kualitas--kepatuhan)
14. [Penutup — Nilai & Langkah Berikutnya](#14-penutup--nilai--langkah-berikutnya)
15. [Persiapan Demo](#15-persiapan-demo)
16. [Kemungkinan Pertanyaan Audiens](#16-kemungkinan-pertanyaan-audiens)
17. [Kata Penutup](#17-kata-penutup)

**Dokumen Pendukung:**
- 🖥️ Slide deck interaktif: `presentasi/index.html`
- 📄 Versi PDF: `presentasi/BPF_Fleet_BBM_System_Presentasi.pdf`
- 🖊️ Versi PPTX: `presentasi/BPF_Fleet_BBM_System_Presentasi.pptx`
- 📋 Ringkasan satu halaman: `ONEPAGER.md`
- 🎬 Video walkthrough: `presentasi/videos/`
- 🎯 Lembar latihan: `PELATIHAN.md`
- ✅ Gladi resik otomatis: `node frontend/scripts/rehearsal.mjs`

---

## 1. Peta Presentasi

| # | Bagian | Durasi | Mengapa di Sini |
|---|--------|--------|-----------------|
| 0 | Pembuka: cerita masalah | 2 mnt | Menyentuh, audiens paham konteks |
| 1 | Satu aplikasi, semua peran | 2 mnt | Gambaran besar sebelum detail |
| 2 | Demo: Air Minum (OB → Finance) | 3 mnt | Fitur terbaru, unik, mudah dipahami |
| 3 | Demo: Dashboard per peran | 3 mnt | Menunjukkan pemisahan hak akses |
| 4 | Demo: Klaim BBM + Kasbon | 3 mnt | Alur uang — inti bisnis |
| 5 | Demo: Realtime & notifikasi | 2 mnt | "Wow factor", teknologi terasa |
| 6 | Demo: Driver PWA offline | 2 mnt | Relevan untuk pengguna lapangan |
| 7 | Demo: Marketing & Chief Driver | 2 mnt | Fitur pendukung penjualan |
| 8 | Demo: Pelamar Kerja | 2 mnt | Menggantikan Google Form |
| 9 | Demo: IT Surabaya & News Scraper | 2 mnt | Content management + SEO |
| 10 | Keamanan & tata kelola | 3 mnt | Menjawab kekhawatiran pengambil keputusan |
| 11 | Kualitas & kepatuhan | 2 mnt | Bukti kredibilitas teknis |
| 12 | Penutup: nilai & langkah berikutnya | 2 mnt | Ajakan bertindak |

**Total durasi:** ±15 menit (demo inti) atau ±30 menit (versi lengkap)

---

## 2. Pembuka — "Cerita dari Lapangan" (2 menit)

> Buka dengan cerita, bukan dengan fitur. Cerita membuat orang menempel.

**Skrip usulan (boleh diparafrase):**

> "Coba bayangkan seorang sopir yang habis isi bensin Rp 300 ribu. Dia bayar pakai uang sendiri dulu. Setibanya di kantor, dia harus mengantre laporan, menyerahkan struk, lalu menunggu berhari-hari uangnya diganti. Di sisi lain, tim Finance harus mengecek satu per satu struk, merekap manual di Excel, dan bertanya-tanya: 'uang yang saya transfer ini untuk yang mana ya?'
>
> Di kantor, OB membeli galon air minum, dan tidak ada bukti resmi kapan dan berapa yang dibeli.
>
> Hari ini, semua itu kami rapikan dalam satu aplikasi — **BPF WorkHub**."

**Satu kalimat kunci:**
> *"Dari 'catat di kertas, rekap di Excel' menjadi 'satu aplikasi, semua tercatat otomatis, semua bisa diaudit'."*

---

## 3. Satu Aplikasi, Semua Peran (2 menit)

**Yang ditampilkan:** halaman Login → masuk sebagai Admin.

**Poin yang dibicarakan:**
- Satu aplikasi yang dipakai semua orang di perusahaan — sopir, OB, GA, Finance, Marketing, Chief Driver, dan Admin.
- Setiap orang masuk dengan Username + PIN 6 digit, dan langsung dibawa ke halamannya masing-masing.
- Tidak ada yang tercampur: sopir tidak bisa melihat rekap keuangan, OB tidak bisa melihat klaim BBM.

**Satu kalimat kunci:**
> *"Satu aplikasi untuk semua, tapi setiap orang melihat dunianya sendiri."*

---

## 4. Demo Utama 1 — Air Minum: OB → Finance → PDF (3 menit) 💧

> Fitur paling baru dan paling mudah diceritakan. Mulai dari sini karena audiens langsung paham alurnya.

**Skenario demo:**

| Langkah | Layar | Yang Dilakukan | Yang Dibicarakan |
|---------|-------|---------------|-----------------|
| 1 | Login OB (`ob_faisol_sby` / `123456`) | Masuk → otomatis ke Halaman Air Minum | "Tiap OB punya halaman sendiri." |
| 2 | Form Air Minum | Isi tanggal, jumlah, pilih jenis & merk, unggah 2 foto | "Dua foto wajib — bukti dengan tanda waktu." |
| 3 | Kirim | Klik Ajukan | Status berubah jadi "Menunggu Verifikasi" |
| 4 | Login Finance (`finance_sby`) | Buka Dashboard Finance | "Finance langsung melihat antrean verifikasi." |
| 5 | Verifikasi | Periksa foto → isi remark → verifikasi | "Finance bisa menambah catatan — semua tercatat." |
| 6 | PDF | Klik 📄 PDF | "Tanda terima resmi yang ditandatangani Finance & GA." |

**Satu kalimat kunci:**
> *"Dari pembelian galon sampai tanda terima resmi — tercatat, terbukti, dan bisa diaudit, tanpa kertas."*

> 💡 **Tips demo:** pastikan 2 foto contoh sudah siap di HP/komputer.

---

## 5. Demo Utama 2 — Dashboard per Peran (3 menit) 🧾💰

**Skenario:** login bergantian 3 akun dan tunjukkan perbedaan halamannya.

| Login sebagai | Halaman | Sorotan |
|---------------|---------|---------|
| **Admin** | Dashboard Admin | Ringkasan seluruh operasi + akses semua menu |
| **GA** | Dashboard GA | Antrean klaim + tombol Approve/Tolak + verifikasi anomali |
| **Finance** | Dashboard Finance | Rekap air minum + antrean verifikasi + Export CSV |

**Poin yang dibicarakan:**
- GA bisa menyetujui atau menolak klaim langsung dari dashboard — alasan penolakan wajib diisi.
- Klaim bertanda ⚠️ (anomali) punya alur verifikasi khusus.
- Finance punya rekap lengkap dengan filter tanggal dan tombol export ke Excel.

**Satu kalimat kunci:**
> *"Setiap peran punya dashboard sendiri — pekerjaan selesai dari satu halaman, bukan berpindah-pindah menu."*

---

## 6. Demo Utama 3 — Klaim BBM, Kasbon & Kode Unik (3 menit) 🚗💰

**Skenario:** ceritakan alur "bayar dulu, ganti belakangan" dengan 4 peran.

| Langkah | Peran | Alur |
|---------|-------|------|
| 1 | **Driver** | Ajukan klaim BBM + foto struk → masuk antrean GA |
| 2 | **GA** | Approve → klaim pindah ke Finance |
| 3 | **Finance** | Cairkan dana → status "Diserahkan" |
| 4 | **Driver** | Isi LPJ (laporan pertanggungjawaban) |
| 5 | **GA** | Verifikasi LPJ → Selesai 🎉 |

**Sorotan: Kode Unik Kasbon**
> "Saat driver mengajukan kasbon Rp 100.000, sistem otomatis menambahkan kode unik — misalnya menjadi Rp 100.023. Saat Finance mentransfer, nominal persis itu yang menjadi bukti: uang ini untuk kasbon siapa."

**Satu kalimat kunci:**
> *"Setiap rupiah tercatat — dari pengajuan, persetujuan, pencairan, sampai pertanggungjawaban."*

---

## 7. Demo Utama 4 — Realtime & Notifikasi (2 menit) ⚡

**Skenario:** buka Dashboard GA dan Dashboard Finance bersebelahan (2 tab browser), lalu:
1. Login OB di tab 3 → buat pengajuan air minum.
2. Lihat: di tab Finance muncul toast 💧 + lonceng 🔔, dan antrean ter-refresh sendiri.

**Poin yang dibicarakan:**
- Semua perubahan berjalan real-time via WebSocket.
- Indikator ⚡ Realtime di pojok kanan atas — kalau putus, muncul 🔴.
- Finance tahu ada pengajuan saat itu juga, bukan besok pagi.

**Satu kalimat kunci:**
> *"Aplikasi ini 'hidup' — begitu ada yang mengajukan, yang berwenang langsung tahu, tanpa menunggu laporan."*

---

## 8. Demo Utama 5 — Driver PWA: Offline di Jalan (2 menit) 📱

**Skenario:** buka `/app/driver` (bisa di mode ponsel DevTools).

**Poin yang dibicarakan:**
- Driver login dengan PIN — identitasnya otomatis menempel di semua laporan.
- 4 tab: ⛽ BBM · 💰 Kasbon · 🗺️ Trip · 📊 Rapor.
- Mode offline: data tersimpan di HP dan terkirim otomatis saat online.
- Rapor performa: masukkan nopol → tahu kendaraan HEMAT / CUKUP / BOROS.
- Aplikasi bisa dipasang di layar utama HP (PWA).

**Satu kalimat kunci:**
> *"Sopir di jalan tetap produktif — sinyal hilang bukan alasan data hilang."*

---

## 9. Demo Pendukung — Marketing & Chief Driver (2 menit) 📣

**Poin yang dibicarakan:**
- Marketing: input jadwal kunjungan + jam kunjungan untuk driver, pantau status.
- Chief Driver: tombol ⚡ Atur Rute Otomatis — kunjungan dibagi per area & urut jam, estimasi jarak/BBM, angka penghematan.

**Satu kalimat kunci:**
> *"Bukan hanya BBM — penjadwalan kunjungan, pembagian sopir, dan rute hemat BBM juga satu pintu."*

---

## 10. Demo Pendukung — IT Surabaya & News Scraper (2 menit) 📰

**Skenario:** login sebagai IT Surabaya, tunjukkan alur scrape → upload → SEO.

| Langkah | Layar | Yang Dilakukan | Yang Dibicarakan |
|---------|-------|---------------|------------------|
| 1 | Login `it_sby` / `123456` | Masuk News Scraper dashboard | "Role IT cabang — semua terpusat di satu halaman, per-cabang access filtering." |
| 2 | WordPress Sites | Klik 🔌 Test Connection | "Multi-site management — bisa kelola beberapa WP sekaligus." |
| 3 | Scrape | Pilih sumber (Newsmaker/Detik) → Check Articles → 2 halaman | "Artikel komoditas langsung di-scrape — badge sumber & filter tersedia." |
| 4 | Upload | Klik Upload to WordPress | "Upload otomatis + SEO score + 24 authority backlinks." |
| 5 | Backlinks | Klik 🔗 Financial Backlinks | "24+ situs otoritas — OJK, BI, Bloomberg — backlink otomatis." |
| 6 | Duplicates | Klik Check Duplicates | "Deteksi & bersihkan artikel duplikat." |

**Satu kalimat kunci:**
> *"Content management yang terintegrasi — dari scraping sampai publikasi, semua otomatis dan SEO-friendly."*

---

## 11. Demo Pendukung — Pelamar Kerja (2 menit) 🪪

**Alur demo:**
1. Buka `/app/apply` (tanpa login) → isi form → muncul No. Registrasi PLM-* + jam interview otomatis.
2. Login Receptionist → data pelamar tadi langsung tampil → Verifikasi → Catat Kehadiran.
3. Coba Mengundurkan Diri tanpa alasan → ditolak (alasan wajib).
4. Pilih tahap laporan → 📄 Laporan PDF → dokumen resmi berlogo BPF.
5. Login Traineer → hanya melihat rekrutan dengan UPLINE miliknya.

**Satu kalimat kunci:**
> *"Dari Google Form manual menjadi sistem internal yang terstruktur — jam interview otomatis, kehadiran tercatat, laporan resmi."*

---

## 11. Keamanan & Tata Kelola (3 menit) 🔐

> Bagian ini yang paling sering ditanya pengambil keputusan.

| Topik | Kalimat yang Bisa Dipakai |
|-------|--------------------------|
| Login PIN per orang | "Setiap orang punya PIN — tidak ada akun bersama, semua aksi tercatat siapa." |
| Role-based access | "GA tidak bisa membuka rekap keuangan; OB tidak bisa melihat klaim." |
| Audit Log | "Semua aksi penting tercatat: siapa, apa, kapan — bisa difilter." |
| Anti peretasan | "Login dibatasi percobaan, token CSRF, unggahan foto diperiksa keamanannya." |
| Kerahasiaan data | "Sesi browser aman, data dilindungi, foto bukti tidak bisa disalahgunakan." |
| Aksi uang dua lapis | "Approve dan pencairan wajib konfirmasi PIN ulang — sekalipun akunnya dipakai orang lain, uang tidak bisa berpindah diam-diam." |
| Keaslian dokumen | "Setiap PDF resmi tercatat hash-nya — unggah file-nya, sistem langsung bilang asli atau sudah diubah." |
| Rawatan akun & data | "Hak akses direview tiap tiga bulan, log lama diarsipkan otomatis, dan tidak ada data yang dihapus tanpa persetujuan manajemen." |

**Satu kalimat kunci:**
> *"Sistem ini dibangun dengan prinsip keamanan berlapis — dari PIN pengguna sampai jejak audit setiap transaksi."*

---

## 12. Kualitas & Kepatuhan (2 menit) 🧪

**Poin yang dibicarakan:**
- 443 uji otomatis backend (pytest) + 104 uji frontend (vitest) — dipastikan hijau di CI tiap rilis.
- Uji end-to-end di produksi untuk alur kritis.
- Pemetaan standar: ISO/IEC 27001, ISO 9241-11, ISO 9001.
- Aksesibilitas: fokus keyboard, kontras warna, mode kontras tinggi, mode gelap.
- Antarmuka responsif — rapi di komputer maupun HP.

**Satu kalimat kunci:**
> *"Bukan prototipe — sistem yang diuji, diamankan, dan siap dipakai harian."*

---

## 13. Penutup — Nilai & Langkah Berikutnya (2 menit)

**Rangkum dalam 3 angka:**
> - **1 aplikasi** untuk semua peran.
> - **0 kertas** yang harus diarsip manual — semuanya digital.
> - **100% tercatat & bisa diaudit** — setiap rupiah, setiap galon, setiap perjalanan.

**Langkah berikutnya yang ditawarkan:**
1. Data master lengkap — daftar armada, driver, merk air minum.
2. Pelatihan singkat per peran (panduan sudah ada: `USER_GUIDE.md`).
3. Roadmap: laporan otomatis mingguan, approval berjenjang, dll.

---

## 14. Persiapan Demo

| Persiapan | Detail |
|-----------|--------|
| Data contoh | 1 pengajuan air minum + 1 klaim BBM + 1 kasbon + 1 pelamar kerja |
| 2–3 tab browser | Dashboard GA, Dashboard Finance, dan login OB |
| Foto contoh | 2 foto air minum + 1 struk BBM, sudah ada di perangkat |
| Akun | Semua role dengan PIN `123456` |
| Mode gelap/kontras | Tunjukkan tombol 🌙 dan 🔆 |
| Koneksi | Pastikan internet stabil (demo realtime) |
| Gladi resik | Jalankan `node frontend/scripts/rehearsal.mjs` — 20/20 cek |
| Video cadangan | Putar `presentasi/videos/walkthrough-all.mp4` jika demo live gagal |

---

## 15. Kemungkinan Pertanyaan Audiens

| Pertanyaan | Jawaban Singkat |
|------------|-----------------|
| "Kalau internet mati?" | Driver tetap bisa kerja (offline-first, sinkron otomatis). |
| "Data aman?" | Login PIN, hak akses per peran, audit log, percobaan login dibatasi. |
| "Bisa diakses dari mana?" | Dari browser apa pun — komputer, laptop, HP. |
| "Bagaimana kalau ada sopir baru / OB baru?" | Admin membuat akun dalam hitungan menit dari halaman Users. |
| "Bisa integrasi Excel?" | Sudah: export CSV rekap air minum, export Excel logsheet & rekap harian. |
| "Apakah ini bisa dipakai untuk cabang lain?" | Ya — tinggal tambah pengguna & data master; alurnya sama. |
| "Data pelamar masih lewat Google Form?" | Tidak — sudah diganti form internal; 914 riwayat Google Sheet lama sudah dimigrasikan. |
| "Ada aplikasi aset terpisah?" | Sudah dimigrasikan total ke WorkHub — 15 AC + 8 kendaraan + 12 komponen. |
| "Upline bisa lihat rekrutannya?" | Ya — Traineer membuka halamannya, otomatis hanya rekrutan dengan UPLINE miliknya. |

---

## 16. Kata Penutup

> "Kami tidak hanya membuat aplikasi — kami merapikan cara kerja sehari-hari. Sopir tidak perlu menunggu uangnya diganti berhari-hari. Finance tidak perlu menerka struk ini milik siapa. OB tidak perlu bingung bukti pembeliannya. Semuanya tercatat, terverifikasi, dan bisa dipertanggungjawabkan — dengan satu aplikasi yang dipakai semua orang, sesuai porsinya masing-masing. Terima kasih."

---

## 📞 Kontak

**PT. Bestprofit Futures — Kantor Pusat Jakarta**  
Equity Tower, SCBD Lot 9, Jl. Jend. Sudirman Kav. 52-53, Jakarta Selatan 12190  
Telp: 031-5349888

---

*BPF WorkHub v2.35.1 · Materi Presentasi · Diperbarui 6 September 2026*
