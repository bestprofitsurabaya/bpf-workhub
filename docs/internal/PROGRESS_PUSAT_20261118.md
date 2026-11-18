# Progres — Pusat & Rapi-Rapi Laporan (18 Nov 2026)

Catatan kerja harian untuk dua pekerjaan yang disetujui bersamaan:

1. **v2.113.2 — sisa Fase 4 desain BBM** (rapikan PDF/CSV + tautan lama).
2. **Roadmap "Admin Pusat"** — Pusat sebagai pengawas lintas cabang, bukan
   operator harian.

Aturan main: setiap langkah yang selesai dicentang di sini **dan** dirilis
dengan entri CHANGELOG + bump 7 titik stamp versi. Jangan ada perubahan yang
hanya hidup di working tree.

---

## Bagian A — v2.113.2 (Fase 4: rapikan CSV & tautan lama)

Status: **selesai — dirilis v2.113.2.**

- [x] **Helper CSV bersama** `frontend/src/utils/csv.js`
      (`csvCell`, `csvLine`, `csvMeta`, `downloadCsv`).
      Sebelumnya 4 halaman menulis Blob/BOM sendiri; `UsersView` membungkus
      semua sel dengan kutip **tanpa meng-escape** kutip di dalamnya, sehingga
      nama seperti `Budi "BS" Santoso` merusak kolom.
- [x] **Dasar hitung tunggal untuk teks** `frontend/src/content/reportBasis.js`
      (`BASIS_VERSION`, `REPORT_BASIS`) — dipakai kartu meta **dan** header CSV
      Rekap/Realisasi/Analisis, supaya file ekspor tidak menjelaskan dasar
      hitung yang berbeda dari layar.
- [x] **CSV Rekap** memakai helper + meta lengkap (periode, cabang, dasar
      hitung berversi, waktu dibuat).
- [x] **CSV Realisasi** memakai helper + meta lengkap (cakupan, YTD, dasar
      hitung, waktu dibuat).
- [x] **CSV Analisis** memakai helper + meta lengkap (periode, cakupan, dasar
      hitung, waktu dibuat).
- [x] **CSV Users** memakai helper — bug escaping nama pengguna selesai.
- [x] **Tautan laporan lama** (`/rekap`, `/expenses`, `/analytics`) memetakan
      periode lama `start_date`/`end_date`/`from`/`to` → `start`/`end` yang
      dibaca context bar `/cash`; `tab`/`view` tidak bisa dibelokkan query.
- [x] Tes: `frontend/src/utils/csv.test.js` (4 tes) +
      `frontend/src/router/routes.test.js` (3 tes baru) — 13 lulus.
- [x] Uji penuh frontend (**335 tes**) + guard backend (**10 tes**) di NAS.
- [x] Deploy + verifikasi health `v2.113.2 stale=false`, lalu commit & push.

**Bukti rilis:** `npm test` 46 berkas / 335 tes lulus; pytest
`test_version_stamp_guard.py` + `test_nav_badges.py` 10 lulus; health
`repo_version=running_version=v2.113.2`.

## Bagian B — Roadmap Admin Pusat

Prinsip yang disepakati: **Pusat = pengawas + pengelola konfigurasi +
operator darurat (break-glass)**. ACC harian tetap di GA/Finance cabang.

### Fase 1 — "Pusat" yang benar (target rilis v2.114.0)

- [ ] Endpoint `GET /api/branches/overview` — fan-out ringan ke DB tiap
      cabang + cache 60 detik; 6 sinyal: klaim BBM menunggu, kasbon di driver,
      LPJ terlambat, air minum menunggu, overtime menunggu, CV Online /
      FirstWork baru; status DB per cabang (hasil parsial, bukan gagal total).
- [ ] Tab **Pusat** di Dashboard Admin: tabel 12 cabang + sinyal + tombol
      "Buka cabang".
- [ ] Banner konteks permanen saat Admin Pusat berada di cabang
      ("Anda Admin Pusat sedang melihat SBY — aksi tercatat atas nama SBY")
      + tombol "Kembali ke Pusat".
- [ ] Branch switcher di topbar khusus HO (bukan hanya di Pengaturan).
- [ ] Badge menu menampilkan total lintas cabang untuk HO.
- [ ] Hapus sisa cek `admin_master` berbasis **nama** di modul CV Online —
      hak lintas cabang hanya dari `admin_all_branches`/`is_ho_admin`.

### Fase 2 — Register lintas cabang (target rilis v2.115.0)

- [ ] CV Online: filter "Semua cabang" + ekspor gabungan (data di master).
- [ ] FirstWork: filter "Semua cabang" + ekspor gabungan.
- [ ] Konsolidasi periode: satu CSV/PDF berisi semua cabang dengan kolom
      cabang.

### Fase 3 — Tata kelola (target rilis v2.116.0)

- [ ] Access review & audit lintas cabang untuk HO.
- [ ] Break-glass: alasan wajib + step-up + jejak audit + notifikasi.
- [ ] Laporan bulanan terjadwal (unduh/email).

---

## Log

| Tanggal | Langkah | Bukti |
|---|---|---|
| 18 Nov 2026 | Audit menu "Laporan & Analisis" → v2.113.1 | commit `a5236cf`, health `v2.113.1` |
| 18 Nov 2026 | Helper CSV + dasar hitung + perbaikan redirect (v2.113.2) | 335 tes frontend + 10 guard lulus, health `v2.113.2` |
