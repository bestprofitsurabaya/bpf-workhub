# 🔔 Web Push Driver (VAPID) — Desain & Operasional

Tanggal: 19 November 2026 · Versi: **v2.128.3**
Status: kode & tes unit selesai; **uji perangkat (Android + iPhone) menyusul**.

---

## 1. Mengapa

SocketIO hanya mengirim notifikasi saat halaman driver terbuka. Driver yang
menutup aplikasi (atau layar mati) tidak tahu ada penugasan kendaraan,
appointment baru, atau klaim yang disetujui. Web Push menjangkau perangkat
walau aplikasi **tertutup**:

| Platform | Dukungan |
|---|---|
| Android — Chrome | ✅ penuh |
| iPhone/iPad — Safari **≥ 16.4** | ✅ hanya bila PWA ditambahkan ke **Layar Utama** |
| iPhone < 16.4 atau tab Safari biasa | ❌ (notifikasi in-app tetap ada) |
| Desktop Chrome/Edge/Firefox | ✅ (tidak dipakai untuk driver, tetap berfungsi) |

Tanpa Background Sync, antrean offline tetap dikirim saat aplikasi dibuka —
Web Push hanya untuk memberi tahu, bukan mengunggah data.

---

## 2. Arsitektur

```
Driver menekan "Aktifkan" (panel 🔔)
  └─ GET /api/push/public-key        (kunci VAPID publik)
  └─ Notification.requestPermission()
  └─ PushManager.subscribe({applicationServerKey})
  └─ POST /api/push/subscribe        (endpoint + p256dh + auth disimpan)

Server membuat notifikasi (assignment/klaim/appointment)
  └─ push_driver_notification() → tabel notifications + SocketIO
  └─ ambil push_subscriptions driver (DB cabang)
  └─ thread: pywebpush → FCM/APNs (VAPID, timeout 8 dtk)
       └─ 404/410 → langganan dihapus otomatis

Service worker (/app/sw.js)
  └─ event 'push' → showNotification(title, body, data.url)
  └─ event 'notificationclick' → fokus tab /app atau buka /app/driver
```

Kegagalan push **tidak pernah** menggagalkan alur bisnis: semua dipanggil
best-effort di latar belakang dan hanya dicatat di log server.

---

## 3. Kunci VAPID

Urutan resolusi (`modules/webpush.py`):

1. environment `VAPID_PUBLIC_KEY` + `VAPID_PRIVATE_KEY` (disarankan untuk
   deployment multi-worker / banyak replika);
2. DB master `system_config` (`vapid_public_key`, `vapid_private_key`) —
   dibuat otomatis sekali bila belum ada;
3. proses ini saja (fallback; **hindari** di produksi multi-worker).

`VAPID_SUBJECT` default `mailto:admin@bpf.local`; ganti dengan email yang
benar bila push service meminta kontak.

> **v2.128.1** — build v2.128.0 sempat menukar urutan kunci saat menyimpan
> ke `system_config` (PEM privat masuk kolom publik). Urutan sudah diperbaiki
> dan `_load_db_keys()` kini menukar kembali otomatis bila mendeteksi baris
> lama yang tertukar. Kunci publik yang benar adalah titik EC P-256
> base64url ±87 karakter; kunci privat berupa blok PEM ±227 karakter.

Membuat kunci manual (opsional):

```bash
docker exec -w /app bpf-workhub-web python3 -c \
  "from modules.webpush import generate_vapid_keys as g; p,u=g(); print(p); print(u)"
```

Simpan hasilnya di `.env` NAS bila ingin kunci tetap lintas rebuild:

```
VAPID_PUBLIC_KEY=<baris kedua>
VAPID_PRIVATE_KEY=<baris pertama, PEM dengan \n>
VAPID_SUBJECT=mailto:it@bestprofit.co.id
```

> Kunci **publik** boleh diketahui klien. Kunci **privat** tidak boleh masuk
> repo/log; simpan di `.env` atau DB.

---

## 4. Endpoint

| Metode | Path | Akses | Fungsi |
|---|---|---|---|
| GET | `/api/push/public-key` | publik | `{enabled, public_key}` |
| POST | `/api/push/subscribe` | sesi driver | upsert langganan perangkat |
| POST | `/api/push/unsubscribe` | sesi driver | hapus langganan perangkat |
| GET | `/api/push/status` | sesi driver | jumlah perangkat terdaftar |

Tabel `push_subscriptions` dibuat lazily per DB cabang (dan master saat
startup): `endpoint` unik (prefix 255), `driver_name`, `p256dh`, `auth`,
`user_agent`, waktu dibuat/diperbarui.

**v2.128.2** — pengiriman berjalan di thread tanpa sesi, jadi DB asal
dicatat (`SELECT DATABASE()`) dan pembersihan langganan mati memakai
`get_db_connection_by_name()`; tanpa ini baris 404/410 di DB cabang tidak
pernah terhapus.

---

## 5. Alur pengguna

1. Login driver → ketuk 🔔 → panel notifikasi.
2. Tekan **Aktifkan** → izin browser → status "✅ Notifikasi HP aktif".
3. iPhone: tombol menampilkan petunjuk **Tambah ke Layar Utama** lebih dulu;
   setelah dibuka dari ikon, aktifkan lagi.
4. **Matikan** menghapus langganan di server + perangkat.

---

## 6. Uji yang sudah & belum dilakukan

Sudah:
- **Uji kirim nyata** (19 Nov 2026): langganan FCM dibuat dari Chromium
  headless (`POST /api/push/subscribe` → `devices: 1`), lalu push dikirim;
  FCM menerima **HTTP 201** dan alur notifikasi penuh
  (`push_driver_notification` → push latar) berjalan tanpa error. Langganan
  yang sudah mati dilaporkan `gone` dan terhapus.
- **Uji perangkat nyata** (20 Nov 2026, SM-A035F / Chrome 157): subscribe
  dari halaman driver menghasilkan endpoint FCM; `Notification.permission`
  = `granted`; notifikasi lokal via `showNotification` **tampil**.
- **Uji TTL terkontrol** (20 Nov 2026): push server dengan `ttl` default (0)
  → FCM 201 tetapi **tidak tampil**; dengan `ttl=86400` + `Urgency: high`
  → **tampil** di panel notifikasi. Implementasi Node (`web-push`, TTL
  86400) juga tampil, memastikan bukan bug pustaka Python.
- **10 tes unit backend**: validasi langganan, batas panjang payload,
  konsistensi pasangan kunci P-256, pembersihan di DB asal, objek Vapid,
  penerusan `ttl`/`Urgency`.
- 3 tes frontend: decode kunci VAPID base64url, deteksi iOS, fallback saat
  `PushManager` tidak ada.
- SQL/endpoint dicek statis; `node --check` service worker.

Belum:
- klik notifikasi membuka `/app/driver` di perangkat (handler sudah ada,
  belum diuji end-to-end di layar);
- Safari iOS ≥ 16.4 (PWA terpasang) — belum ada perangkat iOS;
- langganan mati (hapus app/uninstall) terhapus otomatis setelah 404/410 —
  terlihat pada 1 dari 2 endpoint uji (`410 Gone` → dihapus).

---

## 7. Berkas terkait

- `modules/webpush.py` — skema, kunci, kirim.
- `modules/routes_push.py` — API.
- `modules/notifications.py` — hook `push_driver_notification()`.
- `frontend/src/utils/push.js` — subscribe/unsubscribe.
- `frontend/src/components/DriverNotifBell.vue` — tombol Aktifkan/Matikan.
- `frontend/public/sw.js` — `push` & `notificationclick`.

---

## 8. Catatan kompatibilitas kunci

pywebpush **2.5.0** + py-vapid **1.9.6** tidak dapat memakai string PEM pada
`vapid_private_key` (`Vapid.from_string()` menganggapnya base64 DER). Selalu
oper **objek Vapid** (`Vapid.from_pem(pem.encode())`) — dilakukan otomatis
oleh `_vapid_object()` di `modules/webpush.py` (v2.128.3). Gejala bila salah:
semua push dicatat `error` dengan pesan "Could not deserialize key data".
- `tests/test_webpush.py`, `frontend/src/utils/push.test.js`.

---

## 9. Mengapa TTL wajib > 0 (v2.129.1)

`pywebpush` memakai `ttl=0` bila parameter tidak diisi. TTL 0 bukan "tanpa
kedaluwarsa", melainkan **"antar sekarang atau buang"**: FCM menerima pesan
(HTTP 201) lalu membuangnya bila perangkat belum terhubung pada saat itu.
HP driver hampir selalu dalam kondisi tersebut (layar mati, app di latar,
sinyal buruk).

Karena itu `_send_one()` mengirim:

```python
ttl=MESSAGE_TTL,                    # default 86400 detik (24 jam)
headers={'Urgency': URGENCY},       # default 'high'
```

Dapat diubah lewat env `WEBPUSH_TTL` dan `WEBPUSH_URGENCY`. TTL besar tidak
membuat notifikasi tertunda: bila perangkat online, pesan langsung diantar;
TTL hanya menentukan berapa lama FCM boleh menyimpannya.

**Jangan** menurunkan `WEBPUSH_TTL` ke 0 — gejalanya persis "FCM 201 tetapi
notifikasi tidak pernah muncul".
