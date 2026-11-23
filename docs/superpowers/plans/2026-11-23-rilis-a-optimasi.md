# Rilis A — Optimasi CI, E2E & Alur Harian Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tambah schema drift check di CI, E2E alur kritis, filter+bulk action GA Service, notifikasi Finance realtime, dan riwayat feedback driver.

**Architecture:** Modul backend baru untuk inspeksi skema, endpoint bulk review di `routes_driver_service.py`, event realtime `finance_board`, dan komponen frontend yang memakai pola `api()` + ref yang sudah ada. Schema check hanya terhadap DB master CI.

**Tech Stack:** Python 3.11 / Flask / mysql.connector / pytest, Vue 3 / Vitest / Playwright, GitHub Actions, MariaDB CI service.

**Spec:** `docs/superpowers/specs/2026-11-23-workhub-optimization-design.md`

## Global Constraints

- Versi rilis: **v2.131.3** (bump 7 titik stamp + DB saat rilis).
- Setiap task wajib: failing test → implement → passing test → commit.
- Jangan mengubah alur approve klaim: tetap `/api/queue/approve-ga/<id>`.
- `Tandai selesai` service = `driver_service_reports.status = 'REVIEWED'`.
- Bulk action maksimal 50 ID; `ga_note` wajib hanya untuk `REJECTED`.
- Audit via `log_activity_async` ke `activity_logs` yang sudah ada.
- Tidak menyentuh P1 (ODO, rekonsiliasi Subsidi Tepat).

## Review Focus

- Bulk review dengan ID milik laporan sudah diproses → harus 409, tidak mengubah data.
- Filter tanggal `from > to` → harus 400, bukan query error.
- Event Finance terkirim dua kali saat approve di-retry → harus hanya sekali.
- Riwayat feedback untuk nopol kosong → harus array kosong, bukan 500.
- Schema drift check saat DB tidak tersedia → harus exit 0 dengan pesan skip atau exit 1 jelas, bukan traceback.

---

### Task 1: Schema drift check di CI

**Files:**
- Create: `scripts/check_schema_drift.py`
- Create: `tests/test_schema_drift.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `init.sql` (sumber CREATE TABLE), env `DB_HOST/DB_USER/DB_PASSWORD/DB_NAME`.
- Produces: `main() -> int`; exit 0 bila cocok, 1 bila ada kolom/tabel hilang.

- [ ] **Step 1: Write failing tests**

```python
def test_parse_create_table_mendapat_kolom():
    from scripts.check_schema_drift import parse_init_sql
    ddl = "CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(10));"
    assert parse_init_sql(ddl)["t"] == ["id", "name"]

def test_db_tidak_tersedia_tidak_traceback(monkeypatch):
    from scripts import check_schema_drift
    monkeypatch.setattr(check_schema_drift, 'get_db_connection', lambda: None)
    assert check_schema_drift.main() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_schema_drift.py::test_parse_create_table_mendapat_kolom -q`
Expected: FAIL, modul belum ada.

- [ ] **Step 3: Implement parser & comparator**

Buat `parse_init_sql(text) -> dict[str, list[str]]` (regex `CREATE TABLE IF NOT EXISTS ...`), `compare_with_db(expected, cursor) -> list[str]` (query `information_schema.COLUMNS` untuk `TABLE_SCHEMA = DATABASE()`), dan `main()` yang memakai `get_db_connection()` bila tersedia; bila DB tidak ada, cetak `SKIP` dan return 0.

- [ ] **Step 4: Add CI step**

Tambah setelah `Run tests`:
```yaml
- name: Check schema drift
  run: python scripts/check_schema_drift.py
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_schema_drift.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/check_schema_drift.py tests/test_schema_drift.py .github/workflows/ci.yml
git commit -m "ci: tambah schema drift check terhadap DB master"
```

---

### Task 2: E2E Playwright alur kritis

**Files:**
- Create: `frontend/e2e/critical.spec.ts`
- Create: `scripts/ci_e2e.sh`
- Modify: `.github/workflows/ci.yml`
- Modify: `frontend/package.json` (script `e2e`)

**Interfaces:**
- Consumes: endpoint `/api/driver/service`, `/api/ga/service-reports`, `/api/ga/service-reports/<id>/pdf`.
- Produces: 3 spesifikasi E2E yang bisa dijalankan `npm run e2e`.

- [ ] **Step 1: Write E2E spec untuk submit service driver**

```ts
test('driver kirim KM manual + dua keluhan bernomor', async ({ page }) => {
  await page.goto('/login');
  await page.getByPlaceholder('Masukkan username').fill('driversby_guruh');
  await page.locator('input[type=password]').fill('123456');
  await page.getByRole('button', { name: /Masuk/ }).click();
  await page.goto('/app/driver');
  await page.getByRole('button', { name: /Service/ }).click();
  await page.locator('#svc-km').fill('78179');
  await page.getByPlaceholder(/Rem depan/).fill('Rem depan berbunyi');
  await page.getByRole('button', { name: /Tambah Keluhan/ }).click();
  await page.getByPlaceholder(/Tambah keluhan lain/).fill('AC kurang dingin');
  await page.getByRole('button', { name: /Kirim ke GA/ }).click();
  await expect(page.getByText(/Terkirim ke GA/)).toBeVisible();
});
```

- [ ] **Step 2: Run E2E to verify it fails**

Run: `npm run e2e -- --grep "driver kirim"`
Expected: FAIL (server test belum berjalan / selector belum ada).

- [ ] **Step 3: Buat `scripts/ci_e2e.sh`**

Start Flask dengan env CI, tunggu `/api/health` 200, jalankan `npx playwright test`, lalu kill server. Jangan pakai produksi.

- [ ] **Step 4: Add CI job `e2e`**

Job baru dengan service MariaDB+Redis, checkout, setup Python+Node, install deps, jalankan `bash scripts/ci_e2e.sh`.

- [ ] **Step 5: Run E2E to verify it passes**

Run: `bash scripts/ci_e2e.sh`
Expected: 3 skenario PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/critical.spec.ts scripts/ci_e2e.sh .github/workflows/ci.yml frontend/package.json
git commit -m "test: E2E alur kritis driver-GA-finance"
```

---

### Task 3: Filter & bulk action GA Service

**Files:**
- Modify: `modules/routes_driver_service.py`
- Create: `tests/test_driver_service_bulk.py`
- Modify: `frontend/src/views/dashboard/GaDashboard.vue`
- Modify: `frontend/src/views/dashboard/GaDashboard.test.js`

**Interfaces:**
- Consumes: `driver_service_reports`, `log_activity_async(report_id, 'driver_service_bulk', 'ga', actor, ...)`.
- Produces: `POST /api/ga/service-reports/bulk-review` body `{ids:int[], status:'REVIEWED'|'REJECTED', ga_note?:str}`.

- [ ] **Step 1: Write failing backend test**

```python
def test_bulk_review_menolak_status_invalid(client):
    login(client, 'ga')
    rv = client.post('/api/ga/service-reports/bulk-review',
                     json={'ids': [11], 'status': 'ARCHIVED'})
    assert rv.status_code == 400

def test_bulk_review_tidak_mengubah_baris_sudah_diproses(client):
    login(client, 'ga')
    rv = client.post('/api/ga/service-reports/bulk-review',
                     json={'ids': [99], 'status': 'REVIEWED'})
    assert rv.status_code == 409

def test_filter_tanggal_terbalik_ditolak(client):
    login(client, 'ga')
    rv = client.get('/api/ga/service-reports?from=2026-11-30&to=2026-11-01')
    assert rv.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_driver_service_bulk.py -q`
Expected: FAIL 404.

- [ ] **Step 3: Implement endpoint**

Validasi: `ids` 1..50, status hanya REVIEWED/REJECTED, `ga_note` wajib bila REJECTED. Update hanya baris `status='SUBMITTED'`; catat `log_activity_async` per ID; kembalikan `{status:'success', updated:n}`.

- [ ] **Step 4: Extend GET filter**

`/api/ga/service-reports?status=SUBMITTED&from=2026-11-01&to=2026-11-30&q=rem`
Tanggal `from > to` → 400. `q` mencari `display_id`, `nopol`, `keluhan`.

- [ ] **Step 5: Frontend filter & bulk UI**

Tambah 3 input filter + tombol Terapkan/Reset, checkbox per baris, tombol aksi bulk dengan konfirmasi. Reuse `ask()` dari ConfirmDialog yang sudah ada.

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_driver_service_bulk.py -q && cd frontend && npx vitest run src/views/dashboard/GaDashboard.test.js`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add modules/routes_driver_service.py tests/test_driver_service_bulk.py frontend/src/views/dashboard/GaDashboard.vue frontend/src/views/dashboard/GaDashboard.test.js
git commit -m "feat: filter dan bulk review catatan service GA"
```

---

### Task 4: Notifikasi Finance realtime

**Files:**
- Modify: `modules/realtime.py`
- Modify: `modules/routes_spa.py:437` (setelah approve GA sukses)
- Modify: `frontend/src/views/dashboard/FinanceDashboard.vue`
- Create: `tests/test_finance_notification.py`

**Interfaces:**
- Consumes: `emit_event(event, data, room)` dari `modules/realtime.py`.
- Produces: event `new_finance_task` di room `finance_board` dengan payload `{id, display_id, nominal}`.

- [ ] **Step 1: Write failing test**

```python
def test_approve_ga_emit_notifikasi_finance(monkeypatch):
    called = []
    monkeypatch.setattr('modules.realtime.emit_event',
                        lambda *a, **k: called.append((a, k)))
    # panggil helper emit yang dibuat di routes_spa
    notify_finance_task({'id': 5, 'display_id': 'BPF-1', 'nominal': 100000})
    assert called[0][0][0] == 'new_finance_task'
    assert called[0][1]['room'] == 'finance_board'

def test_notifikasi_satu_event_per_panggilan(monkeypatch):
    called = []
    monkeypatch.setattr('modules.realtime.emit_event',
                        lambda *a, **k: called.append(a))
    notify_finance_task({'id': 5})
    assert len(called) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_finance_notification.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement helper & hook**

`notify_finance_task(row)` di `routes_spa.py` memanggil `emit_event(..., room='finance_board')`. Panggil hanya setelah `UPDATE ... verified_ga` berhasil (rowcount > 0).

- [ ] **Step 4: Tambah room & watcher frontend**

`_ROOM_ROLES['finance_board'] = ('finance','admin')`; `FinanceDashboard.vue` menambah watcher `realtime.items[0]` untuk `new_finance_task` → `load()`.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_finance_notification.py -q && cd frontend && npx vitest run src/views/dashboard/FinanceDashboard.test.js`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/realtime.py modules/routes_spa.py frontend/src/views/dashboard/FinanceDashboard.vue tests/test_finance_notification.py
git commit -m "feat: notifikasi realtime klaim siap bayar untuk Finance"
```

---

### Task 5: Riwayat feedback km/L driver

**Files:**
- Modify: `modules/routes_api_transactions.py`
- Create: `tests/test_feedback_history.py`
- Modify: `frontend/src/views/driver/BBMTab.vue`

**Interfaces:**
- Consumes: `transactions` dengan `km_per_liter > 0`, status `verified_ga|archived`.
- Produces: `GET /api/driver/feedback-history?nopol=<string>` → `{data:[{date, km_per_liter, performa}]}` maksimal 5.

- [ ] **Step 1: Write failing test**

```python
def test_feedback_history_kosong_tanpa_nopol(client):
    login(client, 'driver')
    rv = client.get('/api/driver/feedback-history')
    assert rv.status_code == 200
    assert rv.get_json()['data'] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_feedback_history.py -q`
Expected: FAIL 404.

- [ ] **Step 3: Implement endpoint**

Nopol diambil dari query; bila kosong → `{'data':[]}`. Query 5 baris terakhir dengan `km_per_liter > 0`, urut `created_at DESC`.

- [ ] **Step 4: Frontend kartu ringkas**

Di `BBMTab.vue`, di bawah kartu feedback after-submit, tambah `<div v-if="feedbackHistory.length">` berisi 5 baris tanggal + km/L + label performa. Tombol tutup/buka.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_feedback_history.py -q && cd frontend && npx vitest run src/views/driver/DriverView.test.js`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/routes_api_transactions.py tests/test_feedback_history.py frontend/src/views/driver/BBMTab.vue
git commit -m "feat: riwayat feedback km/L di PWA driver"
```
