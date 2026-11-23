# Desain: Driver Mengajukan Tukar Kendaraan, GA Menyetujui, Serah Terima Berbukti

Tanggal: 2026-11-23
Status: disetujui — diimplementasikan di v2.132.0
Versi target: v2.132.0

## 1. Intent dan alasan

Saat ini tukar kendaraan hanya bisa dilakukan GA/admin lewat `AssignmentsView` →
`POST /api/assignments/swap`. Driver tidak punya cara mengusulkan, sehingga
koordinasi terjadi di luar sistem (chat/telepon), lalu GA mengetik ulang. Akibatnya:

- Tukar kendaraan lambat saat driver sudah sepakat di lapangan.
- Alasan tukar tidak selalu tercatat rapi; `assignment_swaps` hanya terisi saat GA
  mengeksekusi.
- Serah terima pasca-tukar hampir tidak dipakai: 4 dari 5 assignment aktif masih
  `confirmed_by_driver = 0`. Tidak ada bukti kondisi/kilometer kendaraan.

Yang diinginkan: driver bisa **mengajukan** tukar kendaraan sendiri (lebih cepat,
lebih fleksibel), GA cukup **menyetujui**, lalu **kedua driver melakukan serah
terima ulang** dengan bukti odometer + foto. Setiap pengajuan wajib beralasan.

## 2. Goals

1. Driver dapat mengajukan salah satu dari dua jenis, disertai kategori dan alasan
   wajib:
   - **tukar** dua arah dengan driver lain di cabang yang sama, atau
   - **pindah** ke kendaraan kosong (satu arah; kendaraan lamanya masuk pool).
2. GA/admin dapat menyetujui atau menolak dari satu layar, dengan jejak audit.
3. Persetujuan langsung mengeksekusi pertukaran secara atomik: kedua kendaraan
   bertukar pemegang, tanpa kendaraan yang menganggur.
4. Kedua driver menyelesaikan serah terima dengan **odometer + satu foto kendaraan
   yang mereka terima**; status pengajuan menjadi `completed` setelah keduanya.
5. Tidak ada jalur pintas: konfirmasi lama tanpa bukti tidak boleh dipakai untuk
   assignment yang lahir dari pengajuan tukar.

## 3. Non-goals

- Bukan tukar lintas cabang. Hanya driver di DB cabang yang sama.
- Bukan persetujuan berlapis (kepala driver/finance). Finance hanya membaca.
- Bukan negosiasi dua arah di aplikasi: driver tujuan tidak perlu menekan
  "setuju" sebelum GA; konsensusnya terjadi saat serah terima.
- Bukan pengganti alur GA yang sudah ada (`create`, `swap`, `release`). Alur lama
  tetap dipakai untuk penugasan biasa dan koreksi.
- Tidak ada rollback otomatis setelah approve. Salah tukar dikoreksi dengan swap
  GA biasa (tercatat sebagai riwayat baru).

## 4. Anti-goals (gagal walau teknisnya jalan)

- Pengajuan bisa dibuat atas nama driver lain atau lintas cabang.
- Approve ganda / dua pengajuan bersamaan membuat satu driver punya dua kendaraan
  aktif atau satu kendaraan punya dua pemegang.
- Driver bisa menandai "sudah serah terima" tanpa odometer/foto.
- Data pengajuan hilang saat approve gagal di tengah jalan (setengah tukar).
- GA tidak melihat pengajuan masuk sehingga fitur justru memperlambat.

## 5. Kondisi sistem saat ini (hasil recon)

- `vehicle_assignments`: sumber kebenaran penugasan. Satu driver satu baris
  `is_current = 1` (invariant sejak v2.78.0). Kolom relevan: `driver_name`,
  `nopol`, `vehicle_type`, `bbm_type`, `is_current`, `assigned_date`,
  `unassigned_date`, `confirmed_by_driver`, `confirmed_at`, `driver_notes`.
- `assignment_swaps`: log eksekusi (`nopol`, `old_driver`, `new_driver`,
  `category`, `reason`, `ga_name`, `created_at`). Tidak punya status pengajuan.
- `drivers.nopol` adalah cache yang **tidak konsisten** dengan
  `vehicle_assignments`; jangan dipakai sebagai sumber kebenaran.
- Endpoint assignment memakai `get_db_connection()` yang merutekan ke DB cabang
  sesuai sesi. `app.py` memanggil `ensure_assignment_tables()` untuk master dan
  setiap cabang aktif saat startup.
- Upload foto memakai `save_file(file, prefix, nopol, upload_folder)`:
  ekstensi di-whitelist, nama dibangkitkan server, disajikan lewat
  `/uploads/<nama>`. Batas unggah global 16 MB.
- `api()` frontend hanya mengirim JSON. Unggah multipart memakai `fetch` +
  `FormData` + header `X-CSRF-Token` (pola `BBMTab.vue`/`TripTab.vue`).
- Notifikasi driver: `push_driver_notification(driver_name, type, action,
  message, ref_id)` (DB + SocketIO + web push). Tidak ada notifikasi per-role
  untuk GA; badge GA akan dihitung dari endpoint daftar.

## 6. Pendekatan yang dipertimbangkan

| Pendekatan | Isi | Trade-off |
|---|---|---|
| **A. Tabel `assignment_swap_requests` baru** (dipilih) | Antrean & status terpisah dari log eksekusi; `assignment_swaps` tetap murni riwayat | Satu tabel + ensure + endpoint baru; kerja sedang, tapi guardrail dan audit paling jelas |
| B. Tambah kolom status ke `assignment_swaps` | Lebih sedikit kode | Riwayat bercampur antrean; sulit menegakkan "satu pengajuan pending per driver"; log eksekusi jadi kotor |
| C. Driver kirim notifikasi/pesan ke GA | Paling murah | Tidak ada persetujuan terstruktur, alasan, bukti, atau jejak; tidak menyelesaikan masalah |

**Dipilih A.** Alasan: pengajuan punya siklus hidup sendiri (pending → approve →
serah terima), sementara `assignment_swaps` adalah fakta yang sudah terjadi. Tabel
terpisah membuat aturan "satu pending per driver" mudah dijaga dan laporan tetap
bersih.

## 7. Keputusan yang sudah disepakati

1. Driver mengajukan; **GA/admin saja** yang menyetujui. Driver tujuan tidak perlu
   menyetujui lebih dulu.
2. Ada dua jenis pengajuan:
   - **tukar** A↔B: A menerima nopol B, B menerima nopol A;
   - **pindah** ke kendaraan kosong: A menerima nopol kosong Y, nopol lama A (X)
     masuk pool tanpa pengemudi.
3. Bukti serah terima: **odometer + foto kendaraan**.
4. Bukti diambil dari sisi **penerima**:
   - tukar: dua kiriman (A dan B, masing-masing untuk kendaraan yang diterima);
   - pindah: satu kiriman (A untuk kendaraan baru), karena tidak ada penerima lain.
   Ini cukup membuktikan kondisi awal di tangan pemegang baru dan jauh lebih ringan
   daripada empat kiriman.
5. Pengajuan wajib punya kategori + alasan (minimal 10 karakter).
6. Pintu masuk fitur ada di **panel Profil** pada header driver, bukan tab
   navigasi baru. Panel menampilkan identitas, kendaraan saat ini, daftar
   **kendaraan kosong**, daftar **kendaraan yang sudah ada driver**, pengajuan
   saya, dan kartu serah terima.

### Panggilan yang saya ambil (bisa dikoreksi saat review)

- Panel **Profil & Kendaraan** dibuka dari blok identitas di header (nama +
  nopol) dan/atau ikon 👤. Empat tab navigasi yang ada tidak berubah.
- Endpoint konteks tunggal `GET /api/assignments/swap-context` mengembalikan
  kendaraan saya, daftar kendaraan kosong, daftar partner, dan pengajuan saya —
  mengurangi bolak-balik.
- `assignment_swaps` diberi kolom `request_id` agar tiap baris log bisa ditelusuri
  ke pengajuan.
- Status tambahan `superseded`: pengajuan yang assignment-nya sudah berubah
  (karena tukar lain, release, atau assign ulang) ditutup otomatis, bukan
  menggantung. Pengajuan seperti ini **tidak** memblokir konfirmasi driver.
- Tukar berantai diperbolehkan, tetapi approve harus menyadari konflik: pengajuan
  lama yang belum serah terima ditutup sebagai `superseded` dengan catatan.
- Finance dapat membaca daftar, tidak dapat approve/reject.
- Waktu unggah: satu foto per driver, tidak ada watermark (berbeda dari BBM).
- Approve berjalan **satu transaksi pada koneksi DB cabang** (assignments,
  drivers, vehicles, swap log, pengajuan). Akun login dicek read-only ke DB
  master lewat `drivers.user_id`.
- Partner harus punya akun login aktif (role `driver`) karena tanpa itu ia tidak
  bisa menyelesaikan serah terima.

## 8. Model data

### 8.1 Tabel baru di `init.sql` + `ensure_assignment_tables`

```sql
CREATE TABLE IF NOT EXISTS assignment_swap_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    request_code VARCHAR(24) DEFAULT NULL,
    branch_code VARCHAR(10) DEFAULT NULL,
    swap_type VARCHAR(10) NOT NULL DEFAULT 'exchange',  -- 'exchange' | 'move'
    requester_driver VARCHAR(100) NOT NULL,
    requester_nopol VARCHAR(20) NOT NULL,       -- kendaraan yang dilepas pengaju
    target_driver VARCHAR(100) DEFAULT NULL,    -- NULL untuk 'move'
    target_nopol VARCHAR(20) NOT NULL,          -- kendaraan yang diterima pengaju
    category VARCHAR(30) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    ga_name VARCHAR(100) DEFAULT NULL,
    ga_note VARCHAR(500) DEFAULT NULL,
    decided_at DATETIME DEFAULT NULL,
    executed_at DATETIME DEFAULT NULL,
    requester_odo INT DEFAULT NULL,
    requester_photo VARCHAR(255) DEFAULT NULL,
    requester_handover_at DATETIME DEFAULT NULL,
    target_odo INT DEFAULT NULL,
    target_photo VARCHAR(255) DEFAULT NULL,
    target_handover_at DATETIME DEFAULT NULL,
    completed_at DATETIME DEFAULT NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_swap_request_code (request_code),
    KEY idx_swap_req_status (status, created_at),
    KEY idx_swap_req_requester (requester_driver, status),
    KEY idx_swap_req_target (target_driver, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
```

`request_code` = `SWR-YYYYMMDD-<id 4 digit>`, diisi setelah INSERT (dalam transaksi
yang sama). Unik, boleh NULL sesaat.

Arti kolom:

- `requester_nopol` selalu kendaraan yang **dilepas** pengaju.
- `target_nopol` selalu kendaraan yang **diterima** pengaju (nopol B untuk
  `exchange`, nopol kosong untuk `move`).
- `target_driver` hanya terisi untuk `exchange`.
- Kolom `target_*` bukti hanya dipakai untuk `exchange`; pada `move` cukup sisi
  `requester_*`.

### 8.2 Perubahan `assignment_swaps`

Tambah `request_id INT DEFAULT NULL` + `KEY idx_swap_request (request_id)`.
`ensure_assignment_tables` menambalnya secara idempoten dengan memeriksa
`information_schema.COLUMNS` lebih dulu (tidak mengandalkan error "duplicate
column"). `init.sql` ikut diperbarui agar `check_schema_drift.py` tetap hijau.

### 8.3 Status

```
pending ──approve──> approved ──(2 bukti)──> completed
   │  │                 │
   │  ├──reject──> rejected
   │  └──cancel──> cancelled
   └──(assignment berubah / tukar lain disetujui)──> superseded
```

- `pending`: menunggu GA.
- `approved`: pertukaran sudah dieksekusi; menunggu bukti satu/dua driver.
- `completed`: kedua bukti masuk.
- `rejected` / `cancelled` / `superseded`: final.

`superseded` diisi otomatis, bukan oleh tombol pengguna:

1. Saat approve pengajuan baru, pengajuan `approved` lain yang melibatkan salah
   satu driver/nopol dan belum lengkap serah terimanya ditutup `superseded`
   dengan catatan "Ditutup karena tukar berikutnya disetujui".
2. Saat alur GA lama (`create`, `swap`, `release`) mengubah assignment yang
   terlibat pengajuan `pending`/`approved`, pengajuan itu ikut ditutup
   `superseded` dengan catatan "Penugasan diubah oleh GA".
3. Saat handover menemukan assignment sudah tidak cocok, pengajuan ditutup
   `superseded` lalu endpoint mengembalikan 409 `state_changed`. Ini jaring
   pengaman terakhir agar tidak ada pengajuan menggantung.

Pengajuan `superseded` tidak pernah memblokir konfirmasi driver. Karena itu,
koreksi GA tidak bisa membuat driver terkunci selamanya.

## 9. API

Semua endpoint baru memakai sesi. Identitas driver **selalu** dari
`resolve_driver_scope('')`, bukan body. Respons memakai pola
`{status: 'success'|'error', msg, ...}`.

| Method & path | Role | Fungsi |
|---|---|---|
| `GET /api/assignments/swap-context` | driver | `{me:{driver,nopol,vehicle_type}, free_vehicles:[{nopol,vehicle_type}], partners:[{driver_name,nopol,vehicle_type}], requests:[...]}`; partner = assignment aktif lain di cabang yang sama yang punya akun login aktif |
| `POST /api/assignments/swap-requests` | driver | Buat pengajuan JSON `{swap_type:'exchange'|'move', target_driver?, target_nopol, category, reason}` |
| `GET /api/assignments/swap-requests?status=` | driver, ga, admin, finance | Driver: hanya yang melibatkan dirinya. Back-office: semua di cabang itu |
| `POST /api/assignments/swap-requests/<id>/cancel` | driver (pengaju) | Batalkan, hanya `pending` |
| `POST /api/assignments/swap-requests/<id>/approve` | ga, admin | Eksekusi tukar, hanya `pending`; bila ada konflik serah terima, wajib `acknowledge_supersede: true` |
| `POST /api/assignments/swap-requests/<id>/reject` | ga, admin | Tolak + `note` wajib, hanya `pending` |
| `POST /api/assignments/swap-requests/<id>/handover` | driver (A/B) | Multipart `{odometer, photo}` untuk sisi driver yang login |

### 9.1 Validasi create

1. Role driver; nama driver dari sesi (`user_name` di-UPPER-kan, sama dengan
   `vehicle_assignments.driver_name`).
2. Punya tepat satu assignment aktif → `requester_nopol` diambil dari DB, bukan
   dari body.
3. `swap_type` ∈ `{exchange, move}`.
4. Untuk **exchange**:
   - `target_driver` ≠ diri sendiri, ada di `drivers` cabang (`is_active=1`), dan
     punya assignment aktif; `target_nopol` diambil dari assignment itu (body
     hanya mengirim nama driver).
   - Kedua driver punya akun login aktif: join `drivers.user_id` ke `users`
     **master**, syarat `role='driver'`, `is_active=1`, dan
     `users.branch_code` = cabang sesi. Tanpa akun, driver tujuan tidak akan bisa
     mengunggah bukti.
5. Untuk **move**:
   - `target_driver` harus kosong/NULL;
   - `target_nopol` wajib ada di `vehicles` cabang dengan `is_active=1`;
   - nopol itu tidak boleh punya assignment aktif (harus benar-benar kosong).
6. Untuk **exchange**, nopol diperiksa secara *advisory* ke `vehicles` cabang:
   bila baris ada dan `is_active=0` → tolak; bila baris tidak ada, izinkan selama
   assignment aktif ada (assignment adalah sumber kebenaran).
7. `category` ∈ `{driver_request, vehicle_issue, mutasi, other}`.
   `reason` setelah `strip()` panjang 10–500.
8. Tidak ada pengajuan `pending` lain yang melibatkan A (dan B untuk exchange),
   baik sebagai pengaju maupun tujuan. Pengajuan `approved` **tidak** memblokir
   pengajuan baru (sesuai keputusan tukar berantai); konfliknya diselesaikan saat
   approve.
9. `requester_nopol != target_nopol`.

Kode error: 400 (validasi), 403 (bukan driver), 409 (duplikat/konflik), 401 (tanpa
sesi).

### 9.2 Approve (atomik)

Semua langkah berjalan pada **satu koneksi DB cabang** dengan `autocommit=False`.
Pengecekan akun login memakai koneksi read-only terpisah ke DB master (lewat
`drivers.user_id`) dan tidak ikut transaksi cabang.

1. Cek role `ga`/`admin`; `ga_name` dari sesi.
2. Cek konflik serah terima lebih dulu: cari pengajuan `approved` lain yang
   melibatkan A (dan B untuk exchange) atau nopol X/Y dan belum lengkap. Bila ada
   dan body tidak mengirim `acknowledge_supersede: true` → 409
   `supersede_required` berisi ringkasan pengajuan lama. Ini yang memunculkan
   peringatan di UI GA.
3. `SELECT ... FOR UPDATE` pengajuan; harus `pending`.
4. Verifikasi pihak yang terlibat masih punya akun login aktif (join
   `drivers.user_id` → `users` master). Untuk `move`, cukup pengaju. Bila tidak →
   409 `state_changed` ("akun driver tidak aktif").
5. Kunci baris aktif yang terlibat:
   - **exchange**: assignment aktif A harus X, assignment aktif B harus Y; tidak
     boleh ada baris aktif lain untuk A/B maupun X/Y.
   - **move**: assignment aktif A harus X; nopol Y tidak boleh punya assignment
     aktif; Y harus ada di `vehicles` dengan `is_active=1`.
   Bila tidak cocok → 409 `state_changed` dengan pesan "Penugasan sudah berubah —
   batalkan pengajuan dan buat ulang."
6. Tutup **semua** baris aktif A (dan B untuk exchange)
   (`is_current=0`, `unassigned_date=CURDATE()`).
7. Insert assignment baru:
   - **exchange**: A→Y dan B→X.
   - **move**: A→Y saja; X tetap tanpa assignment (pool).
   Semua dengan `assigned_date=CURDATE()`, `is_current=1`,
   `confirmed_by_driver=0`, `driver_notes` = alasan pengajuan,
   `vehicle_type`/`bbm_type` dari kendaraan yang diterima.
8. Perbarui cache `drivers` untuk setiap driver yang menerima kendaraan:
   `nopol`, `vehicle_type`, `bbm_type` sesuai kendaraan baru (bukan hanya
   `nopol`). Baris `drivers` wajib ada; bila hilang → 409 `state_changed`.
9. Insert `assignment_swaps` dengan kategori, alasan berawalan `[SWR-...]`,
   `ga_name` penyetuju, dan `request_id`:
   - **exchange**: X: A→B dan Y: B→A.
   - **move**: X: A→`- (Pool)` dan Y: `- (Pool)`→A.
10. Set pengajuan `approved`, `decided_at`, `executed_at`, `ga_name`, dan
    `ga_note` bila ada catatan supersede.
11. Tutup pengajuan lama yang konflik sebagai `superseded` + catatan otomatis.
12. Jalankan pemeriksaan invarian (`_assert_single_active`): untuk himpunan
    driver/nopol yang tersentuh, tidak boleh ada >1 baris `is_current=1`.
    Gagal → rollback.
13. Commit. Gagal di langkah mana pun → rollback, pengajuan tetap `pending`.
14. Setelah commit: notifikasi ke A (dan B untuk exchange) serta pihak pengajuan
    yang di-supersede; catat `log_activity_async`.

`ga_name` diambil dari sesi (`user_name`/`full_name`); body tidak dipercaya.

### 9.3 Handover

1. `SELECT ... FOR UPDATE` pengajuan; harus `approved`.
2. Driver sesi harus pengaju (A) atau, untuk `exchange`, tujuan (B); sisi yang
   bersangkutan masih NULL.
3. Nopol yang diterima: A→`target_nopol`, B→`requester_nopol` (hanya exchange).
   Assignment aktif (driver, nopol itu) harus ada; bila tidak → tutup pengajuan
   sebagai `superseded` (catatan "assignment berubah sebelum serah terima") lalu
   409 `state_changed`.
4. `odometer` bilangan bulat 0–2.000.000; `photo` wajib dan harus lolos
   `save_file(..., 'SWAP', nopol, UPLOAD_FOLDER)`, kalau tidak → 400.
5. Simpan nama file + odometer + waktu ke kolom sisi driver; set
   `vehicle_assignments.confirmed_by_driver=1, confirmed_at=NOW()` untuk assignment
   tersebut.
6. `status='completed'`, `completed_at=NOW()` bila:
   - **exchange**: kedua sisi terisi;
   - **move**: sisi pengaju terisi (tidak ada pihak lain).
7. Commit; bila DB gagal, file yatim dihapus best-effort. Notifikasi: ke rekan
   (kalau masih menunggu) atau ke pengaju (kalau selesai).

Foto disajikan sebagai `/uploads/<nama file>`.

### 9.4 Pencegahan jalur pintas

- `GET /api/assignments/pending` di-LEFT JOIN ke pengajuan `approved` yang
  **masih cocok dengan assignment saat ini**; baris menyertakan
  `handover_request_id` bila driver harus memakai alur bukti.
  Kecocokan: pengaju → `target_nopol`, tujuan (exchange) → `requester_nopol`.
- `POST /api/assignments/confirm` menolak dengan 409
  `{code: 'handover_required'}` hanya bila ada pengajuan `approved` yang
  sisi driver tersebut belum terisi **dan** nopol assignment yang sedang
  dikonfirmasi sama dengan nopol yang ia terima di pengajuan itu.
- Karena pengajuan yang basi sudah berstatus `superseded`, guard ini tidak bisa
  memblokir driver untuk assignment berikutnya. Tidak ada pengajuan yang
  menggantung tanpa jalan keluar.
- `AssignmentsView` menampilkan status "⏳ belum konfirmasi" seperti biasa; hanya
  sumber konfirmasinya yang berubah.

### 9.5 Konkurensi dengan alur GA lama

Alur lama (`create`, `swap`, `release`) saat ini tidak memakai transaksi/lock.
Agar approve tidak berlomba dengan aksi GA dan melanggar invariant satu driver =
satu kendaraan:

- Keempat jalur (create, swap, release, approve) dibungkus transaksi dan mengunci
  baris assignment yang tersentuh dengan `SELECT ... FOR UPDATE`.
- Sebelum commit, `_assert_single_active(cur, drivers, nopols)` memastikan tidak
  ada driver/nopol dengan lebih dari satu baris `is_current=1`; bila gagal →
  rollback dan 409.
- Ketiga jalur lama memanggil `_supersede_requests_for(cur, drivers, nopols)`
  untuk menutup pengajuan `pending`/`approved` yang terlibat.
- Tidak ada unique index parsial di MariaDB; invarian ditegakkan di kode dan
  diuji (termasuk kasus dua approve bersamaan secara berurutan).
- Perubahan ini kecil dan terisolasi di `routes_api_assignments.py`; alur bisnis
  lama tidak berubah selain menjadi lebih aman.

## 10. UI

### 10.1 Driver — panel "Profil & Kendaraan" dari header

Header saat ini sudah menampilkan nama + nopol. Blok identitas itu dijadikan
tombol (dengan indikator 👤/chevron) yang membuka panel; empat tab navigasi tidak
berubah.

```
┌ Profil & Kendaraan ──────────────────────────┐
│ ABiem · SBY                                  │
│ Kendaraan saya: B 1126 DFC · AVANZA          │
│                                              │
│ Ganti Kendaraan                              │
│ Kendaraan kosong (2)                         │
│  L 1906 TF · AVANZA              [Ambil]     │
│  B 2731 SRQ · AVANZA             [Ambil]     │
│ Kendaraan dengan driver (4)                  │
│  RIVAN · L 1415 CBI · AVANZA     [Tukar]     │
│                                              │
│ Pengajuan saya                               │
│  SWR-20261123-0007 · RIVAN · menunggu GA     │
│    "ban depan aus…"                [Batal]   │
│  SWR-20261123-0008 · pindah ke L 1906 TF     │
│    disetujui — isi bukti                     │
│                                              │
│ Serah terima menunggu                        │
│  Anda menerima L 1415 CBI dari RIVAN         │
│  Odometer [ 48210 ]  Foto [Ambil/unggah]     │
│                              [Kirim Bukti]   │
└──────────────────────────────────────────────┘
```

- Tombol **Ambil** (kendaraan kosong) mengirim `swap_type='move'`; tombol
  **Tukar** (kendaraan ber-driver) mengirim `swap_type='exchange'`.
- Keduanya membuka modal kecil: kategori + alasan (≥10 karakter) + tombol
  "Ajukan". Nopol berasal dari baris yang dipilih, bukan diketik bebas.
- `pending`: tombol Batalkan. `approved`: kartu bukti bila sisi saya belum diisi.
  `completed/rejected/cancelled/superseded`: tampil di daftar dengan badge.
- Banner `pendingTask` di `DriverView`: bila `handover_request_id` ada, tombol
  berbunyi "Isi Serah Terima" dan membuka panel profil (tidak memanggil confirm).
- Bila daftar kosong: tampilkan pesan "Tidak ada kendaraan kosong" / "Tidak ada
  rekan dengan kendaraan aktif" agar tidak terlihat rusak.

### 10.2 GA/admin — `AssignmentsView`

- Tab baru "📨 Pengajuan (N)" di antara "Saat Ini" dan "Riwayat Tukar".
- Tabel: waktu, jenis (🔄 tukar / ➡️ pindah), pengaju (A · X), tujuan
  (B · Y untuk tukar, "kosong" untuk pindah), kategori, alasan, status, aksi.
- `pending`: tombol **Setujui** (modal konfirmasi berisi ringkasan + peringatan
  "kedua kendaraan langsung bertukar" untuk exchange, atau "kendaraan lama A
  masuk pool" untuk move) dan **Tolak** (catatan wajib).
- Bila ada pengajuan `approved` lain yang belum serah terima untuk driver/nopol
  yang sama, modal menyebutkannya dan meminta centang "Saya mengerti pengajuan
  lama akan ditutup sebagai kedaluwarsa". Tanpa centang, approve ditolak server
  (409 `supersede_required`).
- `approved`: tampilkan "menunggu serah terima" + bukti yang sudah masuk (odo,
  foto, waktu).
- `completed`: kedua bukti, foto dapat diklik.
- `rejected`: catatan GA. `superseded`: alasan penutupan otomatis.
- Daftar dimuat bersama `load()`; N di badge dihitung dari status `pending`.
  Segarkan otomatis setiap 60 detik selama halaman terbuka, berhenti saat unmount.

## 11. Notifikasi dan audit

| Kejadian | Penerima | Pesan ringkas |
|---|---|---|
| Approve (tukar) | A dan B | "Tukar disetujui: Anda menerima <nopol>. Isi serah terima (odo + foto)." |
| Approve (pindah) | A | "Pindah kendaraan disetujui: Anda menerima <nopol>. Isi serah terima (odo + foto)." |
| Approve menutup pengajuan lama | pihak pengajuan lama | "Pengajuan <kode> ditutup karena tukar berikutnya disetujui." |
| Reject | A | "Pengajuan tukar ditolak: <catatan>" |
| Bukti pertama | rekan yang belum (exchange) | "Rekan sudah mengisi serah terima — lengkapi milik Anda." |
| Bukti kedua / bukti pindah | A dan B (exchange) / A (move) | "Serah terima tukar kendaraan selesai." |

`ref_id` = `request_code`. Audit `log_activity_async`:
`driver_swap_request`, `ga_swap_approve`, `ga_swap_reject`,
`ga_swap_supersede`, `driver_swap_handover`.

## 12. Keamanan dan isolasi

- Identitas dari sesi; field driver di body diabaikan.
- `get_db_connection()` mengikat assignment, `drivers`, `vehicles`, log swap, dan
  pengajuan ke DB cabang sesi. Partner hanya dari DB yang sama, sehingga tidak ada
  tukar lintas cabang.
- Akun login adalah data master: `drivers.user_id` → `users` master. Pengecekan
  akun bersifat read-only dan tidak ikut transaksi cabang. Dengan begitu driver
  cabang tetap memakai akun pusat, tanpa menyalin data akun ke DB cabang.
- Approve tidak pernah menyentuh dua DB secara menulis: seluruh perubahan ada di
  DB cabang, satu transaksi, satu commit.
- CSRF tetap aktif; unggah memakai header `X-CSRF-Token` seperti pola yang ada.
- Foto lewat `save_file`: ekstensi di-whitelist, nama server-side, tidak ada path
  dari pengguna. Batas 16 MB dari konfigurasi global.
- Approve/reject hanya `ga`/`admin`; finance hanya `GET`.
- Satu pending per driver membatasi spam pengajuan.

## 13. Pengujian

Backend (`tests/test_swap_requests_v2132.py`):

- Ensure: kedua tabel dibuat, idempoten, koneksi luar tidak ditutup; kolom
  `request_id` ditambahkan bila belum ada.
- Create: exchange sukses; move sukses; move ke nopol yang masih ber-driver →
  409; move ke kendaraan nonaktif → 400; diri sendiri; target tanpa assignment;
  target tanpa akun login aktif; alasan <10; kategori salah; duplikat pending
  (A atau B); role bukan driver.
- Approve: exchange sukses (2 assignment baru, 2 baris swap ber-`request_id`,
  baris lama tertutup, cache `drivers` nopol+tipe+BBM benar); move sukses
  (1 assignment baru, nopol lama tanpa assignment, 2 baris log X→pool dan
  pool→Y); state berubah → 409; bukan pending → 409; role finance → 403; konflik
  serah terima tanpa `acknowledge_supersede` → 409; dengan centang → pengajuan
  lama `superseded`.
- Reject: tanpa catatan → 400; sukses → status `rejected`.
- Cancel: hanya pengaju, hanya pending.
- Handover: exchange sisi A lalu B → `completed`; move satu bukti → `completed`;
  kirim ganda → 409; driver lain → 403; assignment berubah → 409 + status
  `superseded`; tanpa foto / odo invalid → 400.
- Alur GA lama (`swap`, `release`, `create`) menutup pengajuan terkait sebagai
  `superseded`.
- Invarian: simulasi assignment ganda pada satu driver/nopol membuat transaksi
  rollback dan 409.
- `/api/assignments/pending` menyertakan `handover_request_id` hanya saat nopol
  masih cocok.
- `/api/assignments/confirm` menolak 409 `handover_required` saat cocok, tetapi
  tetap berhasil setelah pengajuan `superseded`.
- `init.sql` memuat tabel + kolom (tes init.sql yang ada ikut menjaga).

Frontend (Vitest):

- `DriverProfileSheet`: panel terbuka dari blok identitas header; menampilkan
  kendaraan kosong + kendaraan ber-driver; tombol Ambil mengirim `move`, tombol
  Tukar mengirim `exchange`; alasan <10 mengunci tombol; unggah `FormData`
  berisi `odometer` + `photo`.
- `AssignmentsView`: tab pengajuan, kolom jenis, badge N, approve/reject memanggil
  endpoint yang benar, dan centang `acknowledge_supersede` terkirim saat ada
  konflik.

Manual smoke (tanpa mengubah produksi): buat pengajuan di cabang uji lalu
batalkan; approve diuji di DB scratch dengan dua driver uji, bukan di produksi.

## 14. Rilis dan rollback

- Versi `v2.132.0` (fitur baru): bump 7 titik stamp + stamp DB, CHANGELOG,
  PROGRESS, USER_LIST/user guide, help content driver.
- Skema aditif: `init.sql`, `ensure_assignment_tables` (master + semua cabang saat
  startup). `check_schema_drift.py` harus hijau untuk master + 11 cabang.
- Tidak ada migrasi data. Data lama tetap valid; `request_id` lama NULL.
- Rollback: hapus tab/endpoint di rilis berikutnya; tabel dan kolom boleh
  dibiarkan (tidak mengganggu alur lama).

## 15. Yang diserahkan ke builder

- Tata letak/CSS detail panel profil di layar kecil, termasuk daftar panjang
  kendaraan (maks tinggi + scroll).
- Pilihan kata pada pesan/notifikasi dan label tombol.
- Interval polling GA (ditetapkan 60 detik; boleh disesuaikan).
- Penanganan file yatim bila commit gagal (best-effort hapus).
- Penulisan tes data uji dan pemilihan nama driver uji di DB scratch.
