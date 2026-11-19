# BPF Agenda — aplikasi Android (Cordova)

APK agenda BPF. Aplikasi membaca agenda dari **bridge read-only WorkHub**
(`https://nasbpfsby.duckdns.org:8444`) — sumber datanya modul Agenda di
WorkHub, bukan server terpisah.

## Struktur

```
apk/
├── mobile/           # proyek Cordova (config.xml, www/, hooks/, res/)
├── bpfBridge-src/    # plugin native: notifikasi, widget, unduh/bagikan media
├── scripts/
│   ├── build-android.sh   # build APK debug / release
│   ├── android-env.sh     # toolchain JDK + Android SDK + Gradle
│   └── gen-date-icons.js  # ikon tanggal 1–31 untuk launcher dinamis
└── dist/             # hasil build (tidak di-commit)
```

## Prasyarat (sekali)

1. Node/npm + Cordova CLI 13 (`npm i -g cordova`)
2. JDK 17, Android SDK (platform 34/36, build-tools 34/36), Gradle 8.14.2 —
   sesuaikan path di `scripts/android-env.sh` bila berbeda
3. Khusus release: keystore + `~/.config/bpf-workhub/keystore.properties`:

```properties
KEYSTORE=/home/<user>/.config/bpf-workhub/bpf-workhub-release.jks
ALIAS=bpf-calendar
STORE_PASSWORD=...
KEY_PASSWORD=...
```

> Keystore rilis **wajib di-backup**. Tanpa file yang sama, APK tidak bisa
> di-update di perangkat yang sudah terpasang (signature berbeda).

## Build

```bash
cd apk
./scripts/build-android.sh            # debug  → dist/bpf-agenda-<versi>.apk
./scripts/build-android.sh --release  # release → dist/bpf-agenda-<versi>-release.apk
```

Naikkan versi di `mobile/config.xml` (`<widget version="…">`) sebelum build
rilis. Cordova menurunkan `versionName`/`versionCode` dari situ; hook ikon
tanggal juga menyinkronkan baseline manifest agar versi tidak tertahan versi lama.

## Uji cepat

```bash
curl -s https://nasbpfsby.duckdns.org:8444/api/state | head -c 200
curl -s https://nasbpfsby.duckdns.org:8444/api/month | head -c 200
```

Endpoint bridge yang dipakai aplikasi: `/api/state`, `/api/month`,
`/api/stream`, `/api/app/latest`, `/api/app/download/<file>.apk`,
`/assets/up/*`, `/assets/logo.png`.

## Publikasi update (v2.125.0)

Aplikasi memeriksa `/api/app/latest` saat dibuka, mengunduh APK baru,
memverifikasi SHA-256, lalu membuka installer sistem. Tidak perlu Play Store
dan tidak perlu share Nextcloud.

```bash
# folder rilis host (di-mount ke container sebagai /app/data/apk)
./scripts/publish-release.sh dist/bpf-agenda-1.8.0-release.apk "Catatan rilis"

# rilis wajib (tombol "Nanti" disembunyikan di aplikasi)
BPF_UPDATE_MANDATORY=1 ./scripts/publish-release.sh dist/... "Perbaikan penting"

# folder lain (mis. saat uji lokal)
BPF_APK_DIR=/tmp/apk ./scripts/publish-release.sh dist/...
```

`publish-release.sh` membaca versi dari `mobile/config.xml`, menyalin APK ke
folder rilis, dan menulis `latest.json` (versi, versionCode, nama file,
SHA-256, catatan, wajib/tidak). Server menambahkan `apk_url` dan menghitung
ulang hash saat menyajikan manifest.

> Update tidak bisa senyap: Android 8+ tetap menampilkan konfirmasi
> pemasangan dan izin "Pasang aplikasi tak dikenal" per aplikasi. Update
> senyap hanya mungkin lewat MDM/Device Owner.
