# Peta Alur GA / Verifikasi — BPF WorkHub

Tanggal: 18 Nov 2026 · Basis kode: **v2.120.0** (`20ea0d5`)
Sifat dokumen: **peta baca-saja** (tidak mengubah perilaku). Semua nomor baris
mengacu pada kode v2.120.0.

Tujuan: menjawab "apa yang diverifikasi GA, dengan kontrol apa, dan di mana
celahnya" — bukan mendesain ulang. Alur driver ada di dokumen terpisah.

---

## 1. Peta aktor

| Aktor | Mewenang | Tidak boleh |
|---|---|---|
| **GA** | Verifikasi klaim BBM, tolak/perbaiki, kosongkan anomali, approve kasbon, serah terima dana, approve/tolak LPJ, verifikasi trip, verifikasi voucher, ACC tahap GA | Pencairan (Finance), hapus transaksi (Admin) |
| **GA HR** | ACC overtime (driver/OB/security), baca laporan overtime | Klaim BBM/kasbon, pencairan |
| **Finance** | Pencairan klaim (`os_finance`), arsip, approve kasbon tahap Finance, verifikasi air minum | Verifikasi awal GA, ACC atasan |
| **Chief Driver** | ACC tahap 1 kasbon & klaim BBM (atasan driver) | Verifikasi akhir, pencairan |
| **Admin cabang** | Semua aksi GA/Finance di cabangnya, hapus transaksi (tercatat) | ACC atasan — **ditolak 403** (`approvals.py:528`) |
| **Admin Pusat** | Baca lintas cabang; hapus butuh break-glass (alasan + step-up + token sekali pakai, `routes_spa.py:738`) | ACC atasan, aksi harian tanpa break-glass |
| **Traineer** | Verifikasi FirstWork & CV Online | Alur BBM/kasbon |

Sumber peran: `modules/routes_spa.py`, `modules/routes_cash.py`,
`modules/routes_overtime.py`, `modules/approvals.py`, `modules/routes_nav.py`.

---

## 2. Alur A — Klaim BBM (uang keluar)

```
driver submit ──► pending ──ACC Chief Driver──► (gate) ──GA──► verified_ga
                    │                                   │
                    ├─ modified ◄── GA perbaiki          └─► Finance payout ──► os_finance ──► archived
                    └─ rejected (alasan wajib)
```

| Tahap | Endpoint | Peran | Step-up | Catatan |
|---|---|---|---|---|
| Antrean | `GET /api/queue?tab=ga` | ga, finance, admin | — | `pending`/`modified`, tanpa voucher, tanpa dummy (`routes_spa.py:360`) |
| Setujui cepat | `POST /api/queue/approve-ga/<id>` | ga, admin | ✅ | **Gate ACC** (`:400`); tolak 409 bila `ml_anomaly_flag` (`:412`) |
| Verifikasi penuh | `POST /api/queue/verify/<id>` | ga, admin | ✅ | Upload foto MyPertamina, wajib `confirm_anomaly` bila flag ML (`:566`) |
| Kosongkan anomali | `POST /api/queue/anomaly-clear/<id>` | ga, admin | ✅ | Joint sign-off: Finance menolak payout bila belum di-clear (`:467`, `:481`) |
| Tolak | `POST /api/queue/reject/<id>` | ga, admin | — | Alasan ≤500 char |
| Perbaiki | `POST /api/queue/modify/<id>` | ga, admin | — | Status → `modified`, nominal/ODO divalidasi |
| Batalkan verifikasi | `POST /api/queue/unverify/<id>` | ga, admin | — | `verified_ga` → `pending`, clear anomali ikut direset (`:714`) |
| Hapus | `POST /api/queue/delete/<id>` | admin | — | Admin Pusat: break-glass |
| Pencairan | `POST /api/queue/payout/<id>` | finance, admin | ✅ | Hanya `verified_ga`, anomali wajib sudah di-clear (`:467`) |
| Arsip | `POST /api/queue/archive/<id>` | finance, admin | — | `os_finance` → `archived` |
| Detail | `GET /api/transactions/detail/<id>` | ga, finance, admin, chief_driver | — | Foto bukti + rantai waktu/aktor (`:648`) |

Notifikasi driver: `push_driver_notification` pada approve/payout/archive.
Audit: `log_activity_async` pada setiap transisi.

Antrean "Perlu Tindakan" (`modules/bbm_action_queue.py`, v2.103.0) membaca
pekerjaan yang menunggu: klaim > 2 hari, dana di driver > 14 hari, LPJ > 7 hari,
SPBU mismatch. Modul ini **tidak mengubah data**; aksinya memakai endpoint di atas.

---

## 3. Alur B — Kasbon & LPJ

```
DRAFT ──GA approve──► GA_APPROVED ──Finance approve──► FINANCE_APPROVED
  │                                                        │
  └─ rejected                                              ▼
                                              FUNDS_WITH_DRIVER (GA serah terima)
                                                           │
                                              driver submit LPJ
                                                           ▼
                                                    LPJ_SUBMITTED
                                                     │        │
                                          GA approve ┘        └─ GA reject ──► FUNDS_WITH_DRIVER
                                                           ▼
                                                      COMPLETED
```

| Tahap | Endpoint | Peran | Step-up | Catatan |
|---|---|---|---|---|
| Approve GA | `POST /api/cash/approve-ga/<id>` | ga, admin | ✅ | Gate ACC + atomik `WHERE status='DRAFT'` (`routes_cash.py:160`) |
| Approve Finance | `POST /api/cash/approve-finance/<id>` | finance, admin | ✅ | Gate ACC + `WHERE status='GA_APPROVED'` (`:212`) |
| Serah terima | `POST /api/cash/handover/<id>` | ga, admin | ✅ | `FINANCE_APPROVED` → `FUNDS_WITH_DRIVER` (`:264`) |
| Approve LPJ | `POST /api/cash/approve-lpj/<id>` | ga, admin | ✅ | LPJ → `verified_ga`, kasbon → `COMPLETED` (`:332`) |
| Tolak LPJ | `POST /api/cash/reject-lpj/<id>` | ga, admin | — | Transaksi LPJ → `rejected`, kasbon balik ke driver (`:388`) |
| Tolak kasbon | `POST /api/cash/reject/<id>` | ga, admin | — | `:547` |
| Submit LPJ | `POST /api/cash/submit-lpj/<id>` | driver | — | Guard bersama `bbm_guard` (v2.120.0) |

Kontrol LPJ (v2.120.0): foto rusak & hash duplikat **ditolak 400**; ODO mundur,
kapasitas > 90%, tanpa EXIF hanya **ditandai anomali** (`ml_anomaly_flag` +
`proof_meta`) karena satu kasbon bisa menutup beberapa pengisian.

---

## 4. Alur C — Log Trip

| Tahap | Endpoint | Peran | Step-up |
|---|---|---|---|
| Daftar | `GET /api/trips?status=pending` | ga, finance, admin | — |
| Verifikasi | `POST /api/trips/verify/<id>` | ga, admin | — |
| Tolak | `POST /api/trips/reject/<id>` | ga, admin | — |

`verified_by` selalu dari sesi, bukan input klien (`routes_spa.py:301`).
Status: `pending → verified_ga` / `rejected`. Tidak menggerakkan uang.

---

## 5. Alur D — Voucher rekanan (dipisah dari klaim)

`POST /api/voucher/verify/<id>` — GA/admin, **tanpa step-up**
(`routes_voucher.py:254`). Hanya baris `voucher_value > 0`; anomali wajib
di-clear lebih dulu (`code: ANOMALY_NEEDS_CLEAR`, 409). Setelah
`verified_ga`, pemakaian masuk tagihan periode SPBU mitra — bukan payout ke
driver, karena itu tidak dicampur ke `/api/queue`.

---

## 6. Alur E — Overtime (GA HR)

- Driver/OB/Security submit → `hook_create_approval(..., 'overtime_driver'/'overtime_ob')`.
- Rantai ACC: **GA HR saja** (`CHAIN_OVERTIME`, `approvals.py:50`).
- Baca/kelola: `/api/overtime/driver`, `/api/overtime/ob-security`,
  `/api/overtime/report`, PATCH/DELETE `/<modul>/<id>` — `ga_hr`, admin.
- PATCH yang menyentuh keputusan proses memanggil `gate_approval`
  (`routes_overtime.py:1519`).
- Foto bermasalah: `/api/overtime/foto-issues`, `.../replace-foto` (ga_hr/admin).

---

## 7. Alur F — ACC berjenjang (semua dokumen)

| Bagian | Lokasi | Catatan |
|---|---|---|
| Rantai | `approvals.py:49-50` | Kasbon/BBM: Chief Driver → GA → Finance; Overtime: GA HR |
| Buat | `create_approval`/`hook_create_approval` | Dipanggil saat submit driver |
| Antrean | `GET /api/approvals` | Hanya langkah aktif milik sesi; admin tidak melihat |
| Keputusan | `POST /api/approvals/<doc_type>/<doc_ref>/decision` | Role: admin, ga, finance, chief_driver, ga_hr; **admin 403**; alasan wajib saat tolak |
| Gate | `gate_approval` | Dipakai approve-ga BBM, approve-ga/finance kasbon, PATCH overtime |
| Badge | `routes_nav.py:173` | `approvals_pending` untuk ga/chief_driver/ga_hr |

Step-up **tidak** dipasang pada endpoint keputusan ACC (lihat §10).

---

## 8. Alur G — Verifikasi lain (di luar BBM/kasbon)

| Domain | Endpoint | Peran | Step-up | Sifat |
|---|---|---|---|---|
| Air minum | `POST /api/water/purchases/<id>/verify` | finance, admin | ✅ | `pending → verified`; remark wajib |
| Air minum tolak | `.../reject` | finance, admin | — | Alasan wajib |
| FirstWork | `POST /api/first-work/<id>/verify` | traineer, admin | — | `verify/reject/reopen` + event log |
| FirstWork massal | `POST /api/first-work/bulk-verify` | traineer, admin | — | v2.94.0 |
| CV Online | `POST /api/cv-online/<id>/review` | traineer, admin | — | `verify/reject/reopen` + scope cabang |
| Integritas PDF | `POST /api/documents/verify` | banyak peran | — | Cocokkan SHA-256 ke `document_registry` |

---

## 9. Antrean & badge yang dilihat GA

| Badge | Sumber | Isi |
|---|---|---|
| `ga_pending` | `routes_nav.py:141` | klaim `pending`/`modified`, non-voucher, non-dummy |
| `cash_pending` | `:161` | GA: `LPJ_SUBMITTED`; Finance: `GA_APPROVED` |
| `approvals_pending` | `:173` | langkah ACC aktif milik peran |
| `assignments_pending` | `:146` | penugasan belum dikonfirmasi driver |
| `bbm_verify_pending` | `:155` | `verified_ga` siap dicairkan (Finance) |

Admin Pusat memakai agregat `branch_overview` (cache 60 detik), bukan 12 DB
per request (`:186-205`).

---

## 10. Matriks kontrol step-up (uang & keputusan)

| Aksi | Step-up |
|---|---|
| `queue/approve-ga`, `queue/verify`, `queue/anomaly-clear` | ✅ |
| `queue/payout` | ✅ |
| `cash/approve-ga`, `cash/approve-finance`, `cash/handover`, `cash/approve-lpj` | ✅ |
| `water/purchases/<id>/verify` | ✅ |
| `queue/reject`, `queue/modify`, `queue/unverify`, `queue/archive` | ❌ |
| `cash/reject`, `cash/reject-lpj` | ❌ |
| `voucher/verify`, `trips/verify`, `trips/reject` | ❌ |
| `approvals/<doc>/<ref>/decision` | ❌ |

Grant step-up: 10 menit (env `STEPUP_TTL_SECONDS`), PIN user sesi sendiri,
rate-limited, dicabut saat logout (`modules/stepup.py:63-100`).

---

## 11. Temuan saat pemetaan (belum diperbaiki — kandidat rilis berikut)

1. **Jalur verifikasi melewati ACC atasan.** `POST /api/queue/verify/<id>`
   (`routes_spa.py:566`) menyetel `verified_ga` **tanpa** memanggil
   `gate_approval`, padahal `approve-ga` (`:400`) memanggilnya. Klaim yang
   masih menunggu Chief Driver bisa lolos lewat modal "Verifikasi penuh".
   Perbaikan: panggil gate yang sama sebelum update, atau tolak bila
   `approval_requests.status='pending'`.
2. **Identitas pelaku dari body pada dua aksi uang.** `cash/handover` dan
   `cash/approve-lpj` memakai `data.get('ga_name', 'GA Officer')`
   (`routes_cash.py:268`, `:339`) — berbeda dari `approve-ga/finance` yang
   memakai sesi. Ini melemahkan audit trail (nama bisa dipalsukan klien).
3. **Keputusan ACC tanpa step-up.** `approvals/.../decision` menggerakkan
   dokumen menuju pencairan tetapi tidak meminta PIN ulang; aksi yang
   *belum* menyetujui uang sudah step-up, sedangkan ACC atasan tidak.
4. **Approve LPJ tanpa jejak GA & tanpa cek rowcount.** LPJ diubah ke
   `verified_ga` tanpa `ga_approved_by`/`ga_approved_at`, dan `UPDATE` yang
   tidak mengenai baris tetap dibalas sukses (`routes_cash.py:357`). Bila
   transaksi LPJ ber-flag anomali, payout Finance akan tertahan sampai
   `/api/queue/anomaly-clear` dipanggil — alur ini tidak dijelaskan ke GA.
5. **Verifikasi voucher tanpa step-up** meski nilainya masuk tagihan
   (`routes_voucher.py:254`). Bukan payout langsung, tetapi tetap keputusan
   bernilai uang.
6. **Fallback nama audit.** `_queue_actor()`/`_actor()` jatuh ke `'Admin'`/
   `'GA Officer'` bila sesi tidak lengkap; sebaiknya tolak (401) daripada
   menulis nama generik.

---

## 12. Ringkas satu baris

GA adalah **gerbang verifikasi tunggal** untuk klaim BBM, kasbon, LPJ, trip,
dan voucher; uang baru bergerak setelah GA (`verified_ga`/`COMPLETED`) dan
Finance (`os_finance`/`FINANCE_APPROVED`), dengan ACC atasan sebagai prasyarat
di dua alur uang besar. Kontrol terkuat ada di jalur cepat (gate + step-up),
sedangkan jalur "verifikasi penuh" justru menjadi celah ACC (temuan #1).
