# Desain: portal rekrutmen ramah HP (26 Nov 2026)

## Intent

Portal `v2.135.3` sudah menampilkan status tahap dengan benar, tetapi pada
layar 390×844 header + form memakan sekitar 510 px dan kartu berisi pesan
panjang membuat pengguna harus scroll jauh untuk melihat empat tahap.
Tujuan: seluruh tahap terlihat dalam 1–2 layar HP tanpa menghilangkan pesan
konfirmasi humanis yang sudah disetujui.

## Goals

- Kartu ringkas: badge status, judul, dan satu baris ringkasan.
- Pesan lengkap tetap tersedia lewat tombol `Lihat keterangan` (expand).
- Urutan kartu tetap CV → Training → TKD → FirstWork.
- Tahap `SELESAI` tetap redup, tanpa tautan/form, dan tidak bisa diulang —
  expand hanya menampilkan teks.
- `Langkah berikutnya` tetap terlihat di dekat sapaan tanpa perlu scroll.

## Non-goals / anti-goals

- Tidak membuat halaman mobile terpisah atau komponen duplikat.
- Tidak mengubah kontrak `/api/recruitment/lookup` atau data yang dikirim.
- Tidak mengubah urutan tahap.
- Tidak menghapus input NIK/DOB atau token cabang.

## Constraints

- Satu kolom pada lebar < 640 px; grid dua kolom boleh tetap pada layar besar.
- Target sentuh minimal 44 px untuk tombol dan tautan.
- `meta viewport` sudah ada; tidak diubah.
- Teks ringkas tidak boleh menghilangkan informasi status/waktu yang sudah
  diuji di `RecruitmentPortalView.test.js`.

## Pendekatan

- **Dipilih:** kartu ringkas + expand. Alasan: pesan humanis tetap dapat
  dibaca, tapi tinggi kartu turun dari ~200 px menjadi ~96 px saat tertutup.
- CSS-only ditolak karena memotong pesan dengan ellipsis.
- Halaman mobile terpisah ditolak karena duplikasi komponen.

## Detail implementasi

### Struktur kartu

```
┌──────────────────────────────┐
│ ①  CV Online      ✓ Selesai │
│    25 Nov 19.28              │
│    Data diri tersimpan.      │
│    Lihat keterangan  ⌄       │
└──────────────────────────────┘
```

- Badge: `✓ Selesai` bila `SELESAI`, otherwise `Belum`.
- Ringkasan satu baris: bila selesai → `Data tersimpan pada <waktu>`; bila
  belum → kalimat pertama dari pesan yang sudah ada (tanpa mengubah makna).
- Tombol `Lihat keterangan` / `Tutup keterangan` dengan `aria-expanded`.
- Saat dibuka, tampilkan `stepNote(step)` utuh (pesan humanis yang sudah
  disetujui). Expanding tidak mengubah `cardTag`: kartu selesai tetap `<div>`.

### Header & form

- Logo 32 px sejajar dengan judul di satu baris; subtitle satu baris.
- Padding atas halaman 16 px (dari 24 px); jarak header-form 16 px (dari 24 px).
- Input tetap 16 px (mencegah auto-zoom iOS), tinggi minimal 44 px.
- Tombol Cek full-width seperti sekarang.
- Catatan privasi tetap, font 0.8 rem.

### Langkah berikutnya

- Baris `Langkah berikutnya: <label>` tetap di bawah sapaan.
- Kartu sesuai `next_action` mendapat border biru tipis (`rp-card--next`),
  bukan warna mencolok atau animasi.

### CSS

- `@media (max-width: 639px)`: satu kolom, kartu padding 12 px, min-height
  auto, ringkasan satu baris dengan `overflow: hidden; text-overflow: ellipsis`,
  tombol keterangan 44 px tinggi, padding bawah `env(safe-area-inset-bottom)`.
- `@media (min-width: 640px)`: perilaku lama dipertahankan (grid auto-fit,
  kartu penuh).

## Testing

- `frontend/src/views/RecruitmentPortalView.test.js`: kartu menampilkan ringkasan
  ringkas; `Lihat keterangan` membuka pesan penuh; kartu selesai tetap
  `DIV`/tanpa `href` setelah expand; tombol punya `aria-expanded`.
- Verifikasi visual lokal dengan Playwright viewport 390×844: 4 kartu
  terlihat dalam ≤ 2 layar dan tidak ada horizontal scroll.
- `npm test` + `npm run build`.

## Rilis

Patch `v2.135.4`: 7 stamp, CHANGELOG, PROGRESS, push, deploy NAS, sync DB,
smoke NIK `3509190102960003`.
