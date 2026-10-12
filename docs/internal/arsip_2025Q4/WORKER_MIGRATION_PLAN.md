# Migrasi Worker Gunicorn: eventlet → gevent — ✅ SELESAI

**Status: SELESAI (Jalur A dieksekusi).** Disusun 8 Sep 2026 sebagai DRAFT
setelah insiden crash-loop gunicorn 26; dieksekusi **v2.38.0 (deploy live
9 Sep)**; arsitektur patch dipertegas **v2.39.2–v2.39.3 (10 Sep)** setelah
dua insiden lanjutan tertangkap CI/verifikasi. Dokumen ini kini menjadi
*referensi arsitektur* — bukan rencana.

---

## 1. Status final (v2.39.3)

| Komponen | Kondisi final | Catatan |
|---|---|---|
| Worker gunicorn | `gunicorn --worker-class gevent -w 1` (CMD Dockerfile) | sejak v2.38.0; `-w 1` tetap (room SocketIO in-memory) |
| Monkey-patching | **HANYA oleh worker gunicorn** — `--worker-class gevent` mem-patch sebelum app di-load | `app.py` TIDAK boleh mem-patch (insiden CI 34425989650) |
| `async_mode` SocketIO | Deteksi via **argv** di `app.py`: `'gevent'` bila `argv[0]` berakhir `gunicorn` DAN `--worker-class/-k gevent` ada di argv; selain itu `'threading'` | v2.39.3. Deteksi env (`GUNICORN_CMD_ARGS`/`SERVER_SOFTWARE`) v2.39.2 **salah** — tak pernah ada di `os.environ` proses produksi (diverifikasi PID 1 `bbm_web`) |
| gunicorn versi | **23.0.0** (`gunicorn[gevent]==23.0.0`) | gevent tersedia di 26.x via extra — naik kapan saja SETELAH stabil; guard CI menahan naik buta |
| gevent | `gevent>=24.10.1` di requirements.txt | tanpa ini worker gagal boot (insiden gunicorn 26, 8 Sep) |
| eventlet | **dihapus** | deprecated; worker-nya dihapus di gunicorn 26 |
| Guard regresi | `tests/test_worker_patch_guard.py` (4 test) + `tests/test_gunicorn_worker.py` (2 test) | lihat §3 |

## 2. Kronologi keputusan

| Tanggal | Peristiwa | Pelajaran |
|---|---|---|
| 8 Sep | gunicorn 26 menghapus worker eventlet → container crash-loop; rollback ke 23.0.0 + guard CI | dependensi worker implisit wajib di-guard |
| 8 Sep | DRAFT dokumen ini: jalur A gevent / B threading / C stay | — |
| 9 Sep | **v2.38.0 dieksekusi & deploy live**: worker gevent, patch di `app.py` (sesuai desain DRAFT), Flask-SocketIO tanpa `gevent-websocket` → websocket fallback long-polling | E2E submit OT Security lulus; full sync bersih |
| 10 Sep | **CI merah 34425989650** walau 587 test lulus: `monkey.patch_all()` di `app.py` jalan saat `import app` oleh pytest → lock importlib rusak (`cannot release un-acquired lock`). Host lokal hijau karena gevent tak ter-install (fallback threading menyembunyikan bug) → **v2.39.2**: patching keluar dari app.py; pemetaan patch milik worker | patch hanya boleh oleh pihak yang meng-import app PERTAMA, sebelum modul lain |
| 10 Sep | **v2.39.2 hampir salah deploy**: deteksi `async_mode` via env tak pernah benar (PID 1 tak punya kedua var) → produksi akan boot `threading` di worker gevent → **v2.39.3**: deteksi via argv + smoke CI `import app` dgn gevent | verifikasi asumsi di proses nyata SEBELUM deploy; statik guard bisa basi |

## 3. Invariant arsitektur (di-guard test — JANGAN dilanggar)

1. **`app.py` tidak boleh memanggil monkey-patching apa pun**
   (`tests/test_worker_patch_guard.py::test_app_module_tidak_memanggil_monkeypatch`).
   Patch = pekerjaan worker gunicorn via `--worker-class`.
2. **Worker gevent tidak boleh hilang saat merapikan kode**: CMD Dockerfile
   tetap `--worker-class gevent`; `gunicorn[gevent]` + `gevent` tetap di
   requirements.txt (`test_worker_gevent_tidak_ikut_dibuang`).
3. **`socketio_async_mode` tetap terdefinisi** dan dipakai
   `SocketIO(async_mode=…)` (`test_async_mode_tetap_terdefinisi`).
4. **Smoke asli di CI**: `import app` dengan gevent ter-install +
   `-X importtime` (kondisi persis insiden) harus exit 0, tanpa lock error,
   dan `ASYNC_MODE=threading` di luar gunicorn
   (`test_import_app_dengan_gevent_tanpa_merusak_importlib`). Skip di host
   tanpa gevent → **jalan otomatis di job Backend CI** (bukti: 591→592 passed).
5. **Versi gunicorn di-guard** (`tests/test_gunicorn_worker.py`): naik ke 26.x
   hanya lewat bump sadar (gevent extra tersedia di sana).

## 4. Checklist pengujian migrasi (hasil)

- [x] Health 200 + login + SPA dimuat (smoke pasca-deploy v2.38.0, 9 Sep).
- [x] Realtime & alur utama: E2E submit OT Security live + full sync kedua
      modul bersih (9 Sep); list/report + pagination (v2.39.1).
- [x] Emit dari background tidak error (cron cleanup OT + auto-refresh sheet
      aktif di container sejak deploy — log bersih).
- [x] Full pytest suite container hijau + guard worker.
- [ ] Upload foto besar & beban ringan 50 concurrent — **belum diuji formal**
      (operasional normal berjalan sehat sejak 9 Sep; lakukan bila akan menaikkan
      beban/gunicorn 26).
- [x] Rollback plan: image sebelumnya bisa di-deploy ulang
      (`docker compose -p bpf-bbm-system up -d --build web`).

## 5. Naik ke gunicorn 26.x (langkah sisa — opsional)

1. Pastikan beberapa hari operasional gevent stabil (sejak 9 Sep — terpenuhi).
2. `requirements.txt`: `gunicorn[gevent]==26.x` → CI (pytest + guard +
   Trivy) memutuskan; guard versi memang sengaja menahan — bump sadar.
3. Rebuild + smoke live (health, stamp, SW, log) + pantau log `pool exhausted`
   beberapa hari (monkey-patch mengubah perilaku pooling DB).
4. Bila perlu websocket penuh (bukan long-polling): pasang
   `gevent-websocket` pada build yang sama.

> Multi-worker (>1 proses) tetap berarti room SocketIO in-memory harus
> diganti Redis adapter (`bbm_redis` sudah ada di stack).

## 6. Jalur yang TIDAK dipilih (arsip)

- **Jalur B — threading** (`gthread` + `--threads`, tanpa patch): paling
  jujur arsitektur tapi butuh audit titik blocking + uji beban; tidak dipilih.
- **Jalur C — stay di eventlet/gunicorn 23**: eventlet deprecated tanpa
  patch keamanan baru; ditolak.
