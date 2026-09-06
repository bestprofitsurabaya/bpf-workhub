# 🚨 Runbook Tanggap Insiden Keamanan — BPF WorkHub

> **Runbook operasional untuk menangani insiden keamanan informasi** pada BPF
> WorkHub — siapa melakukan apa, kapan, dan bagaimana — dari deteksi sampai
> pemulihan & pelajaran.
>
> Versi 1.0 · v2.33.0 (Tahap 4/6 ISO/IEC 27001) · September 2026
> Berlaku untuk aplikasi web BPF WorkHub (armada BBM, kasbon, overtime, air
> minum, appointment, news scraper) yang berjalan di
> `https://nasbpfsby.duckdns.org:5000`.

---

## 🎯 Tujuan & Ruang Lingkup

Runbook ini menjabarkan **prosedur tanggap insiden** agar setiap insiden
ditangani cepat, konsisten, terdokumentasi, dan buktinya terjaga — sesuai:

| Kontrol ISO/IEC 27001:2022 | Isi |
|---|---|
| **A.5.24** — Perencanaan & persiapan manajemen insiden | Prosedur, peran, kontak, dan kesiapan (dokumen ini) |
| **A.5.25** — Penilaian & keputusan insiden keamanan informasi | Triase: apakah ini insiden? seberapa parah? (Bagian 4) |
| **A.5.26** — Respons terhadap insiden keamanan informasi | Prosedur tanggap per jenis insiden (Bagian 6) |
| **A.5.27** — Pembelajaran dari insiden keamanan informasi | Review pasca-insiden → perbaikan (Bagian 8) |
| **A.5.28** — Pengumpulan bukti | Chain of custody & preservasi bukti (Bagian 7) |

Ruang lingkup: server produksi (`bbm_web`, `bbm_mariadb`, `bbm_redis`,
`bbm_backup`), data 10 database cabang, kredensial, dan akses tim.

---

## 1️⃣ Peran & Kontak

| Peran | Pemegang | Tanggung jawab saat insiden |
|---|---|---|
| **Komandan Insiden** | Manajer IT / Admin | Memimpin tanggap, keputusan eskalasi & komunikasi |
| **Teknisi On-Call** | Tim IT | Diagnosa teknis, eksekusi prosedur, pemulihan |
| **Penghubung Bisnis** | Manajer cabang/GA | Konfirmasi dampak operasional, info ke pengguna |
| **Sekretaris Insiden** | (ditunjuk saat insiden) | Catat timeline di log insiden (Lampiran A) |

Kontak darurat (internal): Manajer IT → Manajer cabang → Komisaris/BO jika
diperlukan. Semua keputusan **non-teknis** (hubungi polisi/otoritas, umumkan ke
publik) di luar Tim IT — naikkan ke manajemen.

> 📞 Nomor telpon kantor: **031-5349888** (isi kontak personil on-call di
> Lampiran B saat ditetapkan).

---

## 2️⃣ Klasifikasi Severity

| Sev | Nama | Contoh | Target respons | Eskalasi |
|---|---|---|---|---|
| **SEV-1** | Kritis | Akses data pribadi bocor ke pihak tak berhak, DB terhapus/di-encrypt, akun admin diambil alih, layanan down total > 30 mnt | Segera (≤ 15 mnt) | Manajer IT + manajemen |
| **SEV-2** | Tinggi | Akun non-admin terkompromi, modul rusak/corrupt, layanan melambat parah, percobaan intrusi aktif | ≤ 1 jam | Manajer IT |
| **SEV-3** | Sedang/Rendah | Anomali kecil, spam, percobaan brute-force terblokir, temuan audit dependensi | ≤ 1 hari kerja | Tim IT |

**Penilaian (A.5.25):** saat insiden dilaporkan, jawab 4 pertanyaan:
1. *Apakah benar insiden keamanan?* — atau salah konfigurasi/kesalahan user?
2. *Data apa yang terpengaruh & seberapa sensitif?* (data pribadi nasabah/karyawan = lebih tinggi)
3. *Apakah masih berlangsung?* — kalau ya, kendalikan dulu, baru investigasi.
4. *Siapa yang perlu tahu?* — ikuti tabel eskalasi, jangan umumkan sebelum dipastikan.

---

## 3️⃣ Sumber Deteksi

Pantau terus-menerus — sebagian besar insiden ditemukan dari:

| Sumber | Cara | Frekuensi |
|---|---|---|
| **Uptime Kuma** (`http://localhost:3001`) | 5 monitor UP/DOWN (WorkHub `/api/health`, Nextcloud, dll.) | Real-time (push/email) |
| **Health endpoint** | `GET /api/health` → `{"status":"ok"}` + cek DB/pool/redis | Manual saat curiga |
| **Log aplikasi** | `docker logs bbm_web --since 5m` (access log JSON + error) | On-demand |
| **Audit log internal** | Halaman Admin → Audit Log (`activity_logs`: 30+ jenis aktivitas, siapa/kapan/IP) | Harian (sekilas) |
| **CI / Dependabot** | GitHub Actions: `pip-audit`, `npm audit`, Trivy image scan; PR Dependabot | Per push / mingguan |
| **Laporan user** | GA/Finance/marketing lapor anomali data | Kapan saja |

---

## 4️⃣ Alur Tanggap (Ringkas)

```
 DETEKSI (Bagian 3)
    │
    ▼
 TRIASE (A.5.25) ──→ Bukan insiden → catat & tutup
    │  tentukan Severity (Bagian 2)
    ▼
 KENDALIKAN (A.5.26) — hentikan/perlambat dampak dulu
    │  (nonaktifkan akun, cabut akses, isolasi)
    ▼
 INVESTIGASI + KUMPULKAN BUKTI (A.5.28) — Bagian 7
    │
    ▼
 PULIHKAN — Bagian 8 (backup, rotasi kredensial, verifikasi)
    │
    ▼
 TUTUP + PELAJARAN (A.5.27) — laporan, perbaikan, update runbook
```

**Aturan emas:**
1. **Jangan panik, jangan hapus** — bukti diamankan dulu sebelum perbaikan.
2. **Kendalikan sebelum menyelidiki lebih dalam** — kalau akun disusupi, nonaktifkan dulu.
3. **Catat semuanya** — isi log insiden (Lampiran A) dari menit pertama.
4. **Jangan umumkan sebelum pasti** — komunikasi diatur Bagian 9.

---

## 5️⃣ Persiapan & Pencegahan (A.5.24)

Yang SUDAH aktif (jaga tetap jalan):
- ✅ **Backup otomatis** tiap 03.00 WIB (`bbm_backup`), retensi 30 hari — verifikasi restore berkala.
- ✅ **Audit dependensi otomatis**: `pip-audit` + `npm audit` + Trivy scan di CI tiap push; Dependabot mingguan.
- ✅ **Step-up auth** — aksi uang wajib PIN ulang (grant 10 menit).
- ✅ **Access review triwulanan** — akun basi/belum login terdeteksi & bisa dinonaktifkan.
- ✅ **Rate limiting login** + CSRF + RBAC berlapis.
- ✅ **Kredensial di `.env`** (tidak di repo); rotasi DB via `scripts/rotate-db-credentials.sh`.
- ✅ **Koneksi DB/web hanya localhost** — publik hanya lewat nginx TLS.

Periksa bulanan: backup bisa di-restore, `.env` tidak ter-commit, daftar kontak
(Lampiran B) masih berlaku, tool tanggap (SSH key) bisa dipakai.

---

## 6️⃣ Prosedur per Jenis Insiden (A.5.26)

### 6.1 Akun terkompromi / akses tidak sah
*Gejala: login aneh dari IP asing, aktivitas di audit log yang tidak dilakukan pemilik, akun nonaktif tiba-tiba aktif.*

1. **Nonaktifkan akun** segera (Admin → Users → toggle, atau langsung ke DB master `users.is_active=0`).
2. Cabut grant step-up / paksa logout: restart sesi (ubah `SECRET_KEY` bila perlu).
3. **Rotasi kredensial terkait**: PIN user (Admin ganti PIN), dan bila akun itu punya akses DB/SSH → rotasi (`scripts/rotate-db-credentials.sh`).
4. Periksa jejak di `activity_logs` + log aplikasi (dari IP mana, aksi apa).
5. SEV-1/2: simpan bukti (Bagian 7), tanyakan ke pemilik akun (apakah PIN pernah bocor/shared).
6. Pelajaran: perkuat PIN lemah, edukasi user.

### 6.2 Kebocoran / akses data tidak sah (data pribadi)
*Gejala: data nasabah/karyawan terlihat pihak tak berhak, export massal aneh, PDF/laporan bocor.*

1. **Identifikasi lingkup**: DB/master/cabang mana, tabel apa, siapa yang bisa akses (matriks peran di SECURITY.md).
2. **Hentikan kebocoran**: cabut akses user/sesi, tutup endpoint bila perlu (matikan via nginx/container sementara).
3. **Kumpulkan bukti** (Bagian 7) — kapan pertama terlihat, lewat jalur mana.
4. ⚠️ **UU PDP**: kebocoran data pribadi wajib dilaporkan ke pemilik data & otoritas **paling lambat 3×24 jam** — naikkan ke manajemen segera (keputusan non-teknis di luar Tim IT).
5. Pemulihan & laporan pasca-insiden.

### 6.3 Layanan down / tidak tersedia
*Gejala: Uptime Kuma merah, `/api/health` tidak 200, browser error.*

1. Cek urutan: `docker ps` (container hidup?) → `docker logs bbm_web --since 10m` (traceback?) → `/api/health` per komponen.
2. Restart wajar: `docker compose restart web`; bila perlu rebuild `docker compose up -d --build web`.
3. Cek DB: `docker logs bbm_mariadb`, disk penuh? (`df -h`, volume DB), koneksi pool (`Threads_connected`).
4. Down > 30 mnt tanpa sebab jelas → anggap SEV-1, cek kemungkinan serangan (log nginx/akses aneh).

### 6.4 Defacement / konten atau SPA rusak / injeksi (SQLi, XSS)
*Gejala: halaman berubah/aneh, input tersimpan berisi script, error SQL di log.*

1. **Jangan sentuh dulu** — screenshot & simpan body halaman (bukti).
2. Cek source: `docker logs`, audit log, perubahan file (`git status` di `/home/it-ef/bpf-workhub`), perubahan DB (baris aneh).
3. Pulihkan dari image/backup terpercaya; hapus data tersusupi (rolling back transaksi).
4. Periksa apakah celah masih terbuka (payload di input apa yang lolos?) — patch & tambah test regresi.
5. Aplikasi ini memakai parameterized query (anti-SQLi), CSRF, dan output Vue escape (anti-XSS) — temuan di sini = prioritas tinggi untuk ditutup.

### 6.5 Serangan brute-force / DDoS / abuse
*Gejala: banyak percobaan login gagal, IP sama membanjiri request, rate limit terpicu.*

1. Rate limiting login sudah aktif — cek log untuk IP & username sasaran.
2. Blokir di firewall/nginx (Host-check anti-scan sudah ada).
3. Nonaktifkan akun sasaran yang lemah; edukasi PIN kuat.
4. DDoS: naikkan ke manajemen (mitigasi di luar scope server ini), jaga availability via nginx cache.

### 6.6 Penyalahgunaan hak internal (insider threat)
*Gejala: user akses data di luar perannya, aksi uang tanpa step-up normal, jam akses aneh.*

1. Kumpulkan bukti audit (`activity_logs`, access log, riwayat step-up).
2. Hentikan akses sementara (nonaktifkan akun) — jangan konfrontasi sebelum bukti lengkap.
3. Laporkan ke manajemen (keputusan SDM di luar Tim IT).
4. Perkuat pemisahan tugas (SoD) & access review berikutnya.

### 6.7 Temuan audit dependensi / CI merah karena vuln
*Gejala: job `pip-audit`/`npm audit`/Trivy gagal, PR Dependabot muncul.*

1. Ini **bukan insiden aktif** bila hanya temuan CI (tidak ter-exploit).
2. Bump versi ke versi aman (seperti yang Dependabot sarankan), jalankan suite test, merge.
3. Vuln critical pada dependensi runtime yang ter-expose → ikuti 6.2 (evaluasi eksploitabilitas).
4. Jangan pernah `ignore` temuan tanpa catatan alasan di repo.

---

## 7️⃣ Pengumpulan Bukti & Chain of Custody (A.5.28)

**Prinsip:** bukti harus utuh, tidak berubah, dan jejak siapa memegangnya tercatat.

Langkah preservasi (lakukan SEBELUM perbaikan):
1. **Log container** → simpan salinan: `docker logs bbm_web > /tmp/insiden_<id>_web.log` (plus mariadb/nginx bila relevan).
2. **Snapshot DB** (bila dicurigai perubahan data): `docker exec bbm_mariadb sh -c 'exec mysqldump --all-databases -u root -p"$MYSQL_ROOT_PASSWORD"' > /tmp/insiden_<id>_db.sql` — simpan di luar server bila SEV-1.
3. **Baris audit** — query `activity_logs` (dan tabel terkait) rentang waktu insiden → export CSV dari UI Admin.
4. **Screenshot / body halaman** untuk defacement/injeksi (waktu + URL tercatat).
5. **File log lain**: `/app/data/news_scraper/*.log` (dalam container), `scraper.log`.

Catat di **log insiden** (Lampiran A): waktu pengambilan, oleh siapa, dari sumber
mana, hash file (`sha256sum`) bila perlu. Simpan bukti di folder khusus
`/tmp/insiden_<id>/` + arsip luar server. **Jangan mengubah/menghapus** sumber
bukti sebelum disalin.

---

## 8️⃣ Pemulihan & Verifikasi

| Kondisi | Tindakan |
|---|---|
| Data korup/terhapus | Restore dari backup otomatis (03.00 WIB, retensi 30 hari): restore DB master + cabang terkait, verifikasi jumlah baris |
| Kredensial bocor | `scripts/rotate-db-credentials.sh` (rotasi idempoten, backup `.env` dulu) + ganti PIN user terkait |
| Akun disusupi | Nonaktifkan → reset PIN → aktifkan kembali setelah diverifikasi |
| Kode dicurigai diubah | Rebuild image dari commit bersih: `git status` bersih → `docker compose up -d --build web` |
| Sesi dicurigai bocor | Ganti `SECRET_KEY` di `.env` (semua sesi lama mati) → restart |

**Verifikasi pemulihan:** `/api/health` 200 + log bersih → login e2e (admin) →
cek data penting (jumlah transaksi/baris sesuai) → konfirmasi ke penghubung bisnis.

---

## 9️⃣ Komunikasi

| Kepada | Kapan | Isi |
|---|---|---|
| Tim IT internal | Segera (semua sev) | Fakta, severity, siapa pegang apa |
| Manajemen | SEV-1/2 | Dampak bisnis, data terpengaruh, rencana |
| Pengguna aplikasi | Bila layanan terganggu / akun terdampak | Apa yang terganggu, kapan pulih, apa yang harus dilakukan user (ganti PIN dll.) |
| Otoritas / pemilik data | Kebocoran data pribadi (UU PDP, ≤ 3×24 jam) | Diputuskan manajemen — Tim IT hanya menyiapkan fakta |

**Satu juru bicara** untuk komunikasi eksternal; semua pesan diverifikasi
Komandan Insiden sebelum dikirim. Jangan menyebut detail teknis yang bisa
memperparah (mis. celah spesifik) di komunikasi publik.

---

## 🔟 Pasca-Insiden (A.5.27)

1. **Review dalam 5 hari kerja** setelah insiden ditutup: timeline, apa yang berhasil/gagal, akar masalah.
2. Tulis **laporan singkat**: kronologi, dampak, akar masalah, tindakan, rekomendasi.
3. **Tindak lanjut** menjadi backlog nyata (patch, monitoring, training, perubahan runbook ini).
4. **Update runbook** bila ada prosedur yang kurang/tidak berjalan — runbook hidup, bukan pajangan.
5. Arsipkan laporan & log insiden (minimum sesuai kebijakan retensi).

---

## Lampiran A — Log Insiden (template)

| Field | Isi |
|---|---|
| ID Insiden | `INC-YYYYMMDD-XX` |
| Dilaporkan | Waktu, oleh, via (Uptime Kuma/user/CI/…) |
| Severity awal → akhir | SEV-? → SEV-? |
| Deskripsi singkat | … |
| Timeline | (tiap langkah: waktu, siapa, apa, hasil) |
| Data terpengaruh | DB/tabel/akun/IP |
| Bukti disimpan | Path + hash |
| Tindakan kendali | … |
| Pemulihan | … |
| Komunikasi | Siapa dihubungi, kapan |
| Status | Terbuka / Terkendali / Ditutup |
| Review (A.5.27) | Tanggal, akar masalah, tindak lanjut |

---

## Lampiran B — Kontak On-Call (isi & jaga mutakhir)

Pemegang peran mengikuti **akun sistem yang ada** (bukan nama generik) —
pastikan nomor HP/WA diisi Manajemen & diverifikasi tiap access review.

| Peran | Akun sistem (role) | Nama / Kontak |
|---|---|---|
| Komandan Insiden | `admin` (Administrator) | *(isi nama + HP)* |
| Teknisi On-Call (HO Jakarta) | `it_hu` (IT Head Office Jakarta) | *(isi nama + HP)* |
| Teknisi On-Call (Surabaya) | `it_sby` (IT Surabaya) | *(isi nama + HP)* |
| Teknisi cadangan cabang | `it_bdg` / `it_smg` / `it_mlg` / `it_mdn` / `it_bjm` / `it_plm` / `it_lpg` / `it_jkt2` | *(sesuai lokasi)* |
| Penghubung Bisnis | Manajer cabang / GA (`ga_*`) | *(isi nama + HP)* |
| Telp kantor | — | 031-5349888 |

---

## Lampiran C — Cek Cepat (cheat-sheet terminal)

```bash
# Status & kesehatan
docker ps --filter name=bbm_
curl -s http://127.0.0.1:5001/api/health

# Log (5 menit terakhir, cari error)
docker logs bbm_web --since 5m | grep -iE 'error|traceback' 

# Restart / rebuild
docker compose restart web
docker compose up -d --build web

# Backup manual semua DB
bash scripts/backup-db.sh

# Rotasi kredensial DB (baca .env dulu — jangan pakai password lama)
bash scripts/rotate-db-credentials.sh

# Akses server (LAN)
ssh -p 22 it-ef@192.168.2.31    # codebase: /home/it-ef/bpf-workhub
```

---

*BPF WorkHub v2.33.0 · Runbook Tanggap Insiden · Diperbarui September 2026 · Tim IT BPF*
