# Rencana Implementasi — Portal Rekrutmen Elegan (v2.135.8)

**Tanggal:** 26 November 2026
**Spec:** `docs/superpowers/specs/2026-11-26-portal-rekrutmen-elegan-design.md`
**Cakupan:** hanya `frontend/src/views/RecruitmentPortalView.vue` (+ tes dan rilis).

## Prinsip

- Tidak ada perubahan backend, API, token, skema, atau aturan tahap.
- Tidak menambah library/komponen baru. Plugin tambahan tidak diperlukan.
- Semua kait tes lama dipertahankan agar regresi perilaku tertangkap.

## Task 1 — Kunci struktur baru lewat tes

**Berkas:** `frontend/src/views/RecruitmentPortalView.test.js`

Tambahkan satu blok tes "tampilan institusi" yang memeriksa:

1. Bilah merek memuat logo resmi (`img[alt=""]` dengan `src="/static/bpf-logo.png"`)
   dan teks "PT Bestprofit Futures".
2. Ada penanda kepercayaan "Data pribadi dilindungi" dan "Cukup NIK 16 digit".
3. Wadah langkah memakai kelas `rp-steps` (daftar vertikal), bukan grid kartu.
4. Baris langkah berikutnya punya kelas `rp-card--next` saat lookup
   mengembalikan `next_action`.
5. Catatan privasi NIK tetap tampil.

Jalankan:

```bash
cd frontend && npx vitest run src/views/RecruitmentPortalView.test.js
```

Tes baru harus GAGAL sebelum komponen diubah (bukti tes benar-benar menguji).

## Task 2 — Tulis ulang template

**Berkas:** `frontend/src/views/RecruitmentPortalView.vue`

Struktur:

```
main.rp-page
  div.rp-shell
    header.rp-brandbar
      img.rp-logo src=/static/bpf-logo.png
      div.rp-brand-text  (b: PT Bestprofit Futures, span: Portal Rekrutmen)
      span.rp-brand-tag  (Portal Rekrutmen)
    section.rp-hero
      p.rp-eyebrow REKRUTMEN KARYAWAN
      h1 Pantau proses rekrutmen Anda
      p.rp-lede ...
      ul.rp-trust (2 item dengan ikon SVG garis)
    form.rp-check  (id/label/input/button/error/privacy dipertahankan)
    section.rp-greeting (nama tersamar + langkah berikutnya)
    section.rp-steps aria-label="Langkah rekrutmen"
      component.rp-card ... (satu baris per tahap)
        span.rp-node (nomor atau centang)
        div.rp-card-body
          div.rp-card-head (judul + badge status)
          p.rp-card-desc
          p.rp-lock-hint / p.rp-summary / p.rp-open
          details.rp-details[data-expand]
        span.rp-chevron (panah, hanya bila bisa dibuka)
    RecruitmentTkdPanel
```

Kait yang WAJIB tetap ada:

- `form.rp-check`, `input[aria-label="NIK 16 digit"]`, `#rp-nik`
- `.rp-card[data-step]`, `data-locked`, `data-status`
- `href` pada kartu yang bisa dibuka; `DIV` untuk selesai; `BUTTON` untuk TKD
- `.rp-card--done`, teks `✓ Selesai`, `Lengkapi CV Online terlebih dahulu.`,
  `Buka tes →`, `Langkah berikutnya: ...`, `Lihat keterangan`,
  `Data tersimpan pada`, `tidak perlu diulang`
- urutan `.rp-card`: CV, TRAINING, TKD, FIRSTWORK

Perubahan teks yang diizinkan: judul hero, deskripsi tahap, label tombol
tetap "Cek Status" / "Mengecek…". Semua bahasa Indonesia.

## Task 3 — Tulis ulang gaya (scoped)

Token di `.rp-page`:

| Token | Nilai |
|---|---|
| `--rp-ink` | `#0B1F3A` |
| `--rp-ink-2` | `#334155` |
| `--rp-muted` | `#64748B` |
| `--rp-bg` | `#F4F6F8` |
| `--rp-paper` | `#FFFFFF` |
| `--rp-line` | `#DCE3EA` |
| `--rp-accent` | `#B3122E` |
| `--rp-accent-soft` | `#FBEAEC` |
| `--rp-success` | `#166534` |
| `--rp-focus` | `#1E4E8C` |

Aturan:

- `.rp-page` memakai latar `--rp-bg`, `min-height: 100vh`, font Inter/system.
- Lebar isi 760 px, padding 24 px; di HP 16 px.
- Bilah merek putih dengan garis bawah rambut; logo tinggi 30 px.
- Tombol utama navy penuh (di HP selebar panel), radius 6 px, min-height 48 px.
- Baris langkah: garis rambut, radius 8 px, tanpa bayangan; baris aktif
  berlatar `--rp-accent-soft` + garis kiri 3 px `--rp-accent`; baris selesai
  diredupkan tetapi teks tetap ≥4.5:1; baris terkunci latar `#F7F9FB`.
- Fokus keyboard: `outline: 2px solid var(--rp-focus); outline-offset: 2px`.
- Transisi 160 ms `ease-out`; hormati `prefers-reduced-motion: reduce`.
- Tanpa emoji di UI baru; centang memakai teks `✓` yang sudah diuji.

## Task 4 — Verifikasi

```bash
cd frontend
npx vitest run src/views/RecruitmentPortalView.test.js
npx vitest run
npm run build
```

Pemeriksaan manual pratinjau: 390 px dan 1280 px, tanpa gulir horizontal,
target sentuh ≥44 px, Tab melalui input → tombol → baris tahap.

## Task 5 — Rilis v2.135.8

1. `CHANGELOG.md` — entri v2.135.8.
2. `modules/company_identity.py`, `frontend/src/stores/identity.js`,
   `frontend/public/sw.js`, `modules/pdf_generator.py` — versi.
3. `docs/internal/PROGRESS.md` — ringkasan.
4. Panduan HTML + PDF `Panduan-Rekrutmen-WorkHub-v2.135.8.pdf`.
5. Commit, push GitHub, `git pull` di NAS, `docker compose up -d --build web`.
6. Verifikasi health (`repo_version = running_version = v2.135.8`,
   `stale=false`), service worker cache, dan halaman portal 200.

## Risiko

- **DOM berubah** → seluruh tes portal harus lulus tanpa mengubah ekspektasi
  perilaku; hanya tes struktur baru yang ditambahkan.
- **Kontras** → periksa pasangan teks/latar; jangan memakai abu < `#64748B`
  untuk teks isi.
- **Logo lebar** → batasi tinggi dan `object-fit: contain`.
