# Rilis B — QR Dokumen Service & Code-splitting Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tambah QR verifikasi pada PDF resmi service dan Kurangi chunk Analytics supaya halaman driver tidak ikut memuat library chart.

**Architecture:** QR dibuat di Python dengan `qrcode[pil]` lalu disisipkan `BPFBasePDF`. Analytics memuat library chart lewat `import()` dinamis di `onMounted`, tanpa dependency baru.

**Tech Stack:** Python 3.11 / fpdf2 / qrcode[pil], Vue 3 / Vite / Vitest.

**Spec:** `docs/superpowers/specs/2026-11-23-workhub-optimization-design.md`

## Global Constraints

- Versi rilis **v2.131.4** (bump 7 titik stamp + DB).
- QR payload persis: `BPF-SERVICE:<display_id>:<sha256(display_id + tanggal ISO)>`.
- Tidak membuat halaman verifikasi publik.
- Tidak menambah dependency chart baru.
- Setiap task: failing test → implement → passing test → commit.

## Review Focus

- QR payload berubah bila tanggal diformat ulang → deterministik, hash memakai `YYYY-MM-DD`.
- QR gagal dirender bila `display_id` mengandung karakter non-ASCII → sanitasi.
- Import dinamis Analytics gagal di lingkungan offline → fallback pesan, bukan halaman kosong.
- Chunk driver tetap kecil → verifikasi via `npm run build`.

---

### Task 1: QR verifikasi PDF service

**Files:**
- Modify: `requirements.txt`
- Modify: `modules/driver_service_pdf.py`
- Create: `tests/test_driver_service_pdf_qr.py`

**Interfaces:**
- Consumes: `row['display_id']`, `row['created_at']` dari `driver_service_reports`.
- Produces: QR PNG tersisip di halaman pertama PDF; payload deterministik.

- [ ] **Step 1: Write failing test**

```python
def test_qr_payload_deterministik():
    from modules.driver_service_pdf import qr_payload
    assert qr_payload('SRV-001', '2026-11-23') == (
        'BPF-SERVICE:SRV-001:' + hashlib.sha256(b'SRV-0012026-11-23').hexdigest())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_driver_service_pdf_qr.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `qr_payload(display_id, created_at) -> str`**

Tanggal diformat `YYYY-MM-DD` (datetime atau string ISO). Hash SHA-256 penuh dari `display_id + tanggal`. Tambah `qrcode[pil]==8.2` ke requirements.

- [ ] **Step 4: Sisipkan QR ke PDF**

Buat image PNG in-memory di `generate()`, render di pojok kanan atas halaman pertama dengan ukuran 18 mm, di bawah header. Pastikan `render_qr()` mengembalikan `BytesIO` agar bisa dipakai `self.image()`.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_driver_service_pdf_qr.py -q`
Expected: PASS. Cek manual: render PDF via `pdftoppm`, QR terlihat.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt modules/driver_service_pdf.py tests/test_driver_service_pdf_qr.py
git commit -m "feat: QR verifikasi pada PDF service"
```

---

### Task 2: Code-splitting Analytics

**Files:**
- Modify: `frontend/src/views/AnalyticsView.vue`
- Modify: `frontend/src/views/AnalyticsView.test.js`

**Interfaces:**
- Consumes: komponen chart yang dipakai `AnalyticsView.vue` saat ini.
- Produces: `loadChartLib()` yang dipanggil `onMounted` memakai `import()` dinamis.

- [ ] **Step 1: Write failing test**

```js
it('tidak me-render chart sebelum library dimuat', async () => {
  const w = mount(AnalyticsView, { global: { plugins: [createPinia()] } })
  expect(w.find('[data-testid="chart-loading"]').exists()).toBe(true)
  w.unmount()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/views/AnalyticsView.test.js`
Expected: FAIL.

- [ ] **Step 3: Implement dynamic import**

Pindahkan `import ChartLib from '...'` ke `async function loadChartLib(){ const m = await import('...'); chartLib.value = m.default }`; panggil di `onMounted`. Tampilkan placeholder `data-testid="chart-loading"` sebelum siap.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/views/AnalyticsView.test.js`
Expected: PASS.

- [ ] **Step 5: Verify bundle**

Run: `cd frontend && npm run build`
Expected: chunk `AnalyticsView` lebih kecil dari 200 kB; chunk `index`/driver tidak bertambah.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/AnalyticsView.vue frontend/src/views/AnalyticsView.test.js
git commit -m "perf: lazy load library chart Analytics"
```
