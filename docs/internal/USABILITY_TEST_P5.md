# Uji Kegunaan P5 — Admin Cabang (`admin_sby`)

Tujuan: memastikan admin cabang bisa menemukan dan menjalankan tugas inti
dengan cepat. Target utama: **time-to-first-action < 30 detik**.

## Metode

- Moderasi ringan, 5 partisipan (idealnya 2 admin cabang, 2 GA, 1 Finance).
- Durasi 20–30 menit per sesi, think-aloud, tanpa membantu kecuali peserta macet > 60 detik.
- Gunakan data demo/staging. Jangan gunakan data produksi.
- Catat waktu, jumlah klik, error, dan kutipan peserta.

## Mengaktifkan mode uji

1. Buka `/app/dashboard?p5=1` lalu login. Mode tersimpan di `localStorage`.
2. Buka bantuan lewat tombol **❓** atau tombol **?**.
3. Panel **🧪 Mode uji kegunaan** menampilkan aksi pertama dan durasinya.
4. Tekan **Reset sesi** sebelum setiap tugas/sesi baru.
5. Matikan mode: `localStorage.removeItem('bpf_p5')` di console.

Time-to-first-action dihitung dari layout aplikasi selesai dimuat setelah login
sampai aksi bermakna pertama: klik kartu dashboard, buka detail, aksi antrean,
atau navigasi lewat pencarian menu. Data hanya di `sessionStorage` browser,
tidak dikirim ke server.

## 5 tugas

| # | Tugas | Selesai bila | Target |
|---|-------|--------------|--------|
| 1 | Temukan antrean klaim BBM yang menunggu verifikasi GA. | Tab Antrean GA terbuka. | < 30 dtk (aksi pertama) |
| 2 | Tolak satu klaim dengan alasan “foto bukti tidak terbaca”. | Toast sukses muncul, alasan tersimpan. | < 45 dtk |
| 3 | Cari arti **LPJ** dan jelaskan singkat. | Peserta menyebut arti yang benar. | < 25 dtk |
| 4 | Buka halaman Kasbon/BBM tanpa memakai sidebar. | Halaman Kasbon terbuka via Ctrl+K. | < 15 dtk |
| 5 | Putar ulang tur singkat dan sebutkan langkah pertama dashboard. | Tur berjalan, peserta menyebut langkah pertama. | < 30 dtk |

Target lulus: minimal **4 dari 5 peserta** berhasil per tugas dan
time-to-first-action **< 30 dtk** pada minimal 4 peserta.

## Naskah fasilitator

> “Terima kasih sudah membantu. Saya akan meminta Anda menyelesaikan lima tugas
> singkat. Silakan berpikir keras saat mengerjakan. Tidak ada jawaban salah;
> yang kami uji adalah tampilan aplikasi, bukan kemampuan Anda. Anda boleh
> berhenti kapan saja.”

Bacakan tugas satu per satu. Jangan menunjukkan menu atau tombol. Jika peserta
bertanya “apakah ini benar?”, jawab: “Silakan lanjutkan seperti yang Anda
anggap paling wajar.”

## Lembar observasi

| Peserta | Tugas | Sukses (Y/T) | Waktu | Klik | Error | Kutipan / gesekan |
|--------|-------|--------------|-------|------|-------|-------------------|
| P1 | 1 | | | | | |
| P1 | 2 | | | | | |
| P1 | 3 | | | | | |
| P1 | 4 | | | | | |
| P1 | 5 | | | | | |

Setelah semua tugas, minta penilaian **SEQ** (1 = sangat sulit, 7 = sangat
mudah) per tugas dan satu pertanyaan: “Apa satu hal yang paling membingungkan?”

## Analisis & tindak lanjut

- Hitung median waktu dan tingkat keberhasilan per tugas.
- Kelompokkan temuan: **Kritis** (tugas gagal/berbahaya), **Tinggi** (butuh
  bantuan), **Sedang** (lambat tapi selesai), **Rendah** (kosmetik).
- Perbaiki temuan Kritis/Tinggi lebih dulu, lalu ulangi tugas yang terdampak.
- Simpan hasil di bagian P5 `PROGRESS.md` (tanggal, jumlah peserta, metrik,
  temuan, perbaikan).

## Status

Perangkat uji dan instrumentasi selesai di repo. Sesi dengan 5 partisipan
belum dijalankan karena membutuhkan pengguna dan data demo; jalankan sesi
sebelum menaikkan versi/men-deploy batch UI/UX.
