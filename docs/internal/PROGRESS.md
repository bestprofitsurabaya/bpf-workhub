# 📊 Progres BPF WorkHub

File ini melacak status project agar AI (Buffy/Codebuff) bisa memahami konteks saat sesi baru dimulai.

**Terakhir diperbarui:** 2026-09-08  
**Branch:** `main`  
**Versi terbaru:** v2.37.7 (8 Sep — kop Tanda Terima air minum per cabang) · v2.37.6 LIVE (7 Sep — layout export air minum + kop per cabang + PLM dinonaktifkan) · v2.37.5 (export rekap air minum PDF & Excel) · v2.37.4 (filter rentang tanggal) · v2.37.3 (detail snapshot audit log) · v2.37.2 (fix foto bukti 500 + preview verifikasi air minum) · v2.37.1 (hotfix scoping admin cabang) · v2.37.0 (edit/hapus air minum + admin per-cabang + Pengaturan terstruktur) — program 6 tahap ISO 27001 SELESAI

---

## 📌 Status Terakhir

| Aspek | Status |
|-------|--------|
| Versi | **v2.37.7 (8 Sep)** — kop Tanda Terima air minum mengikuti cabang sesi (helper `get_branch_identity` + `BPFBasePDF.set_identity`); sebelumnya v2.37.6 layout export air minum + kop per cabang (tabel branches) + PLM dinonaktifkan; v2.37.5 export rekap air minum + v2.37.0 (edit/hapus air minum + admin per-cabang) + v2.37.1 hotfix scoping + v2.37.2 fix foto bukti & preview + v2.37.3 detail snapshot audit |
| Kop Tanda Terima per cabang (v2.37.7) | ✅ **DI REPO + TER-VERIFIKASI LIVE (belum rebuild image)**: PDF Tanda Terima air minum kini berkop cabang sesi via `get_branch_identity()` (tabel branches) — SBY "Graha Bukopin…", MDN "Perintis Kemerdekaan…", JKT "Equity Tower Lt.47…" terverifikasi di container (docker cp kode baru, bukan image final); stamp v2.37.7 + master DB system_version diperbarui dari v2.29.10 yang basi; +13 pytest (test_branch_identity 11 + test_water 2) |
| Data cabang vs situs resmi (8 Sep) | ✅ **Diverifikasi ulang** dgn bestprofit-futures.co.id/hubungi-kami (mirror cabang): 8 cabang aktif cocok; **alamat MLG dikoreksi** ("BPF Tower…" → Ruko Pelita, Jl. Letjen S. Parman No. 59 Kav. 1, 3–5); **JMB Jambi / PTK Pontianak / PKU Pekanbaru ditambahkan NONAKTIF** (pola PLM — diaktifkan Admin saat kantor dipakai); 10 PR Dependabot **semua merged** (CI hijau tiap PR, main hijau setelah batch) |
| Kop dokumen per cabang (v2.37.6) | ✅ **LIVE**: export PDF/Excel air minum kini memakai alamat/telepon/subtitle tabel `branches` sesuai cabang sesi (bug v2.37.5: kop selalu alamat HO); alamat resmi 9 cabang diisi dari bestprofit-futures.co.id; filter `to` kini inklusif (tanggal terakhir bulan tak lagi hilang) |
| Cabang Palembang | ✅ **DINONAKTIFKAN (7 Sep)** — tidak ada kantor cabang: `branches.is_active=0` + user `it_plm`/`admin_plm` nonaktif (login 401 live); DB `bpf_branch_plm` utuh (reversible) |
| Edit/hapus air minum (v2.37.0) | ✅ **SELESAI di repo**: toggle Admin per cabang (`system_config.water_edit_enabled`, default nonaktif → perilaku lama); `PUT/DELETE /api/water/purchases/<id>` wajib step-up 428 + audit snapshot `old_data`; edit hanya status pending/verified (rejected ditolak 400); hapus = baris+item+foto dihapus permanen, snapshot tersimpan; kolom `edited_by/edited_at/edit_count` dibuat otomatis (master+cabang+`ensure_branch_database`); UI WaterView ✏️/🗑️ hanya muncul bila fitur aktif; **19 pytest + 4 vitest baru** |
| Admin per-cabang (v2.37.0) | ✅ **SELESAI di repo**: modul `modules/admin_scope.py` — `admin` = Pusat (semua cabang), `admin_<kode>` = Admin Cabang (terkunci; fail-closed bila DB mati); ho_only di `/api/branches/switch`, docseq list/reset cabang lain, retention overview/archive, access review + export + complete; audit-logs lintas cabang ditolak 403 utk admin cabang; login & `/api/auth/me` kirim `is_ho_admin` → sidebar sembunyikan Access Review/Audit Log + chip "🔒 Cabang"; kolom `users.admin_all_branches` + `managed_branches`; **13 pytest baru** |
| Pengaturan terstruktur (v2.37.0) | ✅ **SELESAI di repo**: peta seksi sticky (6 seksi, IntersectionObserver highlight), toggle switch standar utk edit/hapus air minum dgn konfirmasi; switcher cabang disembunyikan utk admin cabang |
| Approval berjenjang (v2.36.0) | ✅ **SELESAI + DEPLOY LIVE (6 Sep)**: semua pengajuan kasbon/klaim BBM wajib ACC Chief Driver dulu → GA; overtime GA HR → Admin; gate 409 `SUPERVISOR_APPROVAL_REQUIRED` di approve-ga kasbon & BBM + PATCH overtime; jurnal `approval_requests` (master + tiap cabang); override atasan per user via `users.manager_username` (form Users); halaman SPA "✅ ACC Atasan" (`/approvals`); tolak wajib alasan; fail-open utk dokumen lama/DB down; **39 pytest + 5 vitest baru, semua lulus** |
| Step-up auth (Tahap 2) | ✅ **SELESAI + DEPLOY live (5 Sep)**: 8 endpoint uang di-protect → 428 tanpa grant; modal PIN SPA; smoke test live lulus (428→PIN→lolos; logout hilangkan grant; 5 langkah terverifikasi) |
| Access review (Tahap 3) | ✅ **SELESAI + DEPLOY LIVE sesi ini (rebuild + smoke test)**: `/app/access-review` 200, login admin OK, 30 akun terklasifikasi (3 ok / 26 never_login / 1 inactive / 0 stale), export CSV OK, 401 tanpa login; bundle SPA berisi access-review, SW cache v232 |
| Vulnerability mgmt (Tahap 4) | ✅ **SELESAI + DEPLOY LIVE sesi ini**: dependensi di-patch (pip-audit & npm audit 0 temuan), image runtime tanpa tooling build (Trivy 0 HIGH/CRITICAL), CI hijau (Backend + pip-audit 1m24s, Frontend + npm audit 42s, Image-scan Trivy 1m52s), Dependabot aktif, `INCIDENT_RUNBOOK.md` (A.5.24–28); smoke test live: health OK, Flask 3.1.3/mysql-connector 9.7.0 aktif, pip tidak ada, login+access review+users+SPA 200, log bersih |
| Manajemen User | ✅ Admin bisa edit SEMUA detail user: fix tombol Simpan mati saat edit tanpa PIN, `branch_code` kini tersimpan, username bisa diganti (update by-id) |
| Konvensi username | ✅ `{divisi}_{cabang}` (nama bila >1 per divisi-cabang): 12 akun produksi di-rename (`finance_sby`, `ob_faisol_sby`, `gahr_sby`, …) — driver & it_* tidak berubah; helper text contoh pola di form Users; login UI diverifikasi browser 11/11 |
| PDF Air Minum | ✅ Foto bukti diperbesar (60–130 mm mengikuti ruang kosong), TTD lebih ke bawah, header kop simetris (teks rata tengah halaman) |
| Sync Overtime | ✅ Driver (8.745 baris) & OB/Security (600 baris) via Apps Script; auto-refresh login/logout GA HR/Admin; **v2.36.1**: display_id (UNIQUE) tak diisi upsert → baris baru saling menimpa (silent data loss — penyebab "data tidak aktual" yg dilaporkan user) diperbaiki + Refresh UI kini full sync; **v2.36.2**: identitas baris kini `source_uid` = md5(nama\|submitted_at) — tahan geser baris sheet; data produksi dipulihkan & diverifikasi baris-per-baris vs feed (0 selisih) |
| Urutan overtime | ✅ Terkini-di-atas di semua daftar + detail report per nama dibalik terkini-dulu (PDF/Excel, commit `733fd2f`) |
| Data demo air minum | ✅ Dibersihkan 4 Sep — WTR-20260904-10300556, WTR-DEMO-01/02 dihapus (bpf_asset_system + bpf_restore_test); backup `/tmp/bpf_water_demo_backup_20260904.sql`; tabel `water_purchases` kini 0 baris |
| Deploy | ✅ **v2.36.2 LIVE** (6 Sep: v2.36.0 approval `2df2ba7`, docs `80a84ea`, v2.36.1 `109e7a5`, v2.36.2 `92d2de0`) — sebelumnya v2.35.1/v2.33.0/v2.32.0 juga live; `bbm_web` healthy 0 restart |
| Admin cabang & akun (7 Sep) | ✅ **LIVE**: 10 akun `admin_<kode>` dibuat via API (jkt/sby/bdg/smg/mlg/mdn/bjm/plm/lpg/jkt2, PIN awal 123456 — wajib ganti); `admin` → **`admin_master`** (flag `admin_all_branches=1`, jadi backup bila admin cabang kendala); `e2e_admin_tmp` dinonaktifkan; scoping terverifikasi live (admin_bdg: switch cabang & access-review → 403). **v2.37.6: akun `admin_plm` dinonaktifkan (cabang PLM tidak ada)**. Detail: USER_LIST.md |
| Foto bukti & verifikasi (v2.37.2) | ✅ **LIVE**: NameError `session` di `/uploads/` (regresi hardening 584ba88) bikin SEMUA foto bukti 500 — di-fix + 4 pytest regression; modal Verifikasi/Tolak kini menampilkan bukti foto + lightbox klik-perbesar + fallback foto rusak (6 vitest); smoke live: foto 200 image/jpeg dgn sesi finance, 401 tanpa sesi |
| Dashboard Marketing | ✅ Tab "Selesai" kini memakai `/api/appointments/history` (riwayat completed marketing sendiri, lintas tanggal) — sebelumnya memanggil endpoint driver `/completed` → selalu 400/kosong |
| Validasi username | ✅ Backend `/api/users/sync` menolak username role back-office tanpa awalan divisi (`finance_`, `ob_`, …) — Driver/Admin/`it_*` bebas; akun lama (qa/test_check/e2e_driver & (username,role) sudah ada) tetap bisa disimpan |
| Nama asli di tabel Users | ✅ Kolom Username+Nama digabung: Nama Lengkap tebal + username kecil di bawahnya (gaya baris nasabah) — Admin mengenali orangnya |
| Akses CI | ✅ `gh` CLI v2.100 di `~/.local/bin` (device login sbg `bestprofitsurabaya`) — run CI terbaca; semua run terbaru hijau |
| Pool DB | ✅ Master 25 + cabang 5 (Threads_connected 206 → 26) — lihat CHANGELOG v2.29.1 |
| Docker | `bbm_web` running on `nasbpfsby.duckdns.org:5000` |
| App Running | `https://nasbpfsby.duckdns.org:5000` (health 200) |
| Databases | 10 DB terpisah (1 master + 9 cabang) — `doc_sequences` dibuat di master + tiap cabang (v2.29.10) |
| GPS Detail | ✅ Nominatim reverse geocode + disimpan ke DB |
| Watermark | ✅ 4 baris: perusahaan + tanggal + alamat + koordinat |
| Retensi & arsip (Tahap 5) | ✅ **SELESAI + DEPLOY LIVE sesi ini (v2.34.0)**: 6 kelas, overview lintas 10 DB (per_db=10 terverifikasi), arsip audit → `activity_logs_archive` + register `retention_actions`, RETENTION_POLICY.md, UI Settings |
| Integritas dokumen (Tahap 6) | ✅ **SELESAI + DEPLOY LIVE sesi ini (v2.35.0)**: registri SHA-256+signer+timestamp; e2e live: Form OT → registri → verify found=True → tamper 1 byte → found=False; UI Settings |
| Fix kritis (v2.35.1) | ✅ **Kebocoran pool DB cabang di `ensure_branch_database`** (5 koneksi/cabang/startup → semua operasi cabang mati) — diperbaiki & diverifikasi (6× get/close OK, overview 10/10 DB); hook OT `session` NameError → `session_user()` |
| Test Suite | ✅ 551 pytest (+1 regresi kop cabang v2.37.6; 6 skip; 5 security-headers butuh container DB — pre-existing) + 135 vitest — CI GitHub Actions hijau tiap push (Backend: pytest + pip-audit + service mariadb/redis; Frontend: unit test + build + npm audit; Image scan Trivy) |
| Kestabilan | ✅ bbm_web healthy — 0 restart, 0 error di log sejak deploy terakhir |

---

## 🗂️ Riwayat Sesi

### Sesi 2026-09-07 (lanjutan) — v2.37.6: Layout export air minum + kop per cabang + Palembang dinonaktifkan ✅ SELESAI + DEPLOY LIVE

> Melanjutkan sesi terputus (jaringan hilang) di tengah pekerjaan perapian
> layout output PDF air minum + kop alamat per cabang. Keputusan user:
> alamat cabang diambil dari website resmi
> (bestprofit-futures.co.id/hubungi-kami); Palembang dinonaktifkan beserta
> user-nya (tidak ada kantor cabang di sana).

#### 🔑 Akses Server
- SSH `it-ef@nasbpfsby.duckdns.org -p 2211` (password auth — jalan langsung
  dari Haven PRoot; alternatif LAN `192.168.2.31:22`).
- Akun admin live: **`admin_master`** — user `admin` TIDAK ADA (tabel "Akun
  Demo" di README usang). Login API: CSRF dari `GET /api/auth/me` →
  `POST /api/auth/login` + header `X-CSRF-Token`.

#### 🛠️ Yang Dikerjakan
1. **Pulihkan pekerjaan v2.37.6** dari `tmp_deploy/` — `water_report.py` &
   `routes_water.py` belum pernah ter-sync (test sudah), lalu sync + test.
2. **Bugfix yang ditemukan saat verifikasi**:
   - `_month_range` kini INKLUSIF (akhir = hari terakhir bulan) — bug
     v2.37.4: transaksi tanggal terakhir bulan hilang dari daftar/export;
     `tests/test_water_filter.py` disesuaikan.
   - **Kop PDF masih alamat HO** — `WaterReportPDF()` dipanggil tanpa
     override identity; `generate()` kini meng-override dari
     `meta['company']` (tabel `branches`). Terverifikasi live: PDF SBY
     memuat "Graha Bukopin", "Equity Tower" tidak lagi muncul. +1 test
     regresi (`test_kop_mengikuti_cabang`).
3. **Data cabang** (SQL: `scripts/branches_update.sql`; backup pre-update:
   `~/backup_branches_20260907.tsv`):
   - Alamat+telepon resmi 9 cabang diisi (website resmi); phone JKT
     dikoreksi (salahnya nomor 031-… Surabaya, kini 021-29035005).
   - **PLM nonaktif** (`is_active=0`) + user `it_plm`/`admin_plm` nonaktif
     (login → 401). DB `bpf_branch_plm` utuh.
   - `init.sql` seed SBY/JKT/JKT2 kini menyertakan address/phone.
4. **Deploy**: rebuild `bbm_web` 2× (fix kop menyusul verifikasi pertama);
   health 200; export PDF & Excel SBY terverifikasi kopnya (live);
   periode default kini "01/09/2026 s/d 30/09/2026".
5. **Test**: 28/28 test water di container final; full suite 551 pytest +
   6 skip lulus.

#### ⚠️ Catatan
- Snapshot lokal `.remote/bpf-workhub/` (di Haven) BASI — md5 beda dari
  server & kontennya lama. Jangan dijadikan acuan; sumber kebenaran = repo
  di server `/home/it-ef/bpf-workhub` (+ GitHub).
- README.md "Akun Demo" menyebut `admin`/`123456` — usang; live pakai
  `admin_master` (lihat USER_LIST.md).

### Sesi 2026-09-07 — v2.37.0: Edit/hapus transaksi air minum + admin per-cabang + Pengaturan terstruktur ✅ SELESAI DI REPO (belum deploy)

> Permintaan user: (1) role Finance dapat edit & hapus transaksi air minum,
> fitur bisa di-enable/disable Admin; (2) admin harus per-cabang
> (`admin_sby`, `admin_bdg`, …); (3) UI/UX admin (Pengaturan) lebih
> terstruktur & standar. Keputusan user via klarifikasi: edit boleh utk
> status verified + pending; hapus = permanen + audit; scope akses =
> sesuai cabang.

1. **Backend — fitur edit/hapus air minum** (`modules/routes_water.py`):
   key `system_config.water_edit_enabled` per DB cabang (default `false`,
   fail-closed bila DB mati); `GET/PUT /api/water/edit-enabled` (PUT
   admin-only + audit `water_edit_toggle`); `PUT /api/water/purchases/<id>`
   (edit tanggal/items/remark/note — hanya pending & verified, rejected 400)
   dan `DELETE` (hapus permanen baris+item+file foto) — keduanya
   `@stepup_required` (428 tanpa grant) + audit `water_purchase_edit`/
   `water_purchase_delete` dengan `old_data` snapshot lengkap (termasuk
   item & foto); normalisasi item diekstrak ke `_normalize_water_items`
   (dipakai create & edit); kolom `water_purchases.edited_by/edited_at/
   edit_count` via `ensure_water_edit_columns` (startup master+cabang di
   app.py + `ensure_branch_database` + init.sql).
2. **Backend — admin per-cabang** (modul baru `modules/admin_scope.py`):
   `is_ho_admin` (username persis `admin` + env `ADMIN_HO_USERNAMES` + flag
   `users.admin_all_branches`; DB mati → fail-closed = admin cabang),
   `admin_branches` (suffix username + `managed_branches`), `ho_only`
   decorator, `assert_branch_row_scope` (baris luar cabang → 403),
   `ensure_branch_admin_columns`. Terpasang di: `/api/branches/switch`
   (admin cabang 403), `/api/branches/current` (+ `is_ho_admin`), docseq
   list (filter cabang) & reset (cabang lain 403), retention overview &
   archive-audit, access review (list/complete/export), audit-logs (branch
   lain 403). Login & `/api/auth/me` menyertakan `is_ho_admin`.
3. **Frontend**: auth store getter `isHoAdmin` (fallback suffix username);
   AppLayout menyembunyikan Access Review & Audit Log dr sidebar admin
   cabang + chip "🔒 Cabang"; SettingsView sembunyikan switcher cabang utk
   admin cabang; WaterView — status fitur via `/api/water/edit-enabled`,
   tombol ✏️ Edit (modal form terisi, validasi item, step-up) & 🗑️ hapus
   (konfirmasi + step-up), hanya utk finance/admin bila fitur aktif.
4. **Frontend — Pengaturan terstruktur**: peta seksi sticky 6 tombol (Data
   Master, Air Minum, Cabang & Nomor, Kepatuhan ISO, Identitas, Lainnya)
   + highlight seksi aktif via IntersectionObserver; toggle switch
   AKTIF/NONAKTIF utk edit/hapus air minum (dgn konfirmasi & rollback bila
   gagal); seksi baru di dokumen sama.
5. **Test**: `tests/test_admin_scope.py` (13) + `tests/test_water_edit_delete.py`
   (19) — gate fitur 403, step-up 428, edit sukses/rejected/404, delete
   + foto, scoping admin desync 403, toggle PUT admin-only; vitest WaterView
   +4 (fitur nonaktif tanpa tombol, aktif tampil, modal edit PUT, hapus
   DELETE) & SettingsView +2 (peta seksi, toggle PUT). Fixture lama yang
   membuat sesi tanpa `user_name` disesuaikan (docseq/retention/branches/
   access-review) — perilaku produksi tidak berubah.
5b. **Guard tambahan manajemen user (v2.37.0)**: `/api/users` memfilter
   baris ke cabang admin cabang; `/api/users/sync` menolak 403 bila admin
   cabang membuat/mengubah akun `admin` atau akun cabang lain (test
   `TestAdminCabangScope` 3 kasus); hint username admin di UsersView
   diupdate (admin pusat vs admin_kode).
6. **Versi & docs**: stamp v2.37.0 (pdf_generator, company_identity,
   identity.js, init.sql branches, SW cache `bpf-spa-20260907-v2370`);
   init.sql + `water_edit_enabled='false'` + komentar admin per-cabang;
   CHANGELOG v2.37.0, README (badge, fitur air minum & admin per-cabang,
   angka test 508/115), USER_GUIDE (6.6 edit/hapus, 12.3 toggle, 12.4
   catatan snapshot, 12.11 admin per-cabang, stamp), PROGRESS file ini.
7. **Verifikasi**: 511 pytest + 6 skip lulus (host, tanpa container),
   115 vitest lulus, `npm run build` sukses. ⚠️ Full pytest di HOST lama
   (~3,5 menit) — di container: `docker exec bbm_web python3 -m pytest
   tests/ -q`.
8. ⏳ **Langkah sesi berikutnya**: (a) commit + push → CI hijau;
   (b) deploy `docker compose up -d --build web` — kolom baru &
   `water_edit_enabled` dibuat otomatis saat startup (master + 9 cabang);
   (c) smoke test live: login `admin` → aktifkan toggle di Pengaturan →
   login `finance_sby` → edit + hapus 1 pengajuan uji (428→PIN→sukses),
   cek audit log berisi snapshot; buat `admin_sby` uji → verifikasi tidak
   bisa ganti cabang/akses menu lintas cabang; (d) cleanup data uji;
   (e) buat akun admin cabang produksi sesuai kebutuhan (`admin_<kode>`).


### Sesi 2026-09-07 (lanjutan) — Deploy v2.37.1 + akun admin cabang + v2.37.2 fix foto ✅ SELESAI + DEPLOY LIVE

1. **v2.37.1 hotfix di-commit & deploy** — lubang admin cabang update-by-id
   lintas cabang (kini 403) + test toggle air minum deterministik; 520 pytest
   hijau; tag v2.37.0 & v2.37.1 di-push; smoke live: health 200, login admin
   OK (`is_ho_admin` true), log bersih.
2. **10 akun admin cabang dibuat via API** (`admin_<kode>`, PIN awal 123456)
   — verifikasi live: login `admin_bdg` → `is_ho_admin:false`; switch cabang
   & access review → 403.
3. **`admin` di-rename `admin_master`** (permintaan pemilik: akun master utk
   10 cabang + backup) + flag `admin_all_branches=1` — login live OK, username
   lama gagal login; `e2e_admin_tmp` dinonaktifkan; USER_LIST.md diupdate
   (`ade5d32`).
4. **v2.37.2 fix foto bukti** — laporan finance: gambar tak muncul & butuh
   preview saat verifikasi. Akar: `NameError: session` di `/uploads/` (regresi
   hardening 584ba88) → SEMUA foto bukti 500. Fix import + 4 pytest regression;
   SPA: bukti foto di modal verifikasi/tolak + lightbox klik-perbesar +
   fallback foto rusak (6 vitest). Deploy & smoke live: foto 200 (225 KB
   image/jpeg) dgn sesi finance_sby, 401 tanpa sesi, SW cache v2372, log 0
   error.
5. Suite akhir: **524 pytest + 6 skip, 121 vitest** — hijau. Tag v2.37.2
   di-push.
6. **E2E air minum live (permintaan pemilik)** — toggle edit/hapus
   DIAKTIFKAN utk SBY (`water_edit_enabled=true`, audit `water_edit_toggle`)
   + E2E penuh 21/22 ✅: create OB (ob_edwin_sby, 2 foto PIL) → detail 2 foto
   → `/uploads/` 200 image/jpeg dgn sesi finance_sby → verify 428
   STEPUP_REQUIRED → step-up PIN → verified → edit qty 2→3 (edit_count=1)
   → hapus permanen (row + 2 foto terhapus) → audit edit/delete/toggle
   tercatat. Snapshot `old_data` terverifikasi LENGKAP di DB
   (activity_logs.old_data). ⚠️ Gap ditemukan: `/api/audit-logs` hanya
   SELECT kolom ringkasan — old_data/new_data tidak diekspos ke UI Log
   (rekomendasi: endpoint detail per entri audit). Data uji dibersihkan
   (#35-37).
7. **v2.37.3 — detail snapshot audit log** (lanjutan temuan E2E):
   `GET /api/audit-logs/<id>` (old_data/new_data, scoping paritas list) +
   tombol 🔍 di UI Log → modal snapshot Data Lama/Data Baru; +5 vitest
   (126 hijau, 524 pytest tetap).
10. **v2.37.5 — export rekap air minum PDF & Excel resmi**: tombol 📄/📊
   di WaterView (filter ikut), `GET /api/water/purchases/export?format=`,
   generator `modules/water_report.py` (landscape A4, kop perusahaan, 9
   kolom, ringkasan, TTD Finance (Dibuat oleh) & Kepala Cabang (Mengetahui)
   — nama dari `water_head_name` baru di Pengaturan → 🚰 Air Minum, fallback
   label generik); +15 pytest + 4 vitest (551/135 hijau); smoke live: xlsx
   6.1 KB (7 baris Faisol, landscape), pdf 65 KB (teks judul+data tervalidasi
   extractor). ⚠️ `water_head_name` belum diisi — admin isi via Pengaturan.
9. **v2.37.4 — filter rentang tanggal air minum** (saran finance):
   filter bar Dari/Sampai/Status/Cari di WaterView, default bulan
   berjalan; backend `from/to/status/q` (parameterized, tanggal invalid →
   fallback); +12 pytest + 5 vitest (536/131 hijau); deploy & smoke live:
   default Sep→1, Aug→7 (data uji baru dari Faisol 14:03-14:10 — dibiarkan,
   sepertinya tim menguji fitur), q=AQUA OK, SW v2374.
8. **Bersih-bersih data uji air minum** (setelah klarifikasi pemilik via
   audit log): 5 pengajuan sesi lalu (0009..0013, Febri) + 3 sisa uji Febri
   (0003/0005/0008) + 1 uji E2E Edwin (0015) dihapus via API resmi dgn
   step-up + snapshot audit; file foto ikut terhapus. Tabel
   `water_purchases` kini 0 baris — semua data 7 Sep memang data uji
   (demo 4 Sep sudah dihapus Cynthia di sesi pagi, ter-audit 2099-2101).

### Sesi 2026-09-06 (lanjutan) — Deploy v2.36.0 + restrukturisasi docs + v2.36.1/v2.36.2 data overtime tidak aktual ✅ SELESAI + DEPLOY LIVE

1. **v2.36.0 committed & deployed** — saat commit/deploy tertangkap bug
   boot: blok startup approvals memakai `_ret_master` sebelum baris
   import-nya (NameError → worker gagal boot) → diperbaiki & di-amend
   (`2df2ba7`). Smoke live: login CSRF OK, `GET /api/approvals` 200,
   tabel `approval_requests` di master + 9 cabang, kolom
   `users.manager_username` siap. E2E rantai ACC live: submit kasbon
   driver → gate 409 `SUPERVISOR_APPROVAL_REQUIRED` (pending_at =
   chief_driver) → ACC Chief Driver langkah 1 → tolak wajib alasan (400
   tanpa note) → gate tetap 409 setelah tolak; data uji dibersihkan.
2. **Restrukturisasi dokumentasi** (`80a84ea`) — USER_GUIDE → `guides/`,
   materi audiens → `docs/public/`, dokumen internal → `docs/internal/`;
   root hanya README + CHANGELOG; README jadi peta navigasi per audiens;
   USER_LIST disanitasi (PIN tak lagi tertulis); SCAN_DOCS test hygiene
   & cross-link diperbarui (0 broken).
3. **Laporan lapangan "data overtime tidak aktual"** (gahr_sby, 6 Sep):
   diagnosis dua lapis — (a) tombol Refresh hanya incremental →
   edit/penghapusan baris lama sheet tak pernah ditarik; (b) akar:
   `display_id` (kolom UNIQUE) tidak diisi upsert sheet → semua baris
   baru benturan di `''` → **baris saling menimpa** (silent data loss).
   **v2.36.1** (`109e7a5`): display_id deterministik + Refresh UI full
   sync + backfill startup; data dipulihkan 8.675 drift → 8.745 sinkron
   (verifikasi baris-per-baris 0 selisih; backup JSON sebelum repair).
   **v2.36.2** (`92d2de0`): identitas baris kini `source_uid` =
   md5(nama\|submitted_at) — unik terverifikasi & tahan geser baris
   sheet; display_id OTS-<digest12> konsisten antar re-sync; submit
   form PWA Driver kini ber-uid (paritas OB, fix sheet_row=0 menumpuk);
   init.sql/CREATE/cabang disamakan (deploy fresh & paritas cabang);
   full sync 2× → sync ke-2: 0 added 0 updated (idempoten).
4. **Verifikasi**: 482 pytest + 6 skip (container, v2.36.2); SW bump
   v2361 (user perlu reload sekali).

### Sesi 2026-09-06 — v2.36.0: Approval Berjenjang (roadmap #3) ✅ SELESAI — commit+deploy di lanjutan sesi (lihat atas)

> Konteks: sesi terputus — `modules/approvals.py` (475 baris) sudah
> ditulis sesi sebelumnya namun TIDAK terpasang ke mana pun (tidak ada
> import di app.py, tidak ada hook/gate di endpoint, tidak ada test,
> tidak ada UI, tidak ada docs). Sesi ini menuntaskan integrasi penuh,
> memperbaiki 5 bug laten modul + 1 bug call-site, lalu MENYIAPKAN
> dokumentasi. **Commit & deploy menyusul setelah konfirmasi user.**

1. **Bug laten modul diperbaiki** (detail teknis di CHANGELOG v2.36.0):
   import `request` hilang (POST decision → 500); router ACC tidak
   ter-protect role; import DB cabang dari namespace salah
   (`helpers` → `modules.config`); langkah ber-nama kini bisa diputus
   pemegang role sama (chief_driver cadangan); rantai overtime salah
   ambil Chief Driver utk pengaju driver → kini selalu GA HR → Admin.
   Plus 1 bug call-site tertangkap test: variabel gate terbalik
   (`blocked` vs `allowed`) → approve tidak pernah terblokir.
2. **Backend**: 4 titik submit memanggil `hook_create_approval`
   (kasbon `/api/cash/request`, klaim BBM `/driver`, OT Driver PWA, OT
   OB form publik); 3 titik proses di-gate `gate_approval` (cash
   approve-ga, queue approve-ga, PATCH overtime driver/ob) → 409
   `SUPERVISOR_APPROVAL_REQUIRED` + `pending_at`. Upsert reset jurnal
   saat re-submit. Startup (`app.py`) membuat tabel di master + 9
   cabang (pola retention, retry 5×) + kolom `users.manager_username`;
   `ensure_branch_database` ikut membuat tabel ACC utk cabang baru;
   `register_approval_routes(app)` terpasang.
3. **Manajemen User**: `users.manager_username` (init.sql + ALTER
   startup), `/api/users` menyertakan kolomnya, `/api/users/sync`
   menyimpan eksplisit-saja (toggle/bulk tidak menghapus atasan);
   form Users dapat input "Atasan (ACC berjenjang)".
4. **Frontend**: `ApprovalsView.vue` (`/approvals`, menu "✅ ACC Atasan"
   utk chief_driver/ga/finance/ga_hr/admin) — ringkasan, tabel antrean
   ACC milik sesi, modal Keputusan (tolak wajib alasan); CashView &
   GaDashboard menerjemahkan 409 ACC jadi pesan arahan; SW cache
   `bpf-spa-20260906-v2360`; stamp v2.36.0 (pdf_generator,
   company_identity, identity.js).
5. **Test**: `tests/test_approvals.py` 39 pytest (chain/upsert/decide/
   gate fail-open/endpoint/endpoint produksi nyata: submit kasbon
   mencatat jurnal, approve-ga terblokir 409 & lolos setelah full ACC);
   `ApprovalsView.test.js` 5 vitest; 2 test users/sync disesuaikan
   (tuple UPDATE +manager). Verifikasi host: 196 pytest terkait lulus,
   109 vitest lulus, build SPA sukses. ⚠️ Full pytest di HOST timeout
   (test DB retry tanpa container) — jalankan full suite di container:
   `docker exec bbm_web python3 -m pytest tests/ -q`.
6. **Dokumentasi**: CHANGELOG v2.36.0 (detail), README (badge versi +
   seksi fitur ACC + angka test 482/109), SECURITY/USER_GUIDE/
   USER_LIST/DEPLOYMENT/DEPLOY_FRESH/ONEPAGER/PRESENTASI/PELATIHAN/
   RETENTION_POLICY (stamp v2.36.0), USER_GUIDE + seksi 12.10 ACC
   Berjenjang, USER_LIST + atasan di Keamanan Akun, DEPLOYMENT + env
   tetap sama & catatan deploy tabel baru, ONEPAGER/PRESENTASI + angka
   482/109 + slide ACC, PELATIHAN + latihan atasan, file ini.
7. ⏳ **Langkah sesi berikutnya**: (a) commit semua perubahan v2.36.0
   (modul+hook+gate+UI+test+docs, lihat `git status`); (b) deploy
   `docker compose up -d --build web` — tabel `approval_requests` &
   kolom `manager_username` dibuat otomatis di master + 9 cabang saat
   startup; (c) smoke test live: submit kasbon dgn akun driver uji →
   login chief_driver → ACC → approve-ga GA lolos; cek halaman
   /approvals & 409 di sisi SPA; (d) verifikasi pool sehat pasca-startup
   (10 DB) & log bersih; (e) push → CI hijau; (f) cleanup data uji.

### Sesi 2026-09-06 — Sinkronisasi dokumentasi menyeluruh ke v2.35.1 ✅ SELESAI

> Konteks: produksi dipastikan **clear** (health 200, pool master 25 + 9
> cabang ready, Redis ok, `bbm_web` healthy ±11 jam, log bersih, HEAD
> `8153bb9` = v2.35.1 yang ter-deploy). User meminta semua detail
> dokumentasi diperbarui.

1. **Versi stamp → v2.35.1** di 9 dokumen (README, SECURITY, USER_GUIDE,
   DEPLOYMENT, DEPLOY_FRESH, USER_LIST, PRESENTASI, PELATIHAN,
   RETENTION_POLICY) — sebelumnya masih v2.29.10/v2.29.11/v2.34/v2.35.0.
2. **Konstanta versi kode** (fallback bila DB tidak tersedia):
   `pdf_generator.SYSTEM_VERSION`, `company_identity.IDENTITY_DEFAULTS`,
   `frontend identity.js`, seed `init.sql` (SBY/JKT/JKT2).
3. **USER_GUIDE** +4 seksi admin baru: 12.6 Step-up PIN, 12.7 Access
   Review, 12.8 Retensi & Arsip, 12.9 Verifikasi & Registri Dokumen;
   + catatan PIN ulang di alur approve GA (§5.2) + daftar isi.
4. **Angka tes & status ISO diselaraskan**: SECURITY (judul v1.0→v2.35.1 +
   banner program 6/6 selesai), ONEPAGER & PRESENTASI (323/83 → 443/104 +
   materi Tahap 2–6), DEPLOYMENT (323→443 tes CI + env ISO:
   `STALE_ACCOUNT_DAYS`/`STEPUP_TTL_SECONDS`/`RETENTION_DAYS_*` + catatan
   onboarding step-up), DEPLOY_FRESH (+sanity check 428 step-up),
   `.env.example` (+blok var ISO), PELATIHAN (+4 langkah latihan admin),
   USER_LIST (+step-up & access review di Keamanan Akun).
5. **PROGRESS**: baris Deploy (v2.31 → v2.35.1 live), header sesi 5 Sep
   ("repo" → "LIVE"), catatan sesi berikutnya (bagian CHANGELOG v2.35.1).
6. **Verifikasi**: pytest + vitest dijalankan ulang — tidak ada perubahan
   perilaku aplikasi (hanya fallback string versi & dokumentasi).
7. **Commit & deploy** (konfirmasi user "lanjutkan suggestion"): commit
   `3885809` → `docker compose up -d --build web` → `bbm_web` healthy,
   health 200 (master pool 25 + 9 cabang ready, Redis ok), SW cache
   `bpf-spa-20260906-v2351` ter-serve, log bersih.
8. **Verifikasi live langkah panduan baru**: Access Review 30 akun
   (3 ok / 26 never_login / 1 inactive / 0 stale); Retensi overview 6
   kelas × per_db=10 (master+9 cabang — pool fix v2.35.1 tetap sehat);
   registri dokumen endpoint 200 (kosong — benar, data uji telah
   dibersihkan); step-up: verify air minum tanpa grant → **428
   `STEPUP_REQUIRED`**.
9. **Push & CI hijau**: `8153bb9..ffaa8cb` → run `34007849746` sukses 3/3
   job (Frontend 45s, Backend pytest 1m19s, Trivy 1m25s; hanya anotasi
   deprecation Node 20 → 24 pada actions, bukan error).
10. **E2E step-up live dgn data nyata (bukan mock)**: purchase air minum
    asli dibuat via API multipart ber-foto (`WTR-SBY-20260906-0001`, id 21)
    → verify tanpa grant **428** → `POST /api/step-up` PIN benar (grant
    600 dtk) → verify **sukses** (status verified, verified_by tercatat).
    ⚠️ Pelajaran: cookie sesi harus di `-c` jar pada panggilan step-up —
    grant tersimpan di session cookie. **Cleanup penuh**: purchase+items,
    3 jejak activity_logs, 2 jejak step_up, 2 file foto dihapus; counter
    `SBY|WTR|20260906` di-reset agar nomor 0001 tersedia utk pengajuan
    asli berikutnya; 3 purchase asli Faisol (4 Sep) + 6 foto tetap utuh;
    health ok, 9/9 cabang ready, log bersih pasca-uji.

---

### Sesi 2026-09-05 — v2.34.0 + v2.35.0: Tahap 5 (Retensi) + Tahap 6 (Integritas dokumen) ✅ SELESAI + DEPLOY LIVE (fix v2.35.1)

> Konteks: user memerintahkan semua suggestion dikerjakan: lanjut Tahap 5
> (retensi & pemusnahan per kelas + arsip audit trail) DAN Tahap 6
> (integritas & siklus hidup dokumen) + melengkapi Lampiran B runbook.
> Kedua tahap (5 & 6) dituntaskan di repo sesuai standar: modul + UI +
> test + dokumentasi. Deploy menyusul dengan konfirmasi eksplisit.

1. **Tahap 5 (v2.34.0) — Retensi & arsip**: `modules/routes_retention.py`
   — 6 kelas dokumen (audit_logs 5 th, transactions permanen, water 5 th,
   overtime driver/ob 5 th, applicants 2 th; env `RETENTION_DAYS_*`);
   `GET /api/admin/retention/overview` (inventaris live master+9 cabang:
   jumlah, tertua/terbaru, estimasi lewat masa, anti-gagal per DB);
   `POST /api/admin/retention/archive-audit` (arsip `activity_logs` →
   `activity_logs_archive` di DB sama, satu transaksi, min 30 hari;
   register `retention_actions` + audit). Pemusnahan data bisnis TIDAK
   diotomasi (persetujuan manajemen — kebijakan bagian 6). Tabel dibuat
   otomatis di master + tiap cabang saat startup.
2. **Tahap 5 — dokumen**: `RETENTION_POLICY.md` (prinsip, kelas, jadwal
   default, prosedur arsip & pemusnahan, peran, review tahunan) + UI
   Settings → 🗄️ Retensi & Arsip (tabel kebijakan+inventaris, tombol
   arsip dgn konfirmasi, riwayat tindakan). Test `test_retention.py` (+20).
3. **Tahap 6 (v2.35.0) — Integritas dokumen**: `modules/doc_integrity.py`
   — registri `document_registry` (master): SHA-256 + bytes_size + signer
   + role + branch + timestamp + meta; best-effort. Hook di titik terbit
   PDF resmi: Tanda Terima Air (signer = TTD Finance) & Form Permohonan OT
   (driver & ob). `modules/routes_documents.py`: `POST /api/documents/verify`
   (upload PDF → hash → cocokkan; semua role login) + `GET
   /api/admin/documents` (list admin). UI Settings → 🔏 Verifikasi &
   Registri Dokumen. Test `test_doc_integrity.py` (+13).
4. **Runbook Lampiran B** dilengkapi: pemetaan peran insiden ke akun
   sistem nyata (`admin`, `it_hu`, `it_sby`, …) + catatan isi nomor oleh
   manajemen (kontak pribadi tidak tersimpan di sistem).
5. **Verifikasi**: container 443 pytest passed + 6 skip (33 baru) + 104
   vitest + build SPA sukses; host 438 pass + 6 skip (5 errors
   security-headers butuh DB container — pre-existing).
6. **Dokumentasi**: CHANGELOG v2.34.0 & v2.35.0, PROGRESS (roadmap 5 & 6 →
   ✅, status, riwayat), README & SECURITY mengikuti.
7. **Deploy Tahap 5+6 LIVE** (konfirmasi user): tabel baru otomatis dibuat
   (document_registry, activity_logs_archive, retention_actions di master
   + cabang), health OK, log bersih.
8. **Bug #1 — kebocoran pool DB cabang** (fix v2.35.1): `ensure_branch_`
   `database` memanggil 4 helper migrasi dengan `pool.get_connection()`
   tanpa close + `bc` bocor → pool cabang (5) habis tiap startup → semua
   operasi DB cabang gagal. Terdeteksi saat retention overview hanya
   membaca master (per_db=1). Fix + verifikasi: 6× get/close pool cabang
   OK; overview kini membaca 10/10 DB. (Regresi laten yang jadi kritis
   — berpotensi memengaruhi operasi cabang sejak upgrade connector 9.7.)
9. **Bug #2 — hook integritas mati-senyap** (fix v2.35.1): Form OT memakai
   `session.get` tanpa import `session` di routes_overtime → NameError
   tertelan `except: pass`. Fix: helper `session_user()`. Smoke test live
   setelah fix: Form OT → registri terisi → verify found=True →
   **tamper 1 byte → found=False** (bukti deteksi perubahan).
10. **Verifikasi final**: 443 pytest + 6 skip (container) + 104 vitest +
    build; registry dibersihkan dari data uji; log bersih; health OK.

---

### Sesi 2026-09-05 — v2.33.0: Tahap 4/6 ISO — Vulnerability management ✅ SELESAI DI REPO (belum deploy) + Deploy Tahap 3 LIVE

> Konteks: sesi berikutnya sesuai rencana PROGRESS — (a) deploy Tahap 3,
> (b) kerjakan Tahap 4. User konfirmasi: "Ya, deploy sekarang + lanjut
> Tahap 4".

1. **Push 4 commit** (`ffd2c9d..72418a3`): Tahap 1+2+3 + bump SW cache →
   `bpf-spa-20260905-v232` (commit `72418a3`).
2. **Deploy Tahap 3 LIVE**: `docker compose up -d --build web` → `bbm_web`
   healthy, health OK (DB/pool 9 cabang/redis), log bersih (hanya
   EventletDeprecationWarning gunicorn lama).
3. **Smoke test access review live**: `/app/access-review` 200; login admin
   OK; `GET /api/admin/access-review` → 30 akun terklasifikasi
   (3 ok / 26 never_login / 1 inactive / 0 stale, ambang 90 hr, review
   info kosong = belum pernah review); export CSV (BOM) OK; tanpa login 401;
   bundle SPA berisi access-review.
4. **Tahap 4a — audit dependensi & perbaikan**: `pip-audit` awal 30+ temuan
   (flask/werkzeug/pillow/mysql-connector/requests/scikit-learn/protobuf),
   `npm audit` 5 (2 critical, 1 high — vite/vitest/happy-dom/esbuild,
   semua devDependencies). **Semua di-patch**: requirements.txt → Flask
   3.1.3, Werkzeug 3.1.8, mysql-connector-python 9.7.0, Pillow 12.3.0,
   scikit-learn 1.6.1, requests 2.34.2; frontend → vite ^7.2, vitest
   ^3.2.7, happy-dom ^20.14, plugin-vue ^6.0.8. Hasil: pip-audit &
   npm audit **0 temuan**.
5. **Tahap 4b — scan image**: Trivy menemukan 2 HIGH di build-tooling image
   (jaraco.context, wheel — bukan dependensi aplikasi) → Dockerfile buang
   pip/setuptools/wheel/jaraco.context setelah `pip install`. Trivy ulang:
   **0 temuan HIGH/CRITICAL**. CI: job backend + `pip-audit -r
   requirements.txt`, job frontend + `npm audit --audit-level=high`, job
   baru **Image security scan (Trivy 0.74.0)**; `.github/dependabot.yml`
   (pip + npm, mingguan).
6. **Tahap 4c — runbook insiden**: `INCIDENT_RUNBOOK.md` (A.5.24–28) —
   peran/kontak, severity SEV-1..3, sumber deteksi, prosedur per jenis
   insiden (akun terkompromi, kebocoran data + UU PDP 3×24 jam, down,
   defacement/injeksi, brute-force/DDoS, insider, temuan audit), bukti &
   chain of custody, pemulihan, komunikasi, review pasca-insiden,
   template log + cheat-sheet terminal.
7. **Verifikasi**: 410 pytest passed + 6 skipped (container, DB service,
   versi dependensi baru) + 104 vitest + build SPA sukses; runtime image
   baru di-cek (import deps OK).
8. **Dokumentasi**: CHANGELOG v2.33.0, PROGRESS (tabel roadmap tahap 4 →
   ✅, status, riwayat sesi ini), README & SECURITY (A.8.8 + runbook +
   angka test baru).
9. **Deploy Tahap 4 LIVE** (setelah konfirmasi user "Ya, deploy Tahap 4
   sekarang"): `docker compose up -d --build web` → `bbm_web` healthy,
   health OK (db/redis), dependensi baru terverifikasi aktif di container
   (Flask 3.1.3 / Pillow 12.3.0 / sklearn 1.6.1 / mysql-connector 9.7.0 /
   requests 2.34.2), pip tidak ada di runtime, log bersih. Smoke test:
   login admin OK, access review tetap jalan (30 akun), `/api/users` 200,
   SPA 200. CI hijau 3/3 job. Commit `6ace8cb` + commit berikutnya
   (dokumentasi deploy).

---

### Sesi 2026-09-05 — v2.32.0: Tahap 3/6 ISO — Access review triwulanan + laporan akun basi ✅ SELESAI DI REPO (belum deploy)

> Konteks: lanjutan Program Perbaikan Standar Bertahap. User minta semua
> suggestion dikerjakan: (1) commit Tahap 1+2, (2) deploy Tahap 2 + smoke
> test, (3) mulai Tahap 3 (Access review). Tahap 3 dikerjakan tuntas di
> repo sesuai standar (modul + UI + test + dokumentasi); deploy menyusul
> dengan konfirmasi eksplisit.

1. **Commit Tahap 1+2** (`4fc4bca`, 37 file): secrets ke .env (v2.30) +
   step-up auth (v2.31) — termasuk `.gitignore` baru `.env.bak-*` agar
   backup .env lama (berisi kredensial) tidak pernah ter-commit.
2. **Deploy Tahap 2 LIVE** (`docker compose up -d --build web`): health ok
   (DB/Redis/10 pool cabang), log bersih, SPA baru ter-deploy.
3. **Smoke test step-up live 5 langkah lulus**: (a) approve tanpa grant →
   428 `STEPUP_REQUIRED`; (b) PIN salah → 401; (c) PIN benar → grant
   600 dtk; (d) aksi berikutnya lolos step-up (409 = data uji tak ada,
   bukan 428); (e) logout → login ulang → grant hilang (428 lagi).
4. **Tahap 3 — Backend**: `modules/routes_accessreview.py` — klasifikasi
   akun `ok`/`stale` (>90 hari, env `STALE_ACCOUNT_DAYS`)/`never_login`/
   `inactive`; 3 endpoint admin-only (`GET review`, `POST complete` →
   system_config + audit `access_review_complete`, `GET export` CSV);
   `last_login` kolom users yang sudah ada dipakai sebagai dasar.
5. **Tahap 3 — Frontend**: halaman `AccessReviewView.vue` (`/app/
   access-review`, menu Admin 🛂) — kartu ringkasan, badge REVIEW
   TERLAMBAT (>90 hr), tabel status + filter (status/role/cabang/cari),
   tombol 🚫 Nonaktifkan akun basi (A.8.3), Export CSV, Tandai Review
   Selesai.
6. **Test**: `tests/test_access_review.py` (+14, fake-DB pola docseq) +
   `AccessReviewView.test.js` (+6 vitest). Suite: **403 pytest passed +
   6 skipped** (host; security-headers butuh container DB — pre-existing)
   + **104 vitest** + build sukses.
7. **Dokumentasi**: CHANGELOG v2.32.0, PROGRESS (tabel tahap 3 → ✅,
   status terakhir, riwayat), README & SECURITY (ikut update).
8. **Commit Tahap 3** (`ac63db0`, 11 file) — repo bersih, branch `main`.
9. ⏳ **Belum deploy Tahap 3** — user memilih menunda: **"kita lanjut sesi
   berikutnya".** Sesi berikutnya mulai dengan: (a) deploy Tahap 3
   (rebuild + smoke test `/app/access-review` live), lalu (b) Tahap 4
   (Vulnerability management).

---

### Sesi 2026-09-05 — v2.31.0: Tahap 2/6 ISO — Step-up auth (PIN ulang sebelum approve/pay) ✅ SELESAI + DEPLOY LIVE

> Konteks: lanjutan Program Perbaikan Standar Bertahap (roadmap 6 tahap ISO
> 27001). Tahap 1 (Secrets) sudah live; user minta melanjutkan tahap yang
> belum rampung — Tahap 2 (Step-up auth). Pekerjaan sebagian sudah ada di
> working tree (uncommitted); sesi ini menuntaskan: audit cakupan, tutup
> celah `handover`, tambah anti-regresi endpoint nyata, verifikasi penuh,
> dan dokumentasi.

1. **Audit cakupan** — daftar semua endpoint yang menggerakkan uang:
   kasbon (approve-ga, approve-finance, handover, approve-lpj), klaim BBM
   (queue/approve-ga, payout, verify), air minum (verify). Aksi non-uang
   (reject/cancel/archive/edit/reset) sengaja TIDAK di-protect sesuai fokus
   tahap (friction minimal).
2. **Celah ditutup**: `/api/cash/handover` (serah terima dana ke driver)
   sebelumnya TIDAK di-protect — kini `@stepup_required` (backend) + masuk
   `STEPUP_KINDS` di CashView (frontend). Total 8 endpoint di-protect.
3. **Anti-regresi endpoint NYATA** (`tests/test_stepup.py` +10): memanggil
   rute produksi asli (bukan dummy) dengan sesi role benar → tanpa grant
   wajib 428 `STEPUP_REQUIRED`; grant aktif + role salah tetap 403; tanpa
   login 401 (bukan 428). Ditemukan & diperbaiki bug test: `test_client()`
   baru per panggilan = cookie jar beda → sesi hilang (kini 1 client/test).
4. **Verifikasi penuh**: 24 pytest step-up lulus; seluruh suite 391 passed +
   6 skipped (5 test security-headers butuh container DB — pre-existing,
   bukan regresi); vitest 98 passed (termasuk 14 baru: stepup store 7,
   StepUpModal 5, GaDashboard +1 alur 428→PIN→retry, WaterView mock);
   `npm run build` sukses.
5. **Dokumentasi**: CHANGELOG v2.31.0, PROGRESS tabel tahap (2 → ✅ SELESAI,
   catatan belum deploy), status terakhir, riwayat sesi ini.
6. **Deploy LIVE** (sesi ini, setelah konfirmasi user "lanjutkan semua
   suggestion"): `docker compose up -d --build web` → health ok; smoke
   test 5 langkah lulus — approve tanpa grant → 428; PIN salah → 401;
   PIN benar → grant 600 dtk; aksi berikutnya lolos step-up; logout →
   login ulang → grant hilang (428 lagi). Commit `4fc4bca`.
7. ⏳ Tahap 2 selesai live; pekerjaan lanjutan: Tahap 3 (selesai di repo,
   menunggu deploy) & seterusnya — lihat riwayat sesi berikutnya.

---

### Sesi 2026-09-04 — v2.29.9: Validasi username wajib awalan divisi + nama asli di tabel Users + uji onboarding cabang ✅ SELESAI

> Konteks: lanjutan suggestion — user minta semua dikerjakan KECUALI "wajibkan
> ganti PIN awal" (tidak wajib). Jawaban klarifikasi: (1) uji onboarding
> cabang = KEDUANYA (user baru cabang lain + cabang baru utuh dari nol);
> (2) nama asli = nama orang lebih menonjol di tabel; (3) validasi = wajib
> awalan divisi.

1. **Validasi username backend (wajib awalan divisi)** di `/api/users/sync`:
   peta role→awalan (`ga_`, `finance_`, `marketing_`, `ob_`,
   `chief_driver_`, `receptionist_`, `traineer_`, `gahr_`). Pengecualian:
   Driver (nama orang), Admin, `it_*`; akun sistem lama (`qa`,
   `test_check`, `e2e_driver`) & akun dengan (username, role) yang SUDAH ada
   di DB (mis. hasil bulk-create marketing lama bernama orang) tetap bisa
   disimpan/di-toggle — tidak ada akun terkunci. Pesan error ramah berisi
   contoh pola.
2. **Nama asli menonjol di tabel Users**: kolom Username+Nama digabung →
   Nama Lengkap tebal, username kecil di bawahnya; header "User (nama &
   login)", colspan 9→8. CSV export & pencarian tidak berubah. Browser live:
   header & urutan visual terverifikasi, 0 error JS.
3. **Test**: `tests/test_users_sync.py` 8→13 (5 baru: tolak tanpa awalan
   utk marketing & finance, akun lama nonkonform tetap bisa, legacy qa
   boleh, driver/it_* bebas); vitest UsersView +1 (urutan nama→username).
4. **Deploy live**: rebuild `bbm_web` (SW cache v299) → healthy; validasi
   terverifikasi live (buat finance `uang` → 400 pesan awalan).
5. **E2E onboarding (a) user baru cabang lain**: buat `finance_bdg` (cabang
   BDG) → login → sesi branch BDG "Cabang Bandung" → endpoint finance 200
   (scope DB cabang BDG). Akun dihapus.
6. **E2E onboarding (b) cabang baru utuh dari nol**: `POST
   /api/branches/save` + `ensure_db` → cabang TST terdaftar (branches 10→11),
   database `bpf_tst_onboard_v299` dibuat (salinan skema) → user pertama
   `finance_tst` dibuat & login → sesi cabang TST "Cabang Uji Onboarding" →
   endpoint 200 dari DB baru. **Cleanup penuh**: 2 user uji dihapus, cabang
   TST dinonaktifkan + baris branches dihapus, DB uji di-drop, container
   di-restart (pool koneksi bersih). Verifikasi: branches kembali 10,
   DB bpf_ kembali 11 (master+9 cabang+restore_test), users kembali 33,
   health 200, TST tidak ada.
7. **Test suite container**: 335 passed + 6 skipped (341 collected); vitest
   86 passed; build sukses.

---

### Sesi 2026-09-04 — v2.29.10: Standar penomoran dokumen + Kantor Pusat Jakarta (HO) ✅ SELESAI

> Konteks: user minta (1) standar penomoran dokumen & transaksi disepakati
> karena sudah banyak cabang, (2) semua "Pusat Surabaya" dikoreksi — kantor
> pusat hanya satu di Jakarta (Equity Tower), Surabaya = cabang. Keputusan
> user: format urut harian + cabang; data lama dibiarkan apa adanya.

1. **Standar penomoran v2.29.10**: `generate_display_id()` → format
   `{PREFIX}-{BRANCH}-{YYYYMMDD}-{SEQ}` (mis. `WTR-SBY-20260904-0001`).
   Cabang dari sesi login (fallback cabang utama); nomor urut harian per
   (cabang, prefix) dialokasikan atomik via tabel baru `doc_sequences` di DB
   yang sama dengan data (master + tiap cabang) — `INSERT … ON DUPLICATE
   KEY UPDATE seq = LAST_INSERT_ID(seq+1)` → tanpa nomor kembar saat
   permintaan bersamaan. Tanpa koneksi DB (tes/script) fallback in-memory
   dengan format sama. `ensure_doc_sequences()` dipanggil di startup app.py
   & di `ensure_branch_database()`.
2. **Test**: `tests/test_doc_sequences.py` baru (format 4 segmen, unik 50,
   seq naik, jalur DB atomic, DB-down fallback, ensure idempoten, cabang
   dari sesi) + update format test lama (test_cash_and_workflow,
   test_appointments 3→4 segmen).
3. **Koreksi HO Jakarta**: kode default identitas → `Kantor Pusat | Jakarta`
   + Equity Tower (company_identity.py, pdf_generator.py, identity.js,
   SettingsView placeholder), ApplyView/OvertimeFormView/presentasi hardcode
   → Jakarta; `branch_manager.DEFAULT_BRANCH_NAME` → "Cabang Surabaya";
   init.sql SBY → Cabang Surabaya + baris JKT/JKT2; fixtures test
   (test_branches, test_db_resilience) & semua dokumentasi disinkronkan.
4. **DB produksi**: branches SBY → "Cabang Surabaya" (city Surabaya),
   identitas JKT diisi (HO, Equity Tower) + ditulis ke
   `bpf_branch_jkt.system_config`; `system_config` master → subtitle
   "Kantor Pusat | Jakarta" & alamat Equity Tower. Nomor kontak
   dipertahankan (031-5349888) sampai ada nomor HO baru.
5. **Live verify** (setelah deploy, lihat bagian bawah): login UI, health,
   cabang list (SBY Cabang Surabaya, JKT HO), identitas dari endpoint
   `/api/system-config/identity` (Jakarta), e2e WTR dibuat memakai nomor
   baru, PDF & cleanup (lihat catatan deploy di bawah).
6. **Test suite**: pytest container 352 passed + 6 skipped (358 collected,
   termasuk `tests/test_pdf_header_layout.py` — geometri kop via poppler) +
   vitest 86 + build sukses; commit & push; CI hijau.

---

### Sesi 2026-09-05 — v2.29.11: Admin kelola nomor dokumen + operasional produksi ✅ SELESAI

> Konteks: user minta 4 suggestion dikerjakan: (1) cleanup akun uji lama,
> (2) e2e penomoran lintas cabang, (3) fresh deploy test dari nol,
> (4) UI admin kelola nomor dokumen (doc_sequences).

1. **Fitur Admin — Nomor Dokumen**: modul baru `modules/routes_docseq.py`:
   `GET /api/admin/doc-sequences` (daftar counter per cabang dari DB master
   + tiap DB cabang) & `POST /api/admin/doc-sequences/reset` (hapus baris
   seq_key cabang+prefix+tanggal → nomor berikutnya mulai 0001; admin-only
   + audit `doc_seq_reset`). UI: seksi **🔢 Nomor Dokumen** di SettingsView
   (filter cabang, tabel prefix/tanggal/nomor terakhir, tombol Reset dgn
   konfirmasi peringatan). SW cache v2911.
2. **Test**: `tests/test_docseq_admin.py` (+13): parse_seq_key,
   read_sequences/reset_sequences (SQL & commit), route list/reset
   (admin-only 401/403, validasi 400, cabang tak dikenal 404).
3. **Fresh deploy test**: klon bersih dari GitHub (state ter-commit) ke
   `/tmp/bpf_fresh`, compose terpisah (port 3308/5002, container prefiks
   fresh, volume baru) → init.sql jalan (admin + JKT/JKT2), startup membuat
   `doc_sequences`, e2e `WTR-SBY-…-0001` + identitas Jakarta terverifikasi;
   teardown penuh (`down -v` + hapus direktori).
4. **E2E lintas cabang live**: user uji sementara per cabang → WTR cabang
   BDG (`WTR-BDG-…-0001` di bpf_branch_bdg) & CASH cabang MLG
   (`CASH-MLG-…-0001` di bpf_branch_malang) → format & isolasi nomor
   terbukti; seluruh data uji + counter + user uji dihapus.
5. **Cleanup akun uji**: `qa` (aktif, tak pernah login), `e2e_driver`
   (nonaktif), `test_check` (nonaktif) dihapus dari users master + 2 jejak
   login e2e di activity_logs; diverifikasi tanpa referensi data operasional.
6. **Test suite**: pytest container 365 passed + 6 skipped + vitest 86 +
   build sukses; commit & push; CI hijau.

---

### Sesi 2026-09-04 — v2.29.8: Fix tab Selesai Marketing + dokumentasi konvensi username ✅ SELESAI

> Konteks: user minta semua suggestion dikerjakan + kesiapan penuh di server
> produksi tanpa intervensi. Prioritas: hilangkan 400 konsol di tab Selesai
> Marketing (pre-existing), dokumentasikan konvensi username, verifikasi e2e
> alur PDF air minum memakai user hasil rename, deploy + smoke test.

1. **Fix tab Selesai MarketingDashboard**: `/api/appointments/completed`
   adalah endpoint khusus Driver PWA (scope driver_name) → untuk marketing
   login selalu ditolak → tab kosong + 400 di console. Solusi: endpoint baru
   **`GET /api/appointments/history`** (role marketing/chief_driver/ga/admin;
   marketing di-scope `marketing_username` sesi sendiri; status completed
   lintas tanggal; urut `completed_at` DESC; limit 1–100 default 50).
   Frontend `MarketingDashboard.vue` pindah ke endpoint itu.
2. **Test**: `tests/test_appointments_history.py` 5 unit (fake-DB: scope
   marketing, tanpa scope utk GA/admin, order+limit, 403 role luar, limit
   invalid fallback) + 1 vitest MarketingDashboard (tab Selesai memuat dari
   /history, TIDAK memanggil /completed).
3. **Dokumentasi USER_GUIDE** seksi 12.1: tabel konvensi username
   `{divisi}_{cabang}` per role (nama bila >1 orang per divisi-cabang),
   catatan Driver/admin/`it_*`, + checklist onboarding pembukaan user/cabang
   baru 7 langkah; judul & footer → v2.29.8.
4. **Deploy live**: `docker compose up -d --build web` (SW cache v298),
   `bbm_web` healthy, log bersih.
5. **E2E air minum user rename**: `ob_faisol_sby` submit pengajuan berfoto
   (WTR-20260904-17484740) → `finance_sby` verifikasi → PDF tanda terima live
   turun (62 KB): kop seimbang, seksi lengkap, TTD "Finance Officer". Data
   uji + file foto dihapus (0 sisa).
6. **Marketing live**: login `marketing_yusie_sby` → `/history` 200
   `{"data":[]}` (sebelumnya 400); OB tetap ditolak `/completed` (400).
7. **Test suite container**: 330 passed + 6 skipped; vitest 86 passed.

---

### Sesi 2026-09-04 — Konvensi username `{divisi}_{cabang}` + rename massal (lanjutan v2.29.7) ✅ SELESAI

> Konteks: user minta saran user management multi-cabang — username harus
> terbaca divisi & cabang (`finance_sby`, `ob_nama_sby`). Keputusan user:
> pola `{divisi}_{cabang}` (+ nama bila >1 orang), rename akun lama sekarang,
> bantuan form cukup contoh/placeholder.

1. **Saran & keputusan**: pola `{divisi}_{cabang}` — satu orang per
   divisi-cabang; `{divisi}_{nama}_{cabang}` bila >1 (3 OB SBY →
   `ob_faisol_sby`/`ob_febri_sby`/`ob_edwin_sby` dari full_name asli).
   IT (`it_*`) & driver (login PWA nama orang) tidak diubah; `it_*` adalah
   role per cabang (pola lama dipertahankan — jangan ditiru divisi lain).
2. **Rename 12 akun produksi** via `/api/users/sync` by-id (fitur v2.29.7):
   finance_officer→finance_sby, ga_officer→ga_sby, ga_hr_officer→gahr_sby,
   ob1/2/3→ob_{faisol,febri,edwin}_sby, receptionis→receptionist_sby
   (typo), driver→chief_driver_sby, traineer_a→traineer_sby,
   Icang/Yusie/dewi→marketing_{icang,yusie}_sby & marketing_dewi_mlg.
   PIN/role/cabang dipertahankan — verifikasi login 5 akun OK. Dibiarkan:
   admin, it_*, driver, akun test (qa/test_check/e2e_driver).
3. **Selaras repo**: scripts record/rehearsal/verify_*, seed_demo_routes,
   init.sql (seed ga_sby/finance_sby + branch_code SBY), README/USER_LIST/
   USER_GUIDE/PELATIHAN/PRESENTASI/presentasi/DEPLOYMENT/DEPLOY_FRESH.
   ⚠️ Pemilik akun perlu tahu username baru (PIN tetap).
4. **Helper text pola username di form Users** (keputusan "contoh saja"):
   contoh dinamis per role+cabang (ga_sby, ob_sby → ob_faisol_sby bila
   >1 orang); catatan driver/admin/it. Deploy + verifikasi login dari UI
   via browser nyata: 11 skenario landing benar (admin, finance_sby,
   ga_sby, ob_faisol_sby, chief_driver_sby, gahr_sby, receptionist_sby,
   it_sby, marketing_yusie_sby) + PIN salah ditolak + hint tampil di
   /app/users. Satu 400 konsol tab 'Selesai' MarketingDashboard =
   endpoint driver-only pre-existing (ditangkap, tidak menghalangi).

---

### Sesi 2026-09-04 — User Management edit penuh + PDF air minum dirapikan (v2.29.7) ✅ SELESAI + DEPLOY

> Konteks: user minta (1) Admin bisa edit detail semua data user, dan
> (2) PDF tanda terima air minum dirapikan: foto bukti terlalu kecil →
> diperbesar & memanfaatkan ruang kosong di bawah TTD, header tidak simetris.

#### 🔑 Yang dikerjakan

1. **User management — edit semua detail user**:
   - **Bug nyata ditemukan**: tombol 💾 Simpan di modal Edit User SELALU
     nonaktif bila PIN dikosongkan — `(form.pin && form.pin.length !== 6)`
     mengembalikan `''` (truthy untuk atribut boolean Vue) → Admin praktis
     tidak bisa edit user tanpa ganti PIN. Diperbaiki jadi `!!form.pin && …`.
   - **`branch_code` tidak pernah disimpan** oleh `/api/users/sync`
     (INSERT/UPDATE tanpa kolom itu) — pilihan Cabang di form tidak berlaku.
     Kini disimpan dengan pola eksplisit-saja (paritas PIN/team_name) agar
     toggle & bulk action tidak menghapus cabang.
   - **Username bisa diganti** saat edit (update by-id; username adalah kunci
     login, bukan PK) + pesan 400 ramah bila username sudah dipakai user lain.
   - Frontend: form kirim `id` & `branch_code`; test vitest baru (edit user).
2. **PDF Tanda Terima Air Minum**:
   - Foto bukti (SEBELUM/SESUDAH) diperbesar: tinggi sel foto kini 60–130 mm
     mengikuti sisa ruang halaman (dicadangkan ±60 mm utk blok TTD), lebar
     sel dihitung per jumlah foto (2 foto @93 mm, 1 foto selebar halaman).
     Sebelumnya terkunci 52 mm — foto potret HP tampil jauh lebih besar.
   - Tanda tangan terdorong ke bawah; ruang kosong dasar halaman terpakai.
   - **Header kop tidak simetris diperbaiki**: nama perusahaan diratakan ke
     tengah LEBAR HALAMAN (sebelumnya terhadap sisa area setelah logo, geser
     ~7 mm ke kanan). Berlaku untuk semua PDF berlogo BPF.
3. **Verifikasi**: 20 pytest (water + pin protection) + 33 pytest PDF/upload +
   84 vitest semua lulus. Geometri PDF dicek numerik: teks kop di tengah
   297.6 pt (= 105 mm) portrait & 420.9 pt landscape, foto 93×78 mm
   (dokumen pendek) / s.d. 130 mm (halaman baru), garis TTD di ±243 mm dari
   atas. Semua PDF lain (BBM, overtime, detail, aset AC/kendaraan,
   konsolidasi, ringkasan cabang, pelamar, compact) ter-generate tanpa error
   dengan kop simetris.
4. **Unit test backend baru** `tests/test_users_sync.py` (8 test, fake DB —
   pola test_bulk_accounts_manual_route): branch_code tersimpan, username
   diganti via id, toggle/bulk tidak menghapus branch/PIN, duplikat username
   → 400 + rollback, id tidak ada → 404, non-admin → 403.
5. **Deploy live (4 Sep)** — server = perangkat ini (`bbm_web` healthy):
   `docker compose up -d --build web`; health `/api/health` ok (DB/pool/redis);
   login admin e2e 200; test suite container 325 passed + 6 skipped;
   logs bersih. E2E user management live: buat → rename username + ganti
   cabang (SBY→BDG) → toggle nonaktif tanpa branch → branch tetap BDG ✓;
   data uji dibersihkan dari DB (kembali 33 user).

---

### Sesi 2026-09-04 — Detail report terkini-dulu + sinkronisasi dokumentasi (v2.29.6) ✅ SELESAI

> Konteks: lanjutan sesi overtime — user minta laporan detail per karyawan ikut
> urut terbaru-di-atas, lalu seluruh dokumentasi proyek diselaraskan ke v2.29.6.

#### 🔑 Yang dikerjakan

1. **Detail report per nama dibalik terkini-dulu** (commit `733fd2f`): endpoint
   `/api/overtime/detail-report` kini `ORDER BY tanggal DESC, waktu_mulai DESC,
   id DESC` (PDF & Excel). Verifikasi live: baris 1 = 03/09/2026, terakhir =
   01/07/2026. Deployed (`bbm_web` healthy) + CI hijau (Backend 1m1s, Frontend
   7m36s).
2. **Sinkronisasi dokumentasi v2.29.6** (sesi ini): README, USER_GUIDE (overtime:
   Apps Script OB, auto-refresh, urutan terkini-di-atas, PDF form berfoto),
   **DEPLOYMENT.md dipulihkan** (terpotong 464→83 baris sejak rewrite `918d7ee` —
   kini lengkap dgn fakta v2.29.6), DEPLOY_FRESH.md, USER_LIST.md, SECURITY.md,
   ONEPAGER/PRESENTASI/PELATIHAN (angka tes 243/82 → 323/83), CHANGELOG & file ini.
3. **Angka aktual per 4 Sep**: 33 user, 135 transaksi BBM, 8.675 sesi OT Driver,
   599 sesi OT OB/Security, 0 pengajuan air minum (bersih pasca-cleanup demo).

---

### Sesi 2026-09-04 — Overtime: Apps Script OB + fix sinkronisasi (v2.29.6) ✅ SELESAI

> Konteks: user mau 2 sumber overtime dari Google Sheet seperti Driver; sumber
> OB/Security kedua masih URL sheet mentah dan tidak pernah sinkron.

#### 🔑 Yang dikerjakan

1. **Diagnosis**: `overtime_ob_sheet_url` berisi `…/edit` → HTML, bukan CSV →
   `overtime_ob_last_refresh` tidak pernah ada. Sheet sebenarnya bisa di-export
   CSV publik (610 baris) tapi sebaiknya tetap private seperti Driver.
2. **Apps Script OB/Security** dibuat (`scripts/apps_script_overtime_ob_security.gs`,
   SHEET_ID `1AsBq-rHss…`, commit `e450e8b`) + di-deploy user; config diarahkan
   ke Web App.
3. **Bug #1 — redirect mati (regresi `1963283`)**: `allow_redirects=False` →
   Apps Script 302 → body kosong → refresh **0 baris diam-diam**. Ini juga
   mematikan sinkronisasi **Driver**. Fix: ikuti redirect + SSRF di URL akhir;
   Driver diuji penuh 8.831 baris (57 usang ter-update).
4. **Bug #2 — `display_id` kembar di batch besar**: suffix acak 2 digit habis
   (~100/detik) → guard break → id kembar → baris tertimpa diam-diam (hanya
   ~200/599 sesi tersimpan). Fix: `OTL-SH-` + 16 hex digest deterministik.
5. **`submitted_at` OB/Security** — kolom baru (schema idempoten) + parse
   Timestamp sheet → WIB; backfill 599/599. PDF 'TANGGAL FORM' & kolom
   timestamp laporan detail kini memakai waktu submit asli Google Form
   (sebelumnya waktu sync / kosong).
6. **Re-seed OB/Security** (disetujui user): 578 migrasi → 599 sesi sheet
   (11 duplikat form dide-dupe), source='sheet', backup
   `/tmp/overtime_ob_migrasi_backup_20260904.sql`; 4 tanggal korup 1926
   (Edwin P) dikoreksi 2026 di DB — ⚠️ **sel sumber masih 1926**, perlu
   dibetulkan di Google Sheet lalu Refresh.
7. **Verifikasi**: 599 baris tersimpan, uid & display_id unik & konsisten,
   tahun 2025–2026, refresh meta tercatat. Deploy: image rebuild ×2,
   `bbm_web` healthy. Test: 56 pytest overtime lulus (incl. anti-regresi
   redirect).
8. **Auto-refresh OB + polish PDF + sorting** — auto-refresh OB di
   login/logout (mirror Driver); header tabel PDF rata satu baris + kolom
   WAKTU/NO. FORM dilebar; Form PDF semat foto sbg gambar (fallback link utk
   Drive private); sort klien GA HR tanggal terbaru di atas (API sudah DESC).
   Render PNG visual: /tmp/rekap_pg-*.png, /tmp/detail_pg-*.png,
   /tmp/form_pg-1.png. Deploy & verifikasi live (login admin memicu
   refresh OB: meta 12:55:00).

---

### Sesi 2026-09-04 — Pembersihan data demo air minum (v2.29.5) ✅ SELESAI

> Konteks: setelah verifikasi e2e v2.29.4, user Finance ingin evaluasi dokumen
> air minum oleh user sungguhan — daftar demo dibersihkan dulu dari produksi.

#### 🔑 Yang dikerjakan

1. **Hapus data demo dari `bpf_asset_system`** (DB master produksi):
   `WTR-20260904-10300556` (id 11), `WTR-DEMO-02` (id 10), `WTR-DEMO-01`
   (id 9) + item (cascade) + 9 entri `activity_logs` + 2 file foto
   (`WTR_BEFORE/AFTER_Administrator_20260904_103005_*.jpg` di `./uploads`).
2. **Hapus salinan `WTR-DEMO-02`** di `bpf_restore_test` (DB uji-restore).
   ⚠️ `WTR-DEMO-01` masih ada di DB itu (bukan produksi — sengaja dibiarkan).
3. **Backup** SQL lengkap → `/tmp/bpf_water_demo_backup_20260904.sql`
   (purchase + item + log + nama foto; di luar repo).
4. **Verifikasi live** sbg `finance_officer` (HTTPS): daftar pengajuan air
   minum kosong ✓.
5. ⏳ **CI status di GitHub Actions** — repo privat; tanpa `gh`/token sesi ini
   tidak bisa membaca run. Setup akses CI menyusul.

---

### Sesi 2026-09-04 — Format PDF air minum Finance + CI backend (v2.29.4) ✅ SELESAI

> Konteks: lanjutan sesi v2.29.3. Fokus user Finance: perbaikan dokumen Tanda
> Terima Air Minum + perbaikan CI backend yang error tanpa DB.

#### 🔑 Yang dikerjakan

1. **Format PDF air minum (v2.29.4)** — keputusan user: seksi `INFORMASI
   PENGIRIMAN`; urutan Info → Rincian → Verifikasi/Remark → **Lampiran Foto
   (sebelum TTD)** → TTD; nama TTD Finance = **user yang verifikasi**
   (`verified_by`, fallback `system_config`); form OB `Tanggal Pembelian` →
   `Tanggal Pengiriman`. Commit `b0f65df`. Test: 13 pytest water + 4 vitest
   WaterView lulus.
2. **CI backend** — job pytest pakai service mariadb+redis + env DB/SECRET_KEY
   (mirror compose). Commit `1e12feb`.
3. ✅ **Deploy & verifikasi live** — image di-rebuild + `bbm_web` healthy
   (health 200). PDF asli WTR-DEMO-02 diunduh sbg `finance_officer`: berisi
   INFORMASI PENGIRIMAN + TTD Finance `FINANCE_OFFICER` (= verified_by),
   GA dari config; istilah lama tidak ada. Baris demo tanpa foto — urutan
   lampiran dikunci unit test.
4. ✅ **Uji end-to-end ber-foto (live)** — WTR-20260904-10300556 dibuat dgn 2
   foto dummy + diverifikasi `finance_officer`: PDF memuat LAMPIRAN FOTO,
   'Foto SEBELUM diisi' & 'SESUDAH diisi' (3 XObject gambar), urutan benar
   (foto sebelum TTD); TTD Finance = full name user verifier ('FINANCE
   OFFICER'). Render PNG sanity A4 non-blank (`/tmp`).
5. ✅ **SW cache dibersihkan** — `CACHE` → `bpf-spa-20260904`, deploy ulang +
   health 200; browser pengguna akan otomatis membuang shell lama.

---

### Sesi 2026-09-04 — Fix login production + PDF air minum (v2.29.3) ✅ SELESAI

> Konteks: lanjutan sesi v2.29.2. Workhub di-restart & di-rebuild pertama kali
> setelah v2.29.1 untuk men-deploy fix login & perbaikan PDF.

#### 🔑 Yang dikerjakan

1. **Fix login "k.login is not a function"** — regresi sejak 27 Agu: aksi
   `login` tidak sengaja terhapus dari auth store (commit `0450822`) padahal
   `LoginView` tetap memanggilnya. Source sudah difix di `e8c9281` (login +
   CSRF); 4 Sep image di-rebuild (`docker compose build web`) + restart
   (`up -d web`). Verifikasi: container healthy, `/api/health` 200, bundle baru
   berisi `/api/auth/login` + `bpf_csrf`.
2. **Verifikasi login live via HTTPS** (`nasbpfsby.duckdns.org:5000`): alur
   `/api/auth/me` → login admin/123456 → 200, sesi terkonfirmasi
   (`authenticated: true`). `ga_sby`/`finance_sby` PIN `123456` → 401 (bukan
   default — perlu PIN asli utk verifikasi lanjutan).
3. **Anti-regresi login:** test kontrak store di `frontend/src/stores/auth.test.js`
   (7 vitest lulus) — gagal cepat bila `login`/`bootstrap`/`logout` hilang.
4. **Fix PDF Tanda Terima Air Minum** — judul seksi 'TANDA TANGAN'/'LAMPIRAN
   FOTO' bisa orphan di dasar halaman saat dokumen panjang; cek ruang pindah ke
   sebelum judul + test regresi multi-halaman (`tests/test_water.py`, 16 pytest
   lulus). Lihat CHANGELOG v2.29.3.

#### ⚠️ Catatan

- Browser pengguna yang masih menampilkan error login lama: hard-refresh atau
  bersihkan service worker (`sw.js` cache `index.html` lama).
- Dokumen PDF diperiksa menyeluruh (render + ekstraksi teks + layout 1 & 2
  halaman) — isi & TTD Finance/GA sesuai konfigurasi `system_config`.

---

### Sesi 2026-09-04 — Security server-wide + Monitoring (v2.29.2) ✅ SELESAI

> Konteks: lanjutan sesi sebelumnya. Workhub sudah production — sesi ini
> mengerjakan rekomendasi #1 (amankan service lain) & #2 (monitoring) dari
> PROGRESS. Runtime bpf-workhub TIDAK diubah.

#### 🔑 Akses Server (BERUBAH — penting)

- ⚠️ **SSH kini via LAN `192.168.2.31:22`** (port 2211 hanya forward WAN &
  duckdns resolve ke IP LAN dulu → timeout dari jaringan internal).
- Host publik tetap `nasbpfsby.duckdns.org` (port 2211 untuk akses luar).
- Semua perintah sesi ini pakai `ssh -p 22 it-ef@192.168.2.31`.

#### 🛡️ Yang Dikerjakan

1. **Audit port server (read-only, `ss -tlnp` + docker ps)** — hasil: semua DB
   internal ✓; publik yang tersisa memang disengaja (nginx TLS 80/443/5000/
   8443-8445, talk 3478, SSH). Semua vhost nginx proxy ke nama container +
   Host-check anti-scan.
2. **EcoPowerID hardening** — `0.0.0.0:3000` (HTTP polos publik) →
   `127.0.0.1:3000` + healthcheck node-fetch. TLS publik via nginx :8444 tetap
   200. Backup compose: `docker-compose.yml.bak-20260904`.
3. **Kill proses orphan** — `vite preview --port 5299` (bpf-trader-pro, host,
   PPID 1, basi dari sebelum container di-rebuild). Port 5299 tertutup; trader
   via 8445 tetap 200.
4. **Uptime Kuma deployed** — `/home/it-ef/uptime-kuma/` (compose + kredensial
   `.admin-credentials` chmod 600). Localhost:3001, join nextcloud_net.
   Setup otomatis via socket API: admin + **5 monitor UP (200)**: Nextcloud,
   BPF WorkHub `/api/health`, Karaoke, EcoPowerID, Chart Trader Pro.
   Verifikasi: monitorList + DB heartbeat status=1 semua.
5. **Audit endpoint (read-only)** — tool baru `scripts/audit_endpoints.py`:
   217 endpoint terdaftar; daftar kandidat unused → CHANGELOG v2.29.2. Semua
   masih PERLU verifikasi log runtime sebelum dihapus (banyak endpoint internal
   cron/sheet/legacy yang sah). Jangan hapus tanpa data.

#### 📄 File yang Diubah/Ditambah

- Server: `/home/it-ef/EcoPowerID/docker-compose.yml` (bukan repo workhub),
  `/home/it-ef/uptime-kuma/` (baru).
- Repo workhub: `scripts/audit_endpoints.py` (baru), `CHANGELOG.md`,
  `PROGRESS.md` (lokal + perlu sync ke server).

---

### Sesi 2026-09-03 — Debug & Optimasi Production (v2.29.1) ✅ SELESAI

> Konteks: sesi ini melakukan debug + optimasi menyeluruh sampai level production
> atas perintah user. Semua pekerjaan tuntas, terverifikasi, dan ter-deploy.

#### 🔑 Akses Server

| Item | Nilai |
|------|-------|
| Host | `nasbpfsby.duckdns.org` |
| SSH port | `2211` |
| User | `it-ef` |
| Lokasi codebase | `/home/it-ef/bpf-workhub` |
| Compose project | `bpf-bbm-system` (containers: `bbm_web`, `bbm_mariadb`, `bbm_redis`, `bbm_backup`) |
| App URL | `https://nasbpfsby.duckdns.org:5000` (via nextcloud_nginx) |
| Web host port | `127.0.0.1:5001` (localhost-only, akses dev via SSH tunnel) |
| DB host port | `127.0.0.1:3307` (localhost-only) |

#### 🔍 Temuan & Perbaikan

1. **DB pool exhaustion (`Pool exhausted`)** — MariaDB `max_connections=151` tapi
   `Max_used_connections=152`; pool 15×10 DB menembus batas, lalu code fallback
   bikin koneksi non-pool baru (makin parah).
   → `--max-connections=500` + retry ber-backoff (`DB_POOL_RETRIES=3`) di
   `get_db_connection()`, tanpa fallback non-pool.
2. **Dev server di production** — Dockerfile CMD `python3 -u app.py` (Werkzeug,
   `allow_unsafe_werkzeug=True`). Gunicorn ada di requirements tapi tak pernah dipakai.
   → `gunicorn --worker-class eventlet -w 1 --timeout 300` (benar untuk flask-socketio).
3. **Keamanan port** — MariaDB `0.0.0.0:3307` & web `0.0.0.0:5001` terbuka ke internet.
   → keduanya di-bind `127.0.0.1`; HTTPS publik tetap via nextcloud_nginx.
4. **Fresh-deploy SPA rusak** — bind mount `./static` menimpa SPA hasil build image
   (padahal `static/app/` gitignored). → bind mount dihapus; SPA murni dari image.
5. **Access log JSON tak pernah tercetak** — Flask logger default WARNING di production.
   → `app.logger.setLevel(INFO)` + handler eksplisit.
6. **Google Sheets overtime sync error (SSL EOF)** — tanpa retry.
   → retry 3× (backoff 1s/2s) di `_fetch_sheet_rows()`.
7. **`_redis_ping()` hardcoded URL** → baca `REDIS_URL` env.
8. **Scraper DEBUG log flood** → default `INFO` (`SCRAPER_LOG_LEVEL` env).
9. **Pool idle berlebih** — mysql.connector buka SEMUA koneksi saat init:
   `DB_POOL_SIZE=25` × 10 DB = 250 (Threads_connected sempat 206).
   → `BRANCH_POOL_SIZE=5` untuk 9 DB cabang; master tetap 25.
   Hasil terukur: **Threads_connected 206 → 26**.

#### ✅ Verifikasi Akhir (setelah deploy)

- Semua container `Up` + `(healthy)`; `bbm_web` restart count 0.
- Gunicorn master + eventlet worker jalan (cek via `docker top bbm_web`).
- Health `GET /api/health` → 200.
- Login end-to-end: `GET /api/auth/me` (ambil csrf_token) → `POST /api/auth/login`
  (`admin`/`123456` + header `X-CSRF-Token`) → `status: success` (role admin, SBY).
- SPA `/app/login` → 200.
- `docker logs bbm_web --since 5m` → 0 baris error/traceback/pool exhausted.
- Test suite di container rebuilt: **313 passed, 6 skipped**.

#### 📄 File yang Diubah (semua sudah ter-deploy + tersinkron)

`Dockerfile`, `docker-compose.yml`, `app.py`, `modules/config.py`,
`modules/security.py`, `modules/routes_overtime.py`,
`modules/news_scraper/scraper_logger.py`, `CHANGELOG.md`, `PROGRESS.md`,
`README.md`, `DEPLOYMENT.md`, `DEPLOY_FRESH.md`.

---

## 🗄️ Database Architecture

### Arsitektur Multi-Branch DB

```
┌─────────────────────────────────────────────────────┐
│                 MariaDB 10.11                        │
├─────────────────────────────────────────────────────┤
│                                                     │
│  bpf_asset_system  ← Master DB (SBY + shared data) │
│    ├── users (33)                                   │
│    ├── branches (10)                                │
│    ├── system_config                                │
│    ├── transactions (135 — BBM SBY)                 │
│    ├── overtime_driver (8,675 — OT Driver)           │
│    ├── overtime_ob_security (599 — OT OB/Sec)       │
│    ├── trip_masters (Trip SBY)                      │
│    ├── appointments                                 │
│    └── ...38 tables                                 │
│                                                     │
│  bpf_branch_jkt  ← Jakarta HO (Equity Tower)       │
│    └── 38 tables (kosong, siap data baru)           │
│                                                     │
│  bpf_branch_jkt2 ← Jakarta 2 (Pacific Place)       │
│    └── 38 tables                                    │
│                                                     │
│  bpf_branch_bdg  ← Bandung                         │
│    └── 38 tables                                    │
│                                                     │
│  bpf_branch_smg  ← Semarang                        │
│    └── 38 tables                                    │
│                                                     │
│  bpf_branch_malang ← Malang                        │
│    └── 38 tables                                    │
│                                                     │
│  bpf_branch_mdn  ← Medan                           │
│    └── 38 tables                                    │
│                                                     │
│  bpf_branch_bjm  ← Banjarmasin                     │
│    └── 38 tables                                    │
│                                                     │
│  bpf_branch_plm  ← Palembang                       │
│    └── 38 tables                                    │
│                                                     │
│  bpf_branch_lpg  ← Lampung                         │
│    └── 38 tables                                    │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Branch → Database Mapping

| Code | Nama Cabang | Database | Kota |
|------|-------------|----------|------|
| SBY | Cabang Surabaya | `bpf_asset_system` (master) | Surabaya |
| JKT | Kantor Pusat Jakarta (HO) | `bpf_branch_jkt` | Jakarta |
| JKT2 | Cabang Pacific Place | `bpf_branch_jkt2` | Jakarta |
| BDG | Cabang Bandung | `bpf_branch_bdg` | Bandung |
| SMG | Cabang Semarang | `bpf_branch_smg` | Semarang |
| MLG | Cabang Malang | `bpf_branch_malang` | Malang |
| MDN | Cabang Medan | `bpf_branch_mdn` | Medan |
| BJM | Cabang Banjarmasin | `bpf_branch_bjm` | Banjarmasin |
| PLM | Cabang Palembang | `bpf_branch_plm` | Palembang |
| LPG | Cabang Lampung | `bpf_branch_lpg` | Lampung |

### Keuntungan Multi-Branch DB

| Aspek | Manfaat |
|-------|---------|
| **Isolasi Data** | Data BBM/OT/Trip satu cabang tidak tercampur cabang lain |
| **Mirror Server** | Backup/restore per cabang — cukup copy 1 DB |
| **Performance** | Query lebih cepat (data lebih sedikit per DB) |
| **Security** | User cabang A tidak bisa akses data cabang B |
| **Compliance** | Sesuai ISO 27001 — isolasi data per unit bisnis |
| **Disaster Recovery** | Restore cabang tertentu tanpa ganggu cabang lain |

### Cara Kerja

```
1. User login → session['branch_code'] = 'BDG'
2. get_db_connection() → resolve_db_name('BDG') → 'bpf_branch_bdg'
3. Semua query operasional → ke bpf_branch_bdg
4. Query users/branches → selalu ke bpf_asset_system (master)
5. Login/logout → garansi session bersih
```

---

## ✅ Yang Sudah Selesai

### Core Features
- [x] Sistem BBM (klaim, verifikasi, pencairan)
- [x] Sistem Kasbon (kode unik, LPJ, alur relay)
- [x] Log Perjalanan / Trip (auto-save ke IndexedDB)
- [x] Dashboard per role (Admin, GA, Finance)
- [x] Dark mode + High contrast mode

### Multi-Branch Database ⭐ v2.28.0
- [x] **10 database terpisah** (1 master + 9 cabang)
- [x] **Schema sync** — semua DB punya 38 tabel identik
- [x] **Master data sync** — users, branches, config, drivers, vehicles disetiap DB
- [x] **Auto-create** — `ensure_branch_database()` saat startup
- [x] **Backward compatible** — SBY tetap di master DB

### Appointment & Rute
- [x] Marketing Hub (input appointment)
- [x] Chief Driver (board penugasan)
- [x] Atur Rute Otomatis (VRPTW heuristic)
- [x] Geocoding (Nominatim/OpenStreetMap)

### Air Minum
- [x] Form pengajuan OB (foto before/after)
- [x] Verifikasi Finance + PDF tanda terima

### Pelamar Kerja
- [x] Form publik + Dashboard Receptionist + Laporan PDF

### Aset & Pemeliharaan
- [x] 15 unit AC + 8 kendaraan + Health score otomatis

### Overtime
- [x] Driver + OB/Security + Form PWA
- [x] 3 format PDF + Excel export
- [x] GPS detail disimpan ke DB
- [x] Form Permohonan untuk Driver & OB/Security (modul param)
- [x] H+1 OT — maksimal terhitung dari jam terakhir selesai OT
- [x] Filter nama autocomplete (searchable + selectable) di laporan
- [x] Detail Report Landscape A4 + kolom Lokasi (GPS detail)
- [x] OB/Security Refresh dari Google Sheet (dashboard GA HR)
- [x] Detail Report modul-aware (driver/ob) — kolom Posisi vs Plat
- [x] Config sumber data dual-panel (Driver + OB/Security)
- [x] Foto OT auto-cleanup > 6 bulan (cron + background thread + manual API)
- [x] Cron di Docker container — langsung bekerja saat fresh deploy
- [x] Viewer foto bukti 📷 di tab Driver & OB/Security (modal, klik utk full-size)
- [x] Filter Sumber (Sheet/Aplikasi/Migrasi) di tab OB/Security — paritas Driver
- [x] GPS detail di form publik OB/Security (auto-detect Nominatim + simpan ke DB)

### PWA Driver
- [x] 5 tab: BBM, Kasbon, Trip, OT, Rapor
- [x] Foto: 📷 Kamera + 🖼️ Galeri
- [x] Auto-save trip draft (IndexedDB)
- [x] GPS detail box + auto-detect
- [x] Watermark 4 baris (proporsional)

### News Scraper (IT — Multi-Cabang)
- [x] Newsmaker + Detik Finance (64 artikel/scrape)
- [x] Multi-WordPress site (10 cabang)
- [x] Tab Report + Settings + Daily Limit configurable
- [x] SEO 7 Algoritma + Backlinks
- [x] **v2.28.8** — fix filter branch (alias kota) + normalisasi URL WpClient; live test Bandung OK

### Security & Infrastructure
- [x] CSP connect-src — Nominatim diizinkan
- [x] Service Worker — fix redirect error
- [x] Nginx cache-busting
- [x] GPS detail disimpan ke DB
- [x] **SECRET_KEY hardening** — RuntimeError jika env tidak ada di production
- [x] **SQL Injection fix** — parameterized query di `_get_sheet_url()`
- [x] **Connection leak fix** — try/finally + null check di `submit_trip()`

### QA / Test Suite (v2.28.3)
- [x] Fix parser `_pdf_text` — escape string PDF (§7.3.4.2): `\r`/`\n`/oktal kini dibaca benar; PDF aplikasi tidak pernah rusak, murni bug utilitas test
- [x] Refactor — ekstraktor teks PDF digabung ke `tests/pdf_text.py` (sebelumnya 3 salinan duplikat antar file test)
- [x] Fix mock idb di DriverView.test.js (saveTripDraft/loadTripDraft/deleteTripDraft) — hilang 3 error unhandled Vitest
- [x] Hapus dead code `return None` ganda di helpers.resolve_driver_scope()
- [x] Verifikasi host: **236/236 pytest + 82/82 Vitest lulus**
- Catatan: 5 test security-headers butuh DB container (`docker exec bbm_web python3 -m pytest tests/test_security_headers.py`); versi paket host bisa menyimpang dari requirements.txt — container tetap pakai versi pin

---

## 🔄 Yang Sedang Dikerjakan

### Roadmap v2.29.0
- [ ] **Approval berjenjang (multi-level)** — OT/BBM/Kasbon perlu approval atasan sebelum diproses GA/Finance
- [ ] **Dashboard mobile khusus admin** — monitoring real-time dari HP (bukan hanya desktop)
- [ ] **Laporan otomatis mingguan via email** — ringkasan OT, BBM, kasbon terkirim otomatis tiap Senin

### Tech Debt
- [ ] **Audit endpoint unused** — 160/161 endpoint terpakai, sisanya perlu dipetakan atau dihapus
- [ ] **Upgrade MariaDB 10.11 → 11.x** — fitur JSON table, better window functions
- [ ] **Migrate Vue 2 → Vue 3 Composition API sepenuhnya** — beberapa komponen masih pakai Options API

---

## 🛡️ Program Perbaikan Standar Bertahap (disetujui user, 5 Sep 2026)

Roadmap 6 tahap mengacu ISO/IEC 27001:2022, ISO 15489-1, UU PDP (detail saran di
PROGRESS/CHANGELOG). Dikerjakan bertahap — satu tahap per sesi, tiap tahap dengan
tes & verifikasi; perubahan produksi butuh konfirmasi eksplisit.

| Tahap | Fokus | Status |
|-------|-------|--------|
| 1 | Secrets: kredensial DB pindah ke `.env`, fail-fast, tes hygiene (A.8.2/A.8.13) | ✅ **SELESAI + rotasi produksi dijalankan 5 Sep** (health/login/backup OK, password lama mati) |
| 2 | Step-up auth: konfirmasi PIN sebelum aksi approve/pay berisiko (A.8.2/A.8.3/A.8.5) | ✅ **SELESAI 5 Sep + DEPLOY live (v2.31.0)** — 8 endpoint uang di-protect; smoke test live: 428 tanpa grant → PIN → lolos, logout hilangkan grant |
| 3 | Access review triwulanan + laporan akun basi (A.5.15/A.8.2/A.8.3) | ✅ **SELESAI 5 Sep + DEPLOY LIVE (v2.32.0)** — halaman Access Review admin, klasifikasi ok/stale/never/inactive, CSV export, tandai review selesai; 14 pytest + 6 vitest; deploy bersama Tahap 4 (lihat riwayat sesi Tahap 4) |
| 4 | Vulnerability mgmt: audit dependensi di CI + scan image + runbook insiden (A.8.8/A.5.24–28) | ✅ **SELESAI 5 Sep + DEPLOY LIVE (v2.33.0, commit `6ace8cb`)** — dependensi di-patch ke versi aman (pip-audit/npm audit 0 temuan), image runtime tanpa tooling build (Trivy 0 HIGH/CRITICAL), CI: pip-audit + npm audit + job Trivy scan (semua hijau), Dependabot mingguan, `INCIDENT_RUNBOOK.md` (A.5.24–28); 410 pytest + 104 vitest; smoke test live lulus |
| 5 | Retensi & pemusnahan dokumen per kelas + arsip audit trail (ISO 15489, UU PDP) | ✅ **SELESAI + DEPLOY LIVE 5 Sep (v2.34.0)** — kebijakan + 6 kelas + overview inventaris lintas-DB (10 DB), arsip audit trail → `activity_logs_archive` (register `retention_actions`); 20 pytest |
| 6 | Integritas tanda tangan & siklus hidup dokumen (hash + signer + timestamp) | ✅ **SELESAI + DEPLOY LIVE 5 Sep (v2.35.0, fix `v2.35.1`)** — registri SHA-256+signer+timestamp + verifikasi upload; e2e tamper-test lulus; 13 pytest |

**Tahap 1 selesai di repo (5 Sep):**
- `docker-compose.yml` baca `MYSQL_ROOT_PASSWORD`/`MYSQL_PASSWORD`/`DB_PASSWORD`
  dari `.env` (fail-fast `${VAR:?...}`); healthcheck db tanpa password hardcoded.
- `.env.example` dibuat; `modules/config.py` fail-fast di production tanpa
  `DB_PASSWORD` (dev → nilai dev-only yang jelas gagal connect).
- Fix bug `routes_reports.py` (`DB_PASS`→`DB_PASSWORD`) + password mysqldump via
  env `MYSQL_PWD` (tidak tampil di `ps`); `excel_generator.py` tanpa fallback.
- Scripts/docs/CI dibersihkan dari password produksi; `scripts/rotate-db-credentials.sh`
  (rotasi idempoten via ALTER USER, stdin bukan argv, backup .env dulu).
- Tes baru `tests/test_secret_hygiene.py` (+7) — host: 46 lulus + 7 baru (subset).
- ✅ **Rotasi produksi selesai 5 Sep** (persetujuan user): backup 11 DB → ALTER
  USER (root@localhost, root@%, bpf_user@% → hex 24 acak) → `docker compose
  up -d` (db/web/backup recreate) → verifikasi: health `ok`, 10 pool cabang
  ready, login e2e admin sukses, password lama ditolak (1045), backup otomatis
  OK. `.env` lama: `.env.bak-20260905_105155`. ⚠️ Perintah/docs lama yang
  memakai kredensial lama kini tidak berlaku — selalu baca dari `.env`.

**Tahap 2 selesai + deploy live (5 Sep, commit `4fc4bca`, v2.31.0):**
- `modules/stepup.py` — POST /api/step-up (PIN sesi, rate-limited, grant
  `stepup_until` TTL 600 dtk via `STEPUP_TTL_SECONDS`); decorator
  `@stepup_required` → 428 `STEPUP_REQUIRED`; logout hilangkan grant.
- 8 endpoint uang di-protect: kasbon approve-ga/approve-finance/handover/
  approve-lpj, BBM queue approve-ga/payout/verify, air minum verify.
- Frontend: `StepUpModal.vue` global + `stores/stepup.js`; dipakai CashView,
  WaterView, GaDashboard, AdminDashboard (retry utuh setelah PIN, incl. foto).
- Test: `tests/test_stepup.py` 24 (incl. anti-regresi endpoint NYATA 8 rute)
  + 14 vitest (stepup store 7, StepUpModal 5, GaDashboard +1, WaterView mock).
- ✅ **Deploy live 5 Sep** + smoke test 5 langkah lulus (428 → PIN → lolos →
  logout hilangkan grant). SPA bundle berisi kode step-up.

**Tahap 3 selesai di repo (5 Sep, commit `ac63db0`, v2.32.0) — DEPLOY LIVE bersama Tahap 4 (sesi berikutnya):**
- `modules/routes_accessreview.py` — klasifikasi akun `ok`/`stale` (>90 hari,
  env `STALE_ACCOUNT_DAYS`)/`never_login`/`inactive`; endpoint admin-only:
  `GET /api/admin/access-review`, `POST .../complete` (system_config siapa+
  kapan + audit), `GET .../export` CSV.
- Halaman `/app/access-review` (menu Admin 🛂): ringkasan, badge REVIEW
  TERLAMBAT (>90 hr), filter, tombol nonaktifkan akun basi (A.8.3), export
  CSV, tandai review selesai.
- Test: `tests/test_access_review.py` (+14) + `AccessReviewView.test.js` (+6).
- Suite terkini: **403 pytest + 6 skip + 104 vitest**, build sukses.

---

## 📋 Yang Belum Dikerjakan

### Fitur Baru
- [ ] Laporan otomatis mingguan via email
- [ ] Approval berjenjang (multi-level)
- [ ] Dashboard mobile khusus admin

---

## 🐛 Bug yang Sudah Diperbaiki

### v2.28.9 — News Scraper Improvements + WP Auth + Deploy
- ✅ **Source badge + filter**: setiap artikel card menampilkan badge sumber (cyan=newsmaker, orange=detik) + tombol filter per sumber
- ✅ **Newsmaker URL updated**: `https://www.newsmaker.id/id/news/commodity` — spesifik komoditas, selector scraping diupdate (live test: 16 artikel)
- ✅ `save_wp_site()` tidak menyimpan `branch_code` → `it_sby` tidak bisa melihat site → kini `branch_code` disimpan di backend & form UI
- ✅ Investigasi kredensial WP Surabaya: `human/password` tidak ada di WP DB (user tidak ditemukan)
- ✅ Kredensial benar: `it_bpf_surabaya` / Application Password → terverifikasi via curl (HTTP 200)
- ✅ Server WP Surabaya aktifkan HTTP Basic Auth → memblokir UI Application Passwords, tapi REST API tetap bisa via header `Authorization: Basic ...`
- ✅ Deploy: SPA build + Docker image rebuild + container restart — HTTP 200 verified
- ✅ Docker cleanup: ~4.7 GB reclaimed (3.85 GB images + 893 MB build cache)
- ✅ Test suite: 39 passed, 6 skipped (news_scraper) — tidak ada regressi

### v2.28.8 — News Scraper + Stabilitas Sesi Login
- ✅ `it_sby` melihat 0 situs — `wp_sites.json` rusak edit manual + fallback substring branch gagal; kini alias kota (`SBY→surabaya`)
- ✅ Semua request WP 404 `rest_no_route` — URL ganda `/wp-json/` di WpClient; kini dinormalisasi
- ✅ Pesan error auth WP tidak actionable — kini sebut user + cara buat Application Password baru
- ✅ Cookie `session` bentrok Nextcloud (domain sama, port diabaikan) → `SESSION_COOKIE_NAME='bpf_session'`
- ✅ `SECRET_KEY` regenerate tiap deploy → logout massal; DEPLOY_FRESH kini menjaga `.env` lama
- ✅ CSRF stale token di tab lama → `api.js` auto-refresh + retry sekali
- ✅ Lockout login per-IP murni mengunci seluruh kantor NAT → rate-limit kini per kombinasi IP+username
- ✅ WpClient fallback basic auth (`basic_username`/`basic_password`) saat application password ditolak — aktif di semua endpoint scraper
- ⚠️ App password BPF Surabaya ditolak WP (perlu Application Password baru); 8 cabang kredensial masih `PENDING`. Investigaasi live: WP Surabaya hanya izinkan application passwords (basic auth ditolak, XML-RPC 404) — kredensial `human/password` tidak berlaku lagi
- ℹ️ Full suite host: 300 passed; security-headers 7 passed (di container); test PDF overtime flake sekali saat full-run (lulus konsisten standalone — flake lingkungan)
- 🚀 Deployed v2.28.8 ke bbm_web (build SPA + image rebuild) — login it_sby & scraper sites terverifikasi live

### v2.28.5 — Security Hardening
- ✅ **Hardcoded SECRET_KEY (v2.28.5)** — app.py fallback insecure key; kini raise RuntimeError di production jika SECRET_KEY env tidak ada
- ✅ **SQL Injection di _get_sheet_url() (v2.28.5)** — f-string SQL → parameterized query (`%s`)
- ✅ **Dead code di routes_cash.py (v2.28.5)** — return statement kedua yang unreachable dihapus
- ✅ **Missing DB connection check (v2.28.5)** — submit_trip() crash bila conn=None; kini return 500 dengan pesan
- ✅ **Connection leak di submit_trip() (v2.28.5)** — sekarang pakai try/finally + conn=None pattern

### v2.28.4 — OT Parity & Infrastructure
- ✅ **Kolom GPS tidak ada di kode migrasi** — gps_* overtime_driver & trip_masters sebelumnya hanya manual di DB produksi; fresh deploy gagal saat submit OT/Trip ber-GPS. Kini migrasi idempoten ×3 tabel (overtime_driver, overtime_ob_security, trip_masters) + init.sql
- ✅ **Service backup DB tidak pernah jalan** — mariadb:10.11 tidak punya crond → bbm_backup crash-loop sejak v2.21. Kini loop scheduler tanpa cron; dump 10 DB terverifikasi
- ✅ **record.mjs selector login usang** — LoginView v2.27 tak lagi pakai #login-pin; skenario driver (5 tab) & GA HR diperbarui
- ✅ Presentasi & video demo di-regenerate dari data produksi cabang Surabaya (PPTX 12 slide + PDF + 11 mp4) — tersedia di Nextcloud `BPF /Presentasi_BPF_WorkHub_v2.28.4/`

### v2.27.1 — GPS & Infrastructure
- ✅ GPS kecamatan kosong — municipality/district fallback
- ✅ GPS ReferenceError — variable addr undefined
- ✅ CSP blokir Nominatim
- ✅ Service Worker redirect error
- ✅ Photo upload 1 tombol → 2 tombol
- ✅ Watermark font terlalu besar

---

## 📝 Catatan untuk Sesi Berikutnya

> Mulai dari sini: baca `PROGRESS.md` + `CHANGELOG.md` (bagian v2.35.1), lalu
> lanjutkan ke item di bawah. Semua pekerjaan v2.35.1 (Tahap 1–6 ISO + fix
> pool cabang) sudah live di server.

### 🏗️ State Saat Ini (harus diketahui sebelum ubah apa pun)
- Codebase: `/home/it-ef/bpf-workhub` (SSH port 2211, user `it-ef` — kredensial dari tim).
- Compose project `bpf-bbm-system`; container: `bbm_web` (gunicorn), `bbm_mariadb`
  (max_connections=500), `bbm_redis`, `bbm_backup` (cron 03:00 WIB).
- Port host 5001/3307 **localhost-only** — akses dev via SSH tunnel
  (`ssh -L 5001:127.0.0.1:5001 -p 2211 it-ef@nasbpfsby.duckdns.org`).
- SPA di-serve dari image (build via Dockerfile, stage frontend-build) —
  **jangan** pasang bind mount `./static` lagi.
- Env pool: `DB_POOL_SIZE=25` (master), `BRANCH_POOL_SIZE=5` (cabang),
  `DB_POOL_RETRIES=3`.
- Login API butuh CSRF: `GET /api/auth/me` → token → `POST /api/auth/login`
  dengan header `X-CSRF-Token`. Akun test: `admin`/`123456`.
- Deploy cara cepat: edit → sync ke server → `docker compose up -d --build` →
  verifikasi health + login + `docker logs`. Test: `docker exec bbm_web python3 -m pytest tests/ -q`.

### 🎯 Status Rekomendasi Sebelumnya
- ✅ **#1 Amankan service lain** — selesai sesi 2026-09-04 (EcoPowerID port +
  healthcheck, vite orphan 5299, audit port menyeluruh). Karaoke/snipe-it
  belum punya healthcheck di compose — nilai saat deploy ulang berikutnya.
- ✅ **#2 Monitoring** — Uptime Kuma live (5 monitor UP), akses localhost:3001.
  Belum: notifikasi alert (email/Telegram) & watchtower — konfigurasi via UI.
- ✅ **#3a Approval berjenjang** — SELESAI & LIVE (v2.36.0, deploy 6 Sep;
  rantai Chief Driver→GA utk kasbon/BBM, GA HR→Admin utk overtime,
  override atasan per user, halaman "ACC Atasan"); lihat riwayat sesi 6 Sep.
- ⏳ **#3b Roadmap fitur lainnya** — dashboard mobile admin, laporan
  mingguan email. Butuh keputusan produk dulu.
- ⏳ **#4 Tech debt** — audit endpoint sudah (tool + temuan CHANGELOG v2.29.2);
  upgrade MariaDB & migrasi Vue masih terbuka (butuh window + keputusan).

### 🎯 Rekomendasi Langkah Berikutnya
1. **Verifikasi endpoint legacy via log runtime** — grep `docker logs bbm_web`
   (JSON access log) 1-2 minggu utk endpoint kandidat unused di CHANGELOG
   v2.29.2; baru hapus yang benar-benar nol pemanggilan.
2. **Notifikasi Uptime Kuma** — login UI (tunnel :3001) → set alert email/
   Telegram utk 5 monitor.
3. **Roadmap fitur** (lihat "Yang Sedang Dikerjakan") — pilih 1, butuh spesifikasi.
4. **Tech debt besar** (butuh window + backup): MariaDB 10.11 → 11.x,
   migrasi Vue Options → Composition API.

### DB Architecture
- Master: `bpf_asset_system` (SBY + shared)
- Cabang: `bpf_branch_{code}` (terpisah)
- Startup: `ensure_branch_database()` auto-create

---

## 🔗 Link Penting

| Link | URL |
|------|-----|
| App | `https://nasbpfsby.duckdns.org:5000` |
| GitHub | `https://github.com/bestprofitsurabaya/bpf-workhub` |

---

## 👥 Akun IT Cabang

| Role | Username | PIN | Branch | DB |
|------|----------|-----|--------|-----|
| IT HO | `it_hu` | `123456` | JKT | bpf_branch_jkt |
| IT Surabaya | `it_sby` | `123456` | SBY | bpf_asset_system |
| IT Bandung | `it_bdg` | `123456` | BDG | bpf_branch_bdg |
| IT Semarang | `it_smg` | `123456` | SMG | bpf_branch_smg |
| IT Malang | `it_mlg` | `123456` | MLG | bpf_branch_malang |
| IT Medan | `it_mdn` | `123456` | MDN | bpf_branch_mdn |
| IT Banjarmasin | `it_bjm` | `123456` | BJM | bpf_branch_bjm |
| IT Palembang | `it_plm` | `123456` | PLM | bpf_branch_plm |
| IT Lampung | `it_lpg` | `123456` | LPG | bpf_branch_lpg |
| IT Jakarta 2 | `it_jkt2` | `123456` | JKT2 | bpf_branch_jkt2 |

---

*BPF WorkHub v2.37.5 · Progres Tracker · Last updated: 2026-09-07*
