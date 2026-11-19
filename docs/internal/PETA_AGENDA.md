# Peta Modul Agenda — WorkHub sebagai sumber kebenaran

Status: **diterapkan** di v2.123.0, dipurge & dipindah penuh di v2.124.0,
update APK mandiri sejak v2.125.0 (19 Nov 2026).

Tujuan: menyatukan agenda harian BPF ke WorkHub — satu login, satu audit,
multi-cabang — tanpa memutus aplikasi Cordova yang sudah terpasang.

## 1. Keputusan

- **Sumber kebenaran:** modul Agenda di WorkHub (Flask + MySQL + Vue).
- **Aplikasi Android:** sumbernya pindah ke `apk/` di repo WorkHub dan dibangun
  dari sana. Aplikasi memakai **bridge** read-only di nginx port 8444
  (`/api/state`, `/api/month`, `/api/stream`, `/assets/*`).
- **Data lama:** sudah diimpor sekali ke satu cabang tujuan (idempoten via
  `legacy_id`); media disalin ke volume WorkHub. Skrip impornya sudah dihapus.
- **Tanpa mode TV.** Agenda tampil sebagai **kartu ringkas di beranda/dashboard**
  (dekat indikator realtime/offline) yang bisa diklik untuk membuka kalender.
- **Notifikasi hari H opsional** per agenda (`notify_on_day`), sekali per item
  per hari, muncul di lonceng notifikasi.
- **Content creator:** role baru **per cabang**; mengelola agenda cabangnya
  sendiri (buat/edit/terbit/hapus) dan memakai Transcoder. **Tidak** boleh
  terbit lintas cabang — itu hanya admin_master. Tidak mendapat halaman admin
  lain (user, setelan, log, break-glass, matriks cakupan).

## 2. Aktor & hak

| Aksi | Admin cabang | Admin master | Content creator | Role lain |
|---|---|---|---|---|
| Lihat agenda | cabangnya | semua | cabangnya | cabangnya |
| Buat/edit/terbit | cabangnya | semua | cabangnya | — |
| Terbit "semua cabang" | — | ✅ | — | — |
| Hapus (step-up PIN) | cabangnya | semua | cabangnya | — |
| Matriks cakupan | — | ✅ | — | — |
| Transcoder | — | ✅ | ✅ | IT (`it_*`) |

Penegakan di backend: `role_required(['admin','content_creator'])`;
admin memakai `admin_can_operate_branch()`, content creator dikunci ke
`session['branch_code']`. Jangan hanya menyembunyikan tombol di UI.

## 3. Model data

Per DB cabang — `agenda_items`:

```
id, batch_id, branch_code, agenda_date,
title, body, category, audience, audience_roles,
publish_mode, publish_at, end_at,
repeat_rule, repeat_until,
media_url, media_type, attachment_path,
pinned, notify_on_day, active, legacy_id,
created_by, updated_by, created_at, updated_at
```

Aturan:
- `category`: umum | rapat | libur | event | pengumuman.
- `audience`: all | marketing | backoffice | roles (+ `audience_roles` CSV).
- `publish_mode`: now | scheduled. `scheduled` wajib `publish_at`; `end_at`
  opsional dan harus setelah `publish_at`.
- `repeat_rule`: none | weekly | monthly; `repeat_until` opsional (maks 2 tahun).
- Terbit lintas cabang = satu baris per cabang dengan `batch_id` yang sama.
- Hapus = `active=0` (soft delete) + audit; bukan DELETE fisik.
- `notify_on_day` = 0/1; bila 1, kartu dashboard mengirim satu notifikasi
  lonceng pada hari-H (dedupe per user per item per hari di browser).

## 4. API

Baca (login semua role, difilter cabang):
- `GET /api/agenda/month?month=YYYY-MM&branch=&category=&audience=`
- `GET /api/agenda/day?date=YYYY-MM-DD`
- `GET /api/agenda/upcoming?days=7`
- `GET /api/agenda/item/<id>`
- `GET /api/agenda/ics?month=YYYY-MM` (unduh)
- `GET /api/agenda/export.pdf?month=YYYY-MM` (unduh)

Kelola (admin / content_creator):
- `POST /api/admin/agenda/items`
- `PUT /api/admin/agenda/items/<id>`
- `DELETE /api/admin/agenda/items/<id>` (step-up)
- `POST /api/admin/agenda/items/<id>/duplicate`
- `POST /api/admin/agenda/upload` (raw, `X-Filename`)
- `GET /api/admin/agenda/coverage?month=YYYY-MM`

Bridge Cordova (publik, read-only, bentuk respons sama dengan server lama):
- `GET /api/state?date=&audience=`
- `GET /api/month?month=&audience=&items=1`
- `GET /api/stream?audience=` (SSE; bila tidak tersedia, app fallback polling 15 dtk)
- `GET /assets/up/<file>` (Range/seek)
- `GET /assets/logo.png` (logo aplikasi lama)

## 5. Aturan tampil

- Agenda hanya berlaku pada tanggalnya.
- `now`: langsung tayang; `scheduled`: setelah `publish_at`, berhenti di `end_at`.
- Pengulangan diekspansi saat baca; tanggal tidak valid (31 Feb) dijepit ke
  hari terakhir bulan. Editan berlaku untuk seluruh seri.
- Untuk pengulangan, jam tayang mengikuti `publish_at`/`end_at` pada tanggal
  kemunculan.
- Agenda dari batch lintas cabang dideduplikasi saat dibaca lintas cabang
  (bridge & tampilan "semua cabang") memakai `batch_id`/`legacy_id`.

## 6. UI/UX

- `/agenda`: grid bulan + rail "Hari ini" / "Mendatang"; filter kategori,
  audiens, cabang (admin master/content creator).
- Mode kelola: tombol tambah, editor modal, hapus dengan step-up.
- Tab **Cakupan cabang** (matriks mingguan) khusus admin master.
- **Kartu Agenda** ringkas di beranda/dashboard role (hari ini + agenda
  berikutnya), dapat diklik membuka `/agenda`.
- Notifikasi hari H muncul di lonceng realtime bila agenda ditandai.
- Mobile PWA `/m/`: tab Agenda, kalender bulan, daftar per hari.

## 7. Bridge & migrasi

- nginx 8444 diarahkan ke WorkHub (`bpf-workhub-web:5000`); konfigurasi repo
  ada di `nginx/agenda-bridge.conf`.
- Server/container/repo lama sudah **dihapus** (v2.124.0). Tidak ada rollback
  ke server agenda terpisah — WorkHub satu-satunya sumber data.
- APK dibangun dari `apk/` (`scripts/build-android.sh`); package id tetap
  `id.co.bpf.calendar`, tampilan berlabel **BPF Agenda**.
- **Update APK** (v2.125.0): `GET /api/app/latest` (manifest versi + SHA-256)
  dan `GET /api/app/download/<file>.apk`, keduanya publik lewat bridge 8444.
  Folder rilis host `/srv/bpf-workhub/apk` → container `/app/data/apk`.
  `apk/scripts/publish-release.sh <apk> "catatan"` menulis `latest.json`.
  Aplikasi cek versi saat dibuka, unduh, verifikasi hash, lalu membuka
  installer sistem (konfirmasi pengguna tetap wajib).

## 8. Tes

Backend: matriks akses, isolasi cabang, jendela tayang, ekspansi pengulangan,
fan-out batch, dedupe lintas cabang, step-up hapus, guard upload, bentuk
respons bridge, ICS, migrasi idempoten, validasi payload, rilis APK
(manifest, unduhan, traversal, rilis lama).
Frontend: render grid, filter, gate admin/content creator, editor, step-up,
matriks cakupan, kartu dashboard, notifikasi hari H.
Manual: APK lama terhadap bridge, media Range, 12 DB nyata.

## 9. Rilis

v2.123.0 = fondasi modul Agenda + bridge; v2.124.0 = purge server lama +
pemindahan proyek APK ke repo WorkHub; v2.125.0 = update APK via WorkHub
(mirror Nextcloud dihapus).
Setiap rilis tetap: PROGRESS + CHANGELOG + 7 titik stamp + commit/push + deploy.
