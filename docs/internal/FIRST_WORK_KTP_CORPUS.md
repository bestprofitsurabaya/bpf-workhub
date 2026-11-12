# Mengukur OCR KTP pada data nyata (ber-consent)

Tujuan: mengganti angka baseline sintetis (NIK 75,0%, nama 100%) dengan angka
lapangan. Tanpa korpus nyata, angka sintetis **tidak boleh** diklaim sebagai
akurasi produksi.

## 1. Consent dan penyimpanan
- Minta izin tertulis/terekam ke pemilik KTP untuk pemakaian terbatas
  (evaluasi kualitas OCR), sebutkan masa simpan dan siapa yang mengakses.
- Simpan korpus di folder **di luar repo** (mis. `/data/ktp_eval`), bukan di
  NAS produksi, dan jangan pernah commit gambar/`truth.json`.
- Batasi akses ke satu akun, enkripsi disk bila tersedia, dan hapus setelah
  evaluasi selesai (default: ≤7 hari).

## 2. Siapkan label manual
Buat `labels.csv` (satu baris per gambar), diisi dengan membaca KTP asli —
bukan dengan hasil OCR:

```csv
file,nik,nama
ktp_001.jpg,3171010101900001,BUDI SANTOSO
ktp_002.jpg,3171010101900002,SITI AMINAH
```

Lalu validasi dan buat `truth.json` (izin file 600):

```bash
python3 scripts/ktp_corpus_labels.py \
  --corpus /data/ktp_eval --labels /data/ktp_eval/labels.csv \
  --out /data/ktp_eval/truth.json
```

Skrip menolak output di dalam repo dan menolak NIK bukan 16 digit.

## 3. Jalankan pengukuran
Di container/host yang punya Tesseract + `ind`:

```bash
python3 scripts/eval_first_work_ktp.py \
  --corpus /data/ktp_eval --truth /data/ktp_eval/truth.json \
  --out /tmp/fw_ktp_eval.json
```

Laporan memuat akurasi NIK/nama, waktu normalisasi & OCR, dan daftar
kegagalan per file (tanpa menyalin NIK ke log).

## 4. Tafsir dan keputusan
- Bandingkan dengan baseline sintetis; jangan mencampur keduanya.
- Jika NIK < 85% pada korpus ≥50 gambar, pertimbangkan mesin kedua
  (PaddleOCR) — ukur ulang biaya & waktu, jangan langsung mengganti.
- Catat hasil di `CHANGELOG.md` dengan jumlah sampel, kondisi (foto asli,
  bukan scan), dan tanggal. Sebutkan keterbatasan bila sampel kecil.

## 5. Bersihkan
```bash
rm -rf /data/ktp_eval
```
Pastikan tidak ada salinan di folder upload produksi. Evaluasi ini memakai
folder terpisah dan tidak menyentuh data pendaftar.
