# Desain — Kartu First Work Selaras Portal (v2.135.10)

**Tanggal:** 26 November 2026
**Status:** Disetujui arah (visual + ringkasan tahap; hanya alur portal)
**Cakupan:** `modules/pdf_generator.py`, `modules/routes_first_work.py`,
`modules/routes_recruitment.py`, tes

## Maksud

Portal rekrutmen sudah memakai satu bahasa visual: navy tenang, garis
rambut, simpul bernomor, dan status satu kata. Dokumen PDF yang lahir dari
alur portal — **Kartu BPF First Work** — masih memakai tampilan lama tanpa
ringkasan tahap. Akibatnya, dokumen cetak tidak mencerminkan posisi pelamar
di proses yang sama.

`ApplicantReportPDF` (laporan kehadiran interview/training H1–H4) berasal
dari modul pelamar lama, bukan alur portal, sehingga **tidak diubah** dalam
rilis ini.

## Perubahan

### 1. Blok “STATUS REKRUTMEN” di kartu

Empat simpul sejajar, satu garis tipis penghubung:

```
(1)──────(2)──────(3)──────(4)
CV Online  Training  TKD   First Work
Selesai    Berikutnya Belum  Belum
```

- Simpul selesai: ✓ dengan isian hijau redup; ruas garis setelahnya hijau.
- Simpul berikutnya: nomor dengan isian merah redup dan teks merah.
- Simpul belum: nomor dengan isian abu muda dan teks abu.
- Label satu kata: **Selesai / Berikutnya / Belum** — sama dengan portal.
- Blok hanya muncul bila NIK punya kasus rekrutmen; baris legacy tanpa
  kasus tetap menghasilkan kartu identitas seperti sekarang.

### 2. Data dan isolasi cabang

- Ringkasan dihitung dari `recruitment_cases` + `recruitment_steps`
  memakai `portal_summary()` yang sudah dipakai portal.
- `portal_summary()` mendapat parameter opsional `branch_code`; bila diisi,
  langkah difilter ke cabang itu. Kartu memakai cabang submission, sehingga
  staf cabang tidak melihat capaian cabang lain.
- Rute kartu sudah dijaga `_row_allowed`; tidak ada perubahan izin.

### 3. Privasi

- Tidak ada NIK lengkap, nomor HP, atau token di kartu.
- Ringkasan hanya memuat status tahap, bukan detail berkas.

## Yang Tidak Berubah

- Kop resmi, footer versi, QR, dan seluruh 13 field demografi.
- Endpoint, peran, dan aturan cabang.
- `ApplicantReportPDF` dan PDF lain.

## Verifikasi

- Tes unit: blok muncul saat ada kasus; status benar; NIK lengkap tidak bocor.
- Tes rute: langkah cabang lain diabaikan; tanpa kasus blok tidak muncul.
- Render `pdftoppm` untuk memeriksa simpul, garis, dan keterbacaan.
- Seluruh tes Python + guard versi 7 titik.
