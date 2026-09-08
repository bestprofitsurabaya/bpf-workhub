# Rencana Migrasi Worker Gunicorn: eventlet → gevent

**Status:** DRAFT — belum dieksekusi. Disusun 8 Sep 2026 setelah insiden
crash-loop gunicorn 26 (lihat CHANGELOG 8 Sep). Tujuan: aplikasi bisa naik
ke gunicorn ≥ 26 tanpa menghapus worker bawaan.

---

## 1. Latar belakang

| | Kondisi sekarang (v2.37.7) |
|---|---|
| Worker | `gunicorn --worker-class eventlet -w 1` (Dockerfile CMD) |
| Async SocketIO | `async_mode='eventlet'` + `eventlet.monkey_patch()` di `app.py` |
| Alasan `-w 1` | room SocketIO in-memory per-proses (notif realtime driver) |
| gunicorn | 23.0.0 (di-rollback dari 26.2.0 — worker eventlet dihapus di 26.x) |

eventlet **resmi deprecated** (maintainance mode — rekomendasi upstream:
migrasi ke asyncio/gevent). gunicorn 26 menghapus worker eventlet dari
inti; gevent tetap tersedia sebagai extra `gunicorn[gevent]`.

## 2. Pilihan jalur

### Jalur A — gevent (direkomendasikan, perubahan minimal)
1. `requirements.txt`: hapus `eventlet>=0.35.0`, tambah
   `gunicorn[gevent]>=24.10.1` (atau `gevent>=24.10.1` terpisah).
2. `app.py` (baris 8–16): ganti monkey_patch ke
   ```python
   try:
       from gevent import monkey
       monkey.patch_all()
       socketio_async_mode = 'gevent'
   except Exception:
       socketio_async_mode = 'threading'
   ```
   (hapus `import eventlet` & monkey_patch-nya).
3. Dockerfile CMD: `--worker-class gevent` (tetap `-w 1`).
4. `requirements.txt` gunicorn: boleh tetap 23.x dulu, lalu naik ke 26.x
   **setelah** jalur ini stabil (gevent tersedia di kedua versi — 26 via
   extra).

### Jalur B — threading (tanpa monkey-patch, paling jujur secara arsitektur)
- `async_mode='threading'` + worker `gthread` + `--threads 8`.
- **Risiko:** room realtime in-memory aman (tetap 1 proses), tapi semua
  blocking I/O (MySQL pool, requests scraper) menempati thread; perlu
  audit titik blocking panjang. Uji beban wajib.
- Keuntungan: tidak butuh monkey-patch sama sekali — paling tahan masa
  depan (socketio 5.x mendukung penuh).

### Jalur C — tinggal di gunicorn 23
- Tidak ada kerja sekarang; utang teknis tetap ada (eventlet deprecated).
- Guard `tests/test_gunicorn_worker.py` sudah mencegah naik buta.

## 3. Yang harus diuji saat migrasi (checklist)

- [ ] Health 200 + login + SPA dimuat.
- [ ] **Realtime notif driver**: buka PWA driver, submit klaim BBM dari
      akun lain → notif muncul < 2 s (event `new_claim`,
      `driver_notification`).
- [ ] Emit dari background (cron/scraping) tidak error.
- [ ] Upload foto bukti (multipart besar) tidak timeout.
- [ ] Long-polling websocket upgrade via nginx (proxy headers) masih OK.
- [ ] Full pytest suite container + smoke `test_gunicorn_worker.py`
      (worker-class di Dockerfile kini `gevent`).
- [ ] Beban ringan: 50 concurrent GET halaman berat (rekap) — latensi
      stabil (monkey_patch mengubah perilaku pooling DB — pantau
      "pool exhausted").
- [ ] Rollback plan: image sebelumnya tetap bisa di-deploy
      (`docker compose -p bpf-bbm-system up -d --build web` dengan tag
      sebelumnya).

## 4. Estimasi

| Jalur | Effort | Risiko | Kapan |
|---|---|---|---|
| A gevent | ~1–2 jam + uji | Rendah–sedang (monkey_patch) | Kapan saja, jalur pertama |
| B threading | ~3–4 jam + uji beban | Sedang | Bila A bermasalah |
| C stay | 0 | Utang teknis | Default sekarang |

## 5. Catatan penting

- Jangan naik gunicorn 26 **sebelum** jalur A/B selesai — guard CI akan
  menolak (insiden 8 Sep).
- eventlet 0.41.2 masih jalan di Python 3.11 image sekarang; risiko
  utamanya bukan "rusak hari ini" tapi "tidak dapat patch keamanan baru".
- Kalau suatu hari pindah ke **multiple worker** (>1 proses), room
  in-memory SocketIO harus diganti message queue (Redis adapter) —
  redis sudah ada di stack (`bbm_redis`).
