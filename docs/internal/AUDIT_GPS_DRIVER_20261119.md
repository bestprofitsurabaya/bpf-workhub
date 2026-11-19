# 🛰️ Audit GPS Driver — Temuan & Rekomendasi

Tanggal: 19 November 2026
Lingkup: `frontend/src/utils/gps.js`, `frontend/src/stores/driverStore.js`
(`locate()`), pemakaian di `DriverView.vue`, `TripTab.vue`, `BBMTab.vue`,
`OvertimeDriverTab.vue`.
Metode: telaah kode + uji perangkat SM-A035F (Chrome Android) saat uji Sync v2.
Status: **audit — belum ada perubahan kode GPS** (temuan P0 lain sudah
diperbaiki di v2.127.1).

---

## 1. Alur saat ini

```
DriverView.init()
  └─ store.locate()                        (sekali saat halaman dibuka)
       ├─ getPosition()                    navigator.geolocation (15 dtk, maxAge 5 mnt)
       ├─ locateWithAddress()
       │    ├─ addressFromCoords() → reverseGeocode()   → GET nominatim/reverse
       │    └─ nearbySpbu()                            → GET nominatim/search?q=SPBU
       └─ detailedLocation()               → GET nominatim/reverse  (LAGI, koordinat sama)
```

Foto (BBM/OT) memakai `store.gps.addr` yang tersimpan; payload submit
mengirim `gps_lat`, `gps_lon`, `gps_address`, `gps_kelurahan`…`gps_kode_pos`.

Catatan: satu `locate()` = **3 permintaan** ke Nominatim publik untuk
koordinat yang sama (2 reverse + 1 search), dijalankan serial lalu paralel.

---

## 2. Temuan

| # | Tingkat | Temuan | Dampak |
|---|---|---|---|
| G1 | **P1** | Tiga panggilan Nominatim per `locate()`, **tanpa cache** dan tanpa pembatasan laju | Kebijakan Nominatim maks. ±1 req/dtk; 429/penolakan, locate lambat (3–10 dtk), boros kuota. Setiap buka halaman/tab memicu lagi |
| G2 | **P1** | `fetch` Nominatim tanpa `AbortController`/timeout dan **tanpa cek `r.ok`** | Saat sinyal buruk, `locate()` bisa menggantung lama; respons 429/HTML diperlakukan seperti JSON → alamat kosong tanpa pesan |
| G3 | **P1** | `maximumAge: 300000` (5 menit) dan `coords.accuracy` **diabaikan** | Watermark/klaim bisa memakai posisi hingga 5 menit lalu atau akurasi ±2 km (lokasi jaringan), tanpa penanda apa pun |
| G4 | **P2** | `DriverView` menelan error: `store.locate().catch(() => {})` | Driver tidak tahu GPS mati/izin ditolak; alamat kosong dianggap "normal", foto tanpa lokasi tetap bisa dikirim |
| G5 | **P2** | Payload hanya `gps_lat/lon/address`; **tidak ada `gps_at` (waktu) dan `gps_accuracy`** | Server/GA tidak bisa menilai kesegaran & ketelitian lokasi bukti |
| G6 | **P2** | `nearbySpbu()` memakai `q=SPBU` + `bounded=1`, dijalankan serial sebelum `detailedLocation` | Hasil SPBU sering tidak relevan dan menambah 1–3 dtk ke setiap locate |
| G7 | **P3** | Tidak ada cache posisi terakhir / fallback saat GPS gagal; tidak ada panduan izin iOS | Di dalam gedung GPS gagal → semua kolom GPS kosong; pengguna iOS bingung saat diminta izin ulang |
| G8 | **P2** | (`submit-trip`) `pukul_berangkat[]`/`pukul_tujuan[]` kosong → `INSERT` NULL ke kolom NOT NULL → **HTTP 500 + pesan SQL mentah** | Driver yang tidak mengisi "Pukul" gagal kirim; pesan `1048 (23000): Column ... cannot be null` bocor ke UI |

Bukti G8 (uji perangkat 19 Nov 2026):

```
sync item #2: attempts=1, lastError="1048 (23000): Column 'pukul_berangkat' cannot be null"
→ klasifikasi 5xx = retry + backoff (perilaku sync benar), tetapi data valid
  dari sudut pandang UI tidak pernah bisa terkirim.
```

Setelah kolom Pukul diisi, pengiriman berhasil: item antrean terhapus,
`trip_masters` `TRIP-SBY-20261119-0001` terbentuk, lalu dihapus kembali
sebagai data uji.

---

## 3. Rekomendasi (urut prioritas)

1. **Satu permintaan reverse per lokasi** — `locate()` memakai hasil
   `detailedLocation()` untuk `addr`; `nearbySpbu` dijadikan lazy/opsional
   (hanya saat tab BBM dibuka).
2. **Cache geocode** per koordinat dibulatkan 4 desimal (±11 m) selama sesi,
   plus `localStorage` 24 jam untuk alamat terakhir.
3. **Timeout & cek status**: `AbortController` 8 dtk, `if (!r.ok) throw`,
   `try/catch` per panggilan; jangan pernah menggantung UI.
4. **GPS untuk bukti**: `maximumAge: 0` (atau ≤30 dtk) saat ambil foto,
   sertakan `coords.accuracy`; tolak/peringatkan bila `accuracy > 100 m`
   (mis. "GPS belum akurat — tunggu sebentar / keluar ruangan").
5. **Kirim `gps_at` + `gps_accuracy`** di payload BBM/trip/OT; simpan di DB
   (kolom nullable) agar GA dapat menilai bukti. Perlu migrasi kecil.
6. **Tampilkan kegagalan**: ganti `.catch(() => {})` dengan toast
   ("📍 GPS tidak aktif — aktifkan izin lokasi") + tombol coba lagi.
7. **Validasi server `submit-trip`**: bila `pukul_berangkat[]` kosong,
   isi dengan `jam_keberangkatan` (default) atau tolak 400 dengan pesan
   manusiawi; jangan bocorkan error SQL (petakan `IntegrityError` → 400).
8. **iOS**: tambahkan petunjuk izin lokasi (Safari → Pengaturan Situs →
   Lokasi) di panduan driver; uji di iPhone ≥ 16.4.

---

## 4. Catatan uji sync terkait GPS

- Perangkat: SM-A035F, Chrome 157, PWA `/app/driver`, akun `ahmad`.
- Offline (emulasi jaringan): trip masuk antrean, panel menampilkan
  `Log trip · MENUNGGU · 295 B`; status `🟡 Offline · 📦 1 antrean`.
- Online kembali: sync berjalan otomatis; kegagalan 5xx (G8) dijadwalkan
  ulang dengan backoff, bukan dibuang.
- Setelah data Pukul dilengkapi, `syncAll()` mengirim 1 trip, antrean
  kembali 0, status `idle`, `lastSync` terisi.
- Data uji dihapus: `trip_masters`, `trip_details`, dan
  `submit_idempotency` untuk `TRIP-SBY-20261119-0001` = 0 baris tersisa.
