# Audit Aplikasi Android BPF Agenda — 19 Nov 2026

Perangkat uji: **Samsung SM-A035F** (Android 13, 720×1600 px, density 300 →
viewport CSS ±384×853 dp), terhubung lewat *wireless debugging*.
Versi diaudit: **1.8.0 (versionCode 10800)** → diperbaiki di **2.0.5
(versionCode 20005)**.

Dokumen ini mencatat temuan, perbaikan, dan bukti uji. Peta distribusi agenda
ada di [`DISTRIBUSI_AGENDA.md`](DISTRIBUSI_AGENDA.md).

---

## 1. Ringkasan

| # | Temuan | Tingkat | Status |
|---|---|---|---|
| 1 | Aplikasi selalu menampilkan **OFFLINE** walau server membalas 200 | **P0** | ✅ diperbaiki (CORS bridge) |
| 2 | Pemeriksaan & unduhan pembaruan tidak pernah berjalan (alasan sama) | **P0** | ✅ diperbaiki (CORS) |
| 2b | Tombol **Unduh & pasang** berakhir "There was a problem parsing the package" — installer tak bisa membaca APK | **P0** | ✅ diperbaiki (URI grant + FileProvider, `bpfBridge` 1.2.1–1.2.2) |
| 2c | Update tetap gagal setelah izin diperbaiki: authority `bpfmedia` ditolak installer | **P0** | ✅ provider kedua dihapus, pakai FileProvider Cordova |
| 2d | Play Protect memblokir APK internal yang belum dikenal Google | **P1** | ⚠️ kebijakan perangkat — butuh Play Protect off / MDM / Play privat |
| 11 | Layar **Ganti kategori** memakai PIN lama: input `maxlength=6` membuat ketikan baru diabaikan | **P1** | ✅ input dibersihkan & difokus ulang |
| 3 | Orientasi dikunci landscape (`Orientation=landscape`, `sensorLandscape`, `lockLandscape()`) | **P1** | ✅ dilepas |
| 4 | Header penuh: logo + nama + status + kategori + 4 tombol ikon; nama aplikasi terpotong di layar sempit | **P1** | ✅ header ringkas + menu ⋯ |
| 5 | Agenda hanya muncul di modal; tidak ada panel agenda tetap, tidak ada tombol "Hari ini" | **P1** | ✅ panel permanen + tombol |
| 6 | Tombol ikon 30×28 dp; sel tanggal tanpa label aksesibilitas | **P2** | ✅ target ≥ 38 dp, `aria-label`, keyboard |
| 7 | Tanggal panjang terpotong elipsis di panel agenda (360 dp & landscape 640 px) | **P2** | ✅ header agenda ditata ulang |
| 8 | Ikon empty-state memakai emoji (tampil beda/kotak di sebagian perangkat) | **P2** | ✅ SVG garis |
| 9 | Layar PIN terpotong di landscape pendek (petunjuk tidak terlihat, tidak bisa scroll) | **P2** | ✅ padding ringkas + scroll |
| 10 | Tidak ada dokumen yang menjelaskan distribusi agenda ke Marketing/BO | **P2** | ✅ `DISTRIBUSI_AGENDA.md` |

---

## 2. Temuan P0 — CORS bridge

### Gejala

- Layar aplikasi menampilkan badge **OFFLINE** terus-menerus.
- Log nginx menunjukkan permintaan **200** dari perangkat:
  `GET /api/state?audience=marketing ... "https://localhost"`.
- Server membalas 200 tanpa `Access-Control-Allow-Origin`.

### Penyebab

WebView Cordova memakai origin `https://localhost`, sedangkan API dilayani
`https://nasbpfsby.duckdns.org:8444`. `fetch()` dan `EventSource` **wajib**
lolos CORS; tanpa header ACAO, respons 200 tetap ditolak browser dan masuk
`catch` → status OFFLINE. Pemeriksaan pembaruan APK memakai `fetch()` yang
sama, jadi ikut gagal tanpa pesan.

### Perbaikan

`modules/bridge_cors.py`:

- `Access-Control-Allow-Origin: *` untuk `/api/state`, `/api/month`,
  `/api/stream`, dan seluruh `/api/app/*`;
- preflight `OPTIONS` → `204`;
- `Access-Control-Expose-Headers` agar aplikasi bisa membaca
  `X-Checksum-SHA256` saat mengunduh APK;
- dipasang dari `register_agenda_routes()` dan
  `register_app_release_routes()`.

Bridge memang publik dan read-only (tanpa cookie), sehingga `*` aman.

### Bukti

```text
$ curl -sk -H 'Origin: https://localhost' -D - -o /dev/null \
    https://nasbpfsby.duckdns.org:8444/api/state
HTTP/1.1 200 OK
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, OPTIONS
Access-Control-Expose-Headers: Content-Length, Content-Range, X-Checksum-SHA256
```

Tes otomatis: `tests/test_agenda.py::test_bridge_cors_untuk_webview` dan
`tests/test_app_release.py::test_cors_untuk_aplikasi_android` (preflight +
unduhan APK).

### 2.2 Pembaruan gagal dipasang dari dalam aplikasi

Setelah CORS beres, banner pembaruan muncul dan unduhan berjalan (SHA-256
cocok), tetapi layar installer berakhir dengan dialog
**"There was a problem parsing the package."** Log sistem menunjukkan:

```text
W InstallStaging: Error staging apk from content URI
W InstallStaging: java.lang.SecurityException: Permission Denial: opening
  provider androidx.core.content.FileProvider from ProcessRecord{... 
  com.google.android.packageinstaller} that is not exported from UID 10493
```

APK-nya sendiri sehat — `adb install -r` pada berkas yang sama berhasil.
Masalahnya izin URI: `FLAG_GRANT_READ_URI_PERMISSION` menempel pada activity
pemanggil (`InstallStart`), lalu dilepas saat activity itu selesai —
`InstallStaging` yang membaca berkas kemudian ditolak.

Perbaikan lapis 1 (`bpfBridge` 1.2.1) di
`apk/bpfBridge-src/src/android/bpf/bridge/BpfBridgePlugin.java`:

- `ClipData` diisi dengan URI APK (sebagian installer hanya membaca grant
  dari sini);
- grant eksplisit `grantUriPermission()` ke paket installer yang bisa
  menangani `ACTION_VIEW` APK, plus daftar cadangan
  (`com.google.android.packageinstaller`, `com.android.packageinstaller`,
  `com.samsung.android.packageinstaller`) karena *package visibility*
  Android 11+ bisa mengosongkan hasil query.

Setelah itu muncul error kedua:

```text
W InstallStaging: java.lang.SecurityException: The authority
  id.co.bpf.calendar.bpfmedia does not match the one of the contentProvider:
  id.co.bpf.calendar.cdv.core.file.provider
```

Penyebabnya manifest memuat **dua** `<provider>` dengan class yang sama
(`androidx.core.content.FileProvider`): provider milik CordovaLib
(`…cdv.core.file.provider`) dan provider buatan kita (`…bpfmedia`). Android
menyimpan satu record provider per *class*, sehingga record yang dipakai
adalah yang pertama terdaftar — authority `bpfmedia` jadi tidak valid.

Perbaikan lapis 2 (`bpfBridge` 1.2.2):

- provider `bpfmedia` dihapus dari `hooks/dynamic-date.js`;
- plugin memakai FileProvider bawaan Cordova
  (`<package>.cdv.core.file.provider`, root `cache/`) — berkas APK memang
  ditulis ke `cache/apk/`, jadi tidak perlu provider sendiri;
- `apk/bpfBridge-src/src/android/res/xml/bpf_file_paths.xml` dihapus.

Bukti: setelah 2.0.5 terpasang, tombol **Unduh & pasang** membuka dialog
sistem **"BPF Agenda — Do you want to update this app?"** (versi 2.0.3 →
2.0.5), artinya APK sudah terbaca dan lolos pemeriksaan paket. Langkah
selanjutnya diblokir Play Protect (lihat 2.3), bukan oleh aplikasi.

### 2.3 Play Protect memblokir APK internal

Saat konfirmasi pemasangan ditekan, Google Play Protect menampilkan
**"App scan recommended"** lalu **"Harmful app blocked — This app may be
harmful"**; sesi installer ditandai
`INSTALL_FAILED_VERIFICATION_FAILURE: Install not allowed` (`Finsky:
VerifyApps: User selected REJECT`).

Ini konsekuensi APK ditandatangani sendiri dan belum dikenal Google, bukan
cacat aplikasi. Pilihan yang realistis:

1. matikan pemindaian Play Protect di perangkat
   (Play Store → Profil → Play Protect → ⚙ → *Scan apps with Play Protect*,
   perlu PIN perangkat) — cocok untuk perangkat kerja terbatas;
2. kelola perangkat lewat MDM/Android Enterprise (Device Owner) yang boleh
   memasang APK internal;
3. terbitkan di jalur privat Google Play (internal testing).

Tanpa salah satu langkah itu, pembaruan tetap bisa dipasang teknisi dengan
`adb install -r`, tetapi tombol di aplikasi akan berhenti di dialog Play
Protect.

---

## 3. Temuan P1 — orientasi & tata letak

### 3.1 Orientasi terkunci

`apk/mobile/config.xml` memaksa `landscape` + `sensorLandscape`, dan
`app.js` memanggil `screen.orientation.lock()`. Akibatnya pengguna tidak bisa
membaca agenda sambil berdiri/memegang ponsel tegak.

Perbaikan:

- `config.xml`: `Orientation=default`, `AndroidWindowOrientation=unspecified`
  → AndroidManifest `screenOrientation=0` (unspecified, diverifikasi dengan
  `aapt2 dump xmltree`).
- `app.js`: `lockLandscape()` dihapus, diganti `unlockOrientation()` yang
  defensif.
- Posisi track kalender dikembalikan ke tengah pada `resize` dan
  `orientationchange`.

### 3.2 Header terlalu padat

Header lama memuat lima kontrol sekaligus; pada 384 dp nama aplikasi
terpotong. Header baru:

- portrait sempit: logo + nama, titik status, chip `BO`/`MKT`, tombol
  "Hari ini" (ikon), menu ⋯;
- layar lebar: teks status dan "Hari ini" ditampilkan penuh;
- kategori, widget, tema, cek pembaruan, dan versi pindah ke menu ⋯.

### 3.3 Panel agenda permanen

Dulu agenda hanya bisa dilihat lewat modal yang menutup kalender. Sekarang:

- **portrait**: kalender di atas, daftar agenda di bawah (bisa digulir);
- **landscape/tablet**: kalender dan agenda berdampingan;
- judul agenda + jumlah agenda selalu terlihat;
- tombol **Hari ini** mengembalikan bulan & tanggal ke hari berjalan.

---

## 4. Temuan P2 — aksesibilitas & detail

- **Target sentuh**: tombol header ≥ 38 dp, sel tanggal ±44 dp pada
  portrait 384 dp, dan area gulir agenda dipisah dari gestur swipe kalender.
- **Label**: setiap sel tanggal punya `aria-label` berisi tanggal lengkap,
  jumlah agenda, dan nama hari libur; sel bisa difokus dan diaktifkan dengan
  Enter/Spasi.
- **Safe area**: padding memakai `env(safe-area-inset-*)` untuk perangkat
  berponi.
- **Gerak**: `prefers-reduced-motion` mematikan animasi geser.
- **Tema**: gelap/terang mengikuti preferensi sistem saat pertama dibuka;
  pilihan pengguna disimpan di `localStorage`.
- **Empty state**: ikon SVG, bukan emoji.
- **PIN kategori**: field dikosongkan dan difokus ulang setiap layar kategori
  dibuka. Sebelumnya PIN lama tertinggal sehingga ketikan baru diabaikan
  `maxlength=6`, dan pengguna mengira PIN-nya salah.

---

## 5. Matriks uji perangkat

| Uji | Portrait (384×853) | Landscape (853×384) |
|---|---|---|
| Kalender tampil penuh (6 baris) | ✅ | ✅ |
| Panel agenda tampil & bisa digulir | ✅ | ✅ |
| Ganti bulan (tombol + swipe) | ✅ | ✅ |
| Pilih tanggal → agenda diperbarui | ✅ | ✅ |
| Tombol "Hari ini" | ✅ | ✅ |
| Menu ⋯ (kategori/tema/widget/pembaruan) | ✅ | ✅ |
| Layar PIN muat tanpa terpotong | ✅ | ✅ |
| Rotasi tanpa kehilangan posisi bulan | ✅ | ✅ |
| Status Live (SSE) / fallback polling | ✅ | ✅ |
| Unduh & pasang pembaruan dari aplikasi | ✅ sampai dialog pemasangan* | — |

\* APK terunduh, SHA-256 cocok, dan dialog pemasangan sistem muncul. Penekanan
"Update" pada perangkat uji ini diblokir Play Protect (temuan 2d); di
perangkat dengan Play Protect nonaktif / MDM alurnya selesai.

Catatan: angka di atas diverifikasi pada perangkat uji (versi 2.0.5);
tangkapan layar disimpan saat audit dan tidak di-commit (berisi data
operasional).

---

## 6. Rekomendasi lanjutan (belum dikerjakan)

1. **Agenda `audience=roles` belum sampai ke APK.** Bridge hanya menerima
   `marketing`/`backoffice`. Bila agenda finance/GA harus tampil di HP,
   tambahkan parameter role atau login ringan.
2. **`backoffice` = semua non-marketing** (termasuk driver/OB/security).
   Perlu keputusan apakah akan dipecah menjadi `bo_staff`.
3. **APK membaca semua cabang.** Agenda khusus cabang lain ikut terlihat;
   dedupe `batch_id` hanya mencegah duplikat. Bila perlu, tambahkan pemilih
   cabang di layar PIN.
4. **PIN bukan keamanan.** Siapa pun bisa memanggil bridge; jangan taruh
   agenda rahasia di sana.
5. **Update tetap butuh konfirmasi Android** (izin "Pasang aplikasi tak
   dikenal" per aplikasi). Untuk update senyap perlu MDM/Device Owner.
6. **Pengingat hari-H** hanya muncul saat dashboard/APK dibuka; belum ada
   push background.
