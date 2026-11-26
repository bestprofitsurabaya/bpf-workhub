# Portal Rekrutmen — Empat Tahap Seragam (v2.135.9) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Membuat empat tahap portal rekrutmen memakai satu anatomi baris yang seragam, dengan timeline bersambung dan status yang konsisten.

**Architecture:** `.rp-card` menjadi wadah visual; `.rp-card-main` adalah area klik (`a`/`button`/`div`); `.rp-details` selalu menjadi kaki kartu di dalam wadah. Status dihitung dari `summary.next_action` dan `stages`.

**Tech Stack:** Vue 3 `<script setup>`, CSS scoped, Vitest + @vue/test-utils.

**Spec:** `docs/superpowers/specs/2026-11-26-portal-rekrutmen-seragam-design.md`

## Global Constraints

- Hanya `frontend/src/views/RecruitmentPortalView.vue` dan tesnya yang berubah.
- Tidak ada perubahan backend, API, token, skema, atau aturan tahap.
- Nama tetap tersamar; NIK lengkap, cabang, dan token tidak dirender.
- Bahasa Indonesia; tanpa emoji.
- Versi rilis: `v2.135.9` di ketujuh titik stamp.

## Review Focus

- Tahap selesai tidak boleh bisa diklik dan tetap menampilkan keterangan.
- Tahap terkunci tidak boleh membuka tautan/panel dan tetap memberi alasan.
- TKD harus tetap membuka panel, bukan tautan.
- Baris berikutnya harus konsisten antara badge, highlight, dan teks sapaan.
- Layout 390 px tidak boleh bergulir horizontal.

---

### Task 1: Kunci anatomi seragam lewat tes

**Files:**
- Modify: `frontend/src/views/RecruitmentPortalView.test.js`

**Interfaces:**
- Consumes: kelas `.rp-card`, `.rp-card-main`, `.rp-details`; teks `Buka →`, `Berikutnya`, `Selesai`, `1 dari 4 tahap selesai`.
- Produces: ekspektasi tes yang menjadi acuan Task 2–3.

- [ ] **Step 1: Ubah helper dan tes lama**

Tambahkan helper:

```js
function main(w, step) {
  return card(w, step).find('.rp-card-main')
}
```

Ganti pembacaan `href`/`tagName` pada kartu menjadi `main(w, step)`.
Ganti `'✓ Selesai'` menjadi `'Selesai'` pada badge, dan pastikan simpul
`.rp-node` memuat `✓`.

- [ ] **Step 2: Tambah tes baru**

```js
it('badge memakai satu kata dan menandai langkah berikutnya', async () => {
  const w = await mountPortal(`?token=${TOKEN}`, LOOKUP_DONE)
  await cek(w, '3509190102960003')
  expect(card(w, 'CV').text()).toContain('Selesai')
  expect(card(w, 'CV').text()).not.toContain('✓ Selesai')
  expect(card(w, 'TRAINING').text()).toContain('Berikutnya')
  expect(w.find('.rp-steps-head').text()).toContain('1 dari 4 tahap selesai')
})

it('aksi dan kaki keterangan seragam untuk semua tahap', async () => {
  const w = await mountPortal(`?token=${TOKEN}`, LOOKUP_DONE)
  await cek(w, '3509190102960003')
  for (const step of ['TRAINING', 'TKD', 'FIRSTWORK']) {
    expect(card(w, step).text()).toContain('Buka →')
    expect(card(w, step).find('[data-expand]').exists()).toBe(true)
  }
})
```

- [ ] **Step 3: Jalankan tes, pastikan gagal**

Run: `cd frontend && npx vitest run src/views/RecruitmentPortalView.test.js`
Expected: FAIL pada `.rp-card-main`, `Berikutnya`, dan `1 dari 4`.

---

### Task 2: Implementasi template dan skrip

**Files:**
- Modify: `frontend/src/views/RecruitmentPortalView.vue`

**Interfaces:**
- Consumes: `STEPS`, `summary`, `isDone`, `isLocked`, `stageInfo`, `tkdCardOpen`, `cardTag`, `cardAttrs`.
- Produces:
  - `isNext(step: object): boolean`
  - `doneCount(): number`
  - `statusText(step: object): 'Selesai' | 'Berikutnya' | 'Belum' | 'Terkunci'`

- [ ] **Step 1: Tambah fungsi**

```js
function isNext(step) {
  return !isDone(step) && summary.value?.next_action === step.type
}
function doneCount() {
  return STEPS.filter((step) => isDone(step)).length
}
function statusText(step) {
  if (isDone(step)) return 'Selesai'
  if (isLocked(step)) return 'Terkunci'
  if (isNext(step)) return 'Berikutnya'
  return 'Belum'
}
```

- [ ] **Step 2: Ganti struktur baris**

`.rp-card` menjadi `<div>` wadah dengan `data-step`, `data-locked`,
`data-status`, dan kelas `rp-card--done/locked/next`. Di dalamnya:

```html
<component :is="cardTag(step)" class="rp-card-main" v-bind="cardAttrs(step)" @click="onCardClick(step)">
  <span class="rp-node" ...>...</span>
  <span class="rp-card-body">
    <span class="rp-card-head">
      <span class="rp-card-title">{{ step.label }}</span>
      <span class="rp-status" :class="...">{{ statusText(step) }}</span>
    </span>
    <span class="rp-card-desc">{{ step.desc }}</span>
    <span class="rp-card-line">
      <span class="rp-summary">{{ isLocked(step) ? 'Lengkapi CV Online terlebih dahulu.' : summaryText(step) }}</span>
      <span v-if="!isLocked(step) && !isDone(step)" class="rp-action">Buka <span aria-hidden="true">→</span></span>
    </span>
  </span>
</component>
<details v-if="stepNote(step)" class="rp-details" data-expand>
  <summary>Lihat keterangan</summary>
  <p class="rp-full-note">{{ stepNote(step) }}</p>
</details>
```

- [ ] **Step 3: Header dinamis**

```html
<span>{{ summary && known ? `${doneCount()} dari 4 tahap selesai` : '4 tahap' }}</span>
```

- [ ] **Step 4: Jalankan tes**

Run: `cd frontend && npx vitest run src/views/RecruitmentPortalView.test.js`
Expected: PASS.

---

### Task 3: Gaya timeline dan keseragaman

**Files:**
- Modify: `frontend/src/views/RecruitmentPortalView.vue` (blok `<style scoped>`)

**Interfaces:**
- Consumes: kelas dari Task 2.
- Produces: tampilan seragam di 390 px dan 1280 px.

- [ ] **Step 1: Terapkan gaya**

- `.rp-card { position: relative; padding: 0; }`; `.rp-card-main` memakai
  padding 16/18 px, `display:flex`, `gap:14px`, `text-decoration:none`.
- Garis timeline: `.rp-card:not(:last-child)::before` — `left:33px`,
  `top:48px`, `bottom:-11px`, lebar 1 px, warna `--rp-line`; varian
  `--done` memakai `#bfdccb`.
- `.rp-details` di dalam kartu: `padding:0 18px 10px 62px`, garis atas
  rambut; `summary` min-height 40 px.
- `.rp-status { min-width: 88px; text-align:center; }`;
  `.rp-status--next { background: var(--rp-accent-soft); color: var(--rp-accent); }`.
- `.rp-card-line { display:flex; align-items:center; justify-content:space-between; gap:12px; }`.
- `.rp-action { color: var(--rp-ink); font-weight:600; white-space:nowrap; }`;
  `.rp-card--next .rp-action { color: var(--rp-accent); }`.
- Hapus aturan `.rp-open` dan `.rp-details` versi luar kartu.
- Mobile: garis `left:28px; top:44px`, padding kartu 14 px, detail
  `padding-left:54px`.

- [ ] **Step 2: Jalankan tes + build**

Run: `cd frontend && npx vitest run && npm run build`
Expected: semua tes lulus, build sukses.

- [ ] **Step 3: Pratinjau**

Ambil tangkapan 390 px dan 1280 px; periksa tidak ada gulir horizontal,
badge sejajar, garis timeline menyambung, dan kaki keterangan seragam.

---

### Task 4: Rilis v2.135.9

**Files:**
- Modify: `CHANGELOG.md`, `modules/company_identity.py`,
  `frontend/src/stores/identity.js`, `frontend/public/sw.js`,
  `modules/pdf_generator.py`, `docs/internal/USER_LIST.md`,
  `guides/USER_GUIDE.md`, `docs/internal/PROGRESS.md`
- Guide: `/tmp/opencode/guide/guide.html` + PDF

- [ ] **Step 1: Bump ketujuh titik stamp ke v2.135.9**
- [ ] **Step 2: Catat changelog dan progres**
- [ ] **Step 3: Perbarui tangkapan panduan dan PDF**
- [ ] **Step 4: Commit, push, pull NAS, rebuild web**
- [ ] **Step 5: Verifikasi health, versi, service worker, dan halaman portal**
