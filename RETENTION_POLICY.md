# 🗄️ Kebijakan Retensi & Pemusnahan Dokumen — BPF WorkHub

> **Kebijakan penyimpanan, pengarsipan, dan pemusnahan dokumen/rekaman** yang
> dihasilkan & disimpan BPF WorkHub — agar data hanya disimpan selama
> dibutuhkan, dokumen penting diarsipkan utuh, dan pemusnahan tercatat.
>
> Versi 1.0 · v2.34.0 (Tahap 5/6 ISO/IEC 27001) · September 2026
> Mengacu: ISO/IEC 27001 A.8.2/A.8.10, **ISO 15489-1** (records management),
> dan **UU PDP** (pembatasan penyimpanan data pribadi).

---

## 1️⃣ Prinsip

1. **Simpan selama dibutuhkan, jangan lebih** — setiap kelas dokumen punya
   masa retensi (bagian 3). Setelah lewat, rekaman diarsipkan/dimusnahkan.
2. **Arsip dulu, baru musnah** — tidak ada penghapusan tanpa jejak. Arsip
   audit trail dipindah ke tabel arsip (`activity_logs_archive`) sebelum
   dihapus dari tabel aktif.
3. **Semua tindakan tercatat** — setiap arsip/pemusnahan dicatat di register
   `retention_actions` + audit log (siapa, kapan, berapa baris, DB mana).
4. **Data pribadi dilindungi** — data pelamar/karyawan/nasabah tidak disimpan
   lebih lama dari keperluan (UU PDP), dan tidak pernah dimusnahkan tanpa
   persetujuan.
5. **Tanpa persetujuan = tanpa pemusnahan data bisnis** — otomasi di sistem
   hanya untuk *pengarsipan* audit trail. Pemusnahan data bisnis adalah
   keputusan manajemen, dieksekusi manual dengan prosedur bagian 6.

---

## 2️⃣ Kelas Dokumen di BPF WorkHub

| Kelas (key) | Isi | Lokasi data | Tanda tangan resmi |
|---|---|---|---|
| `audit_logs` | Jejak aktivitas (siapa/kapan/IP/aksi) | `activity_logs` — master + tiap cabang | — |
| `transactions` | Transaksi BBM (klaim, foto bukti) | `transactions` | — |
| `water` | Pengajuan air minum + foto bukti & PDF Tanda Terima | `water_purchases` (+ file `uploads/`) | ✅ PDF TTD Finance/GA |
| `overtime_driver` | Sesi lembur Driver (Google Sheet/Apps Script) | `overtime_driver` | ✅ Form PDF |
| `overtime_ob` | Sesi lembur OB/Security | `overtime_ob_security` | ✅ Form PDF |
| `applicants` | Data pelamar kerja (data pribadi) | `applicants` | — |
| *PDF & file lain* | Lampiran & dokumen per kasus | `uploads/` | lihat kelas di atas |

---

## 3️⃣ Jadwal Retensi (default — DAPAT DIUBAH)

> Default di bawah adalah **titik awal** yang wajar secara praktik. Nilai
> resmi ditetapkan/direview Manajemen (lihat bagian 8). Sistem membaca nilai
> dari env `RETENTION_DAYS_<KEY>` bila diatur (mis. `RETENTION_DAYS_AUDIT_LOGS=3650`).

| Kelas | Retensi default | Alasan | Aksi otomatis sistem |
|---|---|---|---|
| Audit trail (`audit_logs`) | **5 tahun** (1.825 hari) | Jejak audit untuk investigasi & kepatuhan | ✅ **Arsip** (dipindah ke `activity_logs_archive`) via menu Admin → Retensi |
| Transaksi BBM | **Permanen** | Dokumen keuangan — sesuai keputusan manajemen | Tidak ada (hanya inventaris) |
| Air minum | 5 tahun | Bukti pengeluaran operasional + tanda terima | Tidak ada otomatis |
| Overtime Driver | 5 tahun | Data kepegawaian/klaim lembur | Tidak ada otomatis |
| Overtime OB/Security | 5 tahun | Data kepegawaian/klaim lembur | Tidak ada otomatis |
| Pelamar kerja | **2 tahun** (730 hari) | Data pribadi — UU PDP data minimization | Tidak ada otomatis |
| Foto overtime (> 6 bln) | 180 hari | Bukti visual sudah lewat masa gugat | ✅ Cron hapus otomatis (lama) |

> ⚠️ Foto/lampiran yang menyertai transaksi BBM/air adalah bagian dari
> dokumen keuangan — retensinya mengikuti dokumen induknya, JANGAN dihapus
> otomatis.

---

## 4️⃣ Inventaris & Pemantauan

Admin dapat melihat **inventaris live** tiap kelas lintas database
(master + 9 cabang): jumlah baris, tanggal tertua/terbaru, dan estimasi
baris yang sudah lewat masa retensi.

- Menu: **Pengaturan → 🗄️ Retensi & Arsip Dokumen** (`GET /api/admin/retention/overview`)
- Semua DB dihitung terpisah lalu dirangkum per kelas.

---

## 5️⃣ Pengarsipan Audit Trail (A.5.28 / ISO 15489)

Jejak audit lebih tua dari masa retensi **diarsipkan** — bukan dihapus:

1. Admin membuka Pengaturan → Retensi, menentukan ambang hari (min. 30 hari).
2. Sistem memindahkan baris `activity_logs` yang lebih tua ke tabel arsip
   `activity_logs_archive` **di DB yang sama** (master + tiap cabang),
   dalam satu transaksi (INSERT…SELECT lalu DELETE). Data arsip utuh,
   berisi kolom asli + `archived_at`.
3. Setiap DB dicatat di register `retention_actions` + audit
   `retention_audit_archive`.

Keunggulan arsip di-DB: utuh (bukan potongan file), ikut backup harian
03.00 WIB, dan tetap bisa dibuka/diekspor kapan pun oleh Admin.

---

## 6️⃣ Pemusnahan Data Bisnis (hanya dengan persetujuan manajemen)

Pemusnahan **permanen** data bisnis (transaksi, overtime, air minum,
pelamar, atau file upload) TIDAK diotomatisasi. Bila manajemen memutuskan
memusnahkan kelas tertentu yang sudah lewat masa retensi:

1. **Keputusan tertulis** — pimpinan/Manajer IT menyetujui kelas, kriteria
   tanggal, dan dasar hukumnya.
2. **Arsip dulu** — backup SQL penuh DB terkait (tool: `scripts/backup-db.sh`)
   disimpan di lokasi aman; verifikasi backup bisa dibuka.
3. **Eksekusi manual** — penghapusan dikerjakan Tim IT via SQL dengan kriteria
   eksplisit (`WHERE tanggal/created_at < batas`), pada DB yang tepat.
4. **Catat** — tulis di register `retention_actions` (baris manual) + audit log.
5. **Verifikasi** — jumlah baris tersisa & integritas data yang masih aktif.

> 🚫 Jangan pernah menghapus data keuangan (transaksi BBM, air minum,
> kasbon) tanpa backup terverifikasi & persetujuan tertulis.

---

## 7️⃣ Peran & Tanggung Jawab

| Peran | Tanggung jawab |
|---|---|
| **Admin / Tim IT** | Menjalankan arsip audit trail berkala, memantau inventaris, eksekusi teknis pemusnahan yang disetujui |
| **Manajer IT** | Merekomendasikan penyesuaian retensi; memimpin pemusnahan yang disetujui |
| **Manajemen / Pimpinan** | Menetapkan jadwal retensi resmi & menyetujui pemusnahan |
| **Semua user** | Tidak menyimpan salinan dokumen rahasia di luar sistem |

---

## 8️⃣ Review Kebijakan

Kebijakan ini direview **setahun sekali** (atau saat perubahan hukum/regulasi,
mis. perubahan UU PDP) oleh Manajer IT bersama manajemen. Perubahan jadwal
retensi diterapkan lewat env `RETENTION_DAYS_*` atau pembaruan dokumen ini.

---

## Lampiran — Cek Cepat

```bash
# Lihat inventaris retensi (admin, via API)
curl -s -b jar http://127.0.0.1:5001/api/admin/retention/overview | python3 -m json.tool

# Arsipkan audit trail > 5 tahun (via UI Pengaturan, atau API)
curl -s -b jar -X POST -H "Content-Type: application/json" -H "X-CSRF-Token: <csrf>" \
  -d '{"days": 1825}' http://127.0.0.1:5001/api/admin/retention/archive-audit

# Backup manual sebelum pemusnahan manual
bash scripts/backup-db.sh
```

---

*BPF WorkHub v2.34.0 · Kebijakan Retensi & Pemusnahan Dokumen · September 2026 · Tim IT BPF*
