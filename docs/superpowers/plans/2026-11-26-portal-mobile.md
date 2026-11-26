# Portal Rekrutmen Mobile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kartu portal rekrutmen ringkas di HP dengan expand untuk pesan lengkap, urutan tahap tetap, dan tahap selesai tetap tidak bisa diulang.

**Architecture:** Perubahan UI murni di `RecruitmentPortalView.vue`: state `expanded`, ringkasan satu baris, tombol expand dengan `aria-expanded`, CSS media query < 640 px. Kontrak API tidak berubah.

**Tech Stack:** Vue 3 + Vitest + CSS media query.

**Spec:** `docs/superpowers/specs/2026-11-26-portal-mobile-design.md`

## Global Constraints

- Urutan kartu tetap `CV, TRAINING, TKD, FIRSTWORK`.
- Kartu `SELESAI` tetap `<div>` tanpa `href`; expand hanya menampilkan teks.
- Input NIK/DOB dan token cabang tidak diubah.
- Pesan humanis `stepNote(step)` tetap tersedia utuh saat dibuka.
- Target sentuh minimal 44 px; tidak ada horizontal scroll pada 390 px.

## Review Focus

- Expand pada kartu selesai tidak boleh membuka form → test `kartu selesai tetap DIV setelah expand`.
- Ringkasan satu baris tidak menghilangkan status/waktu → test `ringkasan memuat status dan waktu`.
- `aria-expanded` berubah saat toggle → test `tombol keterangan punya aria-expanded`.
- Urutan kartu tidak berubah → test `urutan tetap asli`.

---

### Task 1: Kartu ringkas dan expand

**Files:**
- Modify: `frontend/src/views/RecruitmentPortalView.vue`
- Test: `frontend/src/views/RecruitmentPortalView.test.js`

**Interfaces:**
- Consumes: `summary.stages`, `stepNote(step)`, `isDone(step)` yang sudah ada.
- Produces: `expanded` state, `summaryText(step)`, tombol `Lihat keterangan` / `Tutup keterangan`.

- [ ] **Step 1: Tulis tes UI**

Tambahkan ke `frontend/src/views/RecruitmentPortalView.test.js` dengan mock
`LOOKUP_DONE` yang sudah ada:

```js
it('kartu ringkas menampilkan status, waktu, dan tombol keterangan', async () => {
  const w = await mountPortal(`?token=${TOKEN}`, LOOKUP_DONE)
  await cek(w, '3509190102960003', '1996-02-01')
  const cv = card(w, 'CV')
  expect(cv.text()).toContain('✓ Selesai')
  expect(cv.text()).toContain('2026-11-25 19:28:30')
  expect(cv.text()).toContain('Lihat keterangan')
  expect(cv.find('[data-expand]').attributes('aria-expanded')).toBe('false')
})

it('keterangan dibuka dan kartu selesai tetap tidak bisa dibuka', async () => {
  const w = await mountPortal(`?token=${TOKEN}`, LOOKUP_DONE)
  await cek(w, '3509190102960003', '1996-02-01')
  const cv = card(w, 'CV')
  await cv.find('[data-expand]').trigger('click')
  await flushPromises()
  expect(cv.text()).toContain('Data diri dan pendidikan Anda tersimpan')
  expect(cv.find('[data-expand]').attributes('aria-expanded')).toBe('true')
  expect(cv.element.tagName).toBe('DIV')
  expect(cv.attributes('href')).toBeUndefined()
})

it('urutan kartu tetap CV, Training, TKD, FirstWork', async () => {
  const w = await mountPortal(`?token=${TOKEN}`, LOOKUP_DONE)
  await cek(w, '3509190102960003', '1996-02-01')
  expect(w.findAll('.rp-card').map((c) => c.attributes('data-step')))
    .toEqual(['CV', 'TRAINING', 'TKD', 'FIRSTWORK'])
})
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `cd frontend && npm test -- --run src/views/RecruitmentPortalView.test.js`
Expected: FAIL (tombol `data-expand` belum ada).

- [ ] **Step 3: Implementasikan UI**

Di `RecruitmentPortalView.vue`:

- Tambah `const expanded = ref({})` dan fungsi `toggleNote(type)` yang membalik
  `expanded.value[type]`.
- Tambah `summaryText(step)`: bila `isDone(step)` kembalikan
  `Data tersimpan pada <waktu>`; bila tidak, kembalikan kalimat pertama dari
  `stepNote(step)` (potong sebelum titik pertama + `.`).
- Template kartu: badge status, judul, `<p class="rp-summary">` berisi
  `summaryText(step)`, lalu tombol
  `<button v-if="stepNote(step)" type="button" data-expand :aria-expanded="...">`
  dengan teks `Lihat keterangan` / `Tutup keterangan`. Saat expanded tampilkan
  `<p class="rp-full-note">{{ stepNote(step) }}</p>`.
- Jangan mengubah `cardTag`, `cardAttrs`, `isLocked`, atau `onCardClick`.
- Header: logo 32 px sejajar dengan judul; subtitle satu baris.
- CSS: `@media (max-width: 639px)` satu kolom, kartu padding 12 px, ringkasan
  satu baris ellipsis, tombol keterangan min-height 44 px, padding bawah
  `env(safe-area-inset-bottom)`; `@media (min-width: 640px)` pakai gaya lama.

- [ ] **Step 4: Jalankan tes, build, dan cek visual**

Run: `cd frontend && npm test -- --run src/views/RecruitmentPortalView.test.js && npm run build`
Expected: PASS dan build sukses.

Run Playwright lokal 390×844 pada `/app/recruitment-portal`: tidak ada
horizontal scroll dan keempat kartu terlihat dalam ≤ 2 layar.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/RecruitmentPortalView.vue frontend/src/views/RecruitmentPortalView.test.js
git commit -m "feat(portal): kartu ringkas dan keterangan bisa dibuka di HP"
```

---

### Task 2: Rilis v2.135.4

**Files:** `CHANGELOG.md`, `docs/internal/PROGRESS.md`, 7 titik stamp.

- [ ] **Step 1: Bump v2.135.4** pada 7 titik dan tulis catatan changelog/progress.
- [ ] **Step 2: Verifikasi** `npm test`, `npm run build`, `python3 scripts/check_version_stamps.py`.
- [ ] **Step 3: Commit + push + deploy NAS**, `sync_version_stamp.py`, `check_version_stamps.py --with-db`.
- [ ] **Step 4: Smoke** viewport HP dan NIK `3509190102960003`: urutan tetap,
      kartu selesai redup/tanpa tautan, keterangan bisa dibuka.

## Catatan implementasi

- Card `data-step` dipertahankan untuk stabilitas tes dan analitik.
- Jangan memindahkan tombol expand ke dalam `<a>`; kartu selesai bukan tautan.
