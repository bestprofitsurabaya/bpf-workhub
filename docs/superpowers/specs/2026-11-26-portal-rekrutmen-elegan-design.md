# Portal Rekrutmen — Desain Visual “Tenang, Presisi, Terpercaya”

**Tanggal:** 26 November 2026
**Status:** Menunggu persetujuan
**Cakupan:** Tampilan `frontend/src/views/RecruitmentPortalView.vue`

## Maksud

Portal rekrutmen adalah kesan pertama pelamar terhadap PT Bestprofit Futures.
Saat ini halaman berfungsi baik dan ramah HP, tetapi masih terasa seperti
formulir admin. Tujuannya membuatnya terasa seperti layanan keuangan resmi:
tenang, presisi, dan terpercaya — bukan korporat yang dingin.

Pelamar harus langsung memahami tiga hal: data mereka aman, statusnya jelas,
dan langkah berikutnya terlihat.

## Sasaran

- Hierarki jelas: merek → pemeriksaan NIK → langkah berikutnya → empat tahap.
- Bahasa visual formal: navy dalam, putih hangat, garis rambut, aksen merah
  logo yang sangat terbatas.
- Tetap ramah HP: satu kolom, target sentuh ≥44 px, tanpa gulir horizontal.
- Aksesibel: kontras teks memadai, fokus keyboard terlihat, hormati
  `prefers-reduced-motion`.
- Alur, token, privasi, dan panel TKD tidak berubah.

## Bukan Sasaran

- Tidak mengubah backend, skema, token, atau aturan tahap.
- Tidak menambah library/komponen UI baru.
- Tidak mendesain ulang form CV, training, atau FirstWork.
- Tidak menambah mode gelap untuk halaman publik ini.
- Tidak memakai foto, ilustrasi, atau animasi masuk yang berlebihan.

## Anti-sasaran

- Terlihat seperti dashboard admin generik.
- Emoji, warna merah untuk status/error, atau bayangan kartu yang berlebihan.
- Teks abu-abu berkontras rendah atau tombol di bawah 44 px.
- Animasi yang memperlambat pelamar.

## Bahasa Visual

Token warna dan tipe (scoped pada halaman portal):

| Token | Nilai | Pemakaian |
|---|---|---|
| `--rp-ink` | `#0B1F3A` | Judul, tombol utama, langkah aktif |
| `--rp-ink-2` | `#334155` | Teks isi |
| `--rp-muted` | `#64748B` | Keterangan sekunder |
| `--rp-bg` | `#F4F6F8` | Latar halaman |
| `--rp-paper` | `#FFFFFF` | Panel/lembar |
| `--rp-line` | `#DCE3EA` | Garis rambut |
| `--rp-accent` | `#B3122E` | Aksen tipis dari merah logo |
| `--rp-accent-soft` | `#FBEAEC` | Latar penanda langkah aktif |
| `--rp-success` | `#166534` | Status selesai |
| `--rp-focus` | `#1E4E8C` | Cincin fokus keyboard |

- **Tipografi:** system sans yang sudah dipakai aplikasi. Judul 600–700 dengan
  `letter-spacing: -0.01em`; body 16 px di HP, 15–16 px di desktop,
  `line-height: 1.6`.
- **Bentuk:** radius 4 px untuk kontrol, 8 px untuk lembar; tanpa bayangan
  kartu, hanya garis rambut dan satu bayangan lembut pada panel utama.
- **Ikon:** SVG garis (perisai, kunci, centang, panah). Tidak ada emoji.
- **Gerak:** transisi 160 ms `ease-out` untuk hover/fokus; tanpa animasi masuk.

## Susunan Halaman

1. **Bilah merek** (putih, garis bawah rambut)
   Logo resmi `bpf-logo.png` + “PT Bestprofit Futures”; di kanan label kecil
   “Portal Rekrutmen”. Di HP menumpuk rapi.
2. **Kepala halaman**
   Eyebrow “REKRUTMEN KARYAWAN”, H1 “Pantau proses rekrutmen Anda”, satu baris
   penjelas. Di bawahnya dua penanda kepercayaan: “Data pribadi dilindungi” dan
   “Cukup NIK 16 digit”.
3. **Panel pemeriksaan NIK** (lembar putih)
   Label, input 48 px, tombol navy. Di HP tombol selebar panel; di desktop
   sejajar. Catatan privasi dengan ikon kunci.
4. **Ringkasan setelah NIK dikenal**
   Strip sapaan dengan nama tersamar, lalu blok “Langkah berikutnya” yang
   ditonjolkan dengan garis aksen kiri. Bila semua selesai, pesan penutup.
5. **Daftar tahap vertikal** (bukan grid kartu)
   Tiap baris: simpul status (nomor atau centang), judul, badge status,
   ringkasan satu baris, dan panah bila bisa dibuka. Baris aktif memakai latar
   `--rp-accent-soft` + garis kiri aksen; baris selesai diredupkan namun tetap
   terbaca; baris terkunci menampilkan kunci dan petunjuk. “Lihat keterangan”
   tetap tersedia di bawah baris.
6. **Panel TKD** tetap memakai komponen yang ada.

## Perilaku yang Dipertahankan

- Sebelum NIK dikenal, hanya CV yang aktif; tiga tahap lain terkunci.
- Setelah dikenal, keempat tahap aktif; TKD membuka panel, bukan tautan.
- Nama hanya tersamar; cabang, NIK penuh, dan token tidak pernah dirender.
- Teks dan kait uji yang sudah ada dipertahankan: `.rp-card[data-step]`,
  `form.rp-check`, `aria-label="NIK 16 digit"`, “✓ Selesai”,
  “Langkah berikutnya: …”, dan “Lihat keterangan”.

## Risiko dan Mitigasi

- **Struktur DOM berubah** → pertahankan kelas, atribut data, dan teks yang
  diuji; jalankan seluruh tes portal.
- **Logo lebar di HP** → batasi tinggi 28–32 px dan gunakan `object-fit`.
- **Kontras** → periksa pasangan teks/latar terhadap WCAG AA.
- **Perubahan hanya satu berkas** → tidak menyentuh logika, token, atau API.

## Verifikasi

- `npx vitest run src/views/RecruitmentPortalView.test.js`
- Pratinjau 390 px dan 1280 px: tanpa gulir horizontal, target sentuh ≥44 px.
- Pemeriksaan keyboard: Tab melalui input, tombol, dan baris tahap.
- `npm run build`
