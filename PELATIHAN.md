# 🎯 Lembar Latihan per Peran — BPF WorkHub v2.35.1

Panduan latihan singkat (±5–10 menit per peran) untuk gladi resik sebelum demo atau meeting. Tiap latihan menjelaskan langkah yang harus dilakukan dan hasil yang diharapkan.

**PT. Bestprofit Futures — Kantor Pusat Jakarta**  
Equity Tower, SCBD Lot 9, Jl. Jend. Sudirman Kav. 52-53, Jakarta Selatan 12190  
Telp: 031-5349888

---

## 📋 Daftar Isi

1. [OB — Pengajuan Air Minum](#1-ob--pengajuan-air-minum)
2. [Driver — BBM, Kasbon, Trip](#2-driver--bbm-kasbon-trip)
3. [GA — Verifikasi Klaim & Kasbon](#3-ga--verifikasi-klaim--kasbon)
4. [Finance — Rekap & Verifikasi](#4-finance--rekap--verifikasi)
5. [Marketing — Appointment](#5-marketing--appointment)
6. [Chief Driver — Pembagian Tugas](#6-chief-driver--pembagian-tugas)
7. [Receptionist — Pelamar Kerja](#7-receptionist--pelamar-kerja)
8. [Traineer — Pantau Rekrutan](#8-traineer--pantau-rekrutan)
9. [Admin — User & Pengaturan](#9-admin--user--pengaturan)
10. [IT Surabaya — News Scraper](#10-it-surabaya--news-scraper)
11. [Daftar Periksa Sebelum Demo](#11-daftar-periksa-sebelum-demo)

---

## 1. OB — Pengajuan Air Minum

| # | Langkah | Hasil yang Diharapkan |
|---|---------|----------------------|
| 1 | Login `ob_faisol_sby` / PIN `123456` | Langsung masuk Halaman Air Minum, nama Faisol tampil |
| 2 | Klik **➕ Ajukan Pembelian** | Form muncul: tanggal, jumlah, jenis, merk, 2 kolom foto |
| 3 | Pilih jenis Galon, merk AQUA Galon, isi jumlah, unggah foto | Form terisi, tombol kirim aktif |
| 4 | Klik kirim | Pengajuan muncul di daftar dengan status Menunggu Verifikasi |
| 5 | (Coba) kirim tanpa foto | Muncul peringatan foto wajib — pengajuan tidak terkirim |

> 🔍 **Cek isolasi:** login sebagai `ob2` → harus TIDAK melihat pengajuan milik Faisol.

---

## 2. Driver — BBM, Kasbon, Trip

| # | Langkah | Hasil yang Diharapkan |
|---|---------|----------------------|
| 1 | Buka `/app/driver`, login PIN | Masuk aplikasi driver, 4 tab tampil |
| 2 | Tab ⛽ BBM → isi klaim + foto struk | Klaim masuk antrean (cek via GA) |
| 3 | Tab 💰 Kasbon → ajukan nominal | Total otomatis + kode unik |
| 4 | Tab 🗺️ Trip → isi log perjalanan | Tersimpan, muncul di review GA |
| 5 | Tab 📊 Rapor → masukkan nopol | Tampil HEMAT / CUKUP / BOROS |

> 🔍 **Cek offline:** matikan internet → isi data → hidupkan → tekan 🔄 Sinkron → badge antrean hilang.

---

## 3. GA — Verifikasi Klaim & Kasbon

| # | Langkah | Hasil yang Diharapkan |
|---|---------|----------------------|
| 1 | Login `ga_sby` / PIN `123456` | Langsung masuk Dashboard GA |
| 2 | Lihat antrean klaim | Klaim demo (BPF-DEMO-…) tampil |
| 3 | Klik **✅ Approve** satu klaim | Klaim pindah status (ke Finance) |
| 4 | Klik **✕ Tolak** tanpa alasan | Tombol terkunci — alasan wajib |
| 5 | Lihat kasbon menunggu approve | Kasbon DRAFT tampil dengan nominal |
| 6 | (Opsional) buka 🛡 Verifikasi Anomali | Modal konfirmasi muncul |
| 7 | Buka menu 🔧 Aset & Pemeliharaan (`/app/assets`) | Tab AC: 15 unit; tab kendaraan: 8 unit |
| 8 | Klik 🛠️ pada satu unit AC → isi form servis → simpan | Log tercatat + health score otomatis muncul |
| 9 | Buka tab 📋 Rekomendasi → klik 🔄 Perbarui | Daftar rekomendasi tampil |
| 10 | Klik 📄 Laporan PDF AC / Kendaraan | PDF resmi berlogo BPF + TTD GA terunduh |

> 🔍 **Cek akses:** GA mencoba buka `/app/dashboard` → ditolak (guard peran).

---

## 4. Finance — Rekap & Verifikasi

| # | Langkah | Hasil yang Diharapkan |
|---|---------|----------------------|
| 1 | Login `finance_sby` / PIN `123456` | Langsung masuk Dashboard Finance |
| 2 | Lihat Rekap Air Minum | Kartu statistik + ringkasan per OB terisi |
| 3 | Buka antrean verifikasi | Pengajuan pending (WTR-DEMO-01) tampil |
| 4 | Klik **✅ Verifikasi** → isi remark | Status jadi Terverifikasi |
| 5 | Klik 📄 PDF pada yang terverifikasi | PDF tanda terima terbuka |
| 6 | Klik ⬇ Export CSV | File Excel terunduh |
| 7 | Lihat kasbon menunggu Finance | Kasbon GA_APPROVED tampil |

---

## 5. Marketing — Appointment

| # | Langkah | Hasil yang Diharapkan |
|---|---------|----------------------|
| 1 | Login akun Marketing (`marketing_yusie_sby`) | Masuk Marketing Hub |
| 2 | Buat appointment baru (tanggal, sesi, jam kunjungan, alamat) | Tersimpan, muncul di papan |
| 3 | Lihat jadwal hari ini | Appointment demo tampil |
| 4 | (Opsional) edit/batal | Status berubah, notifikasi keluar |

---

## 6. Chief Driver — Pembagian Tugas

| # | Langkah | Hasil yang Diharapkan |
|---|---------|----------------------|
| 1 | Login akun Chief Driver | Masuk board Chief Driver |
| 2 | Lihat "Belum Ditugaskan" | Appointment tanpa driver tampil |
| 3 | Klik ⚡ Atur Rute Otomatis | Modal saran rute per driver |
| 4 | Klik ✅ Terapkan Rute | Driver otomatis ditugaskan + notifikasi |
| 5 | Tugaskan manual (opsional) | Muncul di panel "Tugas Per Driver" |
| 6 | Unduh rekap harian | File Excel terunduh |

---

## 7. Receptionist — Pelamar Kerja

| # | Langkah | Hasil yang Diharapkan |
|---|---------|----------------------|
| 1 | Login akun Receptionist | Masuk dashboard Pelamar Kerja |
| 2 | Buka `/app/apply` (tab baru, tanpa login) → isi form | Sukses + No. Registrasi PLM-* + jam interview otomatis |
| 3 | Cari nama pelamar di dashboard | Baris pelamar tampil |
| 4 | Klik ✅ Verifikasi lalu 🎯 Catat Kehadiran → tandai Interview + H1 | Status naik otomatis |
| 5 | Klik 🚪 Mengundurkan Diri tanpa alasan | Ditolak — alasan wajib |
| 6 | Isi alasan → simpan | Status Mengundurkan Diri |
| 7 | Pilih tahap laporan → 📄 Laporan PDF | PDF resmi berlogo BPF + TTD terunduh |
| 8 | (Opsional) ✏️ Edit data yang salah | Data berubah, tercatat audit |
| 9 | Buka ⚙️ Kelola User → tambah opsi baru | Opsi muncul di dropdown form |
| 10 | Nonaktifkan/hapus salah satu opsi | Opsi hilang dari dropdown, tercatat audit |

---

## 8. Traineer — Pantau Rekrutan

| # | Langkah | Hasil yang Diharapkan |
|---|---------|----------------------|
| 1 | Login akun Traineer | Masuk Rekrutan Saya |
| 2 | Gunakan filter tanggal / user / status | Daftar terfilter sesuai |
| 3 | Perhatikan chip kehadiran (I · H1–H4) | Chip menyala sesuai tahap |
| 4 | (Coba) klik tombol edit/hapus | Tidak ada — Traineer hanya melihat (read-only) |

---

## 9. Admin — User & Pengaturan

| # | Langkah | Hasil yang Diharapkan |
|---|---------|----------------------|
| 1 | Login `admin` / PIN `123456` | Masuk Dashboard Admin |
| 2 | Buka Users → cari user | Daftar user tampil; bisa nonaktifkan/aktifkan |
| 3 | Buka Settings | Nama Finance & GA untuk tanda terima bisa diubah |
| 4 | Buka Audit Log | Aksi-aksi tadi tercatat |
| 5 | Coba tombol 🌙 dan 🔆 | Mode gelap & kontras tinggi berganti |
| 6 | Buka **Access Review** | Kartu ringkasan akun tampil; tombol Export CSV berfungsi |
| 7 | Buka **Settings → Retensi & Arsip** | Tabel kebijakan + inventaris live semua cabang tampil |
| 8 | Buka **Settings → Verifikasi & Registri Dokumen** | Registri PDF resmi tampil; unggah PDF → status keaslian |
| 9 | Minta Finance menekan tombol verifikasi air minum | Modal **PIN ulang** muncul — aksi baru lanjut setelah PIN benar |

---

## 10. IT Surabaya — News Scraper

| # | Langkah | Hasil yang Diharapkan |
|---|---------|----------------------|
| 1 | Login `it_sby` / PIN `123456` | Masuk News Scraper, sidebar 📰 News Scraper tampil |
| 2 | Klik ➕ Add Site → isi nama, WP URL, username, app password | Site tersimpan di daftar |
| 3 | Klik 🔌 Test pada site | Pesan "Koneksi berhasil" muncul |
| 4 | Pilih sumber (Newsmaker/Detik/Semua) → atur halaman → 🔍 Check Articles | Artikel muncul dengan badge sumber (cyan/orange) |
| 5 | Klik 📤 Upload to WordPress | Artikel terupload + SEO score + backlinks otomatis |
| 6 | Klik 🔍 Check Duplicates | Duplikat terdeteksi (jika ada) |
| 7 | Klik 🔗 Backlinks → lihat authority sites | 24+ situs otoritas tampil |
| 8 | Klik 📝 Log | Aktivitas scraper tercatat |

---

## 11. Daftar Periksa Sebelum Demo

- [ ] Data demo masih ada (cek: antrean GA ada klaim, rekap finance ada air minum)
- [ ] 2–3 tab browser siap (GA, Finance, OB) untuk demo realtime
- [ ] Foto contoh siap di perangkat (air minum sebelum/sesudah, struk BBM)
- [ ] Akun & PIN terverifikasi (semua role)
- [ ] PDF slide deck & PPTX siap dibagikan (`presentasi/`)
- [ ] Bersihkan data demo setelah selesai: `ROOT_PW=$(grep -E '^MYSQL_ROOT_PASSWORD=' .env | cut -d= -f2-); docker exec -i bbm_mariadb mariadb -uroot -p"$ROOT_PW" bpf_asset_system < scripts/demo_cleanup.sql`

> 💡 Panduan lengkap & narasi demo ada di **PRESENTASI.md** — slide interaktif **presentasi/index.html**.

---

## 📞 Kontak

**PT. Bestprofit Futures — Kantor Pusat Jakarta**  
Equity Tower, SCBD Lot 9, Jl. Jend. Sudirman Kav. 52-53, Jakarta Selatan 12190  
Telp: 031-5349888

---

*BPF WorkHub v2.35.1 · Lembar Latihan per Peran*
