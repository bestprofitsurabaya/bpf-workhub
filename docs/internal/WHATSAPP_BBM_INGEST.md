# ⛽ Ingest Bukti BBM dari Grup WhatsApp — Riset Metode (20 Nov 2026)

Dokumen riset, belum implementasi. Tujuan: mengambil bukti transaksi BBM
yang saat ini dikirim driver ke grup WhatsApp (foto odometer + struk SPBU)
menjadi data terstruktur di WorkHub, tanpa mengganggu alur driver.

## 1. Temuan di perangkat (terverifikasi)

Perangkat uji: SM-A035F, Android 13, WhatsApp stable, grup "group BBM
Bestprofit". Yang diamati: driver mengirim 1–5 foto per pengisian (odometer,
struk, kadang nota tulis tangan).

| Temuan | Bukti |
|---|---|
| WhatsApp **mengompres** foto menjadi ±1600 px | File hasil unduh: 1599×899 px, 87 KB (foto odometer terbaca jelas) |
| Foto yang sudah dibuka otomatis tersimpan di folder media | `.../Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images/IMG-20261120-WA0000.jpg` |
| Folder itu **bisa dibaca `adb pull` tanpa root** | `adb pull` berhasil (2,5 MB/s) |
| `uiautomator dump` **tidak** memberi isi gambar | Hanya teks UI: nama pengirim, jam, "5 photos", "555 kB" |
| Screenshot layar maksimal 720×1600 | Lebih rendah dari file asli → **jangan** pakai screenshot untuk OCR |
| Nama pengirim di grup ≠ username WorkHub | "dwki setiya nugraha", "guruhwinarto", satu pengirim memakai nomor HP di profil |
| Data di grup bisa beda dengan WorkHub | Foto: `B 2731 SRQ` / `DWIKI SETYA`; tabel `drivers` saat ini: `L 1904 TF` |

Konsekuensi: kualitas maksimum yang bisa didapat = file yang WhatsApp
kirimkan (±1600 px, sudah dikompres). Foto asli dari kamera driver tidak
tersedia lagi. OCR harus dirancang untuk gambar sebesar itu.

## 2. Opsi akuisisi gambar

| Metode | Kualitas | Batch | Risiko | Catatan |
|---|---|---|---|---|
| **Export chat → Include media** | Penuh (file yang sama) | Riwayat, maks. 10.000 pesan terakhir | Rendah (fitur resmi) | Android **tidak** menyimpan otomatis: harus pilih tujuan (Drive/Files/Downloads) di share sheet. `_chat.txt` memberi pengirim + timestamp. |
| **Buka tiap foto → `adb pull` folder media** | Penuh | Otomatis tetapi lambat (harus buka/scroll) | Rendah (pemakaian normal) | Terbukti bekerja. Cocok untuk pilot & tambahan harian. Rapuh bila UI WhatsApp berubah. |
| Screenshot viewer | 720 px | Otomatis | Rendah | Kualitas turun; tidak disarankan. |
| WhatsApp Web / Baileys (linked device) | Penuh | Real-time, besar | **Tinggi: melanggar ToS, akun bisa dibatasi/diblokir** | Butuh QR, nomor khusus, session persisten. Tidak disarankan untuk nomor bisnis utama. |
| Cloud API Groups | Penuh | Real-time resmi | Rendah | **Maks. 8 peserta**, butuh Official Business Account, dan grup lama tidak bisa dipindahkan. Tidak cocok untuk grup existing. |
| Notification listener | Teks/thumbnail | Hanya pesan baru | Sedang (izin khusus) | Tidak dapat riwayat, tidak dapat media penuh. |

**Rekomendasi akuisisi**

1. **Riwayat:** satu kali Export chat (Include media) → simpan ke Downloads →
   `adb pull` → arsipkan zip asli sebagai bukti.
2. **Harian:** buka foto baru lewat otomatisasi UI (scroll + tap), lalu
   `adb pull` dari folder media. Ini pemakaian wajar aplikasi, tanpa root,
   tanpa melanggar ToS.
3. **Jangka panjang:** pindahkan pelaporan ke PWA driver (sudah ada). Ingest
   WhatsApp menjadi jembatan, bukan tujuan akhir.

## 3. Opsi ekstraksi (OCR / VLM)

Bukti benchmark 2026:

- OCR klasik + regex lemah untuk *field*: PaddleOCR hanya 32,5% F1 (SROIE)
  dan 1,5% F1 (CORD Indonesia); Tesseract lebih buruk (CER ±33%).
- OCR + LLM post-processing menaikkan F1 field menjadi ±55–62%.
- **VLM** terbaik: Qwen3-VL-8B (open, Apache 2.0) zero-shot ±0,655 F1
  (ReceiptBench), dan setelah SFT/QLoRA ±0,795 — mengalahkan Gemini-3-Pro
  (0,737). Pada CORD (struk Indonesia berbahasa Indonesia, Rupiah),
  Qwen3-VL-8B QLoRA mencapai field micro-F1 0,93 dan total exact-match 90%.
- Benchmark lain: Gemini Flash sangat akurat pada dokumen bersih (±99% teks),
  tetapi data keluar dari premis.

**Rekomendasi ekstraksi (bertahap)**

1. **Pilot:** VLM sekali jalan (self-hosted Qwen3-VL-8B-Instruct, 4-bit) dengan
   output JSON schema ketat + aturan validasi. Tidak perlu training.
2. **Produksi:** Qwen3-VL-8B + LoRA pada 300–500 foto berlabel dari grup ini
   (odometer & struk SPBU). Target field-F1 > 0,9 untuk nopol, ODO, liter,
   rupiah, tanggal.
3. **Cadangan:** bila ada GPU terbatas, PaddleOCR hanya untuk crop angka
   odometer (digit putih di layar gelap) — bukan untuk seluruh dokumen.
4. Jangan pakai Tesseract untuk struk thermal/foto miring.

## 4. Arsitektur usulan

```
WhatsApp (export / folder media)
   │  gambar + metadata (pengirim, waktu)
   ▼
Ingest (hash SHA-256, dedup)
   ▼
Klasifikasi foto: odometer | struk SPBU | nota tulis | lain
   ▼
VLM → JSON {nopol, driver, odo_km, liter, harga/liter, total, spbu,
            tanggal, jam, jenis_bbm, confidence per field}
   ▼
Validasi aturan:
  - ODO naik dibanding pengisian sebelumnya untuk nopol itu
  - liter × harga ≈ total (±2%)
  - tanggal/jam struk vs timestamp chat (±1 hari)
  - nopol ada di master kendaraan
  - hash gambar belum pernah masuk (proof_registry)
   ▼
Status: auto-OK | perlu review
   ▼
Review UI (Admin/GA) → simpan ke transactions + foto bukti
```

Prinsip: **uang tidak pernah masuk otomatis tanpa validasi**. Item yang
lolos aturan boleh otomatis; sisanya masuk antrean review dengan crop
gambar dan field yang meragukan.

## 5. Skema data minimum

| Field | Sumber | Wajib |
|---|---|---|
| `driver_name` (kunci WorkHub) | pemetaan pengirim grup → user | ya |
| `nopol` | foto (pelat/struk) | ya |
| `odo_km` | foto odometer | ya |
| `liter`, `harga_per_liter`, `total` | struk | ya |
| `spbu`, `jenis_bbm` | struk | ya |
| `tanggal`, `jam` | struk + timestamp chat | ya |
| `foto_hash`, `foto_path` | ingest | ya |
| `confidence` per field | VLM | ya |
| `raw_text` | VLM | untuk audit |

## 6. Pemetaan identitas & rekonsiliasi

- Buat tabel alias: nama tampilan WhatsApp / nomor HP → `users.username`.
- Jangan percaya nopol di master saat ini untuk data historis; ambil nopol
  dari foto, lalu cocokkan dengan `vehicle_assignments` **pada tanggal itu**.
- Kasus nyata: foto `B 2731 SRQ` (Dwiki) vs master `L 1904 TF` — harus
  diselesaikan sebelum impor massal.

## 7. Kepatuhan & keamanan

- Data berisi nomor HP pihak ketiga: simpan hanya yang perlu, batasi akses
  ke Admin/GA, jangan commit ke repo.
- Arsip zip export & gambar mentah disimpan terenkripsi, retensi disepakati.
- Otomatisasi UI hanya membuka & mengunduh — tidak mengirim pesan, tidak
  menambahkan anggota (menghindari pola spam).
- Jangan memakai library tidak resmi (Baileys/whatsapp-web.js) pada nomor
  bisnis utama.

## 8. Rencana kerja

| Tahap | Isi | Perkiraan |
|---|---|---|
| 0 | Pilot 20–50 foto: export/pull, klasifikasi, VLM, ukur akurasi | 1–2 hari |
| 1 | Skema DB + endpoint ingest + review UI sederhana | 3–5 hari |
| 2 | Validasi aturan + dedup + pemetaan driver | 2–3 hari |
| 3 | Otomatisasi pengambilan harian dari perangkat | 2–3 hari |
| 4 | LoRA/peningkatan akurasi bila field-F1 < 0,9 | 3–5 hari |

## 9. Yang perlu diputuskan

1. Jalur akuisisi: **Export chat** (riwayat) atau otomatisasi folder media
   (harian), atau keduanya.
2. Penempatan model: self-hosted di NAS (perlu RAM/GPU) vs API VLM
   (akurat, tetapi data keluar).
3. Cakupan: hanya BBM, atau juga kasbon/trip dari grup yang sama.
