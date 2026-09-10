# 🔁 Redeploy Web App Apps Script — Overtime (v2.39)

> **Kapan panduan ini dipakai:** setelah update server ke v2.39+, Web App
> Apps Script produksi masih menjalankan **script lama** (terverifikasi
> 10 Sep 2026 — feed masih ISO UTC). Kontrak v2.39 mengirim tanggal/jam
> **sesuai tampilan sheet** (zona spreadsheet), sehingga jam di aplikasi =
> jam di sheet **di zona apa pun**. Selama script lama masih jalan, data
> hanya benar bila sheet berzona **WIB**.

---

## 1. Cek Versi Script yang Aktif (30 detik)

Ambil 1 baris dari feed — lihat format kolom `Timestamp`:

```bash
curl -sL "<URL_/exec_driver>" | head -c 400
```

| Output kolom Timestamp | Arti | Aksi |
|---|---|---|
| `"2020-12-12T07:08:54.000Z"` | Script **LAMA** (ISO UTC) | Redeploy (§2) |
| `"2020-12-12 14:08:54"` | Script **v2.39** (wall-clock) | ✅ Tidak perlu apa-apa |

> Terminal "since" / filter tanggal feed lama memakai `T…Z` — parser server
> tetap menerima keduanya, jadi cek ini aman dilakukan kapan saja.

---

## 2. Langkah Redeploy (per Web App — Driver & OB/Security identik)

**Prasyarat:** akun Google yang punya akses ke sheet (view/read-only cukup)
dan tahu URL `/exec` yang terpasang di sistem (lihat `system_config`
`overtime_driver_sheet_url` / `overtime_ob_sheet_url`, atau dashboard GA HR →
⚙️ Sumber Data).

1. Buka **https://script.google.com** → proyek Apps Script yang ada
   (bukan buat baru — URL `/exec` harus tetap sama agar tidak perlu ubah
   konfigurasi sistem).
2. Hapus seluruh isi `Code.gs`, tempel kode terbaru dari repo:
   - Driver → `scripts/apps_script_overtime_driver_v2.gs`
   - OB/Security → `scripts/apps_script_overtime_ob_security.gs`
   (⚠️ perhatikan variabel `SHEET_ID` di baris atas — milik script masing-masing,
   jangan tertukar.)
3. **File → Save** (Ctrl+S).
4. Klik **Deploy → Manage deployments** → ikon ✏️ (Edit) pada deployment
   **"Web app"** yang aktif → **Version: New version** → **Deploy**.
   - *Execute as*: **Me** (akun pemilik script)
   - *Who has access*: **Anyone** — jangan diubah
5. Selesai. URL `/exec` **tidak berubah** — tidak ada konfigurasi sistem
   yang perlu disentuh.

> Jangan pakai "Deploy → New deployment" (membuat URL `/exec` baru).
> Kalau tidak sengaja terlanjur: salin URL baru itu ke dashboard GA HR →
> ⚙️ Sumber Data → simpan, lalu hapus deployment lama.

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
