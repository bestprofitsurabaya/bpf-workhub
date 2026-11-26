# Kartu First Work Selaras Portal (v2.135.10) — Rencana Implementasi

**Goal:** Kartu BPF First Work menampilkan ringkasan empat tahap portal dengan
gaya yang sama (simpul, garis, status satu kata), tanpa membocorkan data
pribadi dan tanpa melihat capaian cabang lain.

**Spec:** `docs/superpowers/specs/2026-11-26-kartu-firstwork-selaras-portal-design.md`

## Batasan

- Hanya PDF kartu First Work; `ApplicantReportPDF` tidak berubah.
- Tidak ada perubahan skema DB, endpoint, token, atau peran.
- NIK lengkap, HP, dan token tidak boleh muncul di PDF.
- Versi rilis `v2.135.10` di tujuh titik stamp.

---

### Task 1: Kunci perilaku lewat tes

**Files:** `tests/test_first_work_card_pdf.py`

- Perluas `FakeConn` agar menjawab `recruitment_cases` dan
  `recruitment_steps` (termasuk filter `branch_code`).
- Tambah tes:
  - blok `STATUS REKRUTMEN` muncul saat ada kasus, memuat empat label dan
    status `Selesai`/`Berikutnya`/`Belum`, tanpa NIK lengkap;
  - langkah cabang lain tidak dihitung;
  - tanpa kasus, blok tidak muncul (kartu legacy tetap satu halaman).
- Jalankan: `python3 -m pytest tests/test_first_work_card_pdf.py -q`
  → harus GAGAL pada blok status.

### Task 2: Data ringkasan per cabang

**Files:** `modules/routes_recruitment.py`, `modules/routes_first_work.py`

- `portal_summary(cursor, nik, known=False, branch_code=None)`:
  tambahkan `AND branch_code=%s` saat `branch_code` diisi.
- Rute kartu: normalisasi NIK, panggil `portal_summary` dengan cabang baris,
  lalu teruskan `stages` dan `next_action` ke `FirstWorkCardPDF.generate`.
- Jalankan tes Task 1 → bagian data lulus, bagian tampilan masih gagal.

### Task 3: Blok status di PDF

**Files:** `modules/pdf_generator.py`

- Tambah warna `NAVY`, `ACCENT`, `SUCCESS` (selaras token portal).
- `FirstWorkCardPDF.generate(row, stages=None, next_action=None)`.
- Metode `_stage_summary(stages, next_action)`:
  - empat kolom, simpul lingkaran, garis penghubung;
  - ✓ untuk selesai, nomor untuk lainnya;
  - label `CV Online / Training / TKD / First Work`;
  - status `Selesai / Berikutnya / Belum`;
  - ruas setelah simpul selesai berwarna hijau redup.
- Blok disisipkan setelah identitas, sebelum demografi.
- Jalankan tes Task 1 → PASS.

### Task 4: Bukti visual

- Render kartu contoh ke PNG (`pdftoppm`), periksa simpul, garis, dan
  keterbacaan pada 100%.
- Pastikan tetap satu halaman untuk baris lengkap dan baris legacy.

### Task 5: Rilis v2.135.10

- Bump tujuh titik stamp; catat `CHANGELOG.md` dan `PROGRESS.md`.
- Perbarui panduan (versi + daftar perubahan) dan PDF panduan.
- Commit, push GitHub, pull NAS, rebuild web.
- Verifikasi health, versi, service worker, portal, dan kode PDF di container.
