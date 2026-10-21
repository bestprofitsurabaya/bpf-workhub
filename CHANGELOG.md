# 📋 Changelog — BPF WorkHub

Riwayat perubahan BPF WorkHub. Ditulis untuk manusia, bukan untuk robot.

> Dokumen ini direkonstruksi (12 Okt 2026) setelah isi historisnya hilang
> saat pengeditan massal — ringkasan di bawah disarikan dari commit log
> `git log` yang tetap utuh. Lihat `git log --oneline` untuk rincian
---

## v2.48.0 — 21 Oktober 2026 (PWA Mobile: Driver, OB & Security)

**Fitur baru** — aplikasi **PWA mobile** di `/m/` (satu shell, otomatis deteksi role
driver / ob / security setelah login PIN). Sumber: `mobile/` (bind-mount
`./mobile:/app/mobile:ro` — edit statik tanpa rebuild image; route Python
`/m/` di `modules/routes_spa.py`).

- **Driver** (5 tab): BBM (foto ODO/struk, harga dari server, GPS + reverse
  geocode Nominatim), Trip (multi-rute + muat appointment hari ini), Overtime
  Driver (foto mulai/selesai base64 + GPS), Kasbon (pengajuan & daftar LPJ →
  isi LPJ lewat tab BBM), Rapor (feedback).
- **OB & Security**: submit overtime (nama & posisi diambil dari sesi server,
  foto mulai wajib, GPS) + riwayat sendiri (`/api/overtime/mine`).
- **Offline queue** di localStorage: BBM/TRIP/OVERTIME antre saat offline dan
  dikirim ulang otomatis saat kembali online (mirip perilaku SPA).
- **Service worker** (`/m/sw.js`): app shell cache-first, `/api/` & Nominatim
  selalu network; manifest standalone + ikon maskable 192/512.
- Keamanan tetap di server: sesi + `X-CSRF-Token`, validasi & harga BBM dari
  `vehicle_fuel_prices`, identitas driver dari sesi (bukan body).
- Diverifikasi E2E dari NAS (21 Okt): login driver `wicak` & OB `ob_febri_sby`
  sukses, endpoint yang dipakai app semua 200, portal `/app/` tidak ada regresi,
  `pytest tests/test_driver_session.py tests/test_driver_context.py` 12 passed.

## v2.47.0 — 16 Oktober 2026 (PDF Kit: kompres PDF untuk IT + daftar lindungi otomatis)

**Fitur baru** — halaman **📄 PDF Kit** (`/app/pdfkit`, menu sidebar IT) untuk role IT
cabang (`it_sby` … `it_lpg`) + admin.

- **Enam mode kompresi**: `lossless` (qpdf — struktur & stream dirapikan; teks, tautan,
  dan gambar asli tidak disentuh), `ringan` 150 dpi, `sedang` 120 dpi, `kuat` 100 dpi,
  `maksimal` 72 dpi + JPEG (Ghostscript `pdfwrite`), dan `target` (rantai otomatis
  lossless → ringan → kuat → maksimal yang **berhenti begitu target ukuran tercapai**).
  Pada semua mode Ghostscript teks & vektor tetap teks sehingga masih bisa dicari.
- **Daftar lindungi otomatis** — berkas yang sha256-nya terdaftar di
  `document_registry` (dokumen terbitan aplikasi: kuitansi air minum, laporan overtime,
  laporan in-out) **dilewati** karena mengompresnya mematahkan verifikasi keaslian
  `POST /api/documents/verify`. PDF **bertanda tangan digital** (`pdfsig`) dan
  **terenkripsi** (`pdfinfo`) juga tidak diproses. Statusnya tampil sebagai
  🛡️ *Dilindungi* / ➖ *Dilewati* beserta alasannya — jadi dokumen yang tidak boleh
  dikompres ditolak sistem, bukan bergantung kedisiplinan operator.
- **Berkas asli tidak pernah ditimpa**: hasil selalu berkas baru `*_kompres.pdf`.
  Hasil yang tidak menyusut ≥2% dibuang dan ditandai "sudah optimal" supaya IT tidak
  mengunduh berkas sia-sia. Tiap berkas dilaporkan: jumlah halaman, ukuran sebelum →
  sesudah, persen hemat, mode yang dipakai, dan apakah teks masih bisa diekstrak.
- **REST**: `GET /api/pdfkit/modes`, `POST /api/pdfkit/jobs` (multipart 1–10 berkas,
  maks 100 MB/berkas & 250 MB sekali submit), `GET /api/pdfkit/jobs`,
  `GET/DELETE /api/pdfkit/jobs/<id>`, `POST /api/pdfkit/jobs/<id>/cancel`,
  `GET /api/pdfkit/download/<job_id>/<file>` (path-guard + hanya milik job). Job
  memakai registry in-memory pola Transcoder, antrean `MAX_CONCURRENT=1` (Ghostscript
  haus RAM), hasil di `data/transcoder/pdfkit/` (volume persisten, retensi 48 jam).
- **Laporan pemakaian** — panel **📄 Pemakaian PDF Kit** di halaman **Audit Log**: per user
  menampilkan jumlah job, berkas, byte sebelum → sesudah, byte & persen yang dihemat,
  lengkap dengan filter tanggal & cabang. Sumbernya `activity_logs` (`pdfkit_submit` dari
  route + `pdfkit_done` yang ditulis worker saat job selesai), jadi angkanya tetap ada
  walau berkas hasil sudah kedaluwarsa (retensi 48 jam). Endpoint: `GET /api/pdfkit/report`.
  Submit & selesai memakai **identitas yang sama** (nama lengkap user, cadangan username)
  supaya satu orang tidak terpecah jadi dua baris di laporan.
- **Dependensi image**: `ghostscript` + `qpdf` ditambahkan di Dockerfile; `poppler-utils`
  yang sudah terpasang dipakai untuk `pdfinfo`/`pdfsig`/`pdftotext` (deteksi sifat PDF).
- `modules/doc_integrity.py`: fungsi baru **`lookup_sha256()`** (cari registri dari hash
  tanpa memuat isi PDF) — dipakai PDF Kit, dan `lookup_pdf()` kini memakainya juga.
- **Uji**: 36 pytest (`tests/test_pdfkit.py` — helper, guard, API, logika rantai target,
  agregasi laporan, kompresi nyata gs/qpdf) + vitest (`PdfKitView.test.js`, `LogsView.test.js`)
  lulus; uji nyata: PDF scan 240 dpi 1,7 MB → 121 KB (maksimal), teks tetap terekstrak.
  Fixture autouse menambal `log_activity_async` sehingga menjalankan suite **tidak** menulis
  jejak uji ke `activity_logs` produksi.

---

## v2.46.5 — 30 September 2026 (Scraper: template meta description & SEO title + skrip WP-CLI konversi artikel lama)

- **Template meta Rank Math** — dua field baru di panel upload: template
  *meta description* (`rank_math_description`, dipotong 160 karakter) dan
  *SEO title* (`rank_math_title`, dipotong 60 karakter). Placeholder:
  `{judul}`, `{kategori}`, `{sumber}`, `{tanggal}`. Kosong = Rank Math
  memakai default (judul post / excerpt).
- Meta description & title juga ikut terkirim saat **update** artikel
  duplikat (dulu hanya focus keyword yang diteruskan).
- **Skrip WP-CLI** `tools/wp-cli/convert-classic-to-blocks.php` — konversi
  massal artikel lama classic → blok (mekanisme identik tombol "Convert
  to blocks", via filter `rest_pre_insert_post` → `do_blocks()`), dengan
  dry-run default, gerbang verifikasi konten (HTML asli harus utuh),
  opsi `--post_type/--limit/--offset/--search/--ids/--force`. Scraper
  sejak v2.46.4 memancarkan blok langsung — skrip ini hanya untuk stok
  artikel lama.
- Test: +1 pytest (template meta) → 70 lulus; 12 vitest lulus.

---

## v2.46.4 — 30 September 2026 (Scraper: artikel Gutenberg-ready + fokus keyword Rank Math)

**Masalah:** artikel hasil scraper terbit sebagai HTML polos tanpa komentar
blok `<!-- wp:... -->` → WordPress menganggap seluruh artikel SATU blok
Classic → tata letak terlihat rusak di editor, dan normal kembali hanya
setelah redaksi menekan "Convert to blocks" manual satu per satu.

- **`wp_block()`** — helper baru di `seo_optimizer` yang membungkus segmen
  HTML dalam komentar blok inti yang sesuai: `<p>` → `wp:paragraph`,
  `<h1>`–`<h6>` → `wp:heading` (+ atribut level), `<figure>` ber-`<img>` →
  `wp:image`, `ul/ol` → `wp:list`, `blockquote` → `wp:quote`, sisanya
  (div styling, `<script>` progress bar, CTA) → `wp:html`.
- **`build_article_html()`** kini memancarkan rangkaian blok per segmen:
  header meta, daftar isi, tiap paragraf/H2, disclaimer, dan blok script
  — semua blok valid dan berpasangan, tidak perlu "Convert to blocks"
  lagi. Efek samping: `<script>` tak lagi mengotori meta description
  Rank Math di editor (hanya di blok Custom HTML).
- **Featured image, tautan sumber, dan CTA** di `routes.py` ikut dibungkus
  blok — penyisipan sumber tak lagi memenggal blok lewat penggantian
  marker di tengah blok lain.
- **Truncation konten >120 KB** kini memotong pada batas blok (baris
  kosong) — dulu bisa meninggalkan blok tanpa penutup (error validasi).
- **Rank Math SEO** — post kini mengirim `meta.rank_math_focus_keyword`
  (diturunkan otomatis dari judul, maks 4 kata bermakna) via REST API
  yang sama. Toggle "🎯 Keyword Rank Math" di panel upload (default ON,
  tersimpan di settings). Bila plugin tidak aktif (WP membalas
  `rest_invalid_param`) upload otomatis diulang tanpa meta — artikel
  tetap terbit.
- Test: +23 pytest (blok Gutenberg, pasangan komentar, derivasi keyword,
  meta & fallback e2e) → 69 pytest scraper lulus; 12 vitest ItEfView lulus.

---

## v2.46.3 — 30 September 2026 (Transcoder: auto-delete salinan share publik — retensi cermin)

- Hasil job yang di-*cleanup* (usia >48 jam, atau job dihapus kapan pun)
  ikut menghapus foldernya di share publik Nextcloud — tautan unduh
  publik mati bersamaan dengan hasil lokal, tidak ada berkas yatim.
- `ncshare.delete_folder(job_id)` (best-effort): gagal jaringan/izin tidak
  menggagalkan pembersihan lokal; status `purged`/`purge_detail`
  tercatat di detail job untuk inspeksi.
- Test: +2 pytest (purge sukses & purge gagal tidak menggagalkan hapus job).

---

## v2.46.2 — 30 September 2026 (Transcoder: tautan unduh publik via share Nextcloud)

**Masalah:** tautan unduhan hasil transcode terikat login WorkHub — tidak
bisa dibagikan ke pihak luar (mis. vendor, tim konten) tanpa memberi
akun.

- Panel **share publik** di UI Transcoder (khusus admin): tempel URL
  Nextcloud share `https://…/index.php/s/<token>` + password →
  `POST /api/transcoder/ncshare`; tersimpan di
  `data/transcoder/nc_share.json` (volume persisten). Password tidak
  dikirim balik ke browser (hanya flag `password_set`).
- **Unggah otomatis** — saat job selesai, setiap hasil langsung diunggah
  ke folder share Nextcloud (best-effort: gagal jaringan tidak
  menggagalkan job). URL publik tersedia via tombol "Tautan publik"
  (`GET /api/transcoder/jobs/<id>/public-links`).
- Test: +8 pytest (config share, unggah, public-links, unconfigured).

---

## v2.46.1 — Desember 2026 (Transcoder: polling adaptif tab hidden + AbortController)

- Polling progres job berhenti saat tab dokumen *hidden*
  (`document.visibilitychange`) — hemat request di latar belakang.
- `AbortController` membatalkan fetch in-flight saat komponen unmount
  (hilang warning setState-unmounted).
- Test: 12 vitest TranscoderView lulus.

---

## v2.46.0 — 26 September 2026 (Transcoder: konversi link YouTube multi-format untuk role IT)

Fitur baru untuk role IT cabang (`it_sby` … `it_lpg`) + admin: konversi link
YouTube ke berbagai format audio/video.

- **Engine** `modules/transcoder/` — job manager in-memory thread-safe
  (pola news_scraper): tiap job = worker daemon (unduh yt-dlp → transcode
  ffmpeg), antrean `MAX_CONCURRENT=1` (server 3.8GB). Progres streaming
  via `-progress pipe:1` + `--newline`.
- **Format output**: mp3 (192k), m4a (128k), wav, mp4 720p, mp4 1080p,
  webm (VP9 + Opus, cpu-used 8 utk CPU lemah), mkv (stream copy).
- **REST API** (ber-session + CSRF): submit 1–10 link sekali submit
  (multi-link, strip duplikat, validasi URL YouTube), daftar job (milik
  user; admin semua), polling detail, cancel, delete (hapus hasil),
  unduh hasil (auth + path-guard + batas ekstensi).
- **Hasil disimpan** di `data/transcoder/` (volume `./data`),
  retensi 48 jam lalu auto-cleanup; nama file di-sanitize (anti
  traversal).
- **Docker**: ffmpeg & ffprobe via apt di Dockerfile; RAM limit web
  dinaikkan 1g → 1536m; volume `./data/transcoder`.
- **UI** `TranscoderView.vue`: form submit multi-link + pilih format,
  daftar job + progres per item realtime (polling 2s), cancel/delete,
  unduh hasil. Menu sidebar 🎬 di `AppLayout`, route `/transcoder`
  role IT + admin only.
- Test: 36 pytest transcoder lulus (lifecycle, antrean, cancel, unduh,
  path-traversal, ncshare); 12 vitest TranscoderView lulus.

---

## v2.45.3 — detail lengkap lihat `git show <commit>` (Scraper: cron auto-scrape aktif ulang dgn filter usia)

- Cron auto-scrape (jam 6,10,14,18 WIB) kini hanya meng-upload artikel
  maksimal `AUTO_SCRAPE_MAX_AGE_DAYS` hari (default 1) sehingga backlog
  lama tidak pernah diterjunkan ke site — pelajaran dari rollback batch
  278 artikel backdate di v2.45.2.
- Mode uji: `--dry-run` di `scripts/auto_scrape.py`.

---

## v2.45.2 (Scraper: cron auto-scrape dimatikan sementara)

- Batch catch-up 278 artikel backdate ter-rollback; cron dinonaktifkan
  sampai filter usia siap (aktif kembali di v2.45.3).

---

## v2.45.1 (Docker: cron auto-scrape — wrapper ekspor PATH)

- `python3: not found` di log cron: PATH default cron tanpa
  `/usr/local/bin` → wrapper `auto_scrape.sh` kini mengekspor PATH.

---

## v2.45.0 (Scraper: auto-scrape cron 6,10,14,18 WIB)

- Cron di image: `scripts/auto_scrape.sh` → scrape + upload terjadwal ke
  site cabang; log `data/news_scraper/auto_scrape.log`.

---

## v2.44.0 — Frontend polish & pembersihan

- Telemeetri in-out (v2.41–v2.44): mode **hybrid** (catat manual + impor
  sheet) vs **sheet** (read-only) via `system_config.inout_mode` — UI
  menyesuaikan tombol sort & input; sinkronisasi manual dari sheet
  dipicu tombol "Sinkron" (refresh roster + last_sync).
- Regresi v2.46.6 (12 Okt 2026): mode dibaca SETELAH `conn.close()`
  sehingga nilai selalu fallback 'hybrid' — fix baca selagi koneksi
  hidup + 3 pytest regresi tersendiri (`test_receptionist_inout.py`).

---

> Catatan rekonstruksi: entri v2.46.5 turun (historis) disarikan dari
> commit log `git log --grep 'v2.4'` — rincian penuh tiap versi lihat
> `git show <hash>`.

---

## v2.41.0 — In-Out Karyawan (receptionist)

Fitur pencatatan kehadiran in-out karyawan di meja resepsionis:

- Roster karyawan aktif dengan status datang/pergi hari ini,
  pencatatan keluar/masuk sekali klik, rekap harian.
- Sinkronisasi dari data sheet (impor massal) + pencatatan manual
  (hybrid) — mode dibaca dari `system_config`.
- Route: `/inout` (role receptionist/admin) di dashboard resepsionis.
- Test: pytest `test_receptionist_inout.py` (schema, mode, roster,
  stats); vitest `EmployeeInOutView`.
