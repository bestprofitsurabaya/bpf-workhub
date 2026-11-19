# Peta Distribusi Agenda

Status: berlaku untuk **v2.126.0** (19 Nov 2026).
Sumber kebenaran data: tabel `agenda_items` di DB tiap cabang WorkHub.
Dokumen ini memetakan **siapa melihat agenda apa, lewat kanal mana**.

Lihat juga: [`PETA_AGENDA.md`](PETA_AGENDA.md) (arsitektur modul),
`modules/agenda.py` (logika filter), `modules/routes_agenda.py` (API).

---

## 1. Ringkasan

Tidak ada pengiriman/duplikasi per penerima. Satu agenda = **satu baris** dengan
kolom `audience`. Setiap kanal membaca baris yang sama, lalu memfilternya
menurut identitas penerima:

| Kanal | Identitas penerima | Cakupan cabang |
|---|---|---|
| WorkHub SPA (`/agenda`) | role login + cabang sesi | cabang sesi / semua (Admin Pusat) |
| Kartu dashboard + lonceng | role login + cabang sesi | idem |
| PWA mobile `/m/` | role login (PIN) | cabang sesi |
| APK Android (bridge 8444) | PIN kategori (`marketing`/`backoffice`) | **semua cabang aktif** |
| PDF / ICS | role login + cabang sesi | idem |

Agenda bertanda `audience=all` selalu tampil di semua kanal dan semua
penerima. Agenda bertanda khusus hanya tampil pada penerima yang cocok.

---

## 2. Model data yang menentukan distribusi

Kolom relevan di `agenda_items` (satu tabel per DB cabang):

| Kolom | Nilai | Efek distribusi |
|---|---|---|
| `audience` | `all`, `marketing`, `backoffice`, `roles` | sasaran penerima |
| `audience_roles` | CSV role, mis. `finance,ga` | dipakai hanya bila `audience=roles` |
| `publish_mode` | `now`, `scheduled` | `scheduled` wajib `publish_at` |
| `publish_at` | datetime | agenda baru muncul mulai jam ini |
| `end_at` | datetime | agenda berhenti tampil setelah jam ini |
| `repeat_rule` | `none`, `weekly`, `monthly` | kemunculan berulang pada tanggalnya |
| `repeat_until` | date | batas akhir pengulangan |
| `active` | 0/1 | soft delete; 0 tidak pernah tampil |
| `notify_on_day` | 0/1 | memicu pengingat hari-H di dashboard |
| `batch_id` | UUID/null | penanda satu agenda yang diterbitkan ke banyak cabang |
| `branch_code` | kode cabang | pemilik baris |

Aturan penting:

- **Satu baris per cabang.** Terbit lintas cabang oleh Admin Pusat membuat satu
  baris di tiap DB cabang dengan `batch_id` yang sama.
- **Dedupe batch.** Saat membaca beberapa cabang sekaligus (APK, Admin Pusat),
  baris dengan `batch_id` sama ditampilkan sekali (`merge_batches=True`).
- **Soft delete.** Hapus = `active=0` + audit, bukan `DELETE`.
- **Pengulangan.** Diekspansi saat baca; editan berlaku untuk seluruh seri.
  Tanggal tidak valid (mis. 31 Feb) dijepit ke akhir bulan.

---

## 3. Matriks audiens × penerima

`✅` tampil, `—` tidak tampil.

| `audience` agenda | Marketing (SPA/PWA) | Role non-marketing* (SPA/PWA) | admin / content_creator | APK PIN Marketing (`444444`) | APK PIN Back Office (`123456`) |
|---|---|---|---|---|---|
| `all` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `marketing` | ✅ | — | ✅ | ✅ | — |
| `backoffice` | — | ✅ | ✅ | — | ✅ |
| `roles: finance,ga` | — | ✅ hanya `finance`/`ga` | ✅ | — | — |
| `roles: marketing` | ✅ | — | ✅ | — | — |
| `roles: driver` | — | ✅ hanya `driver` | ✅ | — | — |

\* Role non-marketing yang ada di WorkHub: `ga`, `finance`, `chief_driver`,
`driver`, `ob`, `receptionist`, `traineer`, `ga_hr`, `security`, `it_*`.
Semua role tersebut dianggap **backoffice** oleh filter `audience=backoffice`.

Catatan APK: aplikasi hanya mengirim `audience=marketing` atau
`audience=backoffice`. Karena itu **agenda `roles` tidak pernah tampil di APK**
(kecuali nanti bridge diubah untuk mengirim role spesifik).

---

## 4. Alur keputusan filter

### 4.1 WorkHub SPA / PWA / PDF / ICS (berbasis role)

`modules/agenda.py::_audience_ok(row, role, audience_filter=None)`

```
admin / content_creator            -> lihat semua
audience == all                    -> lihat
audience == marketing              -> hanya role marketing
audience == backoffice             -> semua role selain marketing
audience == roles                  -> role ada di audience_roles
```

Filter cabang ditentukan `modules/routes_agenda.py::_read_scope()`:

```
admin Pusat (is_ho_admin)          -> semua cabang aktif (atau ?branch=)
admin cabang                       -> cabang yang diizinkan (username/managed)
content_creator & role lain        -> hanya session['branch_code']
```

### 4.2 APK / bridge 8444 (berbasis kategori)

`modules/agenda.py::bridge_state()` / `bridge_month()`

```
audience=all        -> semua item
audience=marketing  -> item all + marketing
audience=backoffice -> item all + backoffice
```

Cabang: `bridge_branches()` = **semua cabang aktif**, lalu dedupe `batch_id`.
Bridge tidak menerima parameter cabang dan tidak memakai sesi login.

---

## 5. Kanal distribusi secara rinci

### 5.1 WorkHub SPA — `/agenda`

- Endpoint: `GET /api/agenda/month?month=YYYY-MM&branch=...`
- Filter role & cabang dilakukan **di server**.
- Filter kategori/audiens di toolbar hanya **filter tampilan** di browser
  (tidak mengubah data yang dikirim server).
- Mode kelola (tambah/edit/hapus) hanya `admin` dan `content_creator`.
- `content_creator` terkunci ke cabangnya; terbit lintas cabang hanya Admin Pusat.

### 5.2 Kartu Agenda dashboard + lonceng

- Komponen: `frontend/src/components/AgendaTodayBar.vue`
- Endpoint: `/api/agenda/day?date=…` dan `/api/agenda/upcoming?days=14`
- Hanya item yang lolos filter role + cabang yang dihitung.
- `notify_on_day=1` → satu notifikasi lonceng per item per hari per user
  (dedupe `localStorage`, key `agenda_notify:<user>:<tanggal>`).
- Tidak ada scheduler; pengingat dikirim saat kartu dashboard dirender.
- Kartu muncul di route `home`, `dashboard`, `finance`, `ga`, `marketing`,
  `chief-driver`.

### 5.3 PWA mobile — `/m/`

- Memakai `GET /api/agenda/month` (role dari sesi login PIN).
- Tab Agenda tersedia untuk semua role; driver/OB/security juga punya tab lain.
- Filter audiens mengikuti role, bukan pilihan manual.

### 5.4 APK Android — bridge `https://nasbpfsby.duckdns.org:8444`

- PIN kategori: **`444444` = Marketing**, **`123456` = Back Office**.
- Pilihan disimpan di `localStorage` (`bpf_audience`) dan dikirim sebagai
  `?audience=` ke `/api/state`, `/api/month`, `/api/stream`.
- `/api/state` → agenda satu hari; `/api/month` → jumlah agenda per tanggal;
  `/api/stream` → SSE `state` tiap 25 detik (maks. 5 menit, lalu reconnect).
- Bridge membaca **semua cabang**; agenda lintas cabang di-dedupe via `batch_id`.
- Cache bridge 15 detik; aksi tulis di WorkHub memanggil `clear_bridge_cache()`
  sehingga perubahan cepat terlihat (maks. ±15 detik).
- PIN bersifat **client-side**, bukan autentikasi. Bridge memang publik
  read-only; PIN hanya memisahkan tampilan dua kelompok.

### 5.5 PDF & ICS

- `GET /api/agenda/export.pdf?month=YYYY-MM`
- `GET /api/agenda/ics?month=YYYY-MM`
- Memakai role + cabang yang sama dengan SPA, plus parameter `audience`
  opsional untuk filter tambahan.
- Batch lintas cabang di-dedupe bila cabang yang dibaca lebih dari satu.

---

## 6. Alur tulis → tampil

```
admin cabang / content_creator
  └─ POST/PUT /api/admin/agenda/items
       ├─ validasi payload (audience, publish window, repeat, media)
       ├─ simpan 1 baris di DB cabangnya
       ├─ audit log
       └─ clear_bridge_cache()

admin Pusat (HO)
  └─ terbit "semua cabang"
       ├─ 1 baris per cabang, batch_id sama
       └─ clear_bridge_cache()

pembaca
  ├─ SPA/PWA  : filter role + cabang, window tayang, repeat
  ├─ APK      : filter audience, semua cabang, dedupe batch, cache 15 dtk
  └─ PDF/ICS  : filter role + cabang (+ audience opsional)
```

Visibilitas waktu (`is_visible`):

1. `active=1`
2. audiens cocok
3. `publish_mode=now` atau `now >= publish_at`
4. bila `end_at` diisi: `now <= end_at`
5. tanggal kemunculan = tanggal agenda / hasil ekspansi pengulangan

---

## 7. Contoh kasus

| Agenda | Cabang | Audience | Tampil di |
|---|---|---|---|
| Rapat umum | SBY | `all` | semua kanal, kedua PIN APK |
| Promo produk | SBY | `marketing` | SPA Marketing, APK PIN 444444 |
| Update absensi | SBY | `backoffice` | SPA non-marketing (GA/Finance/OB/…), APK PIN 123456 |
| Cuti bersama | semua (batch) | `all` | semua cabang, APK (1 item, dedupe) |
| Pelatihan finance | SBY | `roles` + `finance` | SPA/PWA Finance & admin; **tidak di APK** |
| Agenda terjadwal 10.00 | SBY | `all` | baru muncul setelah 10.00; hilang setelah `end_at` |
| Agenda mingguan | SBY | `marketing` | setiap kemunculan mingguan, hanya Marketing |

---

## 8. Celah & risiko yang perlu diputuskan

1. **Agenda `roles` tidak sampai ke APK.** Bila ada agenda untuk `finance`,
   `ga`, atau driver yang harus terlihat di HP, bridge perlu parameter role
   (mis. `?role=finance`) atau APK perlu login.
2. **`backoffice` = semua non-marketing.** Termasuk driver/OB/security.
   Kalau maksudnya hanya staf BO, perlu audience baru (mis. `bo_staff`) atau
   pemetaan role eksplisit.
3. **APK tidak memfilter cabang.** Agenda khusus SBY tetap terlihat di APK
   cabang lain. Dedupe hanya mencegah duplikat batch, bukan kebocoran cabang.
4. **PIN bukan keamanan.** Siapa pun bisa mengubah `localStorage` atau memanggil
   bridge langsung; data memang publik. Jangan menaruh agenda rahasia di sini.
5. **Pengingat hari-H bergantung pada dashboard dibuka.** Tidak ada push
   background/scheduler; dedupe juga per perangkat, bukan per akun lintas HP.
6. **Cache 15 detik.** Agenda baru bisa terlambat tampil di APK maksimal
   ±15 detik (kecuali stream sudah mengirim event berikutnya).

---

## 9. Verifikasi cepat

```bash
# APK Marketing: hanya all + marketing
curl -sk "https://nasbpfsby.duckdns.org:8444/api/state?audience=marketing" | jq '.items[].title'

# APK Back Office: hanya all + backoffice
curl -sk "https://nasbpfsby.duckdns.org:8444/api/state?audience=backoffice" | jq '.items[].title'

# Cek header CORS (wajib ada untuk WebView)
curl -skI -H 'Origin: https://localhost' \
  "https://nasbpfsby.duckdns.org:8444/api/state" | grep -i access-control
```

Tes otomatis: `tests/test_agenda.py` (isolasi cabang, audiens, bridge),
`tests/test_app_release.py` (rilis APK + CORS).
