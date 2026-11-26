# Desain: status tahap di portal rekrutmen (26 Nov 2026)

## Intent

Portal rekrutmen (`v2.135.1`) hanya tahu apakah sebuah NIK dikenal. Untuk NIK
`3509190102960003`, data di produksi menunjukkan CV dan TKD sudah `SELESAI`,
tetapi portal menampilkan keempat kartu (CV, Training, TKD, FirstWork) dengan
tampilan yang sama. Peserta tidak bisa membedakan mana yang sudah selesai,
dan tidak tahu langkah mana yang harus diambil berikutnya.

Tujuan: portal membaca status dari `recruitment_steps` dan menandai tahap
selesai dengan jelas, tanpa mengubah cara peserta masuk (tetap NIK + tanggal
lahir + token cabang) dan tanpa memaksa urutan tahap.

## Goals

- Satu kali cek NIK mengembalikan keberadaan NIK **dan** status empat tahap.
- Tahap selesai ditandai `✓ Selesai` + waktu selesai, tampil redup, dan **tidak
  bisa dijalankan ulang** dari portal. Koreksi data dilakukan petugas.
- Peserta melihat satu baris "Langkah berikutnya" yang tenang.
- Tetap kompatibel dengan klien lama: kunci `known` dan `can_continue` tidak
  dihapus.

## Non-goals / anti-goals

- Tidak memperkenalkan token sesi atau menghapus input tanggal lahir (Rilis C
  sudah di-rollback).
- Tidak menambah tabel/kolom atau memindahkan `applicants` ke master.
- Tidak memaksa urutan CV → Training → TKD → FirstWork; data nyata menunjukkan
  TKD bisa selesai lebih dulu.
- Tidak menyediakan tombol/form ulang untuk tahap yang sudah `SELESAI`.
- Tidak menampilkan NIK lengkap, tanggal lahir, alamat, atau nama lengkap.

## Constraints

- `GET /api/recruitment/lookup` sudah punya rate limit 10/600 detik per IP dan
  `Cache-Control: no-store` — dipertahankan.
- Cabang berasal dari `token` tautan (`cv_online_branch_forms`), bukan input.
- NIK divalidasi 16 digit; DOB divalidasi ISO; keduanya tetap dipakai sebagai
  gerbang seperti sekarang.
- Status diambil dari DB master, best-effort: bila query gagal, respons
  kembali ke kontrak lama (`known`/`can_continue`) tanpa membocorkan error DB.

## Approaches yang dipertimbangkan

1. **Perbesar `/lookup` (dipilih).** Respons ditambah `stages`, `nama_masked`,
   dan `next_action`. Satu permintaan, perubahan UI kecil, klien lama tidak
   rusak karena kunci lama tetap ada. Trade-off: payload lookup sedikit lebih
   besar dan endpoint jadi melakukan lebih dari satu hal.
2. **Endpoint `/api/recruitment/portal/status` baru.** Pemisahan tanggung
   jawab lebih rapi, tapi portal harus mengganti pemanggilan dan ada dua
   kontrak publik yang perlu dijaga. Trade-off: lebih banyak kode dan tes.
3. **Token sesi ala Rilis C.** Paling lengkap, tapi justru di-rollback karena
   menimbulkan masalah; ditolak.

## Desain terpilih

### Backend — respons `/api/recruitment/lookup`

Tambahkan (semua opsional untuk klien lama):

```json
{
  "status": "success",
  "known": true,
  "can_continue": true,
  "nama_masked": "Bili S.",
  "next_action": "TRAINING",
  "stages": [
    {"type": "CV",        "status": "SELESAI", "completed_at": "2026-11-25 19:28:30", "can_open": false},
    {"type": "TRAINING",  "status": "BELUM",   "completed_at": null, "can_open": true},
    {"type": "TKD",       "status": "SELESAI", "completed_at": "2026-11-25 19:24:47", "can_open": false},
    {"type": "FIRSTWORK", "status": "BELUM",   "completed_at": null, "can_open": true}
  ]
}
```

Aturan:

- Cari `recruitment_cases` berdasarkan NIK. Bila ada, ambil semua
  `recruitment_steps` untuk `case_id` itu (semua cabang).
- Agregasi per `step_type` dengan prioritas
  `SELESAI > DIKECUALIKAN > PENDING > BELUM`; waktu selesai diambil dari baris
  `SELESAI` terakhir.
- `can_open`: `false` bila status tahap `SELESAI`; selain itu `CV` `true`, dan
  tiga tahap lain `true` bila `known === true`. Ini menjaga kasus
  TKD-selesai-sebelum-CV tetap bisa diakses, sekaligus mencegah pengulangan
  tahap yang sudah selesai.
- `next_action`: tahap pertama yang belum `SELESAI` dengan urutan
  CV, Training, TKD, FirstWork; bila semua selesai → `DONE`.
- `nama_masked`: kata pertama + inisial kata kedua; tidak ada NIK/DOB/alamat.
- Bila NIK hanya ada di `cv_online_submissions` atau `first_work_submissions`
  tanpa kasus, semua stage `BELUM` dan `nama_masked` kosong.
- Jalur NIK invalid atau token cabang invalid tetap tidak mengambil data.

### Frontend — `RecruitmentPortalView.vue`

- Simpan `summary` dari respons lookup; tidak menyimpan NIK/DOB setelah itu
  kecuali untuk membuka panel TKD yang sudah ada.
- Empat kartu menampilkan:
  - selesai → `✓ Selesai · <tanggal jam> · tidak perlu diulang`, kelas
    `rp-card--done` (redup), dirender sebagai `<div>` tanpa `href` dan tanpa
    aksi klik;
  - belum → `Belum`, tampilan normal;
  - terkunci (NIK belum dikenal) → tetap `data-locked=true` seperti sekarang.
- Tambah satu baris `Langkah berikutnya: <label tahap>` di bawah kartu sapaan.
- Tidak ada animasi baru; perubahan status langsung terbaca dari teks dan
  opasitas kartu.

## Pesan konfirmasi untuk pelamar

Bahasa: kalem, aktif, tidak berterima kasih berlebihan. Setiap pesan
menyatakan dua hal: data sudah tersimpan dan apa yang boleh dilakukan
berikutnya. NIK tidak pernah disebut lengkap.

| Kondisi | Pesan yang ditampilkan |
|---|---|
| Cek berhasil, NIK dikenal | `Data Anda sudah cocok. Halo, {nama_masked}. Berikut rangkuman rekrutmen di cabang ini.` |
| Catatan privasi (sekali, dekat form) | `NIK hanya dipakai untuk mencocokkan data dan tidak ditampilkan lengkap di halaman ini.` |
| CV selesai | `✓ Selesai — CV Online diterima {waktu}. Data diri dan pendidikan Anda tersimpan. Tahap ini tidak perlu diulang.` |
| Training belum tercatat | `Belum tercatat. Absensi training menunggu kehadiran Anda. Hari 2 dibuka setelah Hari 1 tercatat.` |
| TKD selesai | `✓ Selesai — TKD tercatat {waktu}. Bukti penilaian tersimpan; tidak perlu diulang.` |
| FirstWork selesai | `✓ Selesai — KTP dan kartu peserta sudah tercatat {waktu}. Tahap ini tidak perlu diulang; hubungi cabang bila kartu perlu dicetak ulang.` |
| FirstWork belum tercatat | `Belum tercatat. Setelah CV tersedia, Anda bisa mengunggah KTP dan mencetak kartu peserta.` |
| Ada langkah berikutnya | `Langkah berikutnya: {label tahap}. Ikuti jadwal dari cabang.` |
| Semua tahap selesai | `Semua tahap sudah tercatat. Hubungi cabang bila perlu cetak ulang kartu atau koreksi data.` |
| NIK belum dikenal | `NIK ini belum kami temukan. Mulai dari CV Online agar data Anda tercatat.` |
| Tanggal lahir tidak cocok | `Tanggal lahir tidak cocok dengan NIK ini. Periksa kembali atau hubungi resepsionis.` |
| NIK bukan 16 digit | `NIK harus 16 digit angka.` |
| Tautan cabang tidak aktif | `Tautan cabang tidak aktif. Minta tautan baru ke resepsionis.` |
| Terlalu banyak cek | `Terlalu banyak pengecekan dalam sebentar. Tunggu beberapa menit lalu coba lagi.` |

Konfirmasi setelah pengiriman form (dipakai bila halaman form terkait
disentuh dalam rilis ini):

- CV: `CV Online Anda tersimpan dengan nomor {registration_no}. Simpan nomor ini untuk referensi.`
- Training: `Absensi Hari {n} tercatat pukul {waktu}.` + `Hari 2 sekarang tersedia` bila `n=1`.
- TKD: `Jawaban TKD tersimpan. Hasil akan tampil di portal setelah diproses.`
- FirstWork: `KTP diterima. Kartu peserta siap dicetak.`

## Testing

- `tests/test_recruitment_lookup.py`: NIK dengan steps CV+TKD selesai → urutan
  stage benar, waktu sesuai, `next_action=TRAINING`, tidak ada NIK/DOB di
  respons; NIK baru → semua `BELUM`; NIK invalid → kontrak lama.
- `frontend/src/views/RecruitmentPortalView.test.js`: kartu selesai memuat
  `✓ Selesai` dan waktu serta kelas redup; kartu belum tidak; baris langkah
  berikutnya tampil.
- Verifikasi: pytest file terkait, `npm test`, `npm run build`, stamp, deploy.

## Rilis

Perubahan kode dianggap patch `v2.135.2`: 7 titik stamp, CHANGELOG, PROGRESS,
commit + push, deploy NAS, sync stamp DB, smoke NIK `3509190102960003`.
