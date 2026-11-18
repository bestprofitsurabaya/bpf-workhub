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

### Fase 1 — "Pusat" yang benar (rilis v2.114.0) ✅

- [x] Endpoint `GET /api/branches/overview` — fan-out ringan ke DB tiap
      cabang + cache 60 detik (`?refresh=1`); sinyal: klaim BBM menunggu,
      siap cair, kasbon di driver (nominal), LPJ > 7 hari, SPBU mismatch, air
      minum, CV Online, FirstWork (+ kasbon GA/Finance & penugasan untuk
      badge); status DB per cabang (parsial, bukan gagal total).
      *Overtime tidak dihitung — tabelnya bukan antrean persetujuan.*
- [x] Panel **Pusat** di Dashboard Admin: tabel semua cabang + sinyal +
      status DB + tombol "Buka" dan sel angka yang bisa diklik.
- [x] Banner konteks permanen saat Admin Pusat berada di cabang
      ("Anda Admin Pusat sedang melihat SBY — aksi tercatat atas nama cabang")
      + tombol "Kembali ke Pusat"; disimpan di localStorage agar tahan reload.
- [x] Branch switcher di topbar khusus HO (bukan hanya di Pengaturan).
- [x] Badge menu menampilkan total lintas cabang untuk HO (satu cache).
- [x] Hapus cek `admin_master` berbasis **nama** di CV Online & FirstWork —
      hak lintas cabang hanya dari `admin_all_branches`/`is_ho_admin`.
- [x] Uji: 346 tes frontend, 103 tes backend terkait, fan-out live 12 cabang
      (`summary.branches_total=12`, semua `status=ok`), health `v2.114.0`.

### Fase 2 — Register lintas cabang (rilis v2.115.0) ✅

- [x] CV Online: filter "Semua cabang" + satu cabang untuk Admin Pusat; chip
      status & angka hari ini mengikuti filter; ekspor CSV ikut filter (kolom
      **Cabang** tetap ada). Role cabang tetap terkunci di server.
- [x] FirstWork: filter "Semua cabang" + satu cabang; chip, aging, angka hari
      ini, dan ekspor CSV ikut filter; pencarian/referensi ikut terbawa.
- [x] Konsolidasi periode: CSV satu file untuk semua cabang (kolom cabang) atau
      per cabang. PDF tidak ditambahkan — kedua modul memang tidak punya
      laporan PDF; CSV adalah format serah-terima ke HRD/pengundang.
- [x] Uji: 29 tes backend (6 ekspor lintas cabang + CV Online) & 13 tes UI CV/
      FirstWork lulus di NAS.

### Fase 3 — Tata kelola (mulai v2.116.0)

- [x] **Audit lintas cabang (v2.116.0):** `GET /api/admin/audit-logs/all`
      menggabungkan log DB cabang aktif (7 hari, maks. 50/cabang), urut waktu,
      kolom cabang, detail snapshot per cabang, isolasi DB mati, khusus HO.
- [x] Access review sudah global sejak v2.37.0 (`/api/admin/access-review`,
      `is_ho_admin`); tidak perlu fan-out karena user ada di DB master.
- [x] **Break-glass (v2.117.0):** hapus transaksi permanen oleh Admin Pusat
      wajib alasan ≥15 karakter + step-up PIN + token sekali pakai (SHA-256,
      TTL 5 menit, terikat cabang/aksi/target). Audit `break_glass_issue` /
      `break_glass_use` masuk Log cabang (notifikasi in-app); email/WA belum
      tersedia sehingga tidak diklaim.
- [x] **Laporan bulanan (v2.118.0):** panel Pusat → 📊 Laporan Bulanan
      (BBM/kasbon/air/CV/FirstWork per cabang), unduh CSV, email bila SMTP
      dikonfigurasi (503 `EMAIL_NOT_CONFIGURED` bila belum). Status unduh/kirim
      per bulan + penanda "belum dibuat". **Penjadwalan cron tidak dipasang
      aplikasi** — itu langkah ops (butuh kredensial SMTP); jangan diklaim
      sudah berjalan otomatis.

---

## Log

| Tanggal | Langkah | Bukti |
|---|---|---|
| 18 Nov 2026 | Audit menu "Laporan & Analisis" → v2.113.1 | commit `a5236cf`, health `v2.113.1` |
| 18 Nov 2026 | Helper CSV + dasar hitung + perbaikan redirect (v2.113.2) | 335 tes frontend + 10 guard lulus, health `v2.113.2` |
| 18 Nov 2026 | Panel Pusat + switcher + banner + badge total + scope berbasis flag (v2.114.0) | 346 tes frontend, 103 tes backend, fan-out live 12 cabang, health `v2.114.0` |
| 18 Nov 2026 | Laporan bulanan Pusat: agregasi per cabang + CSV + email opsional + status bulanan (v2.118.0) | 9 tes backend + 2 tes UI lulus, health `v2.118.0` |
| 18 Nov 2026 | Break-glass hapus transaksi Pusat: alasan + step-up + token sekali pakai + audit (v2.117.0) | 8 tes backend + 20 tes UI dashboard lulus, health `v2.117.0` |
| 18 Nov 2026 | Audit log lintas cabang untuk HO: gabungan 12 DB cabang + detail per cabang (v2.116.0) | 6 tes backend + 3 tes UI lulus, health `v2.116.0` |
| 18 Nov 2026 | Register lintas cabang: filter cabang + ekspor CSV mengikuti layar di CV Online & FirstWork (v2.115.0) | 352 tes frontend + 75 tes backend terkait lulus; live: Pusat `?branch=MLG`=0 vs `SBY`=1738 baris, `admin_sby` `?branch=MLG` tetap 1738 (terkunci); health `v2.115.0` |
