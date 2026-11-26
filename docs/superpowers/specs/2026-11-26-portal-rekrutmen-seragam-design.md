# Desain — Empat Tahap Seragam (Portal Rekrutmen)

**Tanggal:** 26 November 2026
**Status:** Disetujui (arah A)
**Cakupan:** `frontend/src/views/RecruitmentPortalView.vue` + tes

## Maksud

Empat tahap saat ini terasa seperti empat komponen berbeda: aksi tidak
seragam, “Lihat keterangan” berpindah tempat, dan bahasa status tumpang
tindih. Tujuannya membuat keempatnya satu proses yang terkendali dan
terpercaya, tanpa mengubah alur atau data.

## Keputusan Arah

**Timeline bersambung.** Satu garis tipis menghubungkan simpul 1→4;
ruas setelah tahap selesai berwarna hijau redup. Semua baris memakai
anatomi yang sama.

## Anatomi Baris (sama untuk keempat tahap)

1. **Simpul** — nomor urut; ✓ untuk selesai.
2. **Judul + badge** — badge satu kata: `Selesai`, `Berikutnya`,
   `Belum`, `Terkunci`. Lebar badge disamakan agar kolom kanan rapi.
3. **Deskripsi** — satu baris, hanya di layar lebar.
4. **Baris status** — ringkasan singkat di kiri; aksi `Buka →` di kanan
   untuk tahap yang bisa dibuka.
5. **Kaki kartu** — `Lihat keterangan` di posisi yang sama untuk semua
   tahap yang punya keterangan, termasuk yang selesai.

## Perubahan Perilaku Teks

- Centang tidak lagi ganda: simpul menampilkan ✓, badge menulis `Selesai`
  tanpa ✓.
- Tahap yang ditandai `next_action` memakai badge `Berikutnya`, bukan
  `Belum`.
- Semua aksi memakai satu bentuk: `Buka →` (termasuk TKD).
- Header tahap menjadi dinamis: `1 dari 4 tahap selesai` setelah NIK
  dikenal; `4 tahap` sebelumnya.

## Struktur Teknis

`.rp-card` menjadi wadah visual (div) berisi:

- `.rp-card-main` — area klik; tetap `<a>` untuk tautan, `<button>` untuk
  TKD, `<div>` untuk selesai/terkunci. Kait `href`, `type`, dan tagName
  berpindah ke elemen ini.
- `.rp-details` — kaki kartu di dalam wadah, sehingga tidak pernah ikut
  bernavigasi dan posisinya seragam.

Atribut `data-step`, `data-locked`, `data-status`, kelas `rp-card--done`,
`rp-card--locked`, `rp-card--next` tetap di `.rp-card` agar tes lama
tetap membaca baris yang benar.

## Yang Tidak Berubah

- Backend, token, API, aturan tahap, dan penyamaran nama.
- Teks penting: “Lengkapi CV Online terlebih dahulu.”,
  “Langkah berikutnya: …”, “Lihat keterangan”, “Data tersimpan pada”.
- Urutan tahap: CV, TRAINING, TKD, FIRSTWORK.

## Verifikasi

- Tes portal diperbarui untuk kait `.rp-card-main` dan teks badge baru.
- Tambah tes: badge `Berikutnya`, header `1 dari 4 tahap selesai`,
  dan kaki keterangan berada di dalam kartu untuk tahap aktif.
- Seluruh tes frontend + build.
- Pratinjau 390 px dan 1280 px, tanpa gulir horizontal.
