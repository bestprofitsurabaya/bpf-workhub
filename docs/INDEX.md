# 📚 INDEX — Dokumentasi BPF WorkHub

Rak buku dokumentasi. Pilih lorong sesuai peranmu — tiap dokumen punya pembaca yang jelas. Dokumen yang sudah usang dipindah ke bagian arsip atau ditandai *snapshot*; jangan dijadikan acuan untuk pengambilan keputusan sekarang.

Terakhir dirapikan: **12 November 2026** (era v2.84.0). Dokumen inti yang sudah dikroscek ulang ke server: `README.md` dan `docs/DEVELOPER.md`.

---

## 🧭 Mulai dari sini

| Kalau kamu… | Baca |
|---|---|
| Baru pertama kali dengar aplikasi ini | [README.md](../README.md) *(inti repo)* |
| Harus memakai aplikasi besok pagi | [Panduan Pengguna](../guides/USER_GUIDE.md) → langsung ke bab peranmu |
| Ditunjuk memanggulkan server | [DEPLOYMENT.md](internal/DEPLOYMENT.md) lalu [DEVELOPER.md](DEVELOPER.md) |
| Akan mengembangkan fitur baru | [DEVELOPER.md](DEVELOPER.md) → lalu isi [PROGRESS.md](internal/PROGRESS.md) |
| Perlu men-demo-kan ke manajemen | [PRESENTASI.md](public/PRESENTASI.md) + [One-pager](public/ONEPAGER.md) |

---

## 📖 Untuk pengguna (operasional harian)

| Dokumen | Status | Isinya |
|---|---|---|
| [`guides/USER_GUIDE.md`](../guides/USER_GUIDE.md) | ✅ Aktif (di-stamp tiap rilis) | Panduan langkah demi langkah per peran — OB, Driver, GA, Finance, dst., tanpa istilah teknis |
| [`docs/public/PELATIHAN.md`](public/PELATIHAN.md) | ✅ Aktif | Lembar latihan mandiri 5–10 menit per peran, pas sebelum demo |

## 🎤 Untuk presentasi / manajemen

| Dokumen | Status | Isinya |
|---|---|---|
| [`docs/public/ONEPAGER.md`](public/ONEPAGER.md) | ✅ Aktif | Ringkasan satu halaman untuk dibagikan |
| [`docs/public/PRESENTASI.md`](public/PRESENTASI.md) | ⚠️ Konten v2.40.3 | Skenario demo lengkap (poin bicara, layar, kalimat kunci). *Struktur masih bagus; perbarui cuplikan versi sebelum tampil di hadapan audiens berikutnya.* |
| [`presentasi/`](../presentasi/) | ✅ Aktif | Asset presentasi: `BPF_WorkHub_Presentasi.pptx/.pdf`, badge, video |

## 🚀 Untuk IT & keamanan (kepatuhan)

| Dokumen | Status | Isinya |
|---|---|---|
| [`docs/internal/DEPLOYMENT.md`](internal/DEPLOYMENT.md) | ✅ Aktif | Pasang, update, backup, HTTPS, troubleshooting |
| [`docs/internal/DEPLOY_FRESH.md`](internal/DEPLOY_FRESH.md) | ✅ Aktif | Server kosong → aplikasi jalan |
| [`docs/internal/SECURITY.md`](internal/SECURITY.md) | ✅ Aktif | Program ISO 27001 & ISO 9001: klausul dan penerapannya |
| [`docs/internal/RETENTION_POLICY.md`](internal/RETENTION_POLICY.md) | ✅ Aktif | Masa simpan & pemusnahan tiap kelas dokumen (ISO 15489 · UU PDP) |
| [`docs/internal/INCIDENT_RUNBOOK.md`](internal/INCIDENT_RUNBOOK.md) | ✅ Aktif | Langkah darurat saat kejadian keamanan (A.5.24–28) |
| [`docs/internal/USER_LIST.md`](internal/USER_LIST.md) | ✅ Aktif (di-stamp tiap rilis) | Semua role + konvensi nama akun per cabang |

## 🧭 Untuk developer (perjalanan & rekaman)

| Dokumen | Status | Isinya |
|---|---|---|
| [`CHANGELOG.md`](../CHANGELOG.md) | ✅ Aktif (di-stamp tiap rilis) | Riwayat perubahan per versi — ditulis untuk manusia |
| [`docs/DEVELOPER.md`](DEVELOPER.md) | ✅ Aktif — dikroscek 3 Nov 2026 | Arsitektur, peta DB, alur OTP, deploy, backup — untuk IT/developer |
| [`docs/internal/PROGRESS.md`](internal/PROGRESS.md) | ✅ Aktif | Status roadmap + catatan sesi + rekomendasi langkah berikutnya |
| `docs/internal/arsip_2025Q4/` | 📦 Arsip | Empat dokumen migrasi worker & integrasi LLM (Ox Alpha) era Q4 2025 — referensi historis |

## 🔎 Snapshot audit (titik waktu — jangan dijadikan acuan kondisi hari ini)

Hasil pemeriksaan tertanggal; masih bagus sebagai landasan kenapa suatu keputusan diambil. Status "selesai" tiap temuan selalu lebih akurat dilihat dari `CHANGELOG.md` atau `tests/` dengan nama serupa.

| Dokumen | Snapshot |
|---|---|
| [`AUDIT_PENTEST_20261026.md`](internal/AUDIT_PENTEST_20261026.md) | 26 Okt 2026 — hardening pentest (lihat `tests/test_pentest_hardening_v274.py`) |
| [`AUDIT_FITUR_TERBENAM_20261026.md`](internal/AUDIT_FITUR_TERBENAM_20261026.md) | 26 Okt 2026 — fitur yang tersembunyi & rencananya |
| [`AUDIT_PDF_BBM_20261026.md`](internal/AUDIT_PDF_BBM_20261026.md) | 26 Okt 2026 — mesin PDF klaim BBM |
| [`AUDIT_UI_FINANCE_20261028.md`](internal/AUDIT_UI_FINANCE_20261028.md) | 28 Okt 2026 — perbaikan UI finance (lihat `tests/test_finance_ui_audit_v275.py`) |
| [`AUDIT_FIRSTWORK_BRANCH_20261111.md`](internal/AUDIT_FIRSTWORK_BRANCH_20261111.md) | 11 Nov 2026 — isolasi cabang & perlindungan data pribadi FirstWork (lihat `tests/test_first_work_isolation.py`) |
| [`USABILITY_TEST_P5.md`](internal/USABILITY_TEST_P5.md) | Catatan sesi usability P5 |
| [`RECEPTIONIST_EVENT_LEDGER_PLAN.md`](internal/RECEPTIONIST_EVENT_LEDGER_PLAN.md) | Rencana event ledger receptionist |

---

## 🧹 Aturan main dokumentasi

1. **Satu dokumen, satu pembaca.** Panduan user tidak campur detail server; DEVELOPER tidak mengulang materi UI.
2. **Angka versi tinggal di CHANGELOG.** Fitur diceritakan sebagaimana adanya; kalau penting menyebut sejak kapan, maksimal satu kali.
3. **Stamp versi 7 titik** memaksa dokumen kunci ikut ter-update tiap rilis — jangan loloskan.
4. **Snapshot audit diberi tanggal di nama file** dan tidak diubah isinya; keputusan baru menimpanya lewat CHANGELOG/PROGRESS.
5. Dokumen inti (`README`, `DEVELOPER`, `INDEX`) **dikroscek kembali ke server** tiap perubahan arsitektur besar — cara terbaik mencegah dokumen membusuk lagi.
