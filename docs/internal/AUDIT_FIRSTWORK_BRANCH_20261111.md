# Audit Standar — Absensi FirstWork (Data Pribadi & Isolasi Cabang)

**Tanggal:** 11 November 2026
**Objek:** `bpf-workhub` (NAS `192.168.2.31` / `nasbpfsby.duckdns.org:2211`), fitur **Absensi FirstWork** v2.80.0
**Sifat audit:** baca kode produksi + uji fungsi; perubahan diterapkan pada rilis **v2.82.0**
**Data yang dilindungi:** NIK, nama sesuai KTP, no. HP, email, foto/scan KTP, nama referrer

---

## 1. Ringkasan

Fitur FirstWork adalah form **publik tanpa login** yang menyimpan dokumen identitas.
Sebelum v2.82.0 ada tiga kelas masalah:

| # | Risiko | Tingkat | Bukti (kode v2.80.0) |
|---|---|---|---|
| 1 | Foto KTP bisa dibuka **semua** pegawai yang login | 🔴 Tinggi | `routes_driver.py: /uploads/<path>` hanya cek `session['user_name']` |
| 2 | Isian bisa **nyasar ke cabang lain** tanpa terlihat | 🔴 Tinggi | `_request_branch()` → nilai asing dikembalikan `'SBY'` |
| 3 | **Satu form untuk semua cabang**; cabang hanya parameter URL | 🔴 Tinggi | `?cabang=` bebas diubah siapa pun; tidak ada token |
| 4 | Nomor registrasi **berbagi urutan** semua cabang | 🟠 Sedang | `doc_sequences` key `FW|YYYYMMDD` |
| 5 | Referrer cabang lain bisa ditempel ke isian cabang ini | 🟠 Sedang | `referrer_id` divalidasi `id + active` saja |
| 6 | Admin cabang menerima **seluruh daftar user** semua cabang | 🟠 Sedang | `/api/first-work/referrers/manage` → `SELECT ... FROM users` tanpa scope |
| 7 | Ekspor CSV NIK penuh untuk role yang tidak memverifikasi | 🟠 Sedang | `/api/first-work/export` untuk `finance`, `ga_hr` |
| 8 | NIK (nilai) masuk audit log saat koreksi admin | 🟡 Rendah | `new_data=body` pada PATCH |
| 9 | Endpoint cek NIK = alat enumerasi data pribadi | 🟡 Rendah | 20 cek/menit/IP, tanpa `no-store` |

---

## 2. Temuan & perbaikan

### 2.1 Foto KTP dapat diakses semua pegawai (IDOR)

`GET /uploads/<path:filename>` hanya mewajibkan sesi login. Artinya driver, OB,
security, atau marketing **cabang mana pun** dapat membuka berkas
`/uploads/first_work/FWKTP_*.jpg` bila nama filenya diketahui (nama memuat nomor
registrasi yang berurutan + 6 karakter acak).

**Perbaikan:** path `first_work/*` hanya untuk role `traineer`/`admin`; jalur resmi
`GET /api/first-work/<id>/ktp` (sudah ter-scope cabang) kini `no-store`, `nosniff`,
`as_attachment`, dan **setiap unduhan masuk audit log**
(`first_work_ktp_download`).

### 2.2 Cabang tidak dikenal "diam-diam" jadi SBY

```python
# v2.80.0
if code in codes: return code
return 'SBY' if 'SBY' in codes else codes[0]   # ← semua nilai asing jatuh ke SBY
```

Tautan salah ketik (`?cabang=MLGG`) atau `?cabang=` yang dipalsukan tetap diterima
dan seluruh data pribadi pendaftar masuk antrean **Surabaya** — antrean cabang
yang dituju kosong, dan tidak ada indikator apa pun.

**Perbaikan:** `_resolve_form_branch()` mengembalikan `(None, error)` dan route
menolak **400** dengan pesan yang menyebut cabangnya. Tanpa parameter cabang sama
sekali = tautan lama → tetap cabang utama (SBY), sehingga tautan yang sudah
beredar tidak putus.

### 2.3 Satu form untuk semua cabang

Form publik identik untuk semua cabang; pemisahan hanya bergantung pada parameter
URL yang bisa diubah siapa saja. Ini melanggar syarat "form antar cabang tidak sama".

**Perbaikan:** tabel `first_work_branch_forms` (satu token unik per cabang,
dibuat otomatis saat startup) dan tautan per cabang:

```
/app/first-work-form?cabang=SBY&t=<token-SBY>
/app/first-work-form?cabang=MLG&t=<token-MLG>
```

Aturan validasi (`_token_error`):
- token **cocok** → diterima;
- token cabang lain / token salah → **403**;
- cabang **non-default tanpa token** → **403** (tidak bisa mengaku cabang lain);
- cabang default tanpa token → diterima (kompatibilitas tautan lama).

Admin mendapat daftar tautan per cabang di **Absensi FirstWork → Referensi & Sync
→ Link Form per Cabang** (`GET /api/first-work/branch-forms`, ter-scope cabang;
Admin Pusat melihat semua).

### 2.4 Penomoran dokumen lintas cabang

Semua cabang memakai urutan yang sama (`FW-20261111-0001`), sehingga dua
registrasi berbeda cabang bisa bernomor identik dan tertukar saat dicetak/diarsipkan.

**Perbaikan:** `FW-<CABANG>-YYYYMMDD-####` dengan kunci urutan per cabang
(`FW|CABANG|TANGGAL`). Data lama tidak diubah.

### 2.5 Atribusi referrer lintas cabang

`POST /api/first-work/public` menerima `referrer_id` apa pun yang aktif, termasuk
milik cabang lain — cukup menebak ID. Referrer juga tidak ter-scope saat
ditambah/diubah admin (`PATCH` bisa menyentuh referrer cabang lain).

**Perbaikan:** `_referrer_in_branch()` pada submit, `_referrer_allowed()` pada
`PATCH /api/first-work/referrers/<id>` (403 bila beda cabang), dan Admin Pusat
wajib menyebut `branch_code` saat menambah referrer (tidak lagi otomatis SBY).

### 2.6 Daftar akun di panel referrer

`/api/first-work/referrers/manage` mengirim `SELECT ... FROM users` (semua cabang)
ke admin cabang. **Perbaikan:** daftar dibatasi `branch_code` sesi (user legacy
`NULL`/kosong hanya ikut untuk cabang utama).

### 2.7 Ekspor CSV & PII

- NIK penuh hanya untuk `traineer`/`admin`; `finance`/`ga_hr` menerima
  `6••••4` (minimalisasi data — mereka tidak memverifikasi identitas).
- Respons `Cache-Control: no-store`, nama file memuat cabang, dan ekspor dicatat
  (`first_work_export` beserta jumlah baris + apakah NIK penuh).
- Koreksi admin tidak lagi mencatat nilai NIK/HP ke audit log — hanya nama field.

### 2.8 Cek NIK

`GET /api/first-work/check-nik` menjawab "NIK terdaftar atau tidak" tanpa login.
Kuota diturunkan 20 → **10 cek/menit/IP** dan respons `no-store`. Endpoint tetap
global (satu NIK = satu pendaftaran, mencegah duplikasi PII), sehingga ini masih
merupakan **sisa risiko** yang wajar — lihat §4.

---

## 3. Verifikasi

| Uji | Hasil |
|---|---|
| `pytest tests/test_first_work_isolation.py` | 22 lulus (resolusi cabang, token, penomoran, referrer, penyamaran NIK) |
| `compileall` modul yang diubah | lulus |
| Migrasi `first_work_branch_forms` saat startup | token ter-seed untuk seluruh cabang aktif |
| Probe publik `?cabang=<asing>` | 400 (tidak lagi masuk SBY) |
| Probe publik `?cabang=MLG` tanpa token | 403 |
| Probe publik tanpa parameter (tautan lama SBY) | 200 |
| `GET /api/first-work/branch-forms` tanpa sesi | 401 |

---

## 4. Sisa risiko (belum dikerjakan — sengaja, perlu keputusan pemilik data)

1. **Retensi foto KTP** — belum ada penghapusan otomatis. Standar PII menyarankan
   retensi terbatas (mis. 12 bulan setelah rekrutmen selesai) + prosedur permintaan
   penghapusan. Perlu kebijakan tertulis sebelum diotomasi.
2. **Rate limit in-memory** — `_submit_log`/`_check_log` per proses; pembatasan
   sesungguhnya tetap di nginx. Bisa dipindah ke Redis (sudah tersedia).
3. **Enkripsi at-rest** — KTP tersimpan sebagai file biasa di `/srv/bpf-workhub/uploads`.
   Perlindungan saat ini: permission folder + akses via aplikasi. Enkripsi/volume
   terpisah perlu keputusan infrastruktur.
4. **Cabang utama tanpa token** — tautan lama SBY tetap diterima tanpa token agar
   tidak memutus data historis. Bila ingin seluruh cabang wajib ber-token, cukup
   ubah `_token_error` agar tidak lagi memberi pengecualian `default_code`.
5. **Persetujuan (consent)** — form menyatakan data dipakai untuk rekrutmen, tetapi
   belum ada mekanisme persetujuan eksplisit/terekam sesuai UU PDP.

---

## 5. Berkas yang diubah (v2.82.0)

| Berkas | Perubahan |
|---|---|
| `modules/routes_first_work.py` | resolusi cabang ketat, token per cabang, penomoran ber-cabang, scope referrer & user, header/audit KTP & ekspor, masking NIK, audit tanpa PII |
| `modules/first_work_schema.py` | tabel `first_work_branch_forms` + seed token per cabang aktif |
| `modules/routes_driver.py` | guard `/uploads/first_work/*` (Traineer/Admin saja) |
| `frontend/src/views/FirstWorkFormView.vue` | kirim token cabang, tampilkan error tautan tidak valid |
| `frontend/src/views/FirstWorkView.vue` | panel "Link Form per Cabang" + tautan ber-token |
| `tests/test_first_work_isolation.py` | 22 unit test baru |
| `CHANGELOG.md` | catatan rilis v2.82.0 |

**Rollback:** `git checkout -- <berkas>` lalu `docker compose up -d --build web`.
Tabel `first_work_branch_forms` bersifat aditif (tidak mengubah tabel lama);
kolom `registration_no` lama tetap valid karena format hanya berubah untuk baris baru.
