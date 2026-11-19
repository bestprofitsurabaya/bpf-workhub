# 🔄 Sinkronisasi Driver & Multiplatform (Android + iPhone)

Dokumen internal — audit, desain, dan rencana bertahap untuk membuat input
driver (BBM, LPJ, trip, overtime, kasbon) **tidak pernah hilang** saat sinyal
buruk, di Android maupun iPhone.

Versi kode: **v2.127.0** (19 November 2026)

---

## 1. Ringkasan

| Aspek | Sebelum v2.127.0 | Sesudah v2.127.0 |
|---|---|---|
| Status per item | tidak ada | `pending` / `failed` / terkirim (dihapus) |
| Gagal jaringan | dicoba ulang tiap 30 detik | **backoff eksponensial + jitter** (30 dtk → 1 jam) |
| Ditolak server (4xx) | diulang selamanya tiap 30 dtk | ditandai **failed**, berhenti otomatis |
| Sesi habis (401/403) | item hilang dari pandangan, tanpa pesan | sync **berhenti**, banner "Sesi berakhir" + tombol Masuk |
| Visibilitas antrean | hanya angka badge | **panel antrean**: jenis, waktu, error, ukuran, tombol Coba lagi / Hapus |
| Foto kamera | resolusi asli 2–4 MB | **maks 1600 px, JPEG 0.8** (±250–500 KB) |
| Pemicu sync | online + interval 30 dtk | + saat app dibuka, `visibilitychange`, `pageshow` (iOS) |
| Penyimpanan | IndexedDB saja | + `navigator.storage.persist()` (best-effort) |

Server **sudah idempoten** untuk kelima endpoint submit (`client_uuid` →
tabel `submit_idempotency`), jadi pengiriman ulang aman dan tidak
menggandakan data. Perubahan v2.127.0 seluruhnya di sisi klien.

---

## 2. Audit antrean lama (temuan)

1. **`syncAll()` menelan semua error.** `catch { /* retry nanti */ }` tanpa
   mencatat status — item yang ditolak server (mis. nominal salah) dicoba
   ulang setiap 30 detik tanpa akhir, sementara pengguna tidak tahu apa pun.
2. **401 tidak terlihat.** `api.js` memicu `bpf:unauthorized`, tetapi alur
   driver tidak menampilkan bahwa antrean tertahan; pengguna mengira data
   sudah terkirim.
3. **Tidak ada backoff.** Semua item dikirim serentak setiap 30 detik; di
   sinyal buruk ini memperpanjang antrean dan menguras baterai.
4. **Foto mentah.** `watermark.js` memakai `canvas.width = img.width` lalu
   JPEG 0.85 — foto 12 MP menjadi 2–4 MB per item. Antrean 10 trip bisa
   melewati kuota IndexedDB per-origin di sebagian perangkat.
5. **Trigger kurang.** Hanya `online` + interval. Di iOS, saat app dibuka
   kembali dari background (bfcache), `online` tidak selalu terpicu.
6. **Metadata minim.** Item hanya `{ data, timestamp }` — tidak mungkin
   membedakan "menunggu" vs "ditolak" di UI.

Catatan: bug lama `{ok,data}` pada overtime sudah diperbaiki di v2.120.0;
v2.127.0 menyeragamkan bentuk hasil kelima jalur lewat `sendQueueItem()`.

---

## 3. Desain mesin sync v2

### 3.1 Bentuk item antrean (IndexedDB)

```js
{
  id,                       // autoIncrement
  data,                     // payload submit (FormData/JSON)
  timestamp, createdAt,     // ISO + epoch
  state: 'pending'|'failed',
  attempts,                 // jumlah percobaan
  nextAt,                   // epoch; 0 = boleh sekarang
  lastError,                // pesan server/jaringan terakhir
  size,                     // perkiraan byte (untuk indikator kuota)
  cashId?,                  // khusus lpj_queue
}
```

`addToQueue` tetap memakai `keyPath: 'id', autoIncrement` — metadata baru
tidak mengubah skema IndexedDB (tanpa migrasi DB_VER).

### 3.2 Klasifikasi error

| Kondisi | Klasifikasi | Tindakan |
|---|---|---|
| tanpa status / timeout / `Failed to fetch` | `retry` | tetap `pending`, `nextAt = now + backoff` |
| 408 / 425 / 429 | `retry` | idem |
| ≥ 500 | `retry` | idem |
| 401 / 403 | `auth` | hentikan seluruh sync, item tetap `pending`, panggil `notifyUnauthorized()` |
| 4xx lain (400/409/422) | `failed` | `state = failed`, `nextAt = 0`, tampil di panel + tombol Coba lagi |

Backoff: `min(1 jam, 30 dtk × 2^(attempts-1))` dikali jitter 80–120%.

### 3.3 Urutan pengiriman

`fuel_queue → lpj_queue → trip_queue → overtime_queue → cash_queue`

BBM didahulukan karena LPJ kasbon bergantung pada klaim BBM; trip sesudahnya
agar laporan harian tidak terhambat satu item yang bermasalah.

### 3.4 Pemicu

- saat `DriverView` mount (antrean dari sesi sebelumnya langsung dicoba),
- event `online`,
- `visibilitychange` → visible (Android/iOS),
- `pageshow` (kembali dari bfcache iOS),
- interval 30 detik **hanya saat halaman terlihat**,
- tombol manual: "Sinkron" di status bar & "Sinkron sekarang" di panel.

### 3.5 Perlindungan data lokal

`navigator.storage.persist()` diminta sekali saat driver membuka halaman.
Di iOS Safari dukungannya terbatas, tetapi IndexedDB tetap bertahan selama
pengguna tidak menghapus data situs. Untuk itu pesan di panduan menegaskan:
**jangan "Clear History & Website Data"** pada iPhone.

### 3.6 Batas ukuran foto

`applyWatermark()`: sisi terpanjang 1600 px, `canvas.toBlob('image/jpeg', 0.8)`.
Teks watermark (alamat, tanggal, koordinat) tetap tergambar setelah resize
karena font dihitung dari lebar kanvas hasil.

---

## 4. Matriks platform

| Kemampuan | Android Chrome (PWA) | Android TWA (Play) | iPhone Safari PWA | WebView shell (Cordova) |
|---|---|---|---|---|
| IndexedDB offline queue | ✅ | ✅ | ✅ | ✅ |
| `navigator.storage.persist()` | ✅ | ✅ | ⚠️ terbatas | ⚠️ |
| Background Sync | ✅ | ✅ | ❌ (tidak ada di iOS) | ❌ |
| Web Push | ✅ | ✅ | ✅ iOS ≥ 16.4, **wajib Add to Home Screen** | ❌ tanpa FCM |
| Sync saat app dibuka | ✅ | ✅ | ✅ | ✅ |
| Instalasi tanpa Play | ✅ (Add to Home Screen) | lewat Play | ✅ (Add to Home Screen) | sideload APK |

**Kesimpulan:** satu basis kode PWA melayani Android dan iPhone. Sync
dijamin saat aplikasi dibuka / kembali terlihat; push hanya "pengingat",
bukan pengangkut data.

### Langkah iPhone (untuk pengguna)

1. Buka `https://nasbpfsby.duckdns.org:5000` di **Safari** (bukan Chrome iOS).
2. Ketuk **Bagikan** → **Tambah ke Layar Utama**.
3. Buka dari ikon (bukan tab biasa) agar penyimpanan & push lebih stabil.
4. Jangan menghapus data situs; gunakan tombol **Keluar** untuk ganti akun.

---

## 5. Rencana bertahap

| Tahap | Isi | Status |
|---|---|---|
| 1 | **Sync v2** (dokumen ini): status item, backoff, 401, panel antrean, resize foto, trigger iOS | ✅ v2.127.0 |
| 2 | Panduan Add to Home Screen + Web Push (VAPID) untuk pengingat tugas | ⏳ berikutnya |
| 3 | Android TWA (Bubblewrap) + `/.well-known/assetlinks.json`, distribusi Play internal | opsional |
| 4 | Native iOS (Capacitor + APNs) hanya bila sync latar wajib | belum perlu |

---

## 6. Skenario uji perangkat

Persiapan: akun driver uji, izin menulis **1 trip** (bukan klaim BBM), lalu
hapus setelah tes.

1. Buka PWA, pastikan login dan profil tampil.
2. **Airplane mode** → isi 1 log trip → simpan. Panel antrean menunjukkan
   `Log trip · Menunggu`, status bar `Offline`.
3. **Kill app** (recents → swipe) → buka lagi → antrean masih ada.
4. Matikan airplane mode → dalam ≤ 30 dtk item terkirim, toast
   "✅ 1 data offline terkirim", panel kosong, `Terakhir:` terisi.
5. Ulangi dengan sesi kedaluwarsa (tunggu 12 jam atau hapus cookie):
   banner "Sesi berakhir" muncul, item **tidak** hilang, login ulang →
   item terkirim.
6. Uji tolak server: kirim payload tidak valid saat offline, lalu online →
   item bertanda **Gagal** dengan pesan server; "Coba lagi" hanya mengirim
   ulang item itu.
7. Ukuran foto: foto ODO 12 MP → cek panel; item harus < 1 MB.
8. iPhone (bila tersedia): ulangi langkah 2–4 lewat ikon Home Screen.

---

## 7. Berkas terkait

| Berkas | Peran |
|---|---|
| `frontend/src/stores/driverStore.js` | mesin sync: `syncAll`, `backoffDelay`, `classifySyncError`, `retryItem`, `dropItem` |
| `frontend/src/utils/idb.js` | `updateQueueItem`, `getAllQueueItems`, hitung antrean |
| `frontend/src/views/driver/DriverView.vue` | panel antrean, banner sesi, pemicu sync |
| `frontend/src/utils/watermark.js` | resize 1600 px + JPEG 0.8 |
| `frontend/src/api.js` | `notifyUnauthorized()` (probe `/api/auth/me` sebelum logout) |
| `modules/idempotency.py` | `submit_idempotency` — kunci anti-ganda server |
| `frontend/src/stores/driverStore.test.js` | 11 tes mesin sync (total 20 di berkas ini) |

---

## 8. Batasan yang diketahui

- iOS **tidak punya** Background Sync: data baru terkirim saat app dibuka.
  Web Push (Tahap 2) hanya memberi tahu, tidak mengirim payload antrean.
- `storage.persist()` di iOS dapat mengembalikan `false`; data tetap ada
  sampai pengguna menghapus data situs.
- Bila pengguna menekan **Hapus** di panel, data benar-benar hilang —
  konfirmasi ganda ditampilkan dan hanya untuk item yang sudah `failed`.
- APK Cordova lama (WebView) tidak mewarisi Background Sync/Web Push;
  karena itu arah distribusi utama adalah PWA/TWA.
