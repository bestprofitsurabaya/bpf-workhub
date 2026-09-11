# 🔁 Redeploy Web App Apps Script — Overtime (v3)

> **Kapan panduan ini dipakai:** Web App Apps Script produksi masih menjalankan
> **script lama** (terverifikasi 10–11 Sep 2026 — feed masih ISO UTC; redeploy
> "New version" 2× di proyek lama tidak mengalir). Kontrak v2.39/v3 mengirim
> tanggal/jam **sesuai tampilan sheet** (zona spreadsheet), sehingga jam di
> aplikasi = jam di sheet **di zona apa pun**. Selama script lama masih jalan,
> data hanya benar bila sheet berzona **WIB** (zona kedua sheet terbukti WIB —
> aman sementara).

---

## 1. Cek Versi Script yang Aktif (30 detik)

**Cara paling cepat & pasti — marker versi (script v3+):**

```bash
curl -sL "<URL_/exec_driver>?marker=1"
```

| Respons `?marker=1` | Arti | Aksi |
|---|---|---|
| `"marker":"bpf-ot-driver-2026-09-11-v3"` / `"bpf-ot-ob-2026-09-11-v3"` | Script **v3** aktif | ✅ Selesai |
| JSON lain / error / tanpa `marker` | Script **LAMA** | Redeploy (§2) |

**Cara lama (masih berlaku utk feed mana pun)** — lihat format kolom `Timestamp`:

```bash
curl -sL "<URL_/exec_driver>" | head -c 400
```

| Output kolom Timestamp | Arti | Aksi |
|---|---|---|
| `"2020-12-12T07:08:54.000Z"` | Script **LAMA** (ISO UTC) | Redeploy (§2) |
| `"2020-12-12 14:08:54"` | Script **v2.39+** (wall-clock) | ✅ Tidak perlu apa-apa |

> Terminal "since" / filter tanggal feed lama memakai `T…Z` — parser server
> tetap menerima keduanya, jadi cek ini aman dilakukan kapan saja.

---

## 2. Langkah Redeploy (per Web App — Driver & OB/Security identik)

> 🆕 **11 Sep 2026 — metode BARU: proyek baru + URL baru.** Redeploy "New
> version" di proyek lama dua kali gagal mengalir (feed tetap ISO-UTC walau
> deployment ID & versi sudah benar). Keputusan pemilik: buat SEMUA baru.
> Setiap script kini punya **penanda versi** sehingga tidak ada lagi keraguan
> "lama atau baru" — cek 30 detik: `<URL_/exec>?marker=1`.

**Prasyarat:** akun Google yang punya akses ke sheet (view/read-only cukup).

1. Buka **https://script.google.com** → **New project** (standalone).
   Beri nama jelas, mis. `BPF OT Driver Bridge v3` / `BPF OT OB-Security Bridge v3`.
2. Hapus seluruh isi `Code.gs`, tempel kode terbaru dari repo:
   - Driver → `scripts/gas_bridge_overtime_driver_v3.gs`
   - OB/Security → `scripts/gas_bridge_overtime_ob_security_v3.gs`
   (⚠️ `SHEET_ID` sudah tertanam per script — jangan tertukar.)
   Panel file kiri harus berisi **satu file .gs saja** (dua `doGet` = yang lama
   diam-diam menang).
3. **File → Save** (Ctrl+S).
4. **Deploy → New deployment → Web app**:
   - *Execute as*: **Me** (akun yang punya akses sheet)
   - *Who has access*: **Anyone**
5. Salin URL `/exec` BARU → dashboard GA HR → ⚙️ Sumber Data (modul sesuai)
   → Simpan → 🔄 Refresh.
6. **Verifikasi marker**: buka `<URL_baru>/exec?marker=1` → respons harus
   `"marker":"bpf-ot-driver-2026-09-11-v3"` (Driver) atau
   `"marker":"bpf-ot-ob-2026-09-11-v3"` (OB/Security).
7. Hapus proyek/deployment Apps Script LAMA (Drive Google → hilangkan, atau
   Deploy → Manage deployments → Archive) supaya tidak tertukar lagi.

---

## 3. Verifikasi Pasca-Redeploy

1. **Feed**: ulangi §1 → `Timestamp` kini tanpa `T…Z` (format
   `yyyy-MM-dd HH:mm:ss`).
2. **Full sync**: login GA HR/Admin → menu Overtime → klik 🔄 **Refresh**
   (kedua tab). Ringkasan harus `full: N baru, M diperbarui …` tanpa error.
3. **Paritas** (opsional, di server):
   ```bash
   docker exec bbm_web python3 - <<'PY'
   from modules.config import get_db_connection
   from modules.routes_overtime import _get_sheet_url, _fetch_sheet_rows
   conn = get_db_connection(); cur = conn.cursor(dictionary=True)
   for modul, tabel in (('driver','overtime_driver'), ('ob','overtime_ob_security')):
       rows = _fetch_sheet_rows(_get_sheet_url(conn, modul=modul))
       ts = rows[0].get('Timestamp','')
       cur.execute(f"SELECT COUNT(*) c FROM {tabel} WHERE source='sheet'")
       print(modul, '| feed', len(rows), '| db', cur.fetchone()['c'],
             '| feed versi:', 'v2.39 WALL' if 'T' not in ts else 'LAMA ISO-UTC')
   conn.close()
   PY
   ```
   Angka feed ≈ db (feed bisa berbeda beberapa baris bila ada baris kosong/
   tanpa nama yang memang dilewati).

---

## 4. Re-seed — HANYA Bila Zona Spreadsheet Bukan WIB

Cek dulu zona sheet: **File → Settings → Time zone** (kedua spreadsheet).

> ✅ **Sudah diverifikasi 10 Sep 2026 (v2.39.3)** — TIDAK perlu buka UI
> Google: `scripts/forensic_overtime_tz.py` (jalankan via `docker cp` ke
> `bbm_web` → `python3 /tmp/forensic_overtime_tz.py`) membuktikan dari feed
> itu sendiri: kolom `Tanggal Overtime` Driver terserialisasi
> `…T17:00:00.000Z` = tengah malam **WIB** (GMT+8 akan terbaca `16:00Z`).
> Kedua feed masih script LAMA (ISO-UTC) — verdict & census tersimpan di
> `/tmp/bpf_ot_tz_forensic.json` (container). **Kesimpulan: redeploy §2
> saja, TANPA re-seed.**

| Zona spreadsheet | Perlu re-seed? | Alasan |
|---|---|---|
| **WIB (GMT+7)** | ❌ Tidak | Feed lama (+7) & baru (wall-clock) menghasilkan nilai sama |
| **Bukan WIB** (mis. GMT+8) | ✅ Ya | Baris lama tersimpan bergeser (jam sheet ≠ jam DB) |

**Prosedur re-seed (sheet non-WIB):**

```bash
# 1. Backup dulu (pola: backup_overtime_driver_sheet_20260906.json)
docker exec bbm_mariadb mariadb-dump -u root -p"$DB_PASS" bpf_asset_system \
  overtime_driver overtime_ob_security > /root/backup_ot_$(date +%Y%m%d).sql

# 2. Kosongkan + isi ulang dari feed v2.39 (wall-clock)
docker exec bbm_web python3 scripts/migrate_overtime_driver.py "<URL_/exec_driver>" --reset
docker exec bbm_web python3 scripts/migrate_overtime_ob_security.py "<URL_/exec_ob>" --reset

# 3. Verifikasi: angka baris = feed; jam 00:xx sheet tampil 00:xx di aplikasi
```

> `--reset` mengosongkan tabel sheet (data submit form aplikasi ber-kolom
> `source='form'` ikut hilang bila tabelnya sama — cek dulu kolom `source`
> sebelum memutuskan; bila ada data form, dump-nya ada di backup langkah 1).

**Rollback:** Deploy → Manage deployments → pilih versi lama dari riwayat
deployment. Data tetap aman di backup SQL.

---

## 5. Ringkasan Keputusan

```
Feed masih ISO-UTC?
├─ Sheet zona WIB      → redeploy §2 saja (hasil sudah benar, tinggal supaya konsisten)
└─ Sheet zona non-WIB  → redeploy §2 + re-seed §4 (baris lama bergeser)
Feed sudah wall-clock  → ✅ selesai
```

*Dibuat: 10 Sep 2026 (v2.39.1) — setelah verifikasi paritas menemukan Web App
produksi masih script lama. Lihat PROGRESS.md sesi 2026-09-10.*
